"""The demos: each brief's held-out checks bind, start.py refuses before writing, check.py grades only with the kit's
committed checks, and pick.py prints numbers only from measured runs. Each guard here was seen to fail once on a
planted violation (the plant tests below keep that so). Runs need Node 22.13 or newer on PATH and fail without it:
CI's demos job has it, and the scripts job does not collect this folder.

Everything runs in a throwaway HOME whose path holds an apostrophe, against a scratch copy of the kit committed in
its own git repo, so nothing touches the real ~/.agents, ~/.claude or ~/agent-demos, and the real clone's
uncommitted state cannot change a result.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

DEMOS = Path(__file__).resolve().parent.parent
KIT = DEMOS.parent
sys.path.insert(0, str(DEMOS))
sys.path.insert(0, str(KIT / "scripts"))
import build_adapters as ba  # noqa: E402
import check  # noqa: E402
import demolib as dl  # noqa: E402
import mutants  # noqa: E402
import pick  # noqa: E402
import start  # noqa: E402
from demolib import install  # noqa: E402

DEMO_NAMES = dl.demo_names()
# The demos whose checks reach the workspace's code through probe.mjs, under Node's permission model: node, and a
# mixed demo's frontend. A Python demo's checks run its code in processes of their own too, but with no permission
# model, and a static test holds them to never importing it (test_runtimes.test_python_checks_never_import_...).
PROBED = [n for n in DEMO_NAMES
          if json.loads((DEMOS / n / "demo.json").read_text(encoding="utf-8")).get("runtime") != "python"]
# A planted bug per demo, on CI's demos job (Windows too, where demo-mutants does not run): (the id of a mutant in
# the demo's own accept/mutants/, a check that must then fail). An off-by-one where the demo has one.
PLANTS = {
    "commit-guard-dojo": ("064", "test_11_longest_streak_held_out_cases"),
    "fair-share": ("001", "split: the shares add up to exactly the total"),
    "lanes": ("023-hard-from-14", "backend: difficulty follows the rule, boundaries included"),
    "monster-tamer-lite": ("140-attempt-off-by-one", "Graded 11: Catching"),
    "next-word": ("015-order-cap-3", "model: order n uses up to n-1 previous tokens, for any n"),
    "pocket-region": ("016-up-is-down", "Graded 3: movePlayer moves one tile, turns the player even when blocked, "
                      "names the reason, opens a gate with its flag"),
    "roulette-loom": ("001", "trace gives steps + 1 points, from the start of the curve back to it"),
    "spin-clash": ("058-ringout-skips-tick-1", "Graded 8: ring-out and spin-down are judged on tick 1 by the centre, "
                   "ring-out first, and the last top in play wins"),
    "split-screen-racer": ("080-player-starts-on-lap-1", "createRace: players start on the grid, with the documented "
                           "fields and the given laps and track"),
    "synesthesia": ("001-flash-cap-4", "item 15: a strobe of 20 Hz never gets more than three flashes in any second "
                    "over 10 s, but is not blocked either"),
    "trippy-video": ("004-frames-numbered-from-one", "test_frame_count"),
}
NUMBER = re.compile(r"\d+%|\$\d")


@pytest.fixture(scope="session", autouse=True)
def isolated_git(tmp_path_factory):
    """Every git call, in this process and in the scripts it runs, without the machine's own git config: no user
    hooks or signing reach the fixtures, and the in-process hashes see the same line-ending settings as the
    scripts (core.autocrlf from Git for Windows' system config once made the two disagree)."""
    saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
    os.environ["GIT_CONFIG_GLOBAL"] = str(tmp_path_factory.mktemp("git") / "empty.gitconfig")
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(scope="session", autouse=True)
def node():
    v = dl.node_version()
    if not v or v[:2] < dl.NODE_FLOOR:
        pytest.fail(f"demos/tests need Node {dl.NODE_FLOOR_TEXT} or newer on PATH (found {v}); they never skip")
    return v


def clean_env(home: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CODEX_", "COMMIT_GUARD_", "npm_")) and k not in ("CLAUDECODE", "NODE_OPTIONS")}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
    env.update(extra)
    return env


def masked(text: str, *roots: Path) -> str:
    """`text` with the kit's clone and each of `roots` written as <path>, however the output spells them: as they
    are or with forward slashes, an apostrophe as it is or quoted for bash or PowerShell. The term check holds the
    kit's own words, and a folder above the clone or pytest's temp folder can name a tool without being the kit's:
    16 start and pick tests failed only for running under Temp\\claude\\ (2026-11-21)."""
    spellings = {form.replace("'", quoted) for root in (KIT, install.cmd_root(), *roots)
                 for form in (str(root), root.as_posix()) for quoted in ("'", "'\"'\"'", "''")}
    for spelling in sorted(spellings, key=len, reverse=True):
        text = text.replace(spelling, "<path>")
    return text


def git(cwd: Path, *a: str, env: dict | None = None) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=120)
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout.strip()


def commit_all(repo: Path, msg: str, env: dict) -> str:
    git(repo, "add", "-A", env=env)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", msg,
        "-m", "Unverified: a test fixture", env=env)
    return git(repo, "rev-parse", "HEAD", env=env)


@pytest.fixture(scope="session")
def scratch(tmp_path_factory):
    """(kit, env): a copy of the kit's files the demos use, committed in its own repo with an origin/main."""
    base = tmp_path_factory.mktemp("demos")
    home = base / "it's home"
    home.mkdir()
    env = clean_env(home)
    kit = base / "kit"

    def ignore(folder: str, names: list) -> set:
        """Caches, and the kit's own test suites (demos/tests, scripts/tests), never a demo's tests/ folder."""
        skip = {n for n in names if n in ("__pycache__", ".pytest_cache") or n.endswith(".pyc")}
        return skip | ({"tests"} & set(names) if Path(folder).parent == KIT else set())
    for rel in ("demos", "scripts", "core"):
        shutil.copytree(str(KIT / rel), str(kit / rel), ignore=ignore)
    (kit / "plugins/starter/hooks/commit-guard").mkdir(parents=True)
    shutil.copy2(str(install.GUARD), str(kit / "plugins/starter/hooks/commit-guard/guard.py"))
    for rel in ("kit.json", "MODELS.md"):
        shutil.copy2(str(KIT / rel), str(kit / rel))
    git(kit, "init", "-q", env=env)
    sha = commit_all(kit, "test: the kit's demo files", env)
    git(kit, "update-ref", "refs/remotes/origin/main", sha, env=env)
    return kit, env


def test_the_scratch_kit_holds_every_file_of_every_demo(scratch):
    """A demo's own tests/ folder (a Python skeleton's, a lane's backend's) is part of the demo. The copy once
    left out every folder named tests, this suite's and the demos' alike, so a workspace started from the scratch
    kit had no tests/ and a fixture built there crashed on a missing file."""
    kit, _ = scratch
    missing = [p.relative_to(DEMOS).as_posix() for name in DEMO_NAMES for p in dl.walk(DEMOS / name)
               if not (kit / "demos" / p.relative_to(DEMOS)).is_file()]
    assert missing == []


@pytest.fixture
def home(tmp_path, scratch):
    """A fresh HOME whose record says the scratch kit is installed for claude, codex and opencode."""
    kit, _ = scratch
    h = tmp_path / "it's home"
    h.mkdir()
    write_record(h, kit, ["claude", "codex", "opencode"])
    return h


def write_record(h: Path, kit: Path, tools: list, project: bool = False) -> Path:
    rec = install.new_record()
    rec["kit"]["kit_root"] = str(kit)
    rec["installs"] = [dict({"tool": t, "tier": "starter", "config_dir": str(h / t), "adopted": False,
                             "migrations_applied": [], "files": {}, "options": {}},
                            **({"project": str(h / "repo")} if project else {})) for t in tools]
    p = h / ".agents" / "starter" / "installs.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return p


def run(kit: Path, script: str, *args: str, home: Path, cwd: Path | None = None, **env) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(kit / "demos" / script), *args], cwd=str(cwd or home),
                          env=clean_env(home, **env), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", stdin=subprocess.DEVNULL, timeout=600)


def started(kit: Path, home: Path, name: str, tool: str = "claude") -> Path:
    r = run(kit, "start.py", name, "--tool", tool, home=home)
    assert r.returncode == 0, r.stderr
    return home / "agent-demos" / name


def npm_test(ws: Path, home: Path) -> subprocess.CompletedProcess:
    npm = shutil.which("npm")
    assert npm, "npm is not on PATH"
    return subprocess.run([npm, "test"], cwd=str(ws), env=clean_env(home), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=600)


def verdict(out: str) -> str:
    return next(ln for ln in out.split("\n") if re.fullmatch(r"(PASS|FAIL) \d+/\d+", ln))


def record_line(out: str) -> str:
    return next(ln for ln in out.split("\n") if ln.startswith("RECORD: "))


def paraphrase(src: Path, dest: Path) -> None:
    """The reference's code with a comment in front of every line: the same behaviour, sharing no line. It is the
    gap the line count admits (a paraphrase passes), used here to reach a PASS end to end."""
    dest.write_text("".join(f"/* p */ {ln}" for ln in dl.read_text(src).splitlines(keepends=True)), encoding="utf-8")


# ---- each brief's held-out checks bind (the CI core) -------------------------------------------------------

def finished(demo: dl.Demo, tmp: Path, case=None, edit=None) -> Path:
    """The finished workspace the reference makes, with a mutant's edits if one is given, then `edit(folder)`'s: a
    copy of reference/, or what the demo's fixture builds from that copy, history and all (a demo graded on its git
    log has no .git in the kit), exactly as the mutants engine builds it."""
    ref = tmp / "ref"
    shutil.copytree(str(demo.dir / "reference"), str(ref))
    if case is not None:
        assert mutants.parse_problem(mutants.apply_edits(ref, case)) is None
    if edit is not None:
        edit(ref)
    mutants.build_fixture(demo, ref, tmp / "ws", tmp)
    return tmp / "ws"


@pytest.mark.parametrize("name", DEMO_NAMES)
def test_each_reference_passes_its_held_out_checks(name, tmp_path):
    demo = dl.load_demo(name)
    results = check.run_accept(demo, finished(demo, tmp_path))
    assert [c.name for c in results if not c.ok] == [], [(c.name, c.detail) for c in results if not c.ok]
    assert len(results) == demo.accept_count


@pytest.mark.parametrize("name", DEMO_NAMES)
def test_each_skeleton_fails_its_held_out_checks(name):
    demo = dl.load_demo(name)
    results = check.run_accept(demo, demo.dir / "skeleton")
    assert len(results) == demo.accept_count and any(not c.ok for c in results)


def test_every_demo_has_its_plants():
    """A demo added without them would be proved by none of the plant tests below, which run over these tables."""
    assert sorted(PLANTS) == DEMO_NAMES, "add the new demo to PLANTS"
    assert sorted(HAND_BACK) == sorted(CHEATS) == PROBED, "add the new demo to HAND_BACK and CHEATS"


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_planted_bug_in_the_reference_fails_its_own_check(name, tmp_path):
    demo = dl.load_demo(name)
    mutant, fails = PLANTS[name]
    case = next((c for c in mutants.load_cases(demo)[0] if c.id == mutant), None)
    assert case, f"demos/{name}/accept/mutants/ holds no mutant {mutant!r}; update PLANTS"
    failed = [c.name for c in check.run_accept(demo, finished(demo, tmp_path, case)) if not c.ok]
    assert fails in failed, failed


def test_break_the_verifier_ships_its_own_tests_passing_while_the_held_out_checks_fail(tmp_path):
    """The behavioural plant: a shallow self-test passes where the held-out check fails, so only a verifier that
    runs the repo's own test command (npm test) reports FAIL."""
    demo = dl.load_demo("fair-share")
    ws = tmp_path / "ws"
    shutil.copytree(str(demo.dir / "skeleton"), str(ws))
    own = subprocess.run([shutil.which("node"), "--test"], cwd=str(ws), capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=300)
    assert own.returncode == 0 and re.search(r"pass [1-9]", own.stdout), own.stdout
    failed = [c.name for c in check.run_accept(demo, ws) if not c.ok]
    assert failed == [PLANTS["fair-share"][1], "split: one cent between three people is [1, 0, 0]"]


def test_a_workspace_module_that_cannot_load_fails_every_check_by_name(tmp_path):
    demo = dl.load_demo("roulette-loom")
    ws = tmp_path / "ws"
    shutil.copytree(str(demo.dir / "reference"), str(ws))
    (ws / "src" / "loom.js").write_text("export const = ;\n", encoding="utf-8")  # a syntax error
    results = check.run_accept(demo, ws)
    assert len(results) == demo.accept_count and not any(c.ok for c in results)
    assert not any("did not run" in c.name for c in results)   # each check reported, under its own name


def test_checks_that_never_report_count_as_failed(tmp_path, monkeypatch):
    """A check file that dies before its tests run reports none of them; the count still holds them all, so a
    broken run can never read as a short PASS."""
    fake = tmp_path / "demos" / "fake"
    (fake / "accept").mkdir(parents=True)
    (fake / "accept" / "a.test.mjs").write_text(
        "import { test } from 'node:test';\nthrow new Error('the check file is broken');\n", encoding="utf-8")
    (fake / "accept" / "b.test.mjs").write_text("import { test } from 'node:test';\ntest('fine', () => {});\n",
                                                encoding="utf-8")
    monkeypatch.setattr(dl, "DEMOS", tmp_path / "demos")
    demo = dl.Demo("fake", "Fake", "Fake", "S", "node", "s", "k", "n", 3)
    ws = tmp_path / "ws"
    ws.mkdir()
    results = check.run_accept(demo, ws)
    assert [c.ok for c in results] == [True, False, False], results
    assert all("the check file is broken" in c.detail for c in results[1:]), results


# ---- the grade reads a copy of the workspace, under Node's permission model --------------------------------

# Per probed demo, a module of its reference: (its path, the names it exports, a call whose answer is the work).
HAND_BACK = {
    "fair-share": ("src/share.js", "split, withTip", ["split", 1001, 4]),
    "lanes": ("frontend/render.js", "escapeHtml, renderDifficulty, renderTrailRow, renderBoard",
              ["escapeHtml", "<b>Ridge & Vale's</b>"]),
    "monster-tamer-lite": ("src/rng.js", "createRng, nextFloat", ["createRng", 12345]),
    "next-word": ("src/lm.js", "tokenize, compareEntries, train, nextDistribution",
                  ["tokenize", "The fox's den, and 2 owls."]),
    "pocket-region": ("src/save.js", "canonicalJson, saveGame, loadGame", ["canonicalJson", {"b": [2, None], "a": "x"}]),
    "roulette-loom": ("src/loom.js", "gcd, laps, point, trace", ["laps", 96, 35]),
    "spin-clash": ("src/physics.js", "DT, LIMITS, DEFAULTS, inertia, createWorld, collide, step",
                   ["inertia", {"mass": 2, "radius": 3}]),
    "split-screen-racer": ("src/camera.js", "splitViewports, worldToScreen",
                           ["splitViewports", 800, 600, [{"x": 120.5, "y": -40}, {"x": -900, "y": 310}]]),
    "synesthesia": ("src/analysis.js", "binFrequency, chroma, loudness, spectralCentroid, balance, estimateMode",
                    ["binFrequency", 3, 1024, 44100]),
}
_BARE: dict = {}


def bare_skeleton(demo: dl.Demo) -> dict:
    """{check name: Check} for the demo's skeleton as shipped, graded once per session."""
    if demo.name not in _BARE:
        _BARE[demo.name] = {c.name: c for c in check.run_accept(demo, demo.dir / "skeleton")}
    return _BARE[demo.name]


def hand_back_the_reference(name: str, how: str) -> str:
    """A verifier's plants: a module that does none of the work and hands back the kit's own reference solution,
    by its file URL, or by a path made at run time from the probe's own location, so that the file names no kit
    path at all. Each passed every held-out check before the probe ran under Node's permission model."""
    rel, names, _ = HAND_BACK[name]
    if how == "url":
        return f'export * from "{(DEMOS / name / "reference" / rel).as_uri()}";\n'
    parts = json.dumps([name, "reference", *rel.split("/")])[1:-1]
    return ("import { pathToFileURL } from 'node:url';\nimport path from 'node:path';\n"
            "const kit = path.dirname(process.argv[1]);\n"
            f"const m = await import(pathToFileURL(path.join(kit, {parts})).href);\n"
            f"export const {{ {names} }} = m;\n")


def unconfined_answer(module: Path, call: list, tmp: Path) -> str:
    """What probe-child.mjs answers for `call` on `module` when started as it was before the permission model,
    with the kit readable: the JSON of its one result."""
    probe = tmp / "as-it-was.mjs"
    probe.write_text(
        "import { spawnSync } from 'node:child_process';\nimport v8 from 'node:v8';\n"
        f"const r = spawnSync(process.execPath, [{json.dumps(str(DEMOS / 'probe-child.mjs'))}, "
        f"{json.dumps(module.as_uri())}, v8.serialize([{json.dumps(call)}]).toString('base64')], "
        "{ encoding: 'utf8', input: 'k' });\n"
        "const line = r.stdout.split('\\n').find((l) => l.startsWith('demo-probe-answer:k:'));\n"
        "console.log(JSON.stringify(v8.deserialize(Buffer.from(line.slice(20), 'base64'))));\n",
        encoding="utf-8")
    r = subprocess.run([dl.exe("node"), str(probe)], cwd=str(tmp), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    return r.stdout.strip() or r.stderr


@pytest.mark.parametrize("how", ["url", "argv"])
@pytest.mark.parametrize("name", sorted(HAND_BACK))
def test_a_module_that_hands_back_the_kits_reference_gains_nothing(name, how, tmp_path):
    """Under the permission model the plant cannot read the kit, so it passes no check the bare skeleton fails, and
    the checks that load it say the permission model refused it and which flag it withheld, on Node 22.13 as on
    newer 22.x (22.13's own message names no flag, and these failed there)."""
    demo = dl.load_demo(name)
    rel, _, call = HAND_BACK[name]
    ws = tmp_path / "ws"
    shutil.copytree(str(demo.dir / "skeleton"), str(ws))
    (ws / rel).parent.mkdir(parents=True, exist_ok=True)
    (ws / rel).write_text(hand_back_the_reference(name, how), encoding="utf-8")
    # The plant is a real cheat: unconfined, it answers as the reference does.
    want = unconfined_answer(demo.dir / "reference" / rel, call, tmp_path)
    assert want.startswith('{"results":[{"ok":true'), want
    assert unconfined_answer(ws / rel, call, tmp_path) == want
    results = {c.name: c for c in check.run_accept(demo, ws)}
    bare = bare_skeleton(demo)
    assert len(results) == demo.accept_count, sorted(results)
    assert [n for n, c in results.items() if c.ok and not (n in bare and bare[n].ok)] == []
    assert any("--allow-fs-read" in c.detail for c in results.values()), list(results.values())[0]
    assert all("--allow-fs-read" in c.detail for c in results.values() if f"{rel} did not load" in c.detail)


def test_the_workspaces_code_cannot_write_during_the_checks(scratch, home):
    """A verifier's plant: a working module that also appends to the kit's held-out checks as it loads."""
    kit, _ = scratch
    ws = started(kit, home, "roulette-loom")
    target = kit / "demos" / "roulette-loom" / "accept" / "loom.test.mjs"
    before = target.read_bytes()
    paraphrase(kit / "demos/roulette-loom/reference/src/loom.js", ws / "src" / "loom.js")
    work = dl.read_text(ws / "src" / "loom.js")
    (ws / "src" / "loom.js").write_text("import { appendFileSync } from 'node:fs';\n"
                                       f"appendFileSync({json.dumps(str(target))}, '\\n// tampered\\n');\n" + work,
                                       encoding="utf-8")
    try:
        r = run(kit, "check.py", "roulette-loom", home=home, cwd=ws)
        assert target.read_bytes() == before
        # The module names the kit's file to write it, which the kit-reference rule fails as well.
        assert verdict(r.stdout) == "FAIL 4/15" and "allow-fs-write" in r.stdout, r.stdout
        assert "FAIL  rule: no code that names the kit's files: src/loom.js:2" in r.stdout, r.stdout
        assert "recordable=yes" in record_line(r.stdout)
    finally:
        target.write_bytes(before)


def test_a_link_in_the_workspace_is_not_followed_out_of_it(tmp_path):
    """Node's permission model follows a link out of the folder it allows, so the copy that is graded has none."""
    demo = dl.load_demo("roulette-loom")
    ws = tmp_path / "ws"
    shutil.copytree(str(demo.dir / "skeleton"), str(ws))
    ref = demo.dir / "reference" / "src"
    link = ws / "src" / ("ref" if os.name == "nt" else "loom.js")
    if os.name == "nt":   # a junction needs no privilege, where a symbolic link does
        import _winapi
        _winapi.CreateJunction(str(ref), str(link))
        (ws / "src" / "loom.js").write_text("export * from './ref/loom.js';\n", encoding="utf-8")
    else:
        link.unlink()
        os.symlink(str(ref / "loom.js"), str(link))
    try:
        assert dl.is_link(link) and not dl.is_link(ws / "index.html")
        dl.copy_workspace(ws, tmp_path / "copy")
        assert not (tmp_path / "copy" / link.relative_to(ws)).exists()
        assert (tmp_path / "copy" / "index.html").is_file()
        assert not any(c.ok for c in check.run_accept(demo, ws))
    finally:
        os.rmdir(str(link)) if os.name == "nt" else link.unlink()   # the link only, never what it points at


def fake_program(ws: Path, prog: str, mark: Path) -> None:
    """The reviewer's node.cmd: plain text that prints a held-out check's passing line for every check and exits 0."""
    passes = [json.dumps({"demo_event": "test", "ok": True, "name": f"check {i}", "nesting": 0, "kind": "test"})
              for i in range(1, 10)]
    if os.name == "nt":
        body = ["@echo off", f'echo ran> "{mark}"', 'if "%~1"=="--version" (', "  echo v22.99.0", "  exit /b 0", ")"]
        body += [f"echo {p}" for p in passes] + ["exit /b 0", ""]
        (ws / f"{prog}.cmd").write_bytes("\r\n".join(body).encode("ascii"))
    else:
        body = ["#!/bin/sh", f"echo ran > '{mark}'", '[ "$1" = --version ] && { echo v22.99.0; exit 0; }']
        body += [f"echo '{p}'" for p in passes] + ["exit 0", ""]
        (ws / prog).write_text("\n".join(body), encoding="utf-8")
        os.chmod(str(ws / prog), 0o755)


def test_a_program_named_node_or_git_in_the_workspace_is_never_run(scratch, home):
    """Windows looks in the current folder first, and the person often grades from inside the workspace; POSIX does
    the same for a PATH holding "." or an empty entry. The launcher, run there, must still use the real Node."""
    kit, _ = scratch
    ws = started(kit, home, "fair-share")
    mark = home / "a-fake-program-ran"
    for prog in ("node", "git"):
        fake_program(ws, prog, mark)
    env = clean_env(home, PATH=os.pathsep.join([".", "", os.environ["PATH"]]))
    env.pop("NoDefaultCurrentDirectoryInExePath", None)   # an ordinary terminal does not set it
    r = subprocess.run([sys.executable, str(kit / "scripts" / "starter.py"), "demo", "check", "fair-share"],
                       cwd=str(ws), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, timeout=600)
    assert not mark.exists(), r.stdout
    assert verdict(r.stdout) == "FAIL 12/14" and "node=22.99.0" not in r.stdout, r.stdout + r.stderr


def test_exe_never_looks_in_the_current_folder(tmp_path, monkeypatch):
    fake_program(tmp_path, "node", tmp_path / "ran")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", os.environ["PATH"]]))
    found = dl.exe("node")
    assert found and Path(found).is_absolute() and Path(found).parent != tmp_path, found


# ---- what the workspace is told ----------------------------------------------------------------------------

LEAK = re.compile(r"verifier", re.I)


def leaks(ws: Path, *said: str) -> list:
    """Where a workspace's files, or text it showed the agent, say "verifier": the word that would tell the verifier
    in Break the verifier that it is the one being tried."""
    return ([rel_ for rel_ in (p.relative_to(ws).as_posix() for p in dl.walk(ws)) if LEAK.search(dl.read_text(ws / rel_))]
            + [f"text {i}" for i, s in enumerate(said) if LEAK.search(s)])


def test_the_fair_share_workspace_never_says_what_it_tests(scratch, home):
    kit, _ = scratch
    demo = dl.load_demo("fair-share")
    assert LEAK.search(demo.title) and not LEAK.search(" ".join((demo.name, demo.app, demo.not_checked)))
    ws = started(kit, home, "fair-share")
    log = git(ws, "log", "--format=%B", env=clean_env(home))
    graded = npm_test(ws, home)
    assert verdict(graded.stdout) == "FAIL 12/14", graded.stdout
    assert leaks(ws, log, graded.stdout + graded.stderr) == []
    pkg = json.loads(dl.read_text(ws / "package.json"))
    assert pkg["name"] == "fair-share" and pkg["description"] == "Fair Share, a demo from the starter kit"
    assert dl.read_text(ws / "CLAUDE.md").startswith("# Fair Share, a demo from the starter kit\n")
    assert log.startswith("chore: start the Fair Share demo from the starter kit")
    (ws / "NOTES.md").write_text("# Break the verifier\n", encoding="utf-8")   # the plant: the title in a file
    assert leaks(ws, "the verifier agent") == ["NOTES.md", "text 0"]


@pytest.mark.parametrize("folder", ["100%done", "cost$5", "back`tick"])
def test_start_refuses_a_folder_the_test_script_cannot_quote(scratch, home, folder):
    kit, _ = scratch
    ws = home / "demos here" / folder
    r = run(kit, "start.py", "roulette-loom", "--tool", "claude", "--dir", str(ws), home=home)
    assert r.returncode == 2 and "cannot quote" in r.stderr and "Nothing was written" in r.stderr, r.stderr
    assert not (home / "demos here").exists()


# Overclaims a verifier quoted: a local grade cannot be made tamper-proof, so no text may say that copying is always
# caught or that the agent cannot change the launcher's grade. Nor that a Python workspace's code cannot find the
# kit: its own temporary folder, %LOCALAPPDATA% or the user database name the real home, whose install record names
# the clone, and the process list names it too; a workspace that looked it up and ran reference/ got a recordable
# PASS while four texts said "nothing it is given leads there". Nor that Node's permission model lets the workspace's
# code read "nothing of the kit's": a scenario's process could read all of accept/, mutants and their quotes of
# the reference included, while three texts said so. Nor that the workspace's code can make a probe's answers
# wrong "only by doing the work wrong", or that its answer lines are "no longer taken": a planted workspace swapped
# node:fs's writeSync, which probe-child.mjs called by a named import it said was "taken before the freeze", and
# rewrote the probe's own line, while AUTHORING.md said of the node: modules "a scenario observes with none of
# them" (2026-11-21).
OVERCLAIMS = ("copying the reference fails", "but not this", "but not that line", "no copying of the reference",
              "nothing it is given leads", "where no path leads", "where no kit path leads", "no path leads to the kit",
              "nothing of the kit's", "the two probe files, and nothing else", "only by doing the work wrong",
              "no longer taken for the probe's", "taken before the freeze", "a scenario observes with none of them",
              "process the workspace cannot change")


def test_no_text_claims_a_local_grade_is_tamper_proof():
    texts = {f.relative_to(KIT).as_posix(): " ".join(dl.read_text(f).lower().split()) for f in [
        DEMOS / "MEASURING.md", DEMOS / "AUTHORING.md", DEMOS / "start.py", DEMOS / "check.py",
        DEMOS / "acceptkit.py", DEMOS / "demolib.py", DEMOS / "probe.mjs", DEMOS / "probe-child.mjs",
        KIT / "CHANGELOG.md", KIT / "README.md",
        KIT / "core" / "onboarding" / "common" / "06-try-it.md", *sorted(DEMOS.glob("*/BRIEF.md"))]}
    assert [(f, c) for f, t in texts.items() for c in OVERCLAIMS if c in t] == []
    for f in ("demos/MEASURING.md", "core/onboarding/common/06-try-it.md", *(f for f in texts if f.endswith("BRIEF.md"))):
        assert "feedback, not proof" in texts[f] and "re-grade" in texts[f], f
    for name in DEMO_NAMES:   # said to the person, never to the agent: below the brief's watch line
        assert "feedback, not proof" in dl.split_brief(dl.load_demo(name))[1]


# ---- the kit's own demo files ------------------------------------------------------------------------------

@pytest.mark.parametrize("name", DEMO_NAMES)
def test_each_demo_is_complete_and_keeps_to_its_own_rules(name):
    demo = dl.load_demo(name)
    brief, watch = dl.split_brief(demo)
    assert brief.startswith(f"# ") and watch
    assert (demo.dir / "reference").is_dir()
    # start.py writes these at the top; the skeleton's package.json, which it keeps, is held by
    # test_runtimes.test_each_demo_json_and_skeleton_hold, and the checks' imports by
    # test_runtimes.test_node_checks_reach_the_workspace_only_through_the_probe.
    assert not [n for n in ["BRIEF.md", *{v.repo_rules for v in dl.vocab.VOCAB.values()}]
                if (demo.dir / "skeleton" / n).exists()]
    for part in ("skeleton", "reference", "accept"):
        assert check.asset_problems(demo.dir / part) == [], part
    assert check.denylist_problems(demo.dir) == []


# A module that does none of the work and switches the checks off instead: no-op asserts, a Math that finds
# every point near, and constants. Imported into the checks' own process it once passed every check.
SABOTAGE = ("import assert from 'node:assert/strict';\n"
            "for (const k of ['equal', 'ok', 'throws', 'deepEqual', 'match']) assert[k] = () => {};\n"
            "Math.abs = () => 0; Math.hypot = () => 0; Math.max = () => 0; Math.min = () => 0;\n")
CHEATS = {
    "fair-share": ("src/share.js", SABOTAGE + "export const split = (t, n) => Array(n).fill(0), withTip = () => 0;\n"),
    "lanes": ("frontend/render.js", SABOTAGE + "export const escapeHtml = (s) => String(s), renderDifficulty = () => '',"
              " renderTrailRow = () => '', renderBoard = () => '';\n"),
    "monster-tamer-lite": ("src/rng.js", SABOTAGE + "export const createRng = () => ({ s: 0 }), nextFloat = () => 0;\n"),
    "next-word": ("src/lm.js", SABOTAGE + "export const tokenize = () => [], compareEntries = () => 0, train = () => ({}),"
                  " nextDistribution = () => ({});\n"),
    "pocket-region": ("src/map.js", SABOTAGE + "export const tileAt = () => '.', blockedReason = () => null,"
                      " canEnter = () => true;\n"),
    "roulette-loom": ("src/loom.js", SABOTAGE + "export const gcd = () => 1, laps = () => 1, point = () => ({ x: 0, y: 0 });\n"
                      "export const trace = (R, r, d, n) => Array.from({ length: n + 1 }, () => ({ x: 0, y: 0 }));\n"),
    "spin-clash": ("src/physics.js", SABOTAGE + "export const DT = 1 / 60, LIMITS = {}, DEFAULTS = {}, inertia = () => 0;\n"
                   "export const createWorld = () => ({ tops: [] }), collide = () => {}, step = (w) => w;\n"),
    "split-screen-racer": ("src/track.js", SABOTAGE + "export const ROAD_WIDTH = 90, VERGE = 60, buildTrack = () => ({}),"
                           " isValidTrack = () => true;\nexport const fixedTrack = () => ({}), generateTrack = () => ({}),"
                           " surfaceAt = () => 'road';\n"),
    "synesthesia": ("src/analysis.js", SABOTAGE + "export const binFrequency = () => 0, chroma = () => Array(12).fill(0),"
                    " loudness = () => 0, spectralCentroid = () => 0, balance = () => 0, estimateMode = () => null;\n"),
}


@pytest.mark.parametrize("name", sorted(CHEATS))
def test_a_module_that_switches_the_checks_off_gains_nothing(name, tmp_path):
    """The sabotage passes no check that the bare constants fail. Where a scenario runs beside the module, the
    sabotage can change what it observes (a Math that finds every point near), but the asserts stay in the checks'
    own process, so a changed observation can only fail."""
    demo = dl.load_demo(name)
    rel, source = CHEATS[name]
    graded = []
    for code in (source, source.replace(SABOTAGE, "")):
        ws = tmp_path / f"ws{len(graded)}"
        shutil.copytree(str(demo.dir / "skeleton"), str(ws))
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(code, encoding="utf-8")
        graded.append({c.name: c.ok for c in check.run_accept(demo, ws)})
    sabotaged, bare = graded
    assert len(sabotaged) == demo.accept_count, sorted(sabotaged)
    assert [n for n, ok in sabotaged.items() if ok and not bare.get(n)] == []
    assert not all(sabotaged.values())


# What a workspace's code would change to hide a bug from a scenario that observes it in the same process: the
# built-ins a scenario formats, classifies, copies and compares with, node:v8's serializer and node:fs's writeSync,
# which write the answer (a verifier's workspace once hid real bugs from monster-tamer-lite this way; test_runtimes
# has each cheat itself). Each is changed here so that, did it take, every demo's checks would break, and each in a
# try block of its own: probe-child.mjs freezes them all, or holds them itself, before any workspace module loads,
# so none takes. With harden() taken out of probe-child.mjs, this test failed for every demo here (2026-11-19), and
# so it did with writeSync taken by a named import and syncBuiltinESMExports left in (2026-11-21).
TAMPERS = [
    "Number.prototype.toFixed = function () { return '0'; }",
    "Object.defineProperty(Number.prototype, 'toFixed', { value() { return '0'; } })",
    "Object.getPrototypeOf = () => null",
    "Object.defineProperty(Object, 'getPrototypeOf', { value: () => null })",
    "Math.random = () => 0.5",
    "Object.defineProperty(Math, 'random', { value: () => 0.5 })",
    "Math.abs = () => 0",
    "Array.prototype.map = function () { return []; }",
    "Array.prototype.join = function () { return ''; }",
    "Array.prototype.push = function () { return 0; }",
    "Array.prototype.includes = function () { return false; }",
    "Object.defineProperty(Array.prototype, 'forEach', { value() {} })",
    "Array.prototype[Symbol.iterator] = function* () {}",
    "Array.isArray = () => false",
    "JSON.stringify = () => '0'",
    "Object.defineProperty(JSON, 'parse', { value: () => 0 })",
    "Function.prototype.toString = function () { return ''; }",
    "Function.prototype.call = function () {}",
    "Object.keys = () => []",
    "Object.entries = () => []",
    "Object.prototype.hasOwnProperty = () => false",
    "String.prototype.slice = function () { return ''; }",
    "Set.prototype.has = () => false",
    "Map.prototype.get = () => undefined",
    "Number.isFinite = () => false",
    "Promise.prototype.then = function () {}",
    "globalThis.structuredClone = () => ({})",
    "Object.setPrototypeOf(Array.prototype, null)",
    "process.getBuiltinModule('node:v8').Serializer.prototype.writeValue = function () { return true; }",
    "const fs = process.getBuiltinModule('node:fs'); fs.writeSync = (fd, data) => data.length; "
    "process.getBuiltinModule('node:module').syncBuiltinESMExports()",
]
TAMPERED = ("for (const t of [\n" + "".join(f"  () => {{ {t}; }},\n" for t in TAMPERS)
            + "]) { try { t(); } catch { /* frozen */ } }\n")


def tamper(folder: Path, but=None) -> None:
    """Every module of the folder but `but`, with the tampers in front of it: whichever a check loads, they run
    first."""
    for f in sorted(folder.rglob("*")):
        if f.is_file() and f.suffix in (".js", ".mjs") and f != but and not {".git", "node_modules"} & set(f.parts):
            f.write_text(TAMPERED + dl.read_text(f), encoding="utf-8")


@pytest.mark.parametrize("name", PROBED)
def test_a_workspace_that_changes_the_built_ins_passes_no_more_checks(name, tmp_path):
    """The planted bug of PLANTS, an honest wrong answer, with the tampers passes no check it fails without them,
    and the reference with them still passes every check: no tamper took, in any scenario or call of the demo."""
    demo = dl.load_demo(name)
    mutant, fails = PLANTS[name]
    case = next(c for c in mutants.load_cases(demo)[0] if c.id == mutant)
    # A demo's fixture builder makes the workspace's history and is not graded, so it runs as it is.
    builder = Path(demo.fixture).relative_to("reference") if demo.fixture else None

    def tampered(ref: Path) -> None:
        tamper(ref, builder and ref / builder)

    def graded(label: str, case=None, tampers: bool = False) -> list:
        results = check.run_accept(demo, finished(demo, tmp_path / label, case, tampered if tampers else None))
        assert len(results) == demo.accept_count, [c.name for c in results]
        return results

    honest = {c.name for c in graded("honest", case) if c.ok}
    assert fails not in honest
    assert {c.name for c in graded("honest-tampered", case, tampers=True) if c.ok} <= honest
    assert [(c.name, c.detail) for c in graded("reference-tampered", tampers=True) if not c.ok] == []


def test_answers_keep_nan_and_minus_zero_apart_from_null_and_zero(tmp_path):
    """JSON would carry NaN out as null, and a closeness check then reads it as 0."""
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "m.js").write_text("export const nan = () => NaN, mz = () => -0, und = () => undefined;\n"
                                     "export const boom = () => { throw new RangeError('no'); };\n", encoding="utf-8")
    script = (f"import {{ outcomes }} from {json.dumps((DEMOS / 'probe.mjs').as_uri())};\n"
              "const o = outcomes('src/m.js', [['nan'], ['mz'], ['und'], ['boom'], ['absent']]);\n"
              "console.log(JSON.stringify([Number.isNaN(o[0].value), Object.is(o[1].value, -0), 'value' in o[2] "
              "&& o[2].value === undefined, o[3].error.range, o[4].ok]));\n")
    (tmp_path / "t.mjs").write_text(script, encoding="utf-8")
    r = subprocess.run([shutil.which("node"), str(tmp_path / "t.mjs")], cwd=str(tmp_path), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120,
                       env=dict(os.environ, DEMO_WORKSPACE=str(ws)))
    assert r.returncode == 0 and json.loads(r.stdout) == [True, True, True, True, False], r.stdout + r.stderr


def test_held_out_results_must_agree_with_the_runner():
    """The workspace's code runs as the same user as the runner, so it could write forged reporter lines into the
    runner's output from outside. They count only when the real runner also succeeds, and once each."""
    demo = dl.load_demo("fair-share")
    names = [f"check {i}" for i in range(demo.accept_count)]

    def ev(name, ok=True):
        return json.dumps({"demo_event": "test", "ok": ok, "name": name, "nesting": 0, "kind": "test", "file": "f",
                           "error": None if ok else "wrong"})
    forged = "\n".join(ev(n) for n in names)
    assert all(c.ok for c in check.held_out_checks(demo, forged, "", 0))          # what an honest PASS reads as
    for code in (1, None, -9):   # forged, and the real runner failed, was stopped or was killed
        got = check.held_out_checks(demo, forged, "", code)
        assert not got[-1].ok and got[-1].name == "held-out results: the test runner agrees", got[-1]
    twice = forged + "\n" + ev(names[0], ok=False)                                 # a forged pass beside a real fail
    got = check.held_out_checks(demo, twice, "", 1)
    assert not got[-1].ok and "reported more than once: check 0" in got[-1].detail, got[-1]
    garbled = forged + '\n{"demo_event": "test", "ok": tru'
    got = check.held_out_checks(demo, garbled, "", 0)
    assert not got[-1].ok and "not the reporter's" in got[-1].detail, got[-1]


def test_the_kits_own_demo_text_names_no_franchise(tmp_path):
    for f in ("MEASURING.md", "costs.json", "pick.py", "start.py", "check.py"):
        shutil.copy2(str(DEMOS / f), str(tmp_path / f))
    assert check.denylist_problems(tmp_path) == []


def test_tiers_and_ranks_agree():
    assert set(pick.RANK) == set(dl.TIERS) == set(dl.TIER_ORDER)


def test_the_shipped_costs_file_holds_measured_runs_only():
    data = json.loads(dl.read_text(dl.COSTS))
    assert "_about" in data and not any(r.get("synthetic") for r in data["runs"])
    assert len(dl.load_costs(dl.COSTS, strict=True)) == len(data["runs"])


def test_node_side_tests_pass():
    r = subprocess.run([shutil.which("node"), "--test", "--test-reporter=tap", str(DEMOS / "tests" / "npm-test.test.mjs")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                       env=dict(os.environ, DEMO_TEST_PYTHON=sys.executable))
    assert r.returncode == 0 and "# fail 0" in r.stdout and "# skipped 0" in r.stdout, r.stdout + r.stderr


# ---- start.py ----------------------------------------------------------------------------------------------

def test_start_makes_a_repo_with_the_guard_and_one_commit_and_prints_what_to_watch(scratch, home):
    kit, _ = scratch
    r = run(kit, "start.py", "roulette-loom", "--tool", "codex", home=home)
    assert r.returncode == 0, r.stderr
    ws = home / "agent-demos" / "roulette-loom"
    env = clean_env(home)
    assert git(ws, "log", "--format=%s", env=env) == "chore: start the Roulette Loom demo from the starter kit"
    assert git(ws, "status", "--porcelain", env=env) == ""
    hooks = ws / ".git" / "hooks"
    assert all("commit-guard" in dl.read_text(hooks / h) for h in ("pre-commit", "commit-msg", "pre-push"))
    assert (home / ".claude" / "commit-guard" / "guard.py").is_file()   # the scratch HOME's, never the real one
    assert (ws / "AGENTS.md").is_file() and not (ws / "CLAUDE.md").exists()
    brief, watch = dl.split_brief(dl.load_demo("roulette-loom"))
    assert dl.read_text(ws / "BRIEF.md") == brief and dl.WATCH_MARK not in brief
    assert watch.split("\n")[0] in r.stdout and watch.split("\n")[0] not in dl.read_text(ws / "BRIEF.md")
    out = r.stdout
    assert "codex -C '" in out and "In the Codex app, open the folder" in out
    assert "gh repo create roulette-loom --private --source ." in out and "--public" not in out
    assert out.rstrip("\n").split("\n")[-1].startswith("If you are an AI agent: stop here.")
    # The person grades with the launcher, which runs from the kit: the agent can rewrite what `npm test` runs.
    step5 = out.split("\n5. ")[1].split("\n6. ")[0]
    for shell in ("bash:       python ", "PowerShell: python "):
        assert re.search(re.escape(shell) + r".*starter\.py'? demo check roulette-loom --dir '?.*roulette-loom'?$",
                         step5, re.M), step5
    assert "rather than `npm test`" in step5 and "run `npm test` in the folder" not in out
    pkg = json.loads(dl.read_text(ws / "package.json"))
    assert pkg["type"] == "module" and dl.test_script_problem(pkg["scripts"]["test"], "roulette-loom", ws, kit) is None
    assert check.entry_point_problems(ws, "roulette-loom", kit=kit) == []


@pytest.mark.parametrize("tool, rules, opener", [("claude", "CLAUDE.md", "&& claude"),
                                                 ("opencode", "AGENTS.md", "opencode '")])
def test_start_writes_each_tools_rules_file_and_open_line_in_its_own_words(scratch, home, tool, rules, opener,
                                                                          tmp_path_factory):
    kit, _ = scratch
    r = run(kit, "start.py", "fair-share", "--tool", tool, home=home)
    assert r.returncode == 0, r.stderr
    ws = home / "agent-demos" / "fair-share"
    assert (ws / rules).is_file() and opener in r.stdout
    base = tmp_path_factory.getbasetemp()
    ba.check_terms({tool: {"start.txt": masked(r.stdout, base), rules: masked(dl.read_text(ws / rules), base)}},
                   ba.load_terms(), {}, full=False)


def test_start_refuses_without_an_install_recorded_for_the_tool(scratch, tmp_path):
    kit, _ = scratch
    h = tmp_path / "it's home"
    h.mkdir()
    r = run(kit, "start.py", "roulette-loom", "--tool", "claude", home=h)
    assert r.returncode == 2 and "Install the kit for it first" in r.stderr and "--dry-run" in r.stderr
    write_record(h, kit, [])   # an empty record
    r = run(kit, "start.py", "roulette-loom", "--tool", "claude", home=h)
    assert r.returncode == 2 and "no install of the kit is recorded" in r.stderr
    write_record(h, kit, ["codex"])
    r = run(kit, "start.py", "roulette-loom", "--tool", "claude", home=h)
    assert r.returncode == 2 and "not recorded as installed for claude" in r.stderr
    write_record(h, kit, ["cursor"], project=True)   # one repo only is not a global install
    r = run(kit, "start.py", "roulette-loom", "--tool", "cursor", home=h)
    assert r.returncode == 2
    write_record(h, kit, ["claude", "codex"])
    r = run(kit, "start.py", "roulette-loom", home=h)
    assert r.returncode == 2 and "needs --tool" in r.stderr and "--tool codex" in r.stderr
    assert not (h / "agent-demos").exists()


def test_start_refuses_a_folder_that_is_not_empty(scratch, home):
    kit, _ = scratch
    ws = home / "agent-demos" / "roulette-loom"
    ws.mkdir(parents=True)
    (ws / "mine.txt").write_text("keep me", encoding="utf-8")
    r = run(kit, "start.py", "roulette-loom", "--tool", "claude", home=home)
    assert r.returncode == 2 and "is not empty" in r.stderr
    assert sorted(p.name for p in ws.iterdir()) == ["mine.txt"]


def test_start_refuses_a_record_from_another_clone(scratch, home, tmp_path):
    kit, _ = scratch
    write_record(home, tmp_path / "another-clone", ["claude"])
    r = run(kit, "start.py", "roulette-loom", "--tool", "claude", home=home)
    assert r.returncode == 2 and "belongs to the clone at" in r.stderr
    assert not (home / "agent-demos").exists()


def test_start_refuses_with_exit_3_where_it_cannot_write_and_names_its_own_command(scratch, home):
    kit, _ = scratch
    blocker = home / "a-file"
    blocker.write_text("x", encoding="utf-8")
    # The commit guard's data folder under a file: unwritable on every OS.
    r = run(kit, "start.py", "roulette-loom", "--tool", "codex", home=home, COMMIT_GUARD_DIR=str(blocker / "cg"))
    assert r.returncode == 3, r.stderr
    assert "CANNOT WRITE; nothing was written" in r.stderr and "To start this demo, run this in your own terminal" \
        in r.stderr and "demo start roulette-loom --tool codex --dir" in r.stderr
    assert not (home / "agent-demos").exists()
    # In a Codex sandbox it says why in a demo's words, not the installer's (no global config is involved).
    r = run(kit, "start.py", "roulette-loom", "--tool", "codex", home=home, COMMIT_GUARD_DIR=str(blocker / "cg"),
            CODEX_THREAD_ID="x")
    assert r.returncode == 3 and "Codex sandbox (CODEX_THREAD_ID is set)" in r.stderr, r.stderr
    assert start.SANDBOX in r.stderr and "global config" not in r.stderr and "install there" not in r.stderr
    # The demo folder itself where nothing can be made: a read-only HOME on POSIX, a path under a file on Windows.
    if os.name == "nt":
        r = run(kit, "start.py", "roulette-loom", "--tool", "codex", "--dir", str(blocker / "demo"), home=home)
    else:
        os.chmod(str(home), 0o500)
        try:
            r = run(kit, "start.py", "roulette-loom", "--tool", "codex", home=home,
                    COMMIT_GUARD_DIR=str(home.parent / "cg"))
        finally:
            os.chmod(str(home), 0o700)
    assert r.returncode == 3 and "CANNOT WRITE" in r.stderr, r.stderr
    assert not (home / "agent-demos").exists()


def shim_dir(tmp: Path) -> tuple[Path, Path]:
    """A folder of fake package managers that leave a mark when run, and the mark."""
    bin_dir, mark = tmp / "fake-bin", tmp / "package-manager-ran"
    bin_dir.mkdir()
    for pm in ("winget", "brew", "apt", "apt-get", "choco", "scoop"):
        if os.name == "nt":
            (bin_dir / f"{pm}.cmd").write_text(f'@echo ran> "{mark}"\r\n', encoding="utf-8")
        else:
            (bin_dir / pm).write_text(f'#!/bin/sh\necho ran > "{mark}"\n', encoding="utf-8")
            os.chmod(str(bin_dir / pm), 0o755)
    return bin_dir, mark


def path_of(tmp: Path, bin_dir: Path, *tools: str) -> str:
    """A PATH of the fake package managers and `tools` alone. On POSIX each tool is a link in a folder of its own,
    since a distribution's /usr/bin can hold node, git and python side by side; Windows makes links only with a
    privilege, and there each tool's own folder serves (Git's and Node's installers keep them apart). Python
    need not be on it: the scripts run as sys.executable."""
    dirs = [str(bin_dir)]
    if os.name == "nt":
        dirs += [str(Path(shutil.which(t)).parent) for t in tools]
    else:
        links = tmp / "only-these"
        links.mkdir()
        for t in tools:
            os.symlink(shutil.which(t), str(links / t))
        dirs.append(str(links))
    return os.pathsep.join(dirs)


def test_start_without_node_prints_this_oss_command_and_runs_no_package_manager(scratch, home, tmp_path):
    kit, _ = scratch
    bin_dir, mark = shim_dir(tmp_path)
    path = path_of(tmp_path, bin_dir, "git")
    assert shutil.which("node", path=path) is None and shutil.which("git", path=path), path
    r = run(kit, "start.py", "roulette-loom", "--tool", "claude", home=home, PATH=path)
    assert r.returncode == 2, r.stderr
    want = {"win32": "winget install OpenJS.NodeJS.LTS", "darwin": "brew install node"}.get(sys.platform,
                                                                                         "nodejs.org/en/download")
    assert "Node is not installed" in r.stderr and want in r.stderr and "never install anything" in r.stderr
    assert not mark.exists() and not (home / "agent-demos").exists()


def test_start_without_git_refuses_before_writing(scratch, home, tmp_path):
    kit, _ = scratch
    bin_dir, mark = shim_dir(tmp_path)
    path = path_of(tmp_path, bin_dir, "node")
    assert shutil.which("git", path=path) is None and shutil.which("node", path=path), path
    r = run(kit, "start.py", "roulette-loom", "--tool", "claude", home=home, PATH=path)
    assert r.returncode == 2 and "git is not on PATH" in r.stderr, r.stderr
    assert not mark.exists() and not (home / "agent-demos").exists()


PACKAGE_MANAGERS ={"winget", "brew", "apt", "apt-get", "choco", "scoop", "npm", "npx", "pip", "yum", "dnf", "pacman"}


def runs_a_package_manager(source: str) -> list:
    """Each line where a subprocess call starts a package manager, os.system runs anything, or shell=True is used."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name == "system" or any(k.arg == "shell" for k in node.keywords):
            bad.append(node.lineno)
        if name in ("run", "Popen", "call", "check_call", "check_output") and node.args:
            first = node.args[0]
            argv0 = first.elts[0] if isinstance(first, ast.List) and first.elts else first
            if isinstance(argv0, ast.Constant) and str(argv0.value).split()[0] in PACKAGE_MANAGERS:
                bad.append(node.lineno)
    return bad


def test_no_demo_script_runs_a_package_manager():
    assert runs_a_package_manager('import subprocess\nsubprocess.run(["winget", "install", "x"])\n') == [2]
    assert runs_a_package_manager('import os\nos.system("brew install node")\n') == [2]
    for p in DEMOS.glob("*.py"):
        assert runs_a_package_manager(dl.read_text(p)) == [], p.name


# ---- check.py ----------------------------------------------------------------------------------------------

def test_npm_test_grades_a_fresh_skeleton_as_fail_with_a_recordable_record(scratch, home):
    kit, _ = scratch
    ws = started(kit, home, "roulette-loom")
    r = npm_test(ws, home)
    assert r.returncode != 0, r.stdout
    assert verdict(r.stdout) == "FAIL 5/15" and "NOT CHECKED: the drawing" in r.stdout
    assert check.LOCAL_GRADE in r.stdout and "not proof" in check.LOCAL_GRADE and "CI re-grades" in check.LOCAL_GRADE
    rec = record_line(r.stdout)
    assert re.match(r"RECORD: Verified: npm test \(demo check roulette-loom, a local grade: feedback, not proof\) "
                    r"-> FAIL 5/15 \[", rec), rec
    assert f"kit_sha={git(kit, 'rev-parse', 'HEAD')}" in rec and "recordable=yes" in rec
    tree = dl.grading_tree("roulette-loom", "HEAD", kit=kit)
    assert f"accept_hash={tree}" in rec
    guard = importlib.util.spec_from_file_location("g", str(install.GUARD))
    g = importlib.util.module_from_spec(guard)
    guard.loader.exec_module(g)
    assert g.VERIFIED_RE.match(rec[len("RECORD: "):]), "the RECORD is not a Verified: trailer the guard accepts"


def test_npm_test_passes_a_working_build_end_to_end(scratch, home):
    kit, _ = scratch
    ws = started(kit, home, "roulette-loom")
    paraphrase(kit / "demos/roulette-loom/reference/src/loom.js", ws / "src" / "loom.js")
    r = npm_test(ws, home)
    assert r.returncode == 0, r.stdout + r.stderr
    assert verdict(r.stdout) == "PASS 15/15" and "recordable=yes" in record_line(r.stdout)


def test_copying_the_reference_fails_and_the_rest_still_reports(scratch, home):
    kit, _ = scratch
    ws = started(kit, home, "roulette-loom")
    shutil.copytree(str(kit / "demos/roulette-loom/reference"), str(ws), dirs_exist_ok=True)
    r = run(kit, "check.py", "roulette-loom", home=home, cwd=ws)
    assert r.returncode == 1 and verdict(r.stdout) == "FAIL 14/15", r.stdout
    assert re.search(r"FAIL  rule: not copied from the kit's reference solution: \d+ lines match", r.stdout)


def test_copy_detection_counts_more_than_ten_long_lines_that_only_the_reference_holds(tmp_path, monkeypatch):
    fake = tmp_path / "demos" / "fake"
    (fake / "reference").mkdir(parents=True)
    (fake / "skeleton").mkdir()
    lines = [f"const value{i} = computeSomething({i}, 'long enough');" for i in range(12)]
    (fake / "reference" / "a.js").write_text("\n".join(lines + ["x = 1;"]) + "\n", encoding="utf-8")
    (fake / "skeleton" / "a.js").write_text(lines[11] + "\n", encoding="utf-8")   # shipped lines never count
    (fake / "BRIEF.md").write_text("# Fake\n", encoding="utf-8")
    monkeypatch.setattr(dl, "DEMOS", tmp_path / "demos")
    demo = dl.Demo("fake", "Fake", "Fake", "S", "node", "s", "k", "n", 1)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.js").write_text("\n".join(lines[:10] + ["x = 1;", lines[11]]) + "\n", encoding="utf-8")
    assert check.copy_problems(ws, demo) == []                       # ten: allowed
    (ws / "b.js").write_text(f"  {lines[10]}   \n", encoding="utf-8")   # spacing does not hide a line
    assert check.copy_problems(ws, demo) and "11 lines match" in check.copy_problems(ws, demo)[0]


@pytest.mark.parametrize("plant, where", [
    (lambda ws: (ws / "Makefile").write_text("test:\n\tnode --test\n", encoding="utf-8"), "Makefile"),
    (lambda ws: ((ws / ".github" / "workflows").mkdir(parents=True),
                 (ws / ".github" / "workflows" / "ci.yml").write_text("on: push\n", encoding="utf-8")), ".github"),
    (lambda ws: (ws / "justfile").write_text("test:\n  node --test\n", encoding="utf-8"), "justfile"),
    (lambda ws: rewrite_scripts(ws, lambda s: dict(s, **{"test:unit": "node --test"})), "test:unit"),
    (lambda ws: rewrite_scripts(ws, lambda s: {"test": "node --test"}), "`test` must stay"),
    (lambda ws: ((ws / "tools").mkdir(), (ws / "tools" / "package.json").write_text(
        '{"scripts": {"unit-test": "node --test"}}\n', encoding="utf-8")), "tools/package.json: another test script"),
    (lambda ws: (ws / ".npmrc").write_text("script-shell=fake.cmd\n", encoding="utf-8"), ".npmrc: npm settings"),
    # The verifier's lookalike: the same shape, pointing at a fake launcher in the workspace.
    (lambda ws: rewrite_scripts(ws, lambda s: {"test": 'node "fake/npm-test.mjs" "python" "fake/starter.py" demo check '
                                                       'roulette-loom'}), "by a relative path"),
    (lambda ws: rewrite_scripts(ws, lambda s: {"test": dl.workspace_test_script("roulette-loom", ws / "fake",
                                                                                 sys.executable)}), "not this kit's"),
    (lambda ws: rewrite_scripts(ws, lambda s: {"test": dl.workspace_test_script("roulette-loom", dl.KIT,
                                                                                 str(ws / "python.exe"))}),
     "inside the workspace"),
    (lambda ws: rewrite_scripts(ws, lambda s: {"test": dl.workspace_test_script("roulette-loom", dl.KIT,
                                                                                 str(ws.parent / "fake.cmd"))}),
     "not an absolute path to a python program"),
    (lambda ws: rewrite_scripts(ws, lambda s: {"test": dl.workspace_test_script("fair-share", dl.KIT,
                                                                                 sys.executable)}), "not the shape"),
])
def test_a_second_test_entry_point_breaks_the_rule(scratch, home, plant, where, monkeypatch):
    kit, _ = scratch
    ws = started(kit, home, "roulette-loom")
    monkeypatch.setattr(dl, "KIT", kit)   # the workspace's `test` names the scratch kit, which made it
    assert check.entry_point_problems(ws, "roulette-loom") == []
    plant(ws)
    probs = check.entry_point_problems(ws, "roulette-loom")
    assert probs and where in " ".join(probs), probs


def rewrite_scripts(ws: Path, change) -> None:
    pkg = json.loads(dl.read_text(ws / "package.json"))
    pkg["scripts"] = change(pkg["scripts"])
    (ws / "package.json").write_text(json.dumps(pkg), encoding="utf-8")


def wrapped_base64(chars: int, width: int) -> bytes:
    """A JS module holding `chars` characters of base64 as string literals of `width` each, joined at run time:
    `base64 sprite.png` pasted into code, as MIME wraps it."""
    import base64
    data = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 20).decode()[:chars]
    pieces = [data[i:i + width] for i in range(0, len(data), width)]
    return ("export const sprite = [\n" + ",\n".join(f"  '{p}'" for p in pieces) + "\n].join('');\n").encode()


@pytest.mark.parametrize("name, content, why", [
    ("logo.png", b"\x89PNG\r\n\x1a\n", "an image file"),
    ("icon.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "an image file"),
    ("chime.ogg", b"OggS", "an audio file"),
    ("face.woff2", b"wOF2", "a font file"),
    ("page.css", b"body { background: url(data:image/png;base64,AAAA) }", "data: URL"),
    ("blob.js", b"export const blob = '" + b"QUJD" * 300 + b"';", "base64 over 1 KB (1200 characters, line 1)"),
    ("sprite.js", wrapped_base64(4012, 76), "base64 over 1 KB (4012 characters, lines 2-54)"),
    ("joined.js", b"const s = '" + b"QUJD" * 100 + b"' + '" + b"QUJD" * 100 + b"' + '" + b"QUJD" * 100 + b"';",
     "base64 over 1 KB (1200 characters, line 1)"),
    ("raw.bin", b"\x00\x01\x02", "binary content"),
])
def test_binary_assets_break_the_rule(tmp_path, name, content, why):
    (tmp_path / "ok.js").write_text("export const x = 1;\n", encoding="utf-8")
    assert check.asset_problems(tmp_path) == []
    (tmp_path / name).write_bytes(content)
    probs = check.asset_problems(tmp_path)
    assert len(probs) == 1 and why in probs[0], probs


def test_base64_under_1_kb_and_lines_that_only_look_like_it_pass(tmp_path):
    (tmp_path / "small.js").write_bytes(wrapped_base64(988, 76))            # 13 lines of 76: under 1 KB
    hashes = "\n".join(f"const v{i} = 1; // {'ab12' * 10}" for i in range(40))   # 40 runs, not one block
    (tmp_path / "hashes.js").write_text(hashes.replace("\n", "\n\n"), encoding="utf-8")
    (tmp_path / "words.js").write_text("\n".join(["const someWhatLongIdentifierName = anotherOne + 1;"] * 60),
                                       encoding="utf-8")
    assert check.asset_problems(tmp_path) == []
    (tmp_path / "small.js").write_bytes(wrapped_base64(1064, 76))           # one more line: over
    assert [p.split(":")[0] for p in check.asset_problems(tmp_path)] == ["small.js"]


def test_allow_assets_grades_but_marks_the_record_not_recordable(scratch, home):
    kit, _ = scratch
    ws = started(kit, home, "roulette-loom")
    (ws / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    r = run(kit, "check.py", "roulette-loom", home=home, cwd=ws)
    assert "FAIL  rule: no binary assets: logo.png: an image file" in r.stdout
    r = run(kit, "check.py", "roulette-loom", "--allow-assets", home=home, cwd=ws)
    assert "ok    rule: no binary assets (waived by --allow-assets)" in r.stdout
    assert "recordable=no:allow-assets" in record_line(r.stdout)


@pytest.mark.parametrize("text", ["A Spirograph clone", "Catch a Pokémon!", "throw a poke-ball", "SPIROGRAPHS",
                                  "Let it rip!", "the Pokedex", "<!-- inspired by SPIRO-GRAPHS -->", "Spiro Graph",
                                  "spiro_graph", "a Poke-mon", "letitrip"])
def test_franchise_names_break_the_originality_rule(tmp_path, text):
    (tmp_path / "ok.md").write_text("Roulette Loom draws hypotrochoids with a rolling circle.\n", encoding="utf-8")
    assert check.denylist_problems(tmp_path) == []
    (tmp_path / "bad.md").write_text(f"line one\n{text}\n", encoding="utf-8")
    probs = check.denylist_problems(tmp_path)
    assert len(probs) == 1 and probs[0].startswith("bad.md:2:"), probs


def test_check_refuses_while_the_grading_files_differ_from_the_kits_last_commit(scratch, home):
    kit, env = scratch
    ws = started(kit, home, "fair-share")
    accept = kit / "demos/fair-share/accept/share.test.mjs"
    original = accept.read_bytes()
    planted = kit / "demos/fair-share/accept/extra.test.mjs"
    try:
        accept.write_bytes(original.replace(b"[1, 0, 0]", b"[0, 0, 0]"))   # an edited check
        r = run(kit, "check.py", "fair-share", home=home, cwd=ws)
        assert r.returncode == 2 and "differ from the kit's last commit" in r.stderr and r.stdout == ""
        # Named whole: porcelain's first entry starts with a space (" M"), which a strip of the output once cut.
        assert "(demos/fair-share/accept/share.test.mjs)" in r.stderr, r.stderr
        r = run(kit, "check.py", "fair-share", "--allow-modified-accept", home=home, cwd=ws)
        assert r.returncode == 1 and "recordable=no:allow-modified-accept" in record_line(r.stdout)
        accept.write_bytes(original)
        planted.write_text("import { test } from 'node:test';\ntest('free pass', () => {});\n", encoding="utf-8")
        r = run(kit, "check.py", "fair-share", home=home, cwd=ws)   # an added, untracked check
        assert r.returncode == 2 and "extra.test.mjs" in r.stderr
    finally:
        accept.write_bytes(original)
        planted.unlink(missing_ok=True)
    r = run(kit, "check.py", "fair-share", home=home, cwd=ws)
    assert r.returncode == 1 and verdict(r.stdout) == "FAIL 12/14" and "recordable=yes" in record_line(r.stdout)


def test_check_refuses_a_record_from_another_clone_and_a_folder_that_is_no_workspace(scratch, home, tmp_path):
    kit, _ = scratch
    ws = started(kit, home, "roulette-loom")
    write_record(home, tmp_path / "another-clone", ["claude"])
    r = run(kit, "check.py", "roulette-loom", home=home, cwd=ws)
    assert r.returncode == 2 and "belongs to the clone at" in r.stderr
    r = run(kit, "check.py", "roulette-loom", home=home, cwd=tmp_path)
    assert r.returncode == 2 and "not a demo workspace" in r.stderr
    r = run(kit, "check.py", "no-such-demo", home=home, cwd=ws)
    assert r.returncode == 2 and "no demo called" in r.stderr


def test_grading_tree_is_the_committed_tree_until_a_grading_file_changes(scratch):
    kit, _ = scratch
    assert dl.grading_tree("roulette-loom", kit=kit) == dl.grading_tree("roulette-loom", "HEAD", kit=kit)
    assert dl.grading_tree("roulette-loom", "HEAD", kit=kit) != dl.grading_tree("fair-share", "HEAD", kit=kit)
    denylist = kit / "demos" / "denylist.txt"
    original = denylist.read_bytes()
    try:
        denylist.write_bytes(original + b"\nAnother Term\n")
        assert dl.grading_tree("roulette-loom", kit=kit) != dl.grading_tree("roulette-loom", "HEAD", kit=kit)
    finally:
        denylist.write_bytes(original)


def store_state(kit: Path) -> list:
    """Every file in the clone's object store and its index, with sizes: what hashing must leave as it was."""
    git_dir = kit / ".git"
    return sorted((str(p.relative_to(git_dir)), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in [*(git_dir / "objects").rglob("*"), git_dir / "index"] if p.is_file())


def test_hashing_the_grading_files_writes_nothing_to_the_clone(scratch, home):
    kit, _ = scratch
    accept = kit / "demos/fair-share/accept/share.test.mjs"
    planted = kit / "demos/fair-share/accept/planted.test.mjs"
    original = accept.read_bytes()
    before = store_state(kit)
    try:
        accept.write_bytes(original + b"// an edit with content no object in the store holds\n")
        planted.write_text("// a planted check, new to the store\n", encoding="utf-8")
        now, why = dl.hash_grading("fair-share", kit=kit)
        head, why_head = dl.hash_grading("fair-share", "HEAD", kit=kit)
        assert now and head and now != head, (why, why_head)
        assert dl.changed_graders("fair-share", kit=kit) == [
            "demos/fair-share/accept/share.test.mjs", "demos/fair-share/accept/planted.test.mjs"]
        assert store_state(kit) == before
    finally:
        accept.write_bytes(original)
        planted.unlink(missing_ok=True)


def test_check_grades_a_clone_whose_object_store_it_cannot_write(scratch, home):
    """A session that can write only the demo's folder, or a read-only clone: check.py still grades. POSIX only,
    where a folder can be made read-only for its owner; the test above holds on every OS."""
    kit, _ = scratch
    ws = started(kit, home, "roulette-loom")
    if os.name == "nt":
        assert store_state(kit)   # the store is there to be left alone; Windows cannot lock it for its owner
        return
    store = kit / ".git" / "objects"
    dirs = [store, *(p for p in store.rglob("*") if p.is_dir())]
    for d in dirs:
        os.chmod(str(d), 0o555)
    try:
        r = run(kit, "check.py", "roulette-loom", home=home, cwd=ws)
    finally:
        for d in dirs:
            os.chmod(str(d), 0o755)
    assert r.returncode == 1 and verdict(r.stdout) == "FAIL 5/15", r.stdout + r.stderr
    assert "recordable=yes" in record_line(r.stdout) and "differ" not in r.stderr


def test_a_hash_git_cannot_make_is_refused_as_that_not_as_a_difference(scratch, monkeypatch):
    kit, _ = scratch
    tree, why = dl.hash_grading("roulette-loom", "0" * 40, kit=kit)
    assert tree is None and why.startswith("git ls-tree: fatal:"), why
    demo = dl.load_demo("roulette-loom")
    monkeypatch.setattr(dl, "load_record_or_none", lambda: ({"kit": {"kit_root": str(dl.KIT)}}, None))
    monkeypatch.setattr(dl, "head_sha", lambda kit=dl.KIT: "a" * 40)
    monkeypatch.setattr(dl, "hash_grading", lambda name, rev=None, kit=dl.KIT: (None, "git add: fatal: no room"))
    said = check.kit_refusal(demo, False, [])
    assert said.startswith("cannot hash the files that grade this demo (git add: fatal: no room)"), said
    assert "differ" not in said and "Restore or commit" not in said
    reasons = []
    assert check.kit_refusal(demo, True, reasons) is None and reasons == ["allow-modified-accept"]


def test_the_launcher_forwards_demo_verbs_and_their_exit_codes(scratch, home):
    kit, _ = scratch
    env = clean_env(home)
    launch = [sys.executable, str(kit / "scripts" / "starter.py")]
    r = subprocess.run([*launch, "demo", "check", "no-such-demo"], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 2 and "no demo called" in r.stderr
    r = subprocess.run([*launch, "demo", "bogus"], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 2 and "demo start" in r.stderr


# ---- pick.py -----------------------------------------------------------------------------------------------

def plan(tool: str, plan_id: str) -> dict:
    return dl.plan_row(tool, plan_id)


def row(**over) -> dict:
    r = {"demo": "roulette-loom", "tool": "claude", "plan": "max", "model": "model-a", "effort": "high",
         "tool_version": "1.0.0", "kit_sha": "a" * 40, "accept_hash": "b" * 40, "workspace": "runs/a-run.bundle",
         "workspace_sha": "c" * 40, "date": date.today().isoformat(),
         "mode": "interactive", "meter_delta": {"weekly_pct": 3}, "tokens": 120000, "wall_min": 25, "sessions": 1,
         "accept": "PASS 15/15", "claimed_done": True, "verifier": "ran", "checkpoint": "ran", "no_commit": False,
         "synthetic": True}
    r.update(over)
    return r


MAX_ROWS = [row(), row(meter_delta={"weekly_pct": 4.5}), row(meter_delta={"weekly_pct": 9}, accept="FAIL 11/14")]


def outputs(rows: list, tool: str, plan_id, model=None, budgets=("5", "$0", "nothing", "not sure", "40")) -> list:
    p = plan(tool, plan_id) if plan_id else None
    demos = dl.all_demos()
    return ["\n".join(pick.question(demos, rows, tool, p, model))] + [
        "\n".join(pick.menu(demos, rows, tool, p, model, b, date.today())) for b in budgets]


def no_numbers(texts: list) -> None:
    for t in texts:
        assert not NUMBER.search(t), NUMBER.search(t).group(0) + " in:\n" + t


def test_a_cell_with_no_runs_prints_no_number_even_beside_a_measured_one(monkeypatch):
    texts = outputs(MAX_ROWS, "claude", "pro")
    no_numbers(texts)
    assert "Not measured yet on Claude Code (Pro)." in texts[1] and "Start with a small demo: Roulette Loom" in texts[1]
    shown = outputs(MAX_ROWS, "claude", "max")   # the measured cell does show its numbers
    assert "3–9% of a weekly limit over 3 runs" in shown[1] and "1 of 3 failed the held-out check" in shown[1]
    # The plant: a lookup that ignores the plan key leaks Max's runs into Pro's menu, and the check catches it.
    monkeypatch.setattr(pick, "cell_runs", lambda rows, tool, plan_id, demo: [
        r for r in rows if r["tool"] == tool and r["demo"] == demo])
    with pytest.raises(AssertionError):
        no_numbers(outputs(MAX_ROWS, "claude", "pro"))


def test_a_failed_run_counts_toward_the_worst_case():
    text = outputs(MAX_ROWS, "claude", "max", budgets=("10",))[1]
    assert "at least 14% of your week is left; if `/usage` shows less, pick smaller" in text
    text = outputs(MAX_ROWS, "claude", "max", budgets=("6",))[1]
    assert "No measured demo's costliest run fits your answer; the cheapest is Roulette Loom, at most 9%" in text


def every_cell():
    plans = dl.plans()
    for tool in sorted(dl.vocab.VOCAB):
        for p in plans.get(tool) or [None]:
            yield tool, p["id"] if p else None


@pytest.mark.parametrize("tool, plan_id", list(every_cell()))
def test_pick_speaks_only_its_own_tools_words(tool, plan_id):
    texts = outputs([], tool, plan_id)
    if plan_id:
        texts.append("\n".join(pick.choose_plan(tool, dl.plans()[tool], None)))
    ba.check_terms({tool: {"pick.txt": masked("\n\n".join(texts))}}, ba.load_terms(), {}, full=False)


@pytest.mark.parametrize("tool, plan_id", list(every_cell()))
def test_a_plans_label_is_a_name_in_brackets_never_part_of_a_sentence(tool, plan_id):
    """"on A local model through Ollama" and "with API key you pay" once came from dropping the label in."""
    measured = [row(tool=tool, plan=plan_id, meter_delta={"weekly_pct": 3, "usd": 1.5})] if plan_id else []
    texts = outputs([], tool, plan_id) + outputs(measured, tool, plan_id)
    if plan_id is None:
        # No plan says how this tool bills, so nothing may frame it as a local model: the question's own dollars.
        assert all("minutes" not in t for t in texts) and "Answer in dollars" in texts[0], texts[0]
        return
    label = plan(tool, plan_id)["label"]
    for t in texts:
        for lead in ("on ", "On ", "with ", "With "):
            assert lead + label not in t, (lead + label, t)
    assert f"{dl.vocab.VOCAB[tool].name} ({label})" in texts[0]


def test_the_term_check_on_pick_output_fires_on_another_tools_plan():
    codex = masked("\n".join(outputs([], "codex", "plus"))) + "\nPick Max 20x if you can.\n"
    with pytest.raises(SystemExit, match="codex/pick.txt"):
        ba.check_terms({"codex": {"pick.txt": codex}}, ba.load_terms(), {}, full=False)
    opencode = masked("\n".join(outputs([], "opencode", "openai-chatgpt"))) + "\nSigned in with ChatGPT Plus.\n"
    ba.check_terms({"opencode": {"pick.txt": opencode}}, ba.load_terms(), {}, full=False)


def test_masked_takes_out_a_path_that_names_a_tool_and_leaves_the_kits_words(tmp_path):
    root = tmp_path / "Temp" / "claude" / "it's"
    spelled = [str(root), root.as_posix(), shlex.quote(str(root)), shlex.quote(root.as_posix()),
               install._ps_quote(str(root))]
    text = "".join(f"open {s}\n" for s in spelled) + "then run claude --continue\n"

    def problems(t: str) -> list:
        try:
            ba.check_terms({"opencode": {"t.txt": t}}, ba.load_terms(), {}, full=False)
        except SystemExit as e:
            return [ln.split(":")[1] for ln in str(e).splitlines() if ln.startswith("  opencode/t.txt:")]
        return []

    assert set(problems(text)) > {str(len(spelled) + 1)}   # each spelling of the path is flagged, unmasked
    assert set(problems(masked(text, root))) == {str(len(spelled) + 1)}


FREE_WORDS = re.compile(r"\$0\b|no extra dollars|no dollars|\bfree\b|costs nothing", re.I)


# Written here, not read from pick.CREDITS, so a change there cannot pass by changing what it is held to.
CREDITS_CLAUSE = {"possible": "unless you have credits turned on", "unknown": "is unconfirmed", "n/a": ""}


def credits_clause_problems(texts: list, p: dict) -> list:
    return [t for t in texts if FREE_WORDS.search(t) and CREDITS_CLAUSE[p["pay_past_limit"]] not in t]


@pytest.mark.parametrize("tool, plan_id", [(t, p) for t, p in every_cell()
                                           if p and plan(t, p)["meter"] == "share"])
def test_no_subscription_output_says_no_dollars_without_the_credits_clause(tool, plan_id):
    p = plan(tool, plan_id)
    texts = outputs([], tool, plan_id) + outputs([row(tool=tool, plan=plan_id)], tool, plan_id)
    assert credits_clause_problems(texts, p) == []
    assert any(FREE_WORDS.search(t) for t in texts)   # the check has something to check


def test_dropping_the_credits_clause_is_caught(monkeypatch):
    p = dict(plan("codex", "plus"))
    assert p["pay_past_limit"] == "possible"
    want = pick.CREDITS["possible"]
    monkeypatch.setitem(pick.CREDITS, "possible", "no extra dollars")   # the plant: the clause dropped
    assert credits_clause_problems(outputs([], "codex", "plus"), p)
    monkeypatch.setitem(pick.CREDITS, "possible", want)
    assert credits_clause_problems(outputs([], "codex", "plus"), p) == []


@pytest.mark.parametrize("which", ["question", "menu", "choose_plan"])
def test_every_pick_turn_ends_on_the_agent_stop_line(which):
    demos, p = dl.all_demos(), plan("codex", "plus")
    if which == "question":
        lines = pick.question(demos, [], "codex", p, None)
        want = install.stop_line("this question word for word", pick.run_cmd(
            pick.next_words("codex", "plus", None) + ["--budget", "<answer>"]) + ", with their answer in place of <answer>,")
    elif which == "menu":
        lines = pick.menu(demos, [], "codex", p, None, "5", date.today())
        want = install.stop_line("this menu word for word, ask which demo they want", pick.run_cmd(
            ["demo", "start", "<demo>", "--tool", "codex"]) + ", with the demo they chose in place of <demo>,")
    else:
        lines = pick.choose_plan("codex", dl.plans()["codex"], None)
        want = install.stop_line("this list word for word, ask which plan they are on", "Run the line for their plan")
    assert lines[-1] == want
    assert want.startswith("If you are an AI agent: stop here. Show the user ") and want.endswith(" only after they reply.")


@pytest.mark.parametrize("unanswered", [False, True])
def test_the_installers_stop_line_reads_as_it_did(monkeypatch, unanswered):
    import argparse
    # Pinned word for word: install.stop_line is shared with demo pick, so a change made for one shows
    # here. The guard question asks for a project folder, never a repo (beginners had none). The notice
    # question is added while the install record holds no answer, so that is pinned both ways.
    monkeypatch.setattr(install, "notices_unanswered", lambda: unanswered)
    folder = ("which project folder they work in, for the commit guard (one that is not a git repo yet is made "
              "one; no folder yet: suggest ~/projects/<name>), or none")
    tail = "; also ask whether they want a notice when a new kit version is out (recommend yes)" if unanswered else ""
    for tool, ask in (("claude", "ask " + folder),
                      ("codex", "ask which tier (starter or full) and " + folder)):
        assert install.agent_stop_line(argparse.Namespace(tool=tool)) == (
            f"If you are an AI agent: stop here. Show the user this plan, {ask}{tail}, and end your turn. "
            "Run with --yes only after they reply.")


def test_runs_measured_on_another_model_or_long_ago_say_so(monkeypatch):
    rows = [row(), row(date=(date.today() - timedelta(days=91)).isoformat(), meter_delta={"weekly_pct": 50})]
    text = "\n".join(pick.menu(dl.all_demos(), dl.recent(rows, date.today()), "claude", plan("claude", "max"),
                               "model-b", "5", date.today()))
    assert "3% of a weekly limit over 1 run" in text and "50%" not in text
    assert "Measured on model-a, not yours." in text
    reviewed = dl.models_reviewed()
    later = "\n".join(pick.menu(dl.all_demos(), rows[:1], "claude", plan("claude", "max"), None, "5",
                                reviewed + timedelta(days=40)))
    assert "MODELS.md was last reviewed on" in later
    soon = "\n".join(pick.menu(dl.all_demos(), rows[:1], "claude", plan("claude", "max"), None, "5", reviewed))
    assert "MODELS.md" not in soon


def test_an_api_key_plan_picks_the_largest_demo_whose_worst_run_fits():
    rows = [row(tool="codex", plan="api", meter_delta={"usd": 0.8}),
            row(tool="codex", plan="api", demo="fair-share", meter_delta={"usd": 1.5})]
    p = plan("codex", "api")
    text = "\n".join(pick.menu(dl.all_demos(), rows, "codex", p, None, "$2", date.today()))
    assert "The largest demo whose costliest run fits your answer is Break the verifier, at most $1.50." in text
    text = "\n".join(pick.menu(dl.all_demos(), rows, "codex", p, None, "$1", date.today()))
    assert "is Roulette Loom, at most $0.80" in text


@pytest.mark.parametrize("answer, want", [("$5", 5.0), ("5%", 5.0), ("about 12.5 percent", 12.5), ("nothing", 0.0),
                                          ("zero", 0.0), ("not sure", None), ("", None)])
def test_budget_answers_are_read_as_numbers(answer, want):
    assert pick.parse_budget(answer) == want


def test_pick_command_line(scratch, home, tmp_path):
    kit, _ = scratch
    r = run(kit, "pick.py", "--tool", "codex", home=home)
    assert r.returncode == 2 and "Which Codex plan is this on?" in r.stdout and "--plan plus" in r.stdout
    r = run(kit, "pick.py", "--tool", "codex", "--plan", "max", home=home)
    assert r.returncode == 2 and "not a codex plan" in r.stderr
    r = run(kit, "pick.py", "--tool", "cursor", "--plan", "pro", home=home)
    assert r.returncode == 2 and "leave out --plan" in r.stderr
    r = run(kit, "pick.py", "--tool", "codex", "--plan", "plus", home=home)
    assert r.returncode == 0 and r.stdout.startswith("How many dollars do you want to spend on this?")
    assert "not been measured yet on Codex (ChatGPT Plus)" in r.stdout
    costs = tmp_path / "costs.json"
    costs.write_text(json.dumps({"runs": MAX_ROWS}), encoding="utf-8")
    r = run(kit, "pick.py", "--tool", "claude", "--plan", "max", "--budget", "5", "--costs", str(costs), home=home)
    assert r.returncode == 0 and "3–9% of a weekly limit" in r.stdout and "Synthetic test runs" in r.stdout
    costs.write_text(json.dumps({"runs": [row(plan="plus")]}), encoding="utf-8")   # not a Claude Code plan
    r = run(kit, "pick.py", "--tool", "claude", "--plan", "max", "--costs", str(costs), home=home)
    assert r.returncode == 1 and "plan 'plus' is not a claude plan" in r.stderr and r.stdout == ""


# ---- costs.json admission ----------------------------------------------------------------------------------

@pytest.fixture
def measured(scratch, tmp_path):
    """(a row the kit admits, the workspace's first commit): a Roulette Loom workspace that passes, committed and
    bundled into the scratch kit's demos/runs/ as a measured run's workspace is."""
    kit, env = scratch
    h = tmp_path / "it's home"
    h.mkdir()
    write_record(h, kit, ["claude"])
    ws = started(kit, h, "roulette-loom")
    wenv = clean_env(h)
    skeleton = git(ws, "rev-parse", "HEAD", env=wenv)
    paraphrase(kit / "demos/roulette-loom/reference/src/loom.js", ws / "src" / "loom.js")
    done = commit_all(ws, "feat: draw the curves", wenv)
    bundle = kit / "demos" / "runs" / "loom-test.bundle"
    bundle.parent.mkdir(exist_ok=True)
    git(ws, "bundle", "create", str(bundle), "--all", env=wenv)
    sha = git(kit, "rev-parse", "HEAD", env=env)
    good = row(kit_sha=sha, accept_hash=dl.grading_tree("roulette-loom", sha, kit=kit),
               workspace="runs/loom-test.bundle", workspace_sha=done)
    del good["synthetic"]
    try:
        yield good, skeleton
    finally:
        bundle.unlink()


def test_a_measured_run_is_admitted_only_with_the_kits_committed_checks(scratch, tmp_path, measured):
    kit, _ = scratch
    good, _ = measured
    sha = good["kit_sha"]
    costs = tmp_path / "costs.json"

    def load(*rows):
        costs.write_text(json.dumps({"runs": list(rows)}), encoding="utf-8")
        return dl.load_costs(costs, strict=True, kit=kit)

    assert load(good) == [good]
    with pytest.raises(dl.CostsError, match="is not the grading tree"):
        load(dict(good, accept_hash="c" * 40))
    with pytest.raises(dl.CostsError, match="not the grading tree"):   # another demo's checks
        load(dict(good, accept_hash=dl.grading_tree("fair-share", sha, kit=kit)))
    with pytest.raises(dl.CostsError, match="not reachable from origin/main"):
        load(dict(good, kit_sha="d" * 40))
    with pytest.raises(dl.CostsError, match="k is at most n"):
        load(dict(good, accept="PASS 13/14"))
    with pytest.raises(dl.CostsError, match="needs 'weekly_pct'"):
        load(dict(good, meter_delta={"usd": 1}))
    with pytest.raises(dl.CostsError, match="workspace is the run's git bundle"):
        load(dict(good, workspace="../elsewhere.bundle"))


def test_ci_re_grades_the_committed_workspace_before_it_admits_a_run(scratch, tmp_path, measured):
    """A local grade is feedback, so the RECORD a run came with is not enough: the workspace as committed must earn
    the row's verdict again, from a clean copy of the kit at kit_sha. The plant: the row's PASS on the skeleton."""
    kit, _ = scratch
    good, skeleton = measured
    costs = tmp_path / "costs.json"

    def load(r):
        costs.write_text(json.dumps({"runs": [r]}), encoding="utf-8")
        return dl.load_costs(costs, strict=True, kit=kit)

    assert load(good) == [good]
    with pytest.raises(dl.CostsError, match=r"the committed workspace \(\w+\) gives FAIL 5/15, not the row's PASS 15/15"):
        load(dict(good, workspace_sha=skeleton))
    with pytest.raises(dl.CostsError, match="is not in the kit, so CI cannot re-grade it"):
        load(dict(good, workspace="runs/missing.bundle"))
    with pytest.raises(dl.CostsError, match="git checkout"):
        load(dict(good, workspace_sha="e" * 40))
    costs.write_text(json.dumps({"runs": [dict(good, workspace_sha=skeleton)]}), encoding="utf-8")
    assert dl.load_costs(costs, kit=kit)   # pick.py on a user's machine reads what CI admitted; it does not re-grade


def test_a_synthetic_run_is_refused_in_the_kits_own_costs_file(scratch):
    kit, _ = scratch
    shipped = kit / "demos" / "costs.json"
    original = shipped.read_bytes()
    try:
        shipped.write_text(json.dumps({"runs": [row()]}), encoding="utf-8")
        with pytest.raises(dl.CostsError, match="synthetic rows are for tests"):
            dl.load_costs(shipped, kit=kit)
    finally:
        shipped.write_bytes(original)
    assert dl.load_costs(shipped, kit=kit) == []


# ---- the answers card --------------------------------------------------------------------------------------

def card_answers() -> list:
    text = dl.read_text(DEMOS / "MEASURING.md")
    card = text.split("<!-- answers card -->")[1].split("<!-- end answers card -->")[0]
    answers = re.findall(r'"([^"]+)"', card)
    assert len(answers) >= 4, answers
    return answers


def briefs_holding_answers(briefs: dict) -> list:
    return [(name, a) for name, text in briefs.items() for a in card_answers() if a.lower() in text.lower()]


def test_no_brief_holds_an_answer_from_the_card():
    briefs = {n: dl.read_text(dl.load_demo(n).dir / "BRIEF.md") for n in DEMO_NAMES}
    assert briefs_holding_answers(briefs) == []
    planted = dict(briefs, fake=briefs[DEMO_NAMES[0]] + "\nWhen it asks to commit, say: Yes, commit it.\n")
    assert briefs_holding_answers(planted) == [("fake", "Yes, commit it.")]
