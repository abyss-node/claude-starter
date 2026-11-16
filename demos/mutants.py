#!/usr/bin/env python3
"""Prove a demo's held-out checks bind: the reference passes them, the skeleton fails them, every mutant (a bug
planted in a copy of the reference) fails them, and every legal variant (a change the brief allows) passes.

    python demos/mutants.py <name>... [--only <text>...] [--jobs N] [--verbose]
    python demos/mutants.py --all          # every demo, as CI's demo-mutants job runs them
    python demos/mutants.py --list         # the demo names, as JSON, for CI's matrix

A demo's mutant list is what "done" means for its checks: a gap outside it is written down in the brief's
`## Not graded`, not chased. Each case is graded exactly as a workspace is (check.run_accept: a copy outside the
workspace and the kit, the same runner, environment and permission model), so the proof holds for the grade
itself, not for a runner started some other way. Only the held-out checks are run, not the demo rules.

Files (demos/AUTHORING.md has the whole contract):
  accept/mutants/NNN-slug.json   {id, graded_item, description, file, find, replace, also?, expect?}: must FAIL
  accept/mutants/legal/*.json    {id, description, file, find, replace, also?}: must PASS
`file` is relative to reference/, and `find` must occur in it exactly once (in a file with CRLF line endings, a
`find` written with \\n is matched with \\r\\n). `also` holds more edits: {file?, find, replace}, {file, create,
encoding?} or {file, delete: true}. `expect` names checks (a part of the name each) that must be among the
failures, so a mutant dies for the reason it was written for. A mutated .py, .js or .mjs file must still parse.
When the brief has a `## Graded` list, each mutant's graded_item is one of its numbers and every number has a
mutant; otherwise graded_item is null. A demo with a fixture (demo.json) is built from the mutated copy by the
copy's own builder; the skeleton case is always the folder start.py makes (start.make_workspace).

A demo whose mutants_runner is its own script (demo.json) runs that instead of the list, after the reference and
skeleton cases here; it must grade through `check.py <name> --accept-only --dir <folder>` (DEMO_CHECK) and end
with the line MUTANTS OK.

Prints `reference: PASS k/n`, `skeleton: FAIL k/n`, a `survivor:` line per mutant that passed, `KILLED k/n`,
`LEGAL PASS k/m` and `MUTANTS OK` or `MUTANTS NOT OK`. Exit 0 when all of it holds, 1 when any does not, 2 when
it cannot run (a bad file, a `find` not found exactly once, an edit that does not parse, a fixture that failed).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402
import demolib as dl  # noqa: E402
import start  # noqa: E402

MUTANT_KEYS = {"id", "graded_item", "description", "file", "find", "replace"}
LEGAL_KEYS = {"id", "description", "file", "find", "replace"}
OPTIONAL_KEYS = {"also", "expect", "graded_item"}


class CaseError(Exception):
    """A case cannot be run: the list's fault, not the checks'."""


@dataclass
class Case:
    id: str
    description: str
    edits: list
    graded_item: Optional[int] = None
    expect: list = field(default_factory=list)
    legal: bool = False
    where: str = ""


def load_cases(demo: dl.Demo) -> tuple[list[Case], list[Case]]:
    """(mutants, legal variants), checked for shape and for ids used once."""
    root = demo.dir / "accept" / "mutants"
    out: tuple[list[Case], list[Case]] = ([], [])
    for legal, files in ((False, sorted(root.glob("*.json"))), (True, sorted((root / "legal").glob("*.json")))):
        need = LEGAL_KEYS if legal else MUTANT_KEYS
        for f in files:
            where = f"demos/{demo.name}/{f.relative_to(demo.dir).as_posix()}"
            try:
                data = json.loads(dl.read_text(f))
            except ValueError as e:
                raise CaseError(f"{where}: {e}") from None
            if not isinstance(data, dict) or not need <= set(data) <= need | OPTIONAL_KEYS:
                raise CaseError(f"{where}: keys are {', '.join(sorted(need))} (optional: also, expect"
                                + (", graded_item)" if legal else ")"))
            if not all(isinstance(data[k], str) and data[k] for k in ("id", "description", "file", "find")) \
                    or not isinstance(data["replace"], str):
                raise CaseError(f"{where}: id, description, file and find are non-empty strings, replace a string")
            g = data.get("graded_item")
            if g is not None and (not isinstance(g, int) or isinstance(g, bool)):
                raise CaseError(f"{where}: graded_item is a Graded item's number or null")
            expect = data.get("expect", [])
            if not isinstance(expect, list) or not all(isinstance(x, str) and x for x in expect):
                raise CaseError(f"{where}: expect is a list of check names (a part of each)")
            first = {"file": data["file"], "find": data["find"], "replace": data["replace"]}
            also = data.get("also", [])
            if not isinstance(also, list) or not all(isinstance(e, dict) for e in also):
                raise CaseError(f"{where}: also is a list of edits")
            edits = [first] + [dict({"file": data["file"]}, **e) for e in also]
            out[legal].append(Case(data["id"], data["description"], edits, g, expect, legal, where))
    ids = [c.id for c in out[0] + out[1]]
    twice = sorted({i for i in ids if ids.count(i) > 1})
    if twice:
        raise CaseError(f"demos/{demo.name}/accept/mutants: ids used more than once: {', '.join(twice)}")
    return out


def _target(root: Path, rel: str, where: str) -> Path:
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        raise CaseError(f"{where}: {rel!r} is not a path inside reference/")
    return root / p


def apply_edits(root: Path, case: Case) -> list[Path]:
    """Apply the case's edits to the copy of reference/ at `root`; return the files changed or made."""
    touched = []
    for e in case.edits:
        p = _target(root, e["file"], case.where)
        if e.get("delete") is True:
            if set(e) != {"file", "delete"} or not p.is_file():
                raise CaseError(f"{case.where}: delete names a file of reference/ ({e['file']}), and nothing else")
            p.unlink()
            continue
        if "create" in e:
            if set(e) - {"file", "create", "encoding"} or p.exists() or not isinstance(e["create"], str):
                raise CaseError(f"{case.where}: create makes a new file ({e['file']}) from text, with an encoding")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(e["create"].encode(e.get("encoding", "utf-8")))
            touched.append(p)
            continue
        if set(e) != {"file", "find", "replace"} or not isinstance(e["find"], str) or not e["find"] \
                or not isinstance(e["replace"], str):
            raise CaseError(f"{case.where}: an edit is {{file?, find, replace}}, {{file, create}} or {{file, delete}}")
        if not p.is_file():
            raise CaseError(f"{case.where}: reference/{e['file']} does not exist")
        text = p.read_bytes().decode("utf-8")
        find, replace = e["find"], e["replace"]
        if "\r\n" in text and "\r\n" not in find:
            find, replace = find.replace("\n", "\r\n"), replace.replace("\n", "\r\n")
        if text.count(find) != 1:
            raise CaseError(f"{case.where}: its find occurs {text.count(find)} times in reference/{e['file']}, "
                            "not once")
        p.write_bytes(text.replace(find, replace).encode("utf-8"))
        touched.append(p)
    return touched


def parse_problem(paths: list[Path]) -> Optional[str]:
    """Why one of the edited files no longer parses, or None: a mutant that does not parse proves nothing."""
    node = dl.exe("node")
    for p in paths:
        if p.suffix == ".py":
            try:
                compile(p.read_bytes(), str(p), "exec", dont_inherit=True)
            except (SyntaxError, ValueError) as e:
                return f"{p.name} does not parse: {e}"
        elif p.suffix in (".js", ".mjs") and node:
            r = subprocess.run([node, "--check", str(p)], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", stdin=subprocess.DEVNULL, timeout=120, cwd=str(p.parent))
            if r.returncode:
                return f"{p.name} does not parse: {check.first_line(r.stderr)}"
    return None


def program(path: Path) -> list[str]:
    """argv that runs a kit script by its kind: Python with check.PY_RUNNER_FLAGS, or Node."""
    if path.suffix == ".py":
        return [dl.python_exe() or "", *check.PY_RUNNER_FLAGS, str(path)]
    return [dl.exe("node") or "", str(path)]


def build_fixture(demo: dl.Demo, ref: Path, dest: Path, work: Path) -> None:
    """Make the finished workspace from the (mutated) reference copy `ref` in the empty folder `dest`: the copy
    itself, or what the copy's own builder (demo.json's fixture) makes there, history and all."""
    if demo.fixture is None:
        shutil.copytree(str(ref), str(dest))
        return
    builder = ref / Path(demo.fixture).relative_to("reference")
    dest.mkdir()
    env = dl.scrubbed_env(dl.git_isolation(work, work))
    env.update(DEMO_PYTHON=dl.python_exe() or "", DEMO_NODE=dl.exe("node") or "", DEMO_GIT=dl.exe("git") or "")
    cmd = program(builder) + ["--skeleton", str(demo.dir / "skeleton"), "--out", str(dest)]
    try:
        r = subprocess.run(cmd, cwd=str(work), env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=demo.timeout_s)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CaseError(f"the fixture builder {demo.fixture} did not run: {e}") from None
    if r.returncode:
        raise CaseError(f"the fixture builder {demo.fixture} exited {r.returncode}: "
                        f"{check.first_line(r.stderr) or check.first_line(r.stdout)}")


def skeleton_fixture(demo: dl.Demo, dest: Path) -> None:
    """The folder demos/start.py makes, for Claude Code (a lane's rules files then carry another name, which a
    grade must not depend on), without the commit guard's hooks."""
    dest.mkdir()
    failed = start.make_workspace(demo, "claude", dest, dl.KIT, dl.python_exe() or sys.executable)
    if failed:
        raise CaseError(f"the skeleton workspace could not be made: {failed}")


def grade(demo: dl.Demo, ws: Path, failfast: bool = False) -> list:
    return check.run_accept(demo, ws, failfast=failfast)


def verdict(results: list) -> str:
    k = sum(c.ok for c in results)
    return f"{'PASS' if k == len(results) else 'FAIL'} {k}/{len(results)}"


def run_case(demo: dl.Demo, case: Case) -> tuple[Case, Optional[list], Optional[str]]:
    """(case, the held-out results or None, why it could not run or None)."""
    with tempfile.TemporaryDirectory(prefix="demo-mutant-") as td:
        t = Path(td)
        ref = t / "ref"
        shutil.copytree(str(demo.dir / "reference"), str(ref))
        try:
            why = parse_problem(apply_edits(ref, case))
            if why:
                raise CaseError(f"{case.where}: {why}")
            build_fixture(demo, ref, t / "ws", t)
        except CaseError as e:
            return case, None, str(e)
        return case, grade(demo, t / "ws", failfast=not case.legal and not case.expect), None


def case_ok(case: Case, results: list) -> tuple[bool, str]:
    """Whether the case went as it must, and what to say about it."""
    failed = [c.name for c in results if not c.ok]
    if case.legal:
        return not failed, f"failed {failed[0]}" if failed else ""
    if not failed:
        return False, "passed every check"
    missing = [x for x in case.expect if not any(x in name for name in failed)]
    if missing:
        return False, f"failed, but not {', '.join(missing)} (it failed {', '.join(failed[:3])})"
    return True, failed[0]


def coverage_problems(demo: dl.Demo, mutants: list[Case]) -> tuple[list[str], list[int]]:
    """(cases whose graded_item is wrong, Graded items no mutant reaches)."""
    graded = dl.graded_items(demo)
    if not graded:
        return [f"{c.where}: graded_item is null for a brief with no `## Graded` list"
                for c in mutants if c.graded_item is not None], []
    bad = [f"{c.where}: graded_item {c.graded_item!r} is not a number of the brief's `## Graded` list"
           for c in mutants if c.graded_item not in graded]
    return bad, [n for n in graded if not any(c.graded_item == n for c in mutants)]


def run_own_runner(demo: dl.Demo) -> bool:
    """Run the demo's own mutants runner, echoing it; True when it exits 0 and ends with MUTANTS OK."""
    path = dl.KIT / demo.mutants_runner
    with tempfile.TemporaryDirectory(prefix="demo-mutants-") as td:
        env = dl.scrubbed_env(dl.git_isolation(Path(td), Path(td)))
        env.update(DEMO_CHECK=str(dl.DEMOS / "check.py"), DEMO_NAME=demo.name, DEMO_DIR=str(demo.dir),
                   DEMO_PYTHON=dl.python_exe() or "", DEMO_NODE=dl.exe("node") or "", DEMO_GIT=dl.exe("git") or "")
        try:
            r = subprocess.run(program(path), cwd=td, env=env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", stdin=subprocess.DEVNULL)
        except OSError as e:
            print(f"{demo.mutants_runner} did not run: {e}")
            return False
    print(r.stdout.rstrip("\n"))
    if r.stderr.strip():
        print(r.stderr.rstrip("\n"), file=sys.stderr)
    last = next((ln.strip() for ln in reversed(r.stdout.splitlines()) if ln.strip()), "")
    return r.returncode == 0 and last == "MUTANTS OK"


def run_demo(demo: dl.Demo, only: list[str], jobs: int, verbose: bool) -> int:
    try:
        mutants, legal = load_cases(demo)
        if only:
            mutants = [c for c in mutants if any(o in c.id or o in c.where for o in only)]
            legal = [c for c in legal if any(o in c.id or o in c.where for o in only)]
        bad, uncovered = coverage_problems(demo, mutants)
        if bad:
            raise CaseError(bad[0])
        if demo.mutants_runner == dl.KIT_MUTANTS and not mutants and not only:
            raise CaseError(f"demos/{demo.name}/accept/mutants/ holds no mutant")
    except CaseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{demo.name}: {len(mutants)} mutants, {len(legal)} legal variants, {jobs} at a time")
    ok, errors = True, []
    with tempfile.TemporaryDirectory(prefix="demo-base-") as td:
        t = Path(td)
        try:
            shutil.copytree(str(demo.dir / "reference"), str(t / "ref"))
            build_fixture(demo, t / "ref", t / "ref-ws", t)
            skeleton_fixture(demo, t / "skel-ws")
        except CaseError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        ref, skel = grade(demo, t / "ref-ws"), grade(demo, t / "skel-ws")
    print(f"reference: {verdict(ref)}")
    for c in ref:
        if not c.ok:
            print(f"  reference failed: {c.name}: {c.detail}")
    print(f"skeleton: {verdict(skel)}")
    ok = all(c.ok for c in ref) and not all(c.ok for c in skel)
    if demo.mutants_runner != dl.KIT_MUTANTS:
        own = run_own_runner(demo)
        print("MUTANTS OK" if ok and own else "MUTANTS NOT OK")
        return 0 if ok and own else 1
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        done = list(pool.map(lambda c: run_case(demo, c), mutants + legal))
    killed = legal_ok = 0
    for case, results, error in done:
        if error:
            errors.append(error)
            print(f"ERROR {case.id}: {error}")
            continue
        good, said = case_ok(case, results)
        if case.legal:
            legal_ok += good
            if not good or verbose:
                print(f"{'legal ok' if good else 'legal FAILED'}: {case.id}: {case.description}"
                      + (f" ({said})" if said else ""))
        else:
            killed += good
            if not good:
                print(f"survivor: {case.id} (graded {case.graded_item}): {case.description}: {said}")
            elif verbose:
                print(f"killed {case.id}: {said}")
    print(f"KILLED {killed}/{len(mutants)}")
    print(f"LEGAL PASS {legal_ok}/{len(legal)}")
    if uncovered and not only:
        print(f"uncovered: the brief's Graded items {', '.join(map(str, uncovered))} have no mutant")
    ok = ok and killed == len(mutants) and legal_ok == len(legal) and not (uncovered and not only)
    print("MUTANTS OK" if ok and not errors else "MUTANTS NOT OK")
    return 2 if errors else 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="mutants.py", description="Prove a demo's held-out checks bind.")
    ap.add_argument("names", nargs="*", help="the demos (default with --all: every one)")
    ap.add_argument("--all", action="store_true", help="every demo")
    ap.add_argument("--list", action="store_true", help="print the demo names as JSON and stop")
    ap.add_argument("--only", nargs="+", default=[], help="only cases whose id or file name holds one of these "
                    "(skips the Graded coverage check)")
    ap.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="cases graded at once")
    ap.add_argument("--verbose", action="store_true", help="a line for every case")
    args = ap.parse_args(argv)
    if args.list:
        print(json.dumps(dl.demo_names()))
        return 0
    names = dl.demo_names() if args.all else args.names
    if not names:
        ap.error("name a demo, or pass --all")
    for n in names:
        if n not in dl.demo_names():
            print(dl.unknown_demo(n), file=sys.stderr)
            return 2
    problem = dl.python_problem()
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    # Every git call here and in what it starts (start.py's commit, a fixture builder) reads no system or user
    # config, so the cases are built the same on every machine.
    empty = Path(tempfile.mkdtemp(prefix="demo-gitconfig-"))
    os.environ.update(dl.git_isolation(empty, empty))
    worst = 0
    try:
        for n in names:
            demo = dl.load_demo(n)
            lines = dl.node_problem(demo, demo.app)
            if lines:
                print("\n".join(lines), file=sys.stderr)
                return 2
            worst = max(worst, run_demo(demo, args.only, max(1, args.jobs), args.verbose))
    finally:
        shutil.rmtree(str(empty), ignore_errors=True)
    return worst


if __name__ == "__main__":
    sys.exit(main())
