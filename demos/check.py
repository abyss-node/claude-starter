#!/usr/bin/env python3
"""Grade a demo workspace with the kit's held-out checks.

    python demos/check.py <name> [--dir <workspace>]   # default: the current folder

In a workspace that demos/start.py made, `npm test` runs this through the kit's launcher
(`starter.py demo check <name>`), and the person at the keyboard runs the launcher directly, since the agent
can change what `npm test` runs. A python demo has no package.json: its rules file names the launcher. It grades
a copy of the workspace's plain files in a new temporary folder (demolib.copy_workspace; a copy_git demo's copy
keeps a cleaned .git), with demos/<name>/accept/ run from the kit, never from the workspace: `node --test` with
the kit's reporter, or the demo's own accept_runner (run_accept). The workspace's code runs in processes of its
own, never in the one that asserts: in Node under Node's permission model (demos/probe.mjs), which lets them
read that copy and, of the kit, only the probe files and a scenario's own modules; in Python, which has no such
model, from a copy in a temporary folder (demos/acceptkit.py), where code that goes looking can still find the
kit (demos/MEASURING.md). Node, Python and git are started by full path and from outside the
workspace, so a program named like them in the workspace is never run. The agent can read the checks in the
kit, which only its transcript shows; an edit to them is caught (below). Then five demo rules: one test entry
point, no binary assets, original names (demos/denylist.txt), no copying from demos/<name>/reference/ and no
code naming the kit's files. Every check prints one line; then `PASS k/n` or `FAIL k/n`, a NOT CHECKED line
naming what no test can judge, a line saying what a local grade is worth, and a RECORD line shaped as a
`Verified:` trailer, which the checkpoint copies into the commit. --accept-only runs the held-out checks alone
on a folder, for a demo's own mutants runner; it prints no RECORD and grades nothing.

A grade made here is feedback, not proof. The workspace's code, and the agent, run as the person at the
keyboard, so anything with a shell on this machine can tamper with the clone or the grading processes. A
measured run is admitted to costs.json only after CI re-grades the committed workspace with a clean copy of
the kit at the run's kit_sha (demolib.regrade, which runs this script with --regrade).

The RECORD carries kit_sha and accept_hash: the git tree hash of every file that grades the demo
(demolib.grading_paths). A measured run is admitted to costs.json only when that hash is the tree at kit_sha
and kit_sha is on origin/main, so a check edited in a clone cannot count. Locally this refuses to grade while
those files differ from the clone's last commit; --allow-modified-accept grades anyway and --allow-assets
lets binary assets through, and either marks the RECORD recordable=no. The hash is made in a temporary object
store, so grading writes nothing to the clone and works where only the demo's folder can be written.

Exit: 0 PASS, 1 FAIL, 2 nothing graded (unknown demo, not a demo workspace, grading files modified or not
hashable, the install record names another clone, no Node for a demo that needs it, or no Python 3.9+).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
import os
import re
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import demolib as dl  # noqa: E402
from demolib import Demo  # noqa: E402

REPORTER = dl.DEMOS / "reporter.mjs"
ERROR_LINE = re.compile(r"\s*\w*Error\b")  # the line of a dead check file's stderr that says what killed it
# How a Python accept runner starts: isolated (-I: no PYTHON* variables, no user site-packages, not its own folder
# on sys.path), without site-packages (-S: it is the kit's code, standard library only), writing no bytecode into
# the kit (-B), and printing UTF-8 whatever the console's code page (-X utf8; -I ignores PYTHONIOENCODING).
PY_RUNNER_FLAGS = ("-I", "-S", "-B", "-X", "utf8")

# One test entry point. The verifier ranks CI config first, then package.json scripts and a Makefile or
# justfile (plugins/starter/agents/verifier.md), so a workspace that adds any of these could hand it a test
# command of its own choosing.
CI_PATHS = (".github/workflows", ".gitlab-ci.yml", ".circleci", "azure-pipelines.yml", "Jenkinsfile", ".travis.yml",
            "bitbucket-pipelines.yml", ".woodpecker.yml", ".woodpecker", ".buildkite", ".drone.yml", "appveyor.yml",
            ".appveyor.yml")
RUNNER_FILES = {"makefile", "gnumakefile", "justfile", ".justfile", "taskfile.yml", "taskfile.yaml", "tox.ini",
                "noxfile.py"}

ASSET_KINDS = {
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".avif", ".tif", ".tiff", ".svg"},
    "audio": {".mp3", ".wav", ".ogg", ".oga", ".flac", ".m4a", ".aac", ".opus", ".mid", ".midi", ".weba"},
    "font": {".woff", ".woff2", ".ttf", ".otf", ".eot"},
}
DATA_URL = re.compile(r"data:(image|audio|font)/", re.I)
# Base64 over 1 KB, on one line or wrapped across lines in pieces (76 characters is MIME's wrap, 64 PEM's), as
# string literals joined in code: a block is consecutive lines that each hold a piece, and its size is theirs
# added up. A piece is a run of BASE64_PIECE or more. Shorter runs pass, so base64 cut into pieces under 32
# characters passes, as bytes written out as a number array do: the rule catches a pasted blob, not an embed
# made to get past it (demos/MEASURING.md lists that among what a grade does not rule out).
BASE64_PIECE = re.compile(r"[A-Za-z0-9+/]{32,}={0,2}")
BASE64_MAX = 1024

# Copying from reference/: more than MAX_SHARED distinct lines of at least MIN_LINE characters, once spaces are
# collapsed, that the reference holds and the skeleton and the brief do not. A paraphrase passes; that is the
# cost of a line count.
MIN_LINE = 20
MAX_SHARED = 10

LOCAL_GRADE = ("LOCAL GRADE: feedback for you and the agent, not proof. Anything with a shell on this machine, the "
               "agent included, can tamper with the kit or with this grade. A measured run counts in the kit's "
               "costs.json only after CI re-grades the committed workspace with a clean copy of the kit "
               "(demos/MEASURING.md).")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def first_line(s: str | None) -> str:
    return next((ln.strip() for ln in (s or "").split("\n") if ln.strip()), "")


# --------------------------------------------------------------------------
# Held-out checks
# --------------------------------------------------------------------------

def accept_command(demo: Demo) -> tuple[list[str], str]:
    """(argv, what to call it in a message) of the demo's held-out checks. Without an accept_runner: `node --test`
    with the kit's reporter on accept/*.test.mjs. With one: the demo's runner, a .py file run on the validated
    Python with PY_RUNNER_FLAGS, or a .mjs file run on Node. Each program by its full path; "" when not found."""
    runner = demo.accept_runner
    if runner is None:
        files = sorted((demo.dir / "accept").glob("*.test.mjs"))
        if not files:
            raise dl.DemoError(f"demos/{demo.name}/accept/ holds no *.test.mjs file")
        per_test = max(60, demo.timeout_s // 10) * 1000
        return ([dl.exe("node") or "", "--test", f"--test-reporter={REPORTER.as_uri()}", f"--test-timeout={per_test}",
                 *map(str, files)], "node --test")
    path = str(demo.dir / runner)
    if runner.endswith(".py"):
        return [dl.python_exe() or "", *PY_RUNNER_FLAGS, path], runner
    return [dl.exe("node") or "", path], runner


def run_accept(demo: Demo, ws: Path, copied: bool = False, failfast: bool = False) -> list[Check]:
    """Run the kit's accept/ on a copy of `ws` (or on `ws` itself when it is that copy) and return one Check per
    held-out test, in the order run (see held_out_checks). The runner starts from the copy's parent folder, never
    from the workspace, with DEMO_WORKSPACE naming the copy, DEMO_PYTHON, DEMO_NODE and DEMO_GIT the programs it
    may start (by full path; "" when there is none),
    a fresh DEMO_RESULT_TOKEN that only its own result lines carry, and git kept to the copy. With `failfast` (the
    mutants engine, which needs only a FAIL) DEMO_FAILFAST lets a runner stop at its first failed check."""
    if not copied:
        with tempfile.TemporaryDirectory(prefix="demo-grade-") as td:
            dl.copy_workspace(ws, Path(td) / "ws", git=demo.copy_git)
            return run_accept(demo, Path(td) / "ws", copied=True, failfast=failfast)
    cmd, called = accept_command(demo)
    token = secrets.token_hex(16)
    with tempfile.TemporaryDirectory(prefix="demo-run-") as run_dir:
        env = dl.scrubbed_env(dl.git_isolation(Path(run_dir), ws.parent))
        env.update(DEMO_WORKSPACE=str(ws), DEMO_PYTHON=dl.python_exe() or "", DEMO_NODE=dl.exe("node") or "",
                   DEMO_GIT=dl.exe("git") or "", DEMO_RESULT_TOKEN=token, DEMO_TIMEOUT_S=str(demo.timeout_s))
        if failfast:
            env["DEMO_FAILFAST"] = "1"
        try:
            if not cmd[0]:
                on_python = (demo.accept_runner or "").endswith(".py")
                raise OSError((dl.python_problem() or "no Python") if on_python else "no `node` on PATH")
            r = subprocess.run(cmd, cwd=str(ws.parent), env=env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=demo.timeout_s, stdin=subprocess.DEVNULL)
            out, err = r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else e.stdout or ""
            err = f"the held-out checks took longer than {demo.timeout_s} seconds and were stopped"
            code = None
        except OSError as e:
            out, err, code = "", f"could not run {called}: {e}", None
        else:
            code = r.returncode
    return held_out_checks(demo, out, err, code, token=token, runner=called)


def held_out_checks(demo: Demo, out: str, err: str, code: int | None, token: str | None = None,
                    runner: str = "node --test") -> list[Check]:
    """One Check per held-out test from the result lines. A test that never reported (its file failed to load,
    the runner crashed or timed out) counts as a failed one. The results must also agree with themselves and
    with the runner: each check reported once, no more than demo.json's accept_count, and a runner that exited
    0 when every check passed. A line without the run's `token` is not a result: no process of the workspace's
    is given the token, so a line it prints, through a runner that let its output through or from outside, is
    counted as one that is not the reporter's, which fails the grade."""
    checks, load_errors, stderr, garbled = [], [], {}, 0
    for ln in out.splitlines():
        if not ln.startswith('{"demo_event"'):
            continue
        try:
            ev = json.loads(ln)
        except ValueError:
            ev = None
        if (not isinstance(ev, dict) or not isinstance(ev.get("name", ""), str)
                or (token is not None and ev.get("token") != token)):
            garbled += 1  # the reporter, and acceptkit.result_line, write neither
            continue
        if ev["demo_event"] == "stderr":
            stderr.setdefault(ev.get("file"), []).append(str(ev.get("message") or ""))
            continue
        if ev.get("nesting") != 0 or ev.get("kind") != "test":
            continue
        if ev.get("file") and ev.get("name") == ev.get("file"):  # the file itself failed, outside any test
            said = "".join(stderr.get(ev["file"], [])).splitlines()
            why = next((s.strip() for s in said if ERROR_LINE.match(s)), "") or next(iter(said), "")
            load_errors.append(f"{Path(ev['file']).name}: {why or first_line(ev.get('error'))}")
            continue
        checks.append(Check(ev["name"], bool(ev["ok"]), "" if ev["ok"] else first_line(ev.get("error"))))
    why = "; ".join(load_errors) or first_line(err) or "no result reported"
    reported = len(checks)
    twice = sorted(name for name, k in Counter(c.name for c in checks).items() if k > 1)
    checks += [Check(f"held-out check {i} did not run", False, why)
               for i in range(len(checks) + 1, demo.accept_count + 1)]
    if twice or garbled or reported > demo.accept_count:
        checks.append(Check("held-out results: one per check", False,
                            f"{reported} results for {demo.accept_count} checks"
                            + (f"; reported more than once: {', '.join(twice)}" if twice else "")
                            + (f"; {garbled} result lines that are not the reporter's" if garbled else "")))
    elif all(c.ok for c in checks) and code != 0:
        checks.append(Check("held-out results: the test runner agrees", False,
                            f"every check reported ok, but {runner} "
                            f"{'did not finish' if code is None else f'exited {code}'}"
                            + (f" ({why})" if load_errors or err.strip() else "")))
    elif not all(c.ok for c in checks) and code == 0:
        checks.append(Check("held-out results: the test runner agrees", False,
                            f"a check failed, but {runner} exited 0"))
    return checks


# --------------------------------------------------------------------------
# Demo rules
# --------------------------------------------------------------------------

def rel(p: Path, root: Path) -> str:
    return p.relative_to(root).as_posix()


def entry_point_problems(ws: Path, name: str, home: Path | None = None, regrade: bool = False,
                         kit: Path | None = None, python: bool = False) -> list[str]:
    """What gives the workspace `ws` a test command other than start.py's `test`, which must name the kit at
    `kit` (default: this one). `home` is where the workspace lives when `ws` is a copy of it; with `regrade`
    (CI's re-grade), `test` may name another clone of the kit. A `python` demo's one entry point is the
    launcher its rules file names, so any package.json test script there is a second one."""
    probs = [f"{p}: CI config" for p in CI_PATHS if (ws / p).exists()]
    probs += [f"{rel(p, ws)}: a second way to run the tests" for p in dl.walk(ws) if p.name.lower() in RUNNER_FILES]
    if (ws / ".npmrc").exists():
        probs.append(".npmrc: npm settings, which can change what `npm test` runs (its script-shell, for one)")
    if python:
        for p in dl.walk(ws):
            if p.name == "package.json":
                try:
                    more = json.loads(dl.read_text(p)).get("scripts") or {}
                except (ValueError, AttributeError):
                    more = {}
                probs += [f"{rel(p, ws)}: a test script, {k!r}, beside the launcher" for k in more
                          if "test" in str(k).lower()]
        return probs
    pkg = ws / "package.json"
    if not pkg.is_file():
        return probs + ["package.json is missing; its `test` script is the demo's one test entry point"]
    try:
        scripts = json.loads(dl.read_text(pkg)).get("scripts")
    except (ValueError, AttributeError):
        return probs + ["package.json is not a JSON object"]
    scripts = scripts if isinstance(scripts, dict) else {}
    why = dl.test_script_problem(str(scripts.get("test", "")), name, None if regrade else home or ws,
                                 None if regrade else kit or dl.KIT)
    if why:
        probs.append(f"package.json: `test` must stay what demos/start.py wrote (the launcher's `demo check {name}`): "
                     f"{why}")
    probs += [f"package.json: another test script, {k!r}" for k in scripts if k != "test" and "test" in k.lower()]
    for p in dl.walk(ws):
        if p.name == "package.json" and p != pkg:
            try:
                more = json.loads(dl.read_text(p)).get("scripts") or {}
            except (ValueError, AttributeError):
                more = {}
            probs += [f"{rel(p, ws)}: another test script, {k!r}" for k in more if "test" in str(k).lower()]
    return probs


def asset_problems(ws: Path, ignores: list[str] | None = None) -> list[str]:
    """Binary assets in `ws`, but for files the skeleton's own .gitignore (`ignores`, dl.skeleton_ignores) leaves
    out: what the program writes when it runs, such as a renderer's frames, is its output, not an asset."""
    probs = []
    for p in dl.walk(ws):
        r = rel(p, ws)
        if ignores and dl.ignored(r, ignores):
            continue
        kind = next((k for k, exts in ASSET_KINDS.items() if p.suffix.lower() in exts), None)
        if kind:
            probs.append(f"{r}: {'an' if kind[0] in 'aeiou' else 'a'} {kind} file")
            continue
        data = p.read_bytes()
        if b"\0" in data[:8192]:
            probs.append(f"{r}: binary content")
            continue
        text = data.decode("utf-8", errors="replace")
        if DATA_URL.search(text):
            probs.append(f"{r}: a data: URL holding an image, audio or font")
            continue
        block = base64_block(text)
        if block:
            size, first, last = block
            probs.append(f"{r}: base64 over 1 KB ({size} characters"
                         + (f", lines {first}-{last})" if last > first else f", line {first})"))
    return probs


def base64_block(text: str) -> tuple[int, int, int] | None:
    """(size, first line, last line) of the first base64 block over BASE64_MAX characters, or None."""
    size = first = 0
    for n, ln in enumerate(text.split("\n"), 1):
        here = sum(len(m.group()) for m in BASE64_PIECE.finditer(ln))
        if not here:
            size = 0
            continue
        if not size:
            first = n
        size += here
        if size > BASE64_MAX:
            last = n
            for ln2 in text.split("\n")[n:]:  # report the whole block
                more = sum(len(m.group()) for m in BASE64_PIECE.finditer(ln2))
                if not more:
                    break
                size, last = size + more, last + 1
            return size, first, last
    return None


def denylist_problems(ws: Path) -> list[str]:
    terms = dl.load_denylist()
    probs = []
    for p in dl.walk(ws):
        data = p.read_bytes()
        if b"\0" in data[:8192]:
            continue
        probs += [f"{rel(p, ws)}:{n}: {term!r} names an existing franchise or toy line"
                  for n, term in dl.denylist_hits(data.decode("utf-8", errors="replace"), terms)]
    return probs


def norm(line: str) -> str:
    return " ".join(line.split())


def long_lines(text: str) -> set[str]:
    return {k for k in map(norm, text.split("\n")) if len(k) >= MIN_LINE}


def tree_lines(root: Path) -> set[str]:
    out: set[str] = set()
    for p in dl.walk(root) if root.is_dir() else ():
        out |= long_lines(dl.read_text(p))
    return out


def copy_problems(ws: Path, demo: Demo) -> list[str]:
    ref = (tree_lines(demo.dir / "reference") - tree_lines(demo.dir / "skeleton")
           - long_lines(dl.read_text(demo.dir / "BRIEF.md")))
    kit_written = {"BRIEF.md", "package.json"} | {v.repo_rules for v in dl.vocab.VOCAB.values()}
    shared: dict[str, str] = {}
    for p in dl.walk(ws):
        r = rel(p, ws)
        if r in kit_written or b"\0" in p.read_bytes()[:8192]:
            continue
        for n, ln in enumerate(dl.read_text(p).split("\n"), 1):
            k = norm(ln)
            if len(k) >= MIN_LINE and k in ref and k not in shared:
                shared[k] = f"{r}:{n}"
    if len(shared) <= MAX_SHARED:
        return []
    return [f"{len(shared)} lines match the kit's reference solution (more than {MAX_SHARED} is a copy), first at "
            + ", ".join(list(shared.values())[:3])]


def kit_reference_problems(ws: Path, name: str, kit: Path | None = None) -> list[str]:
    """Where the workspace's code names the kit's files (dl.kit_needles): its clone's path, the default clone
    folder, the install record or a demo's reference/. Not read: documentation (dl.KIT_TEXT_SKIP), the files
    start.py writes at the top (BRIEF.md, the rules files) and package.json's `test`, which names the launcher."""
    needles = dl.kit_needles(name, kit or dl.KIT)
    kit_written = {"BRIEF.md"} | {v.repo_rules for v in dl.vocab.VOCAB.values()}
    probs = []
    for p in dl.walk(ws):
        r = rel(p, ws)
        data = p.read_bytes()
        if r in kit_written or p.suffix.lower() in dl.KIT_TEXT_SKIP or b"\0" in data[:8192]:
            continue
        text = data.decode("utf-8", errors="replace")
        if r == "package.json":
            try:
                pkg = json.loads(text)
                if isinstance(pkg, dict) and isinstance(pkg.get("scripts"), dict):
                    pkg["scripts"].pop("test", None)
                text = json.dumps(pkg)
            except ValueError:
                pass
        for n, ln in enumerate(text.split("\n"), 1):
            seen = dl.kit_text(ln)
            hit = next((x for x in needles if x in seen), None)
            if hit:
                probs.append(f"{r}:{n}: names the kit's files ({hit!r})")
                break
    return probs


def rules(ws: Path, demo: Demo, allow_assets: bool, home: Path | None = None, regrade: bool = False) -> list[Check]:
    def check(name: str, probs: list[str], waived: bool = False) -> Check:
        if waived and probs:
            return Check(f"{name} (waived by --allow-assets)", True, "; ".join(probs))
        return Check(name, not probs, "; ".join(probs))
    python = demo.runtime == "python"
    entry = "the launcher its rules file names" if python else "package.json `test`"
    return [check(f"rule: one test entry point, {entry}",
                  entry_point_problems(ws, demo.name, home, regrade, python=python)),
            check("rule: no binary assets", asset_problems(ws, dl.skeleton_ignores(demo)), waived=allow_assets),
            check("rule: original names (demos/denylist.txt)", denylist_problems(ws)),
            check("rule: not copied from the kit's reference solution", copy_problems(ws, demo)),
            check("rule: no code that names the kit's files", kit_reference_problems(ws, demo.name))]


# --------------------------------------------------------------------------
# The kit side: is this clone's grading the committed one?
# --------------------------------------------------------------------------

def kit_refusal(demo: Demo, allow_modified: bool, reasons: list[str]) -> str | None:
    """Why grading is refused, or None; appends to `reasons` each reason the RECORD is not recordable."""
    rec, problem = dl.load_record_or_none()
    root = ((rec or {}).get("kit") or {}).get("kit_root")
    if root and Path(root).resolve() != dl.KIT.resolve():
        return (f"this machine's install record ({dl.install.record_path()}) belongs to the clone at {root}, not "
                f"{dl.KIT}. Grade with that clone's launcher, so the checks are the ones it installed.")
    if rec is None:
        reasons.append("no-install-record")
    if dl.head_sha() is None:
        reasons.append("not-a-git-clone")
        return None
    (now, why), (head, why_head) = dl.hash_grading(demo.name), dl.hash_grading(demo.name, "HEAD")
    if not allow_modified and (now is None or head is None):
        return (f"cannot hash the files that grade this demo ({why or why_head}), so there is no telling whether "
                f"they are the kit's last commit. {dl.KIT} needs git and a readable .git folder; nothing is "
                "written there. Add --allow-modified-accept to grade anyway (the RECORD then says recordable=no).")
    if now != head and not allow_modified:
        changed = dl.changed_graders(demo.name)
        return ("the files that grade this demo differ from the kit's last commit"
                + (f" ({', '.join(changed[:5])})" if changed else "")
                + ", so a grade from them would not be the kit's. Restore or commit them, or add "
                  "--allow-modified-accept to grade anyway (the RECORD then says recordable=no).")
    if allow_modified:
        reasons.append("allow-modified-accept")
    return None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="check.py", description="Grade a demo workspace with the kit's held-out checks.")
    ap.add_argument("name", help="the demo, as demos/start.py named it")
    ap.add_argument("--dir", type=Path, help="the workspace (default: the current folder)")
    ap.add_argument("--allow-modified-accept", action="store_true",
                    help="grade although the kit's grading files differ from its last commit (not recordable)")
    ap.add_argument("--allow-assets", action="store_true", help="let binary assets through (not recordable)")
    ap.add_argument("--regrade", action="store_true", help="CI's re-grade of a committed workspace that another "
                    "clone made: its `test` may name that clone (demolib.regrade; not recordable)")
    ap.add_argument("--accept-only", action="store_true", help="run the held-out checks alone on the folder, as "
                    "a demo's own mutants runner does; no rules, no RECORD, not a grade")
    args = ap.parse_args(argv)
    try:
        demo = dl.load_demo(args.name)
    except KeyError:
        print(dl.unknown_demo(args.name), file=sys.stderr)
        return 2
    ws = (args.dir.expanduser() if args.dir else Path.cwd()).resolve()
    if args.accept_only:
        node_lines = dl.node_problem(demo, demo.app)
        problem = (dl.python_problem() or (node_lines[0] if node_lines else None)
                   or (None if ws.is_dir() else f"{ws} is not a folder"))
        if problem:
            print(f"error: {problem}", file=sys.stderr)
            return 2
        os.chdir(tempfile.gettempdir())
        held = run_accept(demo, ws, failfast=False)
        for c in held:
            print(f"  {'ok  ' if c.ok else 'FAIL'}  {c.name}" + (f": {c.detail}" if c.detail else ""))
        k = sum(c.ok for c in held)
        print(f"{'PASS' if k == len(held) else 'FAIL'} {k}/{len(held)}")
        print("ACCEPT ONLY: the held-out checks alone, for a mutants runner; not a grade, and no RECORD.")
        return 0 if k == len(held) else 1
    if not (ws / "BRIEF.md").is_file():
        print(f"error: {ws} is not a demo workspace (no BRIEF.md). Run this in the folder demos/start.py made, or "
              "pass --dir <that folder>. Nothing was graded.", file=sys.stderr)
        return 2
    reasons: list[str] = []
    refusal = kit_refusal(demo, args.allow_modified_accept, reasons)
    if refusal:
        print(f"error: {refusal} Nothing was graded.", file=sys.stderr)
        return 2
    lines = dl.node_problem(demo, demo.app)
    if lines:
        print("\n".join(lines).replace("Nothing was written.", "Nothing was graded."), file=sys.stderr)
        return 2
    if dl.python_problem():
        print(f"error: {dl.python_problem()} Run the launcher with a newer Python. Nothing was graded.", file=sys.stderr)
        return 2
    reasons += [f for f, on in (("allow-assets", args.allow_assets), ("regrade", args.regrade)) if on]

    os.chdir(tempfile.gettempdir())  # out of the workspace, which may hold programs named like node or git
    before = dl.grading_tree(demo.name)
    with tempfile.TemporaryDirectory(prefix="demo-grade-") as td:
        copy = Path(td) / "ws"
        dl.copy_workspace(ws, copy, git=demo.copy_git)
        held = run_accept(demo, copy, copied=True)
        checks = held + rules(copy, demo, args.allow_assets, home=ws, regrade=args.regrade)
    tree = dl.grading_tree(demo.name)
    if tree is None:
        reasons.append("accept-hash-unknown")
    elif tree != before:  # the workspace's code runs during the checks, and it may not rewrite them
        reasons.append("grading-files-changed-during-the-run")
    k, n = sum(c.ok for c in checks), len(checks)
    print(f"{demo.app}: {len(held)} held-out checks from the kit's demos/{demo.name}/accept/, then the demo rules, "
          f"on {ws}")
    for c in checks:
        print(f"  {'ok  ' if c.ok else 'FAIL'}  {c.name}" + (f": {c.detail}" if c.detail else ""))
    verdict = f"{'PASS' if k == n else 'FAIL'} {k}/{n}"
    print(verdict)
    print(f"NOT CHECKED: {demo.not_checked}")
    print(LOCAL_GRADE)
    node = dl.node_version()
    cmd = "npm test" if os.environ.get("npm_lifecycle_event") == "test" else f"starter.py demo check {demo.name}"
    facts = [f"kit_sha={dl.head_sha() or 'unknown'}", f"accept_hash={tree or 'unknown'}",
             f"node={'.'.join(map(str, node)) if node else 'none'}",
             f"python={'.'.join(map(str, sys.version_info[:3]))}",
             f"date={datetime.now(timezone.utc).date().isoformat()}",
             "recordable=" + ("yes" if not reasons else "no:" + ",".join(reasons))]
    print(f"RECORD: Verified: {cmd} (demo check {demo.name}, a local grade: feedback, not proof) -> {verdict} "
          f"[{' '.join(facts)}]")
    return 0 if k == n else 1


if __name__ == "__main__":
    sys.exit(main())
