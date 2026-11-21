"""Demos graded in Python, in Node and Python together, and on their git history; the mutants engine; and the
rules and guards those need. Each guard here is seen to fail once on a planted violation.

The demos here are made up, small and quick: a scratch copy of the kit gets them beside the shipped ones and is
committed in its own repo, so start.py, check.py and mutants.py run on them as on any demo. Everything runs in a
throwaway HOME, so nothing touches the real ~/.agents, ~/.claude or ~/agent-demos.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

DEMOS = Path(__file__).resolve().parent.parent
KIT = DEMOS.parent
sys.path.insert(0, str(DEMOS))
sys.path.insert(0, str(KIT / "scripts"))
import check  # noqa: E402
import demolib as dl  # noqa: E402
import mutants  # noqa: E402
from test_demos import clean_env, commit_all, git, record_line, verdict, write_record  # noqa: E402

WATCH = dl.WATCH_MARK


@pytest.fixture(scope="module", autouse=True)
def isolated_git(tmp_path_factory):
    saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
    os.environ["GIT_CONFIG_GLOBAL"] = str(tmp_path_factory.mktemp("git") / "empty.gitconfig")
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def write_tree(root: Path, files: dict) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)


BRIEF = "# {app}\n\nBuild it.\n\n## Graded\n\n1. It doubles a number.\n2. It doubles a negative one.\n\n" \
        "## Not graded\n\n- How it reads.\n\n" + WATCH + "\nWatch it work. A grade is feedback, not proof; CI's " \
        "re-grade admits a run.\n"
RUNNER_HEAD = ("import sys\nfrom pathlib import Path\n"
               "sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)]\n"
               "import acceptkit as ak\n")

# A python demo: tool.py prints twice its argument. The checks run it as a process of its own.
PY_RUNNER = RUNNER_HEAD + (
    "ws = ak.workspace()\n"
    "def doubles(n):\n"
    "    r = ak.run(ak.python_argv(str(ws / 'tool.py'), str(n)), timeout=60)\n"
    "    assert r.returncode == 0, f'tool.py {n} exited {r.returncode}: {r.stderr.strip()[-200:]}'\n"
    "    assert r.stdout.strip() == str(2 * n), f'tool.py {n} printed {r.stdout.strip()!r}'\n"
    "ak.main([('doubles 2', lambda: doubles(2)), ('doubles 21', lambda: doubles(21)),\n"
    "         ('doubles -3', lambda: doubles(-3))])\n")
PY_DEMO = {
    "demo.json": {"title": "Py Tool", "app": "Py Tool", "tier": "S", "stack": "python", "summary": "doubles",
                  "kickoff": "Read BRIEF.md and build it.", "not_checked": "how it reads", "accept_count": 3,
                  "runtime": "python", "accept_runner": "accept/run.py", "mutants_runner": "demos/mutants.py",
                  "timeout_s": 120},
    "BRIEF.md": BRIEF.format(app="Py Tool"),
    "skeleton/tool.py": "import sys\nsys.exit('not built yet: see BRIEF.md')\n",
    "skeleton/.gitignore": "__pycache__/\nframes/\n",
    "reference/tool.py": "import sys\n\nn = int(sys.argv[1])\nprint(2 * n)\n",
    "accept/run.py": PY_RUNNER,
    "accept/mutants/001-adds-one.json": {"id": "001", "graded_item": 1, "description": "adds one",
                                         "file": "tool.py", "find": "int(sys.argv[1])",
                                         "replace": "int(sys.argv[1]) + 1"},
    "accept/mutants/002-no-sign.json": {"id": "002", "graded_item": 2, "description": "drops the sign",
                                        "file": "tool.py", "find": "print(2 * n)", "replace": "print(abs(2 * n))"},
    "accept/mutants/legal/l01-order.json": {"id": "L01", "description": "the factors swapped", "file": "tool.py",
                                            "find": "print(2 * n)", "replace": "print(n * 2)"},
}


def as_files(spec: dict) -> dict:
    return {k: json.dumps(v, indent=2) + "\n" if isinstance(v, dict) else v for k, v in spec.items()}


def make_demo(demos: Path, name: str, spec: dict, **over) -> Path:
    spec = dict(spec)
    spec["demo.json"] = dict(spec["demo.json"], **over)
    d = demos / name
    if d.exists():
        shutil.rmtree(str(d))
    write_tree(d, as_files(spec))
    return d


# A mixed demo: a Node frontend module and a Python backend script, graded by node --test, which reaches the
# frontend through probe.mjs and starts the backend on DEMO_PYTHON. Its skeleton ships package.json and a rules
# file per lane.
MIXED_TEST = (
    "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
    "import { spawnSync } from 'node:child_process';\nimport path from 'node:path';\n"
    "import { values } from '../../probe.mjs';\n"
    "test('the frontend shows a trail', () => {\n"
    "  const [html] = values('frontend/show.js', [['show', 'Ridge']]);\n"
    "  assert.equal(html, '<li>Ridge</li>');\n});\n"
    "test('the backend answers, on the Python the kit chose', () => {\n"
    "  assert.ok(path.isAbsolute(process.env.DEMO_PYTHON), process.env.DEMO_PYTHON);\n"
    "  const r = spawnSync(process.env.DEMO_PYTHON, ['-B', path.join(process.env.DEMO_WORKSPACE, 'backend', "
    "'serve.py')], { encoding: 'utf8' });\n"
    "  assert.equal(r.stdout.trim(), '{\"trails\": 7}', r.stderr);\n});\n")
MIXED_DEMO = {
    "demo.json": {"title": "Two Lanes", "app": "Two Lanes", "tier": "S", "stack": "browser-python",
                  "summary": "two lanes", "kickoff": ["Read BRIEF.md and do session 1.",
                                                      "Read BRIEF.md and do session 2."],
                  "not_checked": "the page", "accept_count": 2, "runtime": "mixed", "accept_runner": None,
                  "mutants_runner": "demos/mutants.py", "timeout_s": 120},
    "BRIEF.md": "# Two Lanes\n\nBuild both.\n\n" + WATCH + "\nWatch. A grade is feedback, not proof; CI's re-grade.\n",
    "skeleton/package.json": {"name": "x", "type": "module", "engines": {"node": ">=22.13"},
                              "scripts": {"test": "exit 1", "serve": "python backend/serve.py"}},
    "skeleton/frontend/AGENTS.md": "# Frontend lane\n",
    "skeleton/backend/AGENTS.md": "# Backend lane\n",
    "skeleton/frontend/show.js": "export function show() { throw new Error('not built yet'); }\n",
    "skeleton/backend/serve.py": "raise SystemExit('not built yet')\n",
    "reference/package.json": {"type": "module"},
    "reference/frontend/show.js": "export function show(name) { return `<li>${name}</li>`; }\n",
    "reference/backend/serve.py": "import json\nprint(json.dumps({'trails': 7}))\n",
    "accept/lanes.test.mjs": MIXED_TEST,
    "accept/mutants/001-no-li.json": {"id": "001", "graded_item": None, "description": "no list item",
                                      "file": "frontend/show.js", "find": "`<li>${name}</li>`",
                                      "replace": "name"},
}

# A demo graded on its git history: the builder replays a skeleton commit and one commit of the work.
GIT_RUNNER = RUNNER_HEAD + (
    "ws = ak.workspace()\n"
    "def g(*a):\n"
    "    return ak.run([ak.program('git'), '-C', str(ws), *a], timeout=60)\n"
    "def own_repo():\n"
    "    r = g('rev-parse', '--show-toplevel')\n"
    "    assert r.returncode == 0 and Path(r.stdout.strip()).resolve() == ws.resolve(), r.stdout + r.stderr\n"
    "def two_commits():\n"
    "    r = g('rev-list', '--count', 'HEAD')\n"
    "    assert r.stdout.strip() == '2', f'{r.stdout.strip()} commits'\n"
    "def verified():\n"
    "    r = g('log', '-1', '--format=%B')\n"
    "    assert 'Verified:' in r.stdout, r.stdout\n"
    "def clean():\n"
    "    r = g('status', '--porcelain')\n"
    "    assert r.returncode == 0 and r.stdout.strip() == '', r.stdout + r.stderr\n"
    "ak.main([('its own repo', own_repo), ('two commits', two_commits), ('the work says Verified', verified),\n"
    "         ('nothing left uncommitted', clean)])\n")
BUILDER = (
    "import argparse, shutil, subprocess\nfrom pathlib import Path\n"
    "ap = argparse.ArgumentParser(); ap.add_argument('--skeleton'); ap.add_argument('--out')\n"
    "a = ap.parse_args(); out = Path(a.out); here = Path(__file__).resolve().parent\n"
    "msgs = [l for l in (here / 'messages.txt').read_text().split('\\n---\\n')]\n"
    "import os\n"
    "def git(*x): subprocess.run([os.environ['DEMO_GIT'], '-c', 'user.name=b', '-c', 'user.email=b@localhost', '-C', str(out), *x],"
    " check=True, capture_output=True)\n"
    "shutil.copytree(a.skeleton, str(out), dirs_exist_ok=True)\n"
    "git('init', '-q'); git('add', '-A'); git('commit', '-q', '-m', msgs[0])\n"
    "shutil.copytree(str(here / 'work'), str(out), dirs_exist_ok=True)\n"
    "git('add', '-A'); git('commit', '-q', '-m', msgs[1])\n")
GIT_DEMO = {
    "demo.json": {"title": "Git Log", "app": "Git Log", "tier": "S", "stack": "python", "summary": "history",
                  "kickoff": "Read BRIEF.md and do it.", "not_checked": "the prose", "accept_count": 4,
                  "runtime": "python", "accept_runner": "accept/run.py", "mutants_runner": "demos/mutants.py",
                  "timeout_s": 120, "copy_git": True, "fixture": "reference/build.py"},
    "BRIEF.md": "# Git Log\n\nCommit it.\n\n" + WATCH + "\nWatch. A grade is feedback, not proof; CI's re-grade.\n",
    "skeleton/notes.py": "NOTES = []\n",
    "reference/build.py": BUILDER,
    "reference/messages.txt": "chore: start\n\nUnverified: the skeleton\n---\nfeat: add a note\n\n"
                              "Verified: python -m unittest -> OK\n",
    "reference/work/notes.py": "NOTES = ['first']\n",
    "accept/run.py": GIT_RUNNER,
    "accept/mutants/001-unverified.json": {"id": "001", "graded_item": None, "description": "the work unverified",
                                           "file": "messages.txt", "find": "Verified: python -m unittest -> OK",
                                           "replace": "Unverified: nothing ran"},
    "accept/mutants/002-one-commit.json": {"id": "002", "graded_item": None, "description": "one commit only",
                                           "file": "build.py", "find": "git('add', '-A'); git('commit', '-q', "
                                           "'-m', msgs[1])", "replace": "pass"},
}

FAKES = {"py-tool": PY_DEMO, "two-lanes": MIXED_DEMO, "git-log": GIT_DEMO}


@pytest.fixture(scope="module")
def fake_kit(tmp_path_factory):
    """(kit, env): the kit's demo files plus the made-up demos, committed in a repo of their own."""
    base = tmp_path_factory.mktemp("fakekit")
    home = base / "it's home"
    home.mkdir()
    env = clean_env(home)
    kit = base / "kit"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "tests")
    for rel in ("demos", "scripts", "core"):
        shutil.copytree(str(KIT / rel), str(kit / rel), ignore=ignore)
    (kit / "plugins/starter/hooks/commit-guard").mkdir(parents=True)
    shutil.copy2(str(dl.install.GUARD), str(kit / "plugins/starter/hooks/commit-guard/guard.py"))
    for rel in ("kit.json", "MODELS.md"):
        shutil.copy2(str(KIT / rel), str(kit / rel))
    for name, spec in FAKES.items():
        make_demo(kit / "demos", name, spec)
    git(kit, "init", "-q", env=env)
    sha = commit_all(kit, "test: the kit with made-up demos", env)
    git(kit, "update-ref", "refs/remotes/origin/main", sha, env=env)
    return kit, env


@pytest.fixture
def fhome(tmp_path, fake_kit):
    kit, _ = fake_kit
    h = tmp_path / "it's home"
    h.mkdir()
    write_record(h, kit, ["claude", "opencode"])
    return h


def run(kit: Path, script: str, *args: str, home: Path, cwd: Path | None = None, **env) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(kit / "demos" / script), *args], cwd=str(cwd or home),
                          env=clean_env(home, **env), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", stdin=subprocess.DEVNULL, timeout=900)


def started(kit: Path, home: Path, name: str, tool: str = "claude") -> tuple[Path, subprocess.CompletedProcess]:
    r = run(kit, "start.py", name, "--tool", tool, home=home)
    assert r.returncode == 0, r.stderr
    return home / "agent-demos" / name, r


@pytest.fixture
def local_demos(tmp_path, monkeypatch):
    """A demos/ folder of made-up demos for in-process tests, with the kit's helpers beside them."""
    d = tmp_path / "demos"
    d.mkdir()
    for f in ("acceptkit.py", "probe.mjs", "probe-child.mjs", "reporter.mjs", "denylist.txt"):
        shutil.copy2(str(DEMOS / f), str(d / f))
    monkeypatch.setattr(dl, "DEMOS", d)
    monkeypatch.setattr(check, "REPORTER", d / "reporter.mjs")
    return d


# ---- demo.json ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("over, why", [
    ({"runtime": "node"}, "runtime is 'python'"),
    ({"accept_runner": None}, "names its accept_runner"),
    ({"accept_runner": "accept/run.mjs"}, "ending .py"),
    ({"accept_runner": "../run.py"}, "accept_runner is a file"),
    ({"timeout_s": 5}, "timeout_s is the seconds"),
    ({"timeout_s": True}, "timeout_s is the seconds"),
    ({"mutants_runner": "accept/mutants/run.py"}, "mutants_runner is 'demos/mutants.py'"),
    ({"copy_git": True}, "names its fixture"),
    ({"kickoff": []}, "kickoff is the first message"),
    ({"surprise": 1}, "keys must be"),
])
def test_demo_json_refuses_what_the_scripts_cannot_run(local_demos, over, why):
    make_demo(local_demos, "py-tool", PY_DEMO)
    assert dl.load_demo("py-tool").runtime == "python"     # the unplanted file loads
    make_demo(local_demos, "py-tool", PY_DEMO, **over)
    with pytest.raises(dl.DemoError, match=re.escape(why)):
        dl.load_demo("py-tool")


def test_a_kickoff_list_is_one_message_per_session(local_demos):
    make_demo(local_demos, "two-lanes", MIXED_DEMO)
    demo = dl.load_demo("two-lanes")
    assert demo.kickoffs == ("Read BRIEF.md and do session 1.", "Read BRIEF.md and do session 2.")
    assert demo.needs_node and dl.load_demo("two-lanes").runtime == "mixed"


def test_skeleton_package_rules(local_demos):
    make_demo(local_demos, "two-lanes", MIXED_DEMO)
    assert dl.skeleton_package(dl.load_demo("two-lanes"))["engines"] == {"node": ">=22.13"}
    spec = dict(MIXED_DEMO)
    spec["skeleton/package.json"] = {"type": "module", "scripts": {"test": "x", "test:unit": "node --test"}}
    make_demo(local_demos, "two-lanes", spec)
    with pytest.raises(dl.DemoError, match="test:unit would be a second test entry point"):
        dl.skeleton_package(dl.load_demo("two-lanes"))
    spec = dict(PY_DEMO, **{"skeleton/package.json": {"type": "module"}})
    make_demo(local_demos, "py-tool", spec)
    with pytest.raises(dl.DemoError, match="a python demo ships no package.json"):
        dl.skeleton_package(dl.load_demo("py-tool"))


# ---- a Python accept runner --------------------------------------------------------------------------------

def test_a_python_demo_is_graded_on_the_validated_python_in_isolation(local_demos, tmp_path):
    make_demo(local_demos, "py-tool", PY_DEMO)
    demo = dl.load_demo("py-tool")
    assert [c.ok for c in check.run_accept(demo, demo.dir / "reference")] == [True] * 3
    assert [c.ok for c in check.run_accept(demo, demo.dir / "skeleton")] == [False] * 3
    # What the runner sees: -I and -S, a cwd outside the copy, the copy outside the workspace, DEMO_PYTHON by its
    # full path; and what the workspace's process sees: no DEMO_ variable at all, and an empty HOME.
    probe = RUNNER_HEAD + (
        "import json, os\nws = ak.workspace()\n"
        "def flags():\n"
        "    assert sys.flags.isolated == 1 and sys.flags.no_site == 1, sys.flags\n"
        "    assert Path.cwd().resolve() == ws.parent.resolve(), (Path.cwd(), ws)\n"
        "    assert os.path.isabs(os.environ['DEMO_PYTHON']) and os.environ['DEMO_RESULT_TOKEN']\n"
        "    assert os.environ['GIT_CEILING_DIRECTORIES'] == str(ws.parent)\n"
        "def child():\n"
        "    r = ak.run(ak.python_argv('-c', 'import json, os; print(json.dumps(dict(os.environ)))'), timeout=60)\n"
        "    env = json.loads(r.stdout)\n"
        "    assert not [k for k in env if k.upper().startswith('DEMO_')], sorted(env)\n"
        "    assert os.listdir(env['HOME']) == [] and env['HOME'] != os.environ.get('HOME'), env['HOME']\n"
        "ak.main([('flags', flags), ('child', child), ('third', lambda: None)])\n")
    (demo.dir / "accept" / "run.py").write_text(probe, encoding="utf-8")
    ws = tmp_path / "ws"
    shutil.copytree(str(demo.dir / "reference"), str(ws))
    got = check.run_accept(demo, ws)
    assert [(c.name, c.ok) for c in got] == [("flags", True), ("child", True), ("third", True)], got


def test_no_variable_tells_the_workspaces_process_where_the_kit_is(local_demos, tmp_path, monkeypatch):
    """Python has no permission model: a workspace process that learnt the clone's path could read reference/.
    A grade started in the clone has PWD naming it, and any variable could; none reaches the checks' processes."""
    make_demo(local_demos, "py-tool", PY_DEMO)
    demo = dl.load_demo("py-tool")
    planted = {"PWD": str(KIT), "OLDPWD": str(KIT / "demos"), "MY_TOOL_DIR": str(KIT / "scripts").upper(),
               "KIT_URL": (KIT / "demos").as_uri()}
    for k, v in planted.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PATH", str(KIT / "scripts") + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("NEAR_MISS", str(KIT) + "-elsewhere")   # a sibling folder is not the kit
    out = tmp_path / "env.json"
    runner = RUNNER_HEAD + (
        "import json\nws = ak.workspace()\n"
        "def child():\n"
        "    r = ak.run(ak.python_argv('-c', 'import json, os; print(json.dumps(dict(os.environ)))'), timeout=60)\n"
        f"    open({str(out)!r}, 'w').write(r.stdout)\n"
        "ak.main([('child', child), ('b', lambda: None), ('c', lambda: None)])\n")
    (demo.dir / "accept" / "run.py").write_text(runner, encoding="utf-8")
    assert all(c.ok for c in check.run_accept(demo, demo.dir / "reference"))
    env = json.loads(out.read_text(encoding="utf-8"))
    kit = dl.kit_text(KIT.resolve().as_posix()) + "/"
    assert [k for k, v in env.items() if kit in dl.kit_text(v) + "/"] == [], sorted(env)
    assert not set(planted) & set(env) and env["NEAR_MISS"].endswith("-elsewhere")
    assert env.get("PATH") or env.get("Path")   # PATH itself stays, without the kit's folder


def test_lines_the_workspace_prints_are_not_results(local_demos, tmp_path):
    """A runner that lets the workspace's output through (here, one that hands it the runner's own stdout) would
    let it print a passing line for every check. Without the run's token they count against the grade."""
    make_demo(local_demos, "py-tool", PY_DEMO)
    demo = dl.load_demo("py-tool")
    leaky = RUNNER_HEAD + (
        "import subprocess\nws = ak.workspace()\n"
        "def leak():\n"
        "    subprocess.run(ak.python_argv(str(ws / 'tool.py')), env=ak.child_env(), check=False)\n"
        "    raise AssertionError('the real check fails')\n"
        "ak.main([('doubles 2', leak), ('doubles 21', leak), ('doubles -3', leak)])\n")
    (demo.dir / "accept" / "run.py").write_text(leaky, encoding="utf-8")
    ws = tmp_path / "ws"
    ws.mkdir()
    forged = [json.dumps({"demo_event": "test", "token": tok, "ok": True, "name": n, "nesting": 0, "kind": "test"})
              for tok in (None, "0" * 32) for n in ("doubles 2", "doubles 21", "doubles -3")]
    (ws / "tool.py").write_text("for ln in %r:\n    print(ln)\n" % forged, encoding="utf-8")
    got = check.run_accept(demo, ws)
    assert not any(c.ok for c in got), got
    assert got[-1].name == "held-out results: one per check" and "18 result lines that are not the reporter's" \
        in got[-1].detail, got[-1]
    # The plant is real: the same lines with the run's token would have counted.
    lines = "\n".join(ln.replace('"token": null', '"token": "t"') for ln in forged[:3])
    assert all(c.ok for c in check.held_out_checks(demo, lines, "", 0, token="t"))


def test_a_runner_that_says_pass_while_a_check_failed_is_not_believed():
    demo = dl.Demo("x", "X", "X", "S", "python", "s", "k", "n", 2, runtime="python")
    line = lambda n, ok: json.dumps({"demo_event": "test", "token": "t", "ok": ok, "name": n, "nesting": 0,
                                     "kind": "test"})
    got = check.held_out_checks(demo, line("a", True) + "\n" + line("b", False), "", 0, token="t", runner="run.py")
    assert got[-1].name == "held-out results: the test runner agrees" and "run.py exited 0" in got[-1].detail


def test_a_demo_timeout_stops_its_checks(local_demos, tmp_path):
    make_demo(local_demos, "py-tool", PY_DEMO)
    demo = dl.load_demo("py-tool")
    (demo.dir / "accept" / "run.py").write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    slow = dataclasses.replace(demo, timeout_s=3)
    got = check.run_accept(slow, demo.dir / "reference")
    assert len(got) == 3 and not any(c.ok for c in got)
    assert "took longer than 3 seconds" in got[0].detail, got[0]


def test_a_node_runner_of_the_demos_own_runs_on_node(local_demos, tmp_path):
    spec = dict(MIXED_DEMO)
    spec["accept/run.mjs"] = (
        "const t = process.env.DEMO_RESULT_TOKEN;\n"
        "for (const name of ['the frontend shows a trail', 'the backend answers, on the Python the kit chose'])\n"
        "  console.log(JSON.stringify({ demo_event: 'test', token: t, ok: true, name, nesting: 0, kind: 'test' }));\n")
    make_demo(local_demos, "two-lanes", spec, accept_runner="accept/run.mjs")
    demo = dl.load_demo("two-lanes")
    assert check.accept_command(demo)[0][0] == dl.exe("node")
    assert all(c.ok for c in check.run_accept(demo, demo.dir / "reference"))


def test_a_mixed_demo_reaches_its_python_backend_from_node_test(local_demos):
    make_demo(local_demos, "two-lanes", MIXED_DEMO)
    demo = dl.load_demo("two-lanes")
    assert [c.ok for c in check.run_accept(demo, demo.dir / "reference")] == [True, True]
    assert [c.ok for c in check.run_accept(demo, demo.dir / "skeleton")] == [False, False]


# ---- scenarios, and the probe's limits ---------------------------------------------------------------------

SCENARIO = ("export async function stepped({ load }, n) {\n"
            "  const m = await load('src/sim.js');\n"
            "  const w = m.world();\n  for (let i = 0; i < n; i++) m.step(w);\n  return w;\n}\n"
            "export async function token({ load }) {\n"
            "  const m = await load('src/sim.js');\n  return m.leak ? m.leak() : null;\n}\n")
SCENARIO_TEST = (
    "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
    "import { scenario, values } from '../../probe.mjs';\n"
    "const S = new URL('./scenarios.mjs', import.meta.url);\n"
    "test('stepping ten thousand times keeps count', () => {\n"
    "  assert.deepEqual(scenario(S, 'stepped', [10000]), { t: 10000 });\n});\n"
    "test('the workspace never sees the result token', () => {\n"
    "  assert.ok(process.env.DEMO_RESULT_TOKEN, 'the checks have one');\n"
    "  assert.equal(scenario(S, 'token', []), null);\n});\n"
    "test('a call that never returns is stopped', () => {\n"
    "  assert.throws(() => values('src/sim.js', [['spin']], { timeoutMs: 2000 }), /within 2 seconds/);\n});\n")


def test_a_scenario_runs_beside_the_workspace_under_the_permission_model(local_demos, tmp_path):
    spec = {
        "demo.json": dict(MIXED_DEMO["demo.json"], title="Sim", app="Sim", stack="node", runtime="node",
                          kickoff="Build it.", accept_count=3),
        "BRIEF.md": MIXED_DEMO["BRIEF.md"],
        "skeleton/src/sim.js": "export const world = () => ({ t: 0 });\nexport function step() {}\n",
        "reference/src/sim.js": ("export const world = () => ({ t: 0 });\nexport function step(w) { w.t += 1; }\n"
                                 "export const leak = () => process.env.DEMO_RESULT_TOKEN ?? null;\n"
                                 "export function spin() { for (;;); }\n"),
        "accept/scenarios.mjs": SCENARIO,
        "accept/sim.test.mjs": SCENARIO_TEST,
    }
    make_demo(local_demos, "sim", spec)
    demo = dl.load_demo("sim")
    got = check.run_accept(demo, demo.dir / "reference")
    assert all(c.ok for c in got), got
    # The plant: a workspace that hands back the kit's reference through a scenario's load cannot read it.
    ws = tmp_path / "ws"
    shutil.copytree(str(demo.dir / "skeleton"), str(ws))
    (ws / "src" / "sim.js").write_text(f'export * from "{(demo.dir / "reference" / "src" / "sim.js").as_uri()}";\n',
                                       encoding="utf-8")
    got = check.run_accept(demo, ws)
    assert not got[0].ok and "allow-fs-read" in got[0].detail, got[0]


# A scenario whose workspace module reads files of accept/ by their path beside the scenario module, which its own
# command line names. The probe granted that whole folder once, and accept/mutants/ quotes the reference: a
# verifier counted 5,696 of spin-clash's 16,794 reference characters in its mutants' find strings.
PEEK_SIM = ("import { readFileSync } from 'node:fs';\n"
            "export const world = () => ({ t: 0 });\nexport function step(w) { w.t += 1; }\n"
            "export function peek(rel) {\n"
            "  const here = process.argv.find((a) => a.startsWith('file:') && a.endsWith('/scenarios.mjs'));\n"
            "  try { return readFileSync(new URL(rel, here), 'utf8').trim(); } catch (e) { return `denied: ${e.code}`; }\n"
            "}\n")
PEEK_TEST = (
    "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
    "import { scenario } from '../../probe.mjs';\n"
    "const S = new URL('./scenarios.mjs', import.meta.url);\n"
    "test('a scenario runs with the module it imports', () => {\n"
    "  assert.deepEqual(scenario(S, 'stepped', [3]), { t: 3, twice: 6 });\n});\n"
    "for (const rel of ['./mutants/001-off.json', './notes.mjs', '../reference/src/sim.js']) {\n"
    "  test(`the workspace cannot read ${rel}`, () => {\n"
    "    const got = scenario(S, 'peek', [rel]);\n"
    "    assert.equal(got, 'denied: ERR_ACCESS_DENIED', `it read ${rel}: ${got}`);\n  });\n}\n"
    "test('a scenario that imports the mutant list never runs', () => {\n"
    "  assert.throws(() => scenario(new URL('./leaky.mjs', import.meta.url), 'cases'),\n"
    "    /leaky\\.mjs imports \\.\\/mutants\\/001-off\\.json, which a scenario's process may not read/);\n});\n")
PEEK_DEMO = {
    "demo.json": dict(MIXED_DEMO["demo.json"], title="Peek", app="Peek", stack="node", runtime="node",
                      kickoff="Build it.", accept_count=5),
    "BRIEF.md": MIXED_DEMO["BRIEF.md"],
    "skeleton/src/sim.js": "export const world = () => ({ t: 0 });\nexport function step() {}\n",
    "reference/src/sim.js": PEEK_SIM,
    "accept/helpers.mjs": "// The grader's own arithmetic.\nexport const twice = (n) => 2 * n;\n",
    "accept/scenarios.mjs": ("import { twice } from './helpers.mjs';   // what the scenario needs, and so may read\n"
                             "// import { SECRET } from './notes.mjs';  a commented-out import is not followed\n"
                             "export async function stepped({ load }, n) {\n"
                             "  const m = await load('src/sim.js');\n  const w = m.world();\n"
                             "  for (let i = 0; i < n; i++) m.step(w);\n  return { t: w.t, twice: twice(n) };\n}\n"
                             "export async function peek({ load }, rel) {\n"
                             "  return (await load('src/sim.js')).peek(rel);\n}\n"),
    "accept/notes.mjs": "export const SECRET = 'a module of accept/ no scenario imports';\n",
    "accept/leaky.mjs": ("import mutant from './mutants/001-off.json' with { type: 'json' };\n"
                         "export async function cases() { return mutant; }\n"),
    "accept/mutants/001-off.json": json.dumps({"id": "001", "graded_item": None, "description": "off by one",
                                               "file": "src/sim.js", "find": "w.t += 1", "replace": "w.t += 2"}) + "\n",
    "accept/peek.test.mjs": PEEK_TEST,
}


def test_a_scenarios_process_reads_only_the_modules_it_imports(local_demos):
    make_demo(local_demos, "peek", PEEK_DEMO)
    demo = dl.load_demo("peek")
    got = check.run_accept(demo, demo.dir / "reference")
    assert [(c.name, c.ok) for c in got] == [
        ("a scenario runs with the module it imports", True),
        ("the workspace cannot read ./mutants/001-off.json", True),
        ("the workspace cannot read ./notes.mjs", True),
        ("the workspace cannot read ../reference/src/sim.js", True),
        ("a scenario that imports the mutant list never runs", True)], got
    # The plant is real: with the folder granted, as the probe once did, the same workspace reads the mutant list
    # and the module no scenario imports, and the leaky scenario runs; reference/, outside accept/, stays shut.
    probe = local_demos / "probe.mjs"
    planted = dl.read_text(probe).replace("reads = scenarioReads(scenarioPath);",
                                          "reads = [path.dirname(scenarioPath)];")
    assert planted != dl.read_text(probe)
    probe.write_text(planted, encoding="utf-8")
    got = check.run_accept(demo, demo.dir / "reference")
    assert [c.ok for c in got] == [True, False, False, True, False], got
    assert '"find": "w.t += 1"' in got[1].detail and "a module of accept/ no scenario imports" in got[2].detail, got


# A scenario reads the workspace's values with the built-ins of the process it shares with the workspace's code. A
# verifier's workspace once changed one of them in 5 to 7 lines and hid a real bug, three times over: a
# Number.prototype.toFixed that made each stream the scenario formatted unique (seeds 0 and 65536 collided), an
# Object.getPrototypeOf that made a class instance look plain, and a Math.random the scenario could not take away.
# Another rewrote the scenario's own table of seeds, imported by the URL on its command line, and another hooked the
# promises made after it loaded and rewrote the record a scenario's helper resolved with. probe-child.mjs now
# freezes the built-ins (harden), takes Node's ways of looking into the process away (takeAway) and freezes what
# the kit's modules there export (freezeExports) before any workspace module loads, and holds the clocks itself.
# These scenarios still format and classify beside the workspace, which the monster-tamer-lite ones no longer do,
# so that the freeze alone is what each check here rests on.
FROZEN_SCENARIOS = (
    "export const SEEDS = [0, 65536, 7];\n"
    "export async function streams({ load }) {\n"
    "  const m = await load('src/gen.js');\n"
    "  return SEEDS.map((seed) => { const g = m.makeGen(seed); return [0, 1, 2].map(() => m.next(g).toFixed(9)).join(','); });\n"
    "}\n"
    "const look = async (gen) => ({ proto: Object.getPrototypeOf(gen) });\n"
    "export async function prototype({ load }) {\n"
    "  const m = await load('src/gen.js');\n"
    "  const { proto } = await look(m.makeGen(1));\n"
    "  return proto === Object.prototype ? 'Object.prototype' : String(proto && proto.constructor && proto.constructor.name);\n"
    "}\n"
    "export async function clockless({ load, withoutClocks }) {\n"
    "  const m = await load('src/gen.js');\n"
    "  try { withoutClocks(() => { const g = m.makeGen(3); for (let i = 0; i < 10; i++) m.next(g); }); return 'ran'; }\n"
    "  catch (e) { return String(e.message); }\n"
    "}\n"
    "export async function copy({ load }) {\n"
    "  const m = await load('src/gen.js');\n"
    "  return JSON.stringify(m.makeGen(5));\n"
    "}\n"
    "export async function source({ load }) {\n"
    "  const m = await load('src/gen.js');\n"
    "  return Function.prototype.toString.call(m.next);\n"
    "}\n")
FROZEN_CHECKS = ["each seed has a stream of its own", "the state is plain data", "it reads no clock",
                 "the state holds the seed alone", "next reads no global"]
FROZEN_TEST = (
    "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n"
    "import { scenario } from '../../probe.mjs';\n"
    "const S = new URL('./scenarios.mjs', import.meta.url);\n"
    f"test({FROZEN_CHECKS[0]!r}, () => {{\n"
    "  const got = scenario(S, 'streams');\n  assert.equal(new Set(got).size, 3, got.join(' | '));\n});\n"
    f"test({FROZEN_CHECKS[1]!r}, () => {{\n  assert.equal(scenario(S, 'prototype'), 'Object.prototype');\n}});\n"
    f"test({FROZEN_CHECKS[2]!r}, () => {{\n  assert.equal(scenario(S, 'clockless'), 'ran');\n}});\n"
    f"test({FROZEN_CHECKS[3]!r}, () => {{\n  assert.equal(scenario(S, 'copy'), '{{\"s\":5}}');\n}});\n"
    f"test({FROZEN_CHECKS[4]!r}, () => {{\n  assert.doesNotMatch(scenario(S, 'source'), /globalThis/);\n}});\n")
GEN = ("export const makeGen = (seed) => ({ s: seed >>> 0 });\n"
       "export function next(g) {\n  g.s = (Math.imul(g.s ^ (g.s >>> 15), 0x2c1b3c6d) + 0x9e3779b9) >>> 0;\n"
       "  return g.s / 4294967296;\n}\n")
FROZEN_DEMO = {
    "demo.json": dict(MIXED_DEMO["demo.json"], title="Frozen", app="Frozen", stack="node", runtime="node",
                      kickoff="Build it.", accept_count=len(FROZEN_CHECKS)),
    "BRIEF.md": MIXED_DEMO["BRIEF.md"],
    "skeleton/src/gen.js": "export function makeGen() { throw new Error('not built yet'); }\n",
    "reference/src/gen.js": GEN,
    "accept/scenarios.mjs": FROZEN_SCENARIOS,
    "accept/frozen.test.mjs": FROZEN_TEST,
}
# The real bugs, edits of GEN, each failing one check alone.
A_CLASS = ("({ s: seed >>> 0 })", "new (class Gen { constructor(s) { this.s = s; } })(seed >>> 0)")
LOW_BITS = ("seed >>> 0", "seed & 0xffff")
A_CLOCK = ("return g.s / 4294967296;", "return g.s / 4294967296 + Math.random() * 0;")
AN_EXTRA_FIELD = ("({ s: seed >>> 0 })", "({ s: seed >>> 0, t: 0 })")
A_GLOBAL = ("return g.s / 4294967296;", "return g.s / 4294967296 + (globalThis.bias || 0);")
FREEZE_BUILT_INS = "\nharden();\n"
FREEZE_EXPORTS = "  for (const href of deserialize(Buffer.from(modules, 'base64'))) freezeExports(href, await import(href));\n"
# A promise hook that makes the record a scenario's helper resolves with say "plain", for either module's hook.
HOOKED = ("const then = Promise.prototype.then;\nlet busy = false;\n"
          "const plain = (v) => { if (v && typeof v === 'object' && 'proto' in v) v.proto = Object.prototype; };\n"
          "const hook = (p) => {\n  if (busy) return;\n  busy = true;\n"
          "  try { then.call(p, plain, () => {}); } finally { busy = false; }\n};\n")
# Each cheat, generalized: the real bug it hid, the check that bug fails, what the module imports for it, and the
# cheat as an assignment and as a definition (for a hook, through each module that hands one out).
FROZEN_CHEATS = {
    "a prototype method": (
        LOW_BITS, FROZEN_CHECKS[0], "",
        ["const toFixed = Number.prototype.toFixed;\nlet tick = 0;\n"
         "Number.prototype.toFixed = function (d) { return `${toFixed.call(this, d)}~${tick++}`; };\n",
         "const toFixed = Number.prototype.toFixed;\nlet tick = 0;\n"
         "Object.defineProperty(Number.prototype, 'toFixed', { value(d) { return `${toFixed.call(this, d)}~${tick++}`; } });\n"]),
    "an Array method": (
        LOW_BITS, FROZEN_CHECKS[0], "",
        ["const join = Array.prototype.join;\nlet tick = 0;\n"
         "Array.prototype.join = function (s) { return `${join.call(this, s)}~${tick++}`; };\n",
         "const join = Array.prototype.join;\nlet tick = 0;\n"
         "Object.defineProperty(Array.prototype, 'join', { value(s) { return `${join.call(this, s)}~${tick++}`; } });\n"]),
    "Object.getPrototypeOf": (
        A_CLASS, FROZEN_CHECKS[1], "",
        ["const real = Object.getPrototypeOf;\nObject.getPrototypeOf = (o) => (real(o) === null ? null : Object.prototype);\n",
         "const real = Object.getPrototypeOf;\n"
         "Object.defineProperty(Object, 'getPrototypeOf', { value: (o) => (real(o) === null ? null : Object.prototype) });\n"]),
    "Math.random": (
        A_CLOCK, FROZEN_CHECKS[2], "",
        ["Math.random = () => 0.5;\n",
         "Object.defineProperty(Math, 'random', { configurable: true, get: () => () => 0.5, set() {} });\n"]),
    "JSON": (
        AN_EXTRA_FIELD, FROZEN_CHECKS[3], "",
        ["const stringify = JSON.stringify;\n"
         "JSON.stringify = (v, ...rest) => stringify(v && typeof v === 'object' && 's' in v ? { s: v.s } : v, ...rest);\n",
         "const stringify = JSON.stringify;\nObject.defineProperty(JSON, 'stringify', {\n"
         "  value: (v, ...rest) => stringify(v && typeof v === 'object' && 's' in v ? { s: v.s } : v, ...rest) });\n"]),
    "Function.prototype.toString": (
        A_GLOBAL, FROZEN_CHECKS[4], "",
        ["const toString = Function.prototype.toString;\n"
         "Function.prototype.toString = function () { return toString.call(this).replaceAll('globalThis', 'g'); };\n",
         "const toString = Function.prototype.toString;\nObject.defineProperty(Function.prototype, 'toString', {\n"
         "  value() { return toString.call(this).replaceAll('globalThis', 'g'); } });\n"]),
    # Not a verifier's: the answer rewritten as probe-child.mjs serializes it, past every check at once.
    "the serializer": (
        A_CLASS, FROZEN_CHECKS[1], "import v8 from 'node:v8';\n",
        ["const write = v8.Serializer.prototype.writeValue;\n"
         "v8.Serializer.prototype.writeValue = function (v) {\n"
         "  if (v && v.results && v.results[0] && v.results[0].value === 'Gen') v.results[0].value = 'Object.prototype';\n"
         "  return write.call(this, v);\n};\n",
         "const write = v8.Serializer.prototype.writeValue;\n"
         "Object.defineProperty(v8.Serializer.prototype, 'writeValue', { value(v) {\n"
         "  if (v && v.results && v.results[0] && v.results[0].value === 'Gen') v.results[0].value = 'Object.prototype';\n"
         "  return write.call(this, v);\n} });\n"]),
    "the scenario's own table": (
        LOW_BITS, FROZEN_CHECKS[0], "",
        ["const at = process.argv.find((a) => a.startsWith('file:') && a.endsWith('/scenarios.mjs'));\n"
         "const { SEEDS } = await import(at);\nSEEDS.forEach((s, i) => { SEEDS[i] = i; });\n",
         "const at = process.argv.find((a) => a.startsWith('file:') && a.endsWith('/scenarios.mjs'));\n"
         "const { SEEDS } = await import(at);\nSEEDS.forEach((s, i) => Object.defineProperty(SEEDS, i, { value: i }));\n"]),
    # Not a verifier's either: every promise made once the module has loaded, the helper's among them.
    "a promise hook": (
        A_CLASS, FROZEN_CHECKS[1], "import { createHook } from 'node:async_hooks';\nimport v8 from 'node:v8';\n",
        [HOOKED + "createHook({ init(id, type, trigger, p) { if (type === 'PROMISE') hook(p); } }).enable();\n",
         HOOKED + "v8.promiseHooks.onInit(hook);\n"]),
}


def frozen_ws(tmp_path: Path, name: str, source: str) -> Path:
    ws = tmp_path / name
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "gen.js").write_text(source, encoding="utf-8")
    return ws


def frozen_results(demo, ws: Path) -> list:
    return [(c.name, c.ok) for c in check.run_accept(demo, ws)]


def caught(prelude: str, cheat: str, source: str) -> str:
    """The cheat in a try block, so that the module loads whether it took or not."""
    return prelude + "try {\n" + cheat + "} catch { /* the built-ins are frozen */ }\n" + source


@pytest.mark.parametrize("cheat", sorted(FROZEN_CHEATS))
def test_a_workspace_cannot_change_the_built_ins_a_scenario_observes_with(local_demos, tmp_path, cheat):
    """Each cheat, as written, throws as its module loads, so every check fails. Caught, so that the module loads,
    it changes nothing a check sees: the bug fails the same checks as it does alone. The built-ins here include
    what the kit's own modules export."""
    make_demo(local_demos, "frozen", FROZEN_DEMO)
    demo = dl.load_demo("frozen")
    assert frozen_results(demo, demo.dir / "reference") == [(n, True) for n in FROZEN_CHECKS]
    (find, replace), fails, prelude, forms = FROZEN_CHEATS[cheat]
    buggy = GEN.replace(find, replace)
    assert buggy != GEN
    alone = frozen_results(demo, frozen_ws(tmp_path, "bug", prelude + buggy))
    assert alone == [(n, n != fails) for n in FROZEN_CHECKS], alone
    for i, form in enumerate(forms):
        got = check.run_accept(demo, frozen_ws(tmp_path, f"as-written-{i}", prelude + form + buggy))
        assert not any(c.ok for c in got) and all("TypeError" in c.detail for c in got), got
        assert frozen_results(demo, frozen_ws(tmp_path, f"caught-{i}", caught(prelude, form, buggy))) == alone
    # The plant: without the freeze, each form of the cheat hides the bug from every check. Both parts of it go,
    # since freezing what the kit's modules export also freezes the built-ins their prototypes lead to.
    child = local_demos / "probe-child.mjs"
    text = dl.read_text(child)
    assert FREEZE_BUILT_INS in text and FREEZE_EXPORTS in text
    child.write_text(text.replace(FREEZE_BUILT_INS, "\n").replace(FREEZE_EXPORTS, ""), encoding="utf-8")
    for i, form in enumerate(forms):
        got = frozen_results(demo, frozen_ws(tmp_path, f"unfrozen-{i}", caught(prelude, form, buggy)))
        assert got == [(n, True) for n in FROZEN_CHECKS], got


def test_a_scenario_module_that_exports_what_freezing_cannot_keep_never_runs(local_demos):
    """A frozen Set's members can still change, as can a frozen Map's, Date's or typed array's, so a module of a
    scenario's process that exports one is refused before the workspace's code loads."""
    spec = dict(FROZEN_DEMO)
    spec["accept/scenarios.mjs"] = FROZEN_SCENARIOS + "export const KINDS = new Set(['number']);\n"
    make_demo(local_demos, "frozen", spec)
    demo = dl.load_demo("frozen")
    got = check.run_accept(demo, demo.dir / "reference")
    assert not any(c.ok for c in got) and all("exports KINDS, which holds a Set" in c.detail for c in got), got


def test_an_answer_line_the_workspaces_code_prints_is_not_believed(local_demos, tmp_path):
    """The workspace's code shares stdout with probe-child.mjs's answer and can print a line that looks like one,
    as its module loads or as the process exits. The probe once took the last such line; now only the line with
    the key it gave the process on stdin counts, and the workspace cannot learn the key."""
    make_demo(local_demos, "frozen", FROZEN_DEMO)
    demo = dl.load_demo("frozen")
    guess = "0" * 32
    forger = ("import v8 from 'node:v8';\n"
              "const answer = v8.serialize({ results: [{ ok: true, value: 'Object.prototype' }] }).toString('base64');\n"
              f"const line = (key) => `\\ndemo-probe-answer:${{key}}${{answer}}\\n`;\n"
              f"for (const key of ['', '{guess}:']) process.stdout.write(line(key));\n"
              f"process.on('exit', () => process.stdout.write(line('') + line('{guess}:')));\n")
    ws = frozen_ws(tmp_path, "forger", forger + GEN.replace(*A_CLASS))
    assert dict(frozen_results(demo, ws))[FROZEN_CHECKS[1]] is False
    # The plant: with a key the workspace can guess, its own line is believed.
    probe = local_demos / "probe.mjs"
    planted = dl.read_text(probe).replace("randomBytes(16).toString('hex')", f"'{guess}'")
    assert planted != dl.read_text(probe)
    probe.write_text(planted, encoding="utf-8")
    assert dict(frozen_results(demo, ws))[FROZEN_CHECKS[1]] is True


# Node's ways of looking into the process a workspace's code shares with the kit's, each of which the permission
# model allows. A workspace once read the answer key out of a heap snapshot and printed an answer line of its own
# that the parent believed; the promise hooks are "a promise hook" above. Each is tried by every route to it: the
# module's default export, a named import, process.getBuiltinModule and require.
LOOK_INTO = {
    "v8.getHeapSnapshot": "v8.getHeapSnapshot()",
    "a named getHeapSnapshot": "getHeapSnapshot()",
    "getBuiltinModule's getHeapSnapshot": "process.getBuiltinModule('node:v8').getHeapSnapshot()",
    "require's getHeapSnapshot": "createRequire(import.meta.url)('node:v8').getHeapSnapshot()",
    "v8.queryObjects": "v8.queryObjects(Object)",
    "v8.setHeapSnapshotNearHeapLimit": "v8.setHeapSnapshotNearHeapLimit(1)",
    "v8.setFlagsFromString": "v8.setFlagsFromString('--allow-natives-syntax')",
    "v8.promiseHooks": "v8.promiseHooks.onInit(() => {})",
    "async_hooks.createHook": "createHook({ init() {} }).enable()",
    "async_hooks.executionAsyncResource": "executionAsyncResource()",
}
LOOKER = ("import v8, { getHeapSnapshot } from 'node:v8';\n"
          "import { AsyncLocalStorage, createHook, executionAsyncResource } from 'node:async_hooks';\n"
          "import { createRequire } from 'node:module';\n"
          "const attempt = (f) => { try { f(); return 'ran'; } catch (e) { return String(e && e.message); } };\n"
          "export const look = () => ({\n"
          + "".join(f"  {json.dumps(k)}: attempt(() => {v}),\n" for k, v in LOOK_INTO.items())
          + "});\n"
          "const als = new AsyncLocalStorage();\n"
          "export const kept = () => [als.run(5, () => als.getStore()), v8.deserialize(v8.serialize({ a: [1] })).a[0],\n"
          "  typeof v8.getHeapStatistics().total_heap_size];\n")


def test_nodes_ways_of_looking_into_the_process_are_taken_away(local_demos, tmp_path):
    """Each throws, by every route to it, before any workspace module loads; what reads no value of the process
    (the serializer, the statistics, AsyncLocalStorage) still works."""
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "look.js").write_text(LOOKER, encoding="utf-8")
    script = tmp_path / "t.mjs"
    script.write_text(f"import {{ outcomes }} from {json.dumps((local_demos / 'probe.mjs').as_uri())};\n"
                      "console.log(JSON.stringify(outcomes('src/look.js', [['look'], ['kept']])));\n", encoding="utf-8")

    def looked() -> list:
        r = subprocess.run([dl.exe("node"), str(script)], cwd=str(tmp_path), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, env=dict(os.environ, DEMO_WORKSPACE=str(ws)))
        assert r.returncode == 0, r.stdout + r.stderr
        return json.loads(r.stdout)

    look, kept = looked()
    assert look["ok"] and kept == {"ok": True, "value": [5, 1, "number"]}, (look, kept)
    assert {k: "taken away by the checks" in v for k, v in look["value"].items()} == dict.fromkeys(LOOK_INTO, True), look
    # The plant: without harden(), each one runs.
    child = local_demos / "probe-child.mjs"
    text = dl.read_text(child)
    assert FREEZE_BUILT_INS in text
    child.write_text(text.replace(FREEZE_BUILT_INS, "\n"), encoding="utf-8")
    look, _ = looked()
    assert look["value"] == dict.fromkeys(LOOK_INTO, "ran"), look


# ---- the copy: git history, and git kept to the copy ------------------------------------------------------

def test_a_copy_git_copy_keeps_the_history_and_drops_what_runs_commands(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    env = dict(os.environ)
    git(ws, "init", "-q", env=env)
    (ws / "a.txt").write_text("a\n", encoding="utf-8")
    commit_all(ws, "first", env)
    git(ws, "update-index", "--assume-unchanged", "a.txt", env=env)
    git(ws, "config", "core.fsmonitor", "sh -c 'echo ran > fsmonitor-ran'", env=env)
    git(ws, "config", "core.hooksPath", "elsewhere", env=env)
    git(ws, "config", "include.path", str(tmp_path / "more.gitconfig"), env=env)
    (ws / ".git" / "hooks" / "post-checkout").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    # The plant is real: in the workspace itself, `git status` runs the fsmonitor command.
    subprocess.run(["git", "-C", str(ws), "status", "--porcelain"], capture_output=True, env=env, timeout=120)
    assert (ws / "fsmonitor-ran").is_file()
    (ws / "fsmonitor-ran").unlink()
    alt = ws / ".git" / "objects" / "info" / "alternates"   # objects borrowed from a store outside the workspace
    alt.parent.mkdir(parents=True, exist_ok=True)
    alt.write_text(str(tmp_path / "other" / "objects") + "\n", encoding="utf-8")
    copy = tmp_path / "copy"
    dl.copy_workspace(ws, copy, git=True)
    cfg = dl.read_text(copy / ".git" / "config")
    assert "fsmonitor" not in cfg and "hookspath" not in cfg.lower() and "include" not in cfg, cfg
    assert not (copy / ".git" / "hooks").exists() and not (copy / ".git" / "objects" / "info" / "alternates").exists()
    r = subprocess.run(["git", "-C", str(copy), "status", "--porcelain"], capture_output=True, text=True, env=env,
                       timeout=120)
    assert r.returncode == 0 and not (copy / "fsmonitor-ran").exists(), r.stderr
    assert git(copy, "log", "--format=%s", env=env) == "first"
    assert git(copy, "ls-files", "-v", env=env).startswith("h a.txt")   # the index's flags came along
    assert git(copy, "reflog", "--format=%gs", env=env).startswith("commit (initial)")
    dl.copy_workspace(ws, tmp_path / "plain")   # an ordinary demo's copy has no .git at all
    assert not (tmp_path / "plain" / ".git").exists()


def test_git_in_a_graded_copy_never_finds_a_repo_above_it(local_demos, tmp_path, monkeypatch):
    """The copy sits in a temporary folder; were that inside a repo, a copy with no .git of its own would be
    graded on that repo's history (seen once in a brief's own runner, which then graded the kit's)."""
    above = tmp_path / "a-repo"
    above.mkdir()
    git(above, "init", "-q", env=dict(os.environ))
    monkeypatch.setattr(tempfile, "tempdir", str(above))
    runner = RUNNER_HEAD + (
        "import subprocess\nws = ak.workspace()\n"
        "def no_repo():\n"
        "    r = subprocess.run(['git', '-C', str(ws), 'rev-parse', '--show-toplevel'], capture_output=True,"
        " text=True)\n"
        "    assert r.returncode != 0, 'git found ' + r.stdout\n"
        "ak.main([('no repo', no_repo), ('b', lambda: None), ('c', lambda: None)])\n")
    make_demo(local_demos, "py-tool", dict(PY_DEMO, **{"accept/run.py": runner}))
    demo = dl.load_demo("py-tool")
    assert check.run_accept(demo, demo.dir / "reference")[0].ok
    # Without the ceiling, git does find the repo above a folder there: the ceiling is what keeps it out.
    (above / "x").mkdir()
    r = subprocess.run(["git", "-C", str(above / "x"), "rev-parse", "--show-toplevel"], capture_output=True,
                       text=True, env=dict(os.environ))
    assert r.returncode == 0 and Path(r.stdout.strip()).resolve() == above.resolve(), r.stderr


# ---- the rules ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("plant", [
    lambda kit: f"const ref = {json.dumps(str(kit / 'demos' / 'py-tool' / 'reference' / 'tool.py'))};",
    lambda kit: f"from_url = '{(kit / 'demos').as_uri()}'",
    lambda kit: "p = '" + str(kit).replace("\\", "\\\\").upper() + "'",
    lambda kit: "home = Path.home() / '.claude-starter' / 'demos'",
    lambda kit: "rec = json.load(open(os.path.expanduser('~/.agents/starter/installs.json')))",
    lambda kit: "src = open('../../demos/py-tool/reference/tool.py').read()",
])
def test_code_that_names_the_kits_files_breaks_the_rule(tmp_path, plant):
    kit = tmp_path / "it's kit"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "tool.py").write_text("print(1)\n", encoding="utf-8")
    (ws / "README.md").write_text(f"Run `python {kit / 'scripts' / 'starter.py'} demo check py-tool`.\n",
                                  encoding="utf-8")
    (ws / "package.json").write_text(json.dumps({"scripts": {"test": f'node "{kit}/demos/npm-test.mjs"'}}),
                                     encoding="utf-8")
    assert check.kit_reference_problems(ws, "py-tool", kit) == []   # docs and the launcher's `test` may name it
    (ws / "src.js").write_text("// a module\n" + plant(kit) + "\n", encoding="utf-8")
    probs = check.kit_reference_problems(ws, "py-tool", kit)
    assert len(probs) == 1 and probs[0].startswith("src.js:2: names the kit's files"), probs


def test_a_package_json_field_naming_the_kit_breaks_the_rule(tmp_path):
    kit = tmp_path / "kit"
    ws = tmp_path / "ws"
    ws.mkdir()
    pkg = {"scripts": {"test": f'node "{kit}/demos/npm-test.mjs"'}, "imports": {"#ref": str(kit / "demos")}}
    (ws / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    assert check.kit_reference_problems(ws, "x", kit)


def test_ignored_reads_gits_plain_patterns():
    pats = ["frames/", "*.mp4", "/out", "docs/*.png"]
    yes = ["frames/f_0001.png", "a/frames/x.png", "clip.mp4", "deep/clip.mp4", "out/a.png", "docs/x.png"]
    no = ["frames.png", "src/out/a.png", "docs/sub/x.png", "src/a.png", "framesx/a.png"]
    assert [p for p in yes if not dl.ignored(p, pats)] == [] and [p for p in no if dl.ignored(p, pats)] == []


def test_the_asset_rule_leaves_what_the_skeleton_ignores_alone(local_demos, tmp_path):
    make_demo(local_demos, "py-tool", dict(PY_DEMO, **{"skeleton/.gitignore": "frames/\n*.mp4\n"}))
    demo = dl.load_demo("py-tool")
    ws = tmp_path / "ws"
    write_tree(ws, {"tool.py": "print(1)\n", "frames/frame_0001.png": b"\x89PNG\r\n\x1a\n", "clip.mp4": b"\0\0"})
    assert check.asset_problems(ws, dl.skeleton_ignores(demo)) == []
    (ws / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")   # the plant: an asset the skeleton does not ignore
    assert check.asset_problems(ws, dl.skeleton_ignores(demo)) == ["logo.png: an image file"]
    assert len(check.asset_problems(ws)) == 3   # without the skeleton's patterns, the output counts too
    make_demo(local_demos, "py-tool", dict(PY_DEMO, **{"skeleton/.gitignore": "frames/\n!frames/keep.png\n"}))
    with pytest.raises(dl.DemoError, match="plain patterns only"):
        dl.skeleton_ignores(dl.load_demo("py-tool"))


def test_python_bytecode_is_never_graded(tmp_path):
    write_tree(tmp_path, {"tool.py": "print(1)\n", "__pycache__/tool.cpython-312.pyc": b"\x00\x01binary"})
    assert check.asset_problems(tmp_path) == [] and [p.name for p in dl.walk(tmp_path)] == ["tool.py"]
    (tmp_path / "stray.pyc").write_bytes(b"\x00\x01")   # bytecode outside the cache is still binary content
    assert check.asset_problems(tmp_path) == ["stray.pyc: binary content"]


def test_a_python_demos_one_entry_point_is_the_launcher(tmp_path):
    ws = tmp_path / "ws"
    write_tree(ws, {"tool.py": "print(1)\n"})
    assert check.entry_point_problems(ws, "py-tool", python=True) == []
    (ws / "package.json").write_text(json.dumps({"scripts": {"test": "python -m unittest"}}), encoding="utf-8")
    assert check.entry_point_problems(ws, "py-tool", python=True) == ["package.json: a test script, 'test', beside "
                                                                        "the launcher"]
    (ws / "package.json").unlink()
    (ws / "tox.ini").write_text("[tox]\n", encoding="utf-8")
    assert check.entry_point_problems(ws, "py-tool", python=True) == ["tox.ini: a second way to run the tests"]


# ---- start.py and check.py on the new kinds of demo, end to end ------------------------------------------

def test_a_python_demo_starts_without_package_json_and_names_the_launcher(fake_kit, fhome):
    kit, _ = fake_kit
    ws, r = started(kit, fhome, "py-tool")
    assert not (ws / "package.json").exists() and (ws / "CLAUDE.md").is_file()
    rules = dl.read_text(ws / "CLAUDE.md")
    assert "demo check py-tool" in rules and "npm test" not in rules and "unittest" in rules, rules
    assert "wrote CLAUDE.md, made a git repo" in r.stdout and "rather than `npm test`" not in r.stdout
    g = run(kit, "check.py", "py-tool", home=fhome, cwd=ws)
    assert g.returncode == 1 and verdict(g.stdout) == "FAIL 5/8", g.stdout + g.stderr
    assert "ok    rule: one test entry point, the launcher its rules file names" in g.stdout
    rec = record_line(g.stdout)
    assert "recordable=yes" in rec and f"python={'.'.join(map(str, sys.version_info[:3]))}" in rec
    (ws / "tool.py").write_text("import sys\nprint(int(sys.argv[1]) * 2)\n", encoding="utf-8")
    (ws / "__pycache__").mkdir()
    (ws / "__pycache__" / "tool.cpython-39.pyc").write_bytes(b"\x00bytecode")   # what running its tests leaves
    g = run(kit, "check.py", "py-tool", home=fhome, cwd=ws)
    assert g.returncode == 0 and verdict(g.stdout) == "PASS 8/8", g.stdout + g.stderr


def test_a_mixed_demo_keeps_the_skeletons_package_json_and_names_each_lanes_rules_file(fake_kit, fhome):
    kit, _ = fake_kit
    ws, r = started(kit, fhome, "two-lanes", tool="claude")
    pkg = json.loads(dl.read_text(ws / "package.json"))
    assert pkg["type"] == "module" and pkg["engines"] == {"node": ">=22.13"} and pkg["scripts"]["serve"]
    assert pkg["name"] == "two-lanes" and dl.test_script_problem(pkg["scripts"]["test"], "two-lanes", ws, kit) is None
    assert (ws / "frontend" / "CLAUDE.md").is_file() and not (ws / "frontend" / "AGENTS.md").exists()
    assert (ws / "backend" / "CLAUDE.md").is_file() and (ws / "CLAUDE.md").is_file()
    assert "This demo takes 2 sessions" in r.stdout and "Read BRIEF.md and do session 2." in r.stdout
    assert git(ws, "status", "--porcelain", env=clean_env(fhome)) == ""   # one commit holds all of it
    ws2 = fhome / "elsewhere"
    r = run(kit, "start.py", "two-lanes", "--tool", "opencode", "--dir", str(ws2), home=fhome)
    assert r.returncode == 0 and (ws2 / "frontend" / "AGENTS.md").is_file() and not (ws2 / "frontend" / "CLAUDE.md").exists()
    g = run(kit, "check.py", "two-lanes", home=fhome, cwd=ws)
    assert verdict(g.stdout) == "FAIL 5/7", g.stdout + g.stderr


# Where the workspace's code can learn the kit's path, and the words demos/MEASURING.md's "Where the kit is" uses for
# each. The list once left out the workspace's own rules file, the shortest route: a Python workspace that read the
# launcher's path there and ran the kit's reference got a recordable PASS, by a route no text named.
KIT_ROUTES = {"the rules file": "rules file names the launcher", "package.json's test": "`package.json` `test`",
              "a probe's command line": "probe process's own command line", "the process list": "process list",
              "the install record": "install record"}


def routes_measuring_omits(text: str) -> list[str]:
    parts = text.split("\n- Where the kit is.")
    section = " ".join(parts[1].split("\n- ")[0].split()) if len(parts) == 2 else ""
    return [route for route, words in KIT_ROUTES.items() if words not in section]


def test_measuring_names_where_a_workspace_learns_the_kits_path(fake_kit, fhome):
    kit, _ = fake_kit
    path = dl.kit_text(kit.resolve().as_posix())
    ws, _ = started(kit, fhome, "py-tool")
    # A python demo's test command is the launcher's, its bash form first, quoted for a shell (an apostrophe in a
    # user name splits the path's text).
    bash = next(ln.strip().strip("`") for ln in dl.read_text(ws / "CLAUDE.md").split("\n") if "demo check" in ln)
    assert path in dl.kit_text(shlex.split(bash)[1]), bash
    ws, _ = started(kit, fhome, "two-lanes")
    assert path in dl.kit_text(json.loads(dl.read_text(ws / "package.json"))["scripts"]["test"])
    text = dl.read_text(DEMOS / "MEASURING.md")
    assert routes_measuring_omits(text) == []
    planted = text.replace("A python demo's rules file names the launcher", "A python demo's brief names the launcher")
    assert planted != text and routes_measuring_omits(planted) == ["the rules file"]


def test_a_git_graded_demo_is_graded_on_its_own_history(fake_kit, fhome):
    kit, _ = fake_kit
    ws, _ = started(kit, fhome, "git-log")
    env = clean_env(fhome)
    g = run(kit, "check.py", "git-log", home=fhome, cwd=ws)
    assert verdict(g.stdout) == "FAIL 7/9", g.stdout + g.stderr   # own repo, clean, the rules; not 2 commits
    (ws / "notes.py").write_text("NOTES = ['first']\n", encoding="utf-8")
    git(ws, "add", "-A", env=env)
    git(ws, "-c", "user.name=t", "-c", "user.email=t@localhost", "-c", f"core.hooksPath={fhome / 'no-hooks'}",
        "commit", "-q",
        "-m", "feat: add a note", "-m", "Verified: python -m unittest -> OK", env=env)
    g = run(kit, "check.py", "git-log", home=fhome, cwd=ws)
    assert verdict(g.stdout) == "PASS 9/9", g.stdout + g.stderr
    (ws / "notes.py").write_text("NOTES = []\n", encoding="utf-8")   # uncommitted work is seen in the copy
    g = run(kit, "check.py", "git-log", home=fhome, cwd=ws)
    assert "FAIL  nothing left uncommitted" in g.stdout, g.stdout


def test_ci_re_grades_a_python_run_before_it_admits_it(fake_kit, fhome, tmp_path, monkeypatch):
    kit, kenv = fake_kit
    monkeypatch.setattr(dl, "DEMOS", kit / "demos")   # costs.json is read in this process: its demos are the kit's
    ws, _ = started(kit, fhome, "py-tool")
    wenv = clean_env(fhome)
    skeleton = git(ws, "rev-parse", "HEAD", env=wenv)
    (ws / "tool.py").write_text("import sys\nprint(int(sys.argv[1]) * 2)\n", encoding="utf-8")
    done = commit_all(ws, "feat: double", wenv)
    bundle = kit / "demos" / "runs" / "py-tool-test.bundle"
    bundle.parent.mkdir(exist_ok=True)
    git(ws, "bundle", "create", str(bundle), "--all", env=wenv)
    sha = git(kit, "rev-parse", "HEAD", env=kenv)
    row = {"demo": "py-tool", "tool": "claude", "plan": "max", "model": "m", "effort": "high", "tool_version": "1",
           "kit_sha": sha, "accept_hash": dl.grading_tree("py-tool", sha, kit=kit),
           "workspace": "runs/py-tool-test.bundle", "workspace_sha": done, "date": "2026-11-16",
           "mode": "interactive", "meter_delta": {"weekly_pct": 1}, "tokens": None, "wall_min": 5, "sessions": 1,
           "accept": "PASS 8/8", "claimed_done": True, "verifier": "ran", "checkpoint": "ran", "no_commit": False}
    costs = tmp_path / "costs.json"
    try:
        costs.write_text(json.dumps({"runs": [row]}), encoding="utf-8")
        assert dl.load_costs(costs, strict=True, kit=kit) == [row]
        costs.write_text(json.dumps({"runs": [dict(row, workspace_sha=skeleton)]}), encoding="utf-8")
        with pytest.raises(dl.CostsError, match=r"gives FAIL 5/8, not the row's PASS 8/8"):
            dl.load_costs(costs, strict=True, kit=kit)
    finally:
        bundle.unlink()


# ---- the mutants engine ------------------------------------------------------------------------------------

def mutate(kit: Path, home: Path, name: str, *args: str) -> subprocess.CompletedProcess:
    return run(kit, "mutants.py", name, "--jobs", "2", *args, home=home)


def test_the_mutants_engine_passes_a_list_that_binds(fake_kit, fhome):
    kit, _ = fake_kit
    for name, killed, legal in (("py-tool", "KILLED 2/2", "LEGAL PASS 1/1"), ("git-log", "KILLED 2/2", None),
                                ("two-lanes", "KILLED 1/1", None)):
        r = mutate(kit, fhome, name)
        assert r.returncode == 0 and killed in r.stdout and r.stdout.rstrip().endswith("MUTANTS OK"), \
            r.stdout + r.stderr
        assert "reference: PASS" in r.stdout and "skeleton: FAIL" in r.stdout
        if legal:
            assert legal in r.stdout
    listed = run(kit, "mutants.py", "--list", home=fhome)
    assert {"py-tool", "git-log", "two-lanes", "roulette-loom", "fair-share"} <= set(json.loads(listed.stdout))


def plant_case(kit: Path, rel: str, data) -> Path:
    p = kit / "demos" / "py-tool" / "accept" / "mutants" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return p


@pytest.mark.parametrize("rel, data, code, said", [
    ("003-harmless.json", {"id": "003", "graded_item": 1, "description": "a harmless comment", "file": "tool.py",
                           "find": "print(2 * n)", "replace": "print(2 * n)  # same"}, 1, "survivor: 003"),
    ("003-stale.json", {"id": "003", "graded_item": 1, "description": "stale", "file": "tool.py",
                        "find": "print(3 * n)", "replace": "x"}, 2, "occurs 0 times"),
    ("003-broken.json", {"id": "003", "graded_item": 1, "description": "does not parse", "file": "tool.py",
                         "find": "print(2 * n)", "replace": "print(2 * n"}, 2, "does not parse"),
    ("003-wrong-reason.json", {"id": "003", "graded_item": 1, "description": "killed elsewhere", "file": "tool.py",
                               "find": "print(2 * n)", "replace": "print(2 * n + 1)", "expect": ["no such check"]},
     1, "not no such check"),
    ("legal/l02-bad.json", {"id": "L02", "description": "not legal at all", "file": "tool.py",
                            "find": "print(2 * n)", "replace": "print(n)"}, 1, "legal FAILED: L02"),
    ("003-not-graded.json", {"id": "003", "graded_item": 9, "description": "no such item", "file": "tool.py",
                             "find": "print(2 * n)", "replace": "print(n)"}, 2, "graded_item 9 is not"),
    ("003-dup.json", {"id": "001", "graded_item": 1, "description": "dup", "file": "tool.py",
                      "find": "print(2 * n)", "replace": "print(n)"}, 2, "used more than once: 001"),
    ("003-bad.json", "{not json", 2, "003-bad.json"),
])
def test_the_mutants_engine_fails_a_list_that_does_not_bind(fake_kit, fhome, rel, data, code, said):
    kit, _ = fake_kit
    planted = plant_case(kit, rel, data)
    try:
        r = mutate(kit, fhome, "py-tool")
    finally:
        planted.unlink()
    assert r.returncode == code and said in r.stdout + r.stderr, r.stdout + r.stderr
    assert "MUTANTS OK" not in r.stdout


def test_the_mutants_engine_needs_every_graded_item_reached(fake_kit, fhome):
    kit, _ = fake_kit
    m = kit / "demos" / "py-tool" / "accept" / "mutants" / "002-no-sign.json"
    saved = m.read_bytes()
    m.unlink()
    try:
        r = mutate(kit, fhome, "py-tool")
        assert r.returncode == 1 and "Graded items 2 have no mutant" in r.stdout, r.stdout + r.stderr
        r = mutate(kit, fhome, "py-tool", "--only", "001")   # a filtered run skips the coverage check
        assert r.returncode == 0, r.stdout + r.stderr
    finally:
        m.write_bytes(saved)


def test_the_mutants_engine_fails_a_reference_that_fails_and_a_skeleton_that_passes(fake_kit, fhome):
    kit, _ = fake_kit
    ref = kit / "demos" / "py-tool" / "reference" / "tool.py"
    skel = kit / "demos" / "py-tool" / "skeleton" / "tool.py"
    saved = ref.read_bytes(), skel.read_bytes()
    try:
        skel.write_bytes(saved[0])   # the skeleton already does the work
        r = mutate(kit, fhome, "py-tool")
        assert r.returncode == 1 and "skeleton: PASS 3/3" in r.stdout, r.stdout
    finally:
        ref.write_bytes(saved[0])
        skel.write_bytes(saved[1])


def test_a_demos_own_mutants_runner_must_end_with_mutants_ok(fake_kit, fhome):
    kit, kenv = fake_kit
    d = kit / "demos" / "py-tool"
    runner = d / "accept" / "mutants" / "run.py"
    js = d / "demo.json"
    saved = js.read_bytes()
    runner.write_text(
        "import os, subprocess, sys\n"
        "r = subprocess.run([os.environ['DEMO_PYTHON'], os.environ['DEMO_CHECK'], os.environ['DEMO_NAME'],\n"
        "                    '--accept-only', '--dir', os.path.join(os.environ['DEMO_DIR'], 'reference')],\n"
        "                   capture_output=True, text=True)\n"
        "print(r.stdout)\n"
        "print('MUTANTS OK' if r.returncode == 0 and 'PASS 3/3' in r.stdout else 'MUTANTS NOT OK')\n",
        encoding="utf-8")
    try:
        js.write_text(json.dumps(dict(json.loads(saved), mutants_runner="demos/py-tool/accept/mutants/run.py")),
                      encoding="utf-8")
        r = mutate(kit, fhome, "py-tool")
        assert r.returncode == 0 and "ACCEPT ONLY" in r.stdout and r.stdout.rstrip().endswith("MUTANTS OK"), \
            r.stdout + r.stderr
        runner.write_text("print('KILLED 0/1')\n", encoding="utf-8")   # the plant: it never says OK
        r = mutate(kit, fhome, "py-tool")
        assert r.returncode == 1 and r.stdout.rstrip().endswith("MUTANTS NOT OK"), r.stdout
    finally:
        js.write_bytes(saved)
        runner.unlink()


# ---- the kit's own demo files ------------------------------------------------------------------------------

def imports_in_process(source: str) -> list[int]:
    """Lines of a Python accept file that would bring the workspace's code into the checks' process: exec or eval,
    __import__, importlib's import_module, spec_from_file_location or exec_module, runpy."""
    import ast
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in ("exec", "eval", "__import__", "import_module", "spec_from_file_location", "exec_module",
                        "run_path", "run_module", "module_from_spec"):
                bad.append(node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                                                     else [])
            if any(m and m.split(".")[0] == "runpy" for m in mods):
                bad.append(node.lineno)
    return bad


def test_python_checks_never_import_the_workspace():
    assert imports_in_process("import importlib.util\nspec = importlib.util.spec_from_file_location('m', p)\n") == [2]
    assert imports_in_process("exec(open(ws / 'tool.py').read())\n") == [1]
    assert imports_in_process("import runpy\n") == [1]
    assert imports_in_process(PY_RUNNER) == [] and imports_in_process(GIT_RUNNER) == []
    for name in dl.demo_names():
        acc = dl.load_demo(name).dir / "accept"
        for f in sorted(acc.rglob("*.py")):
            if "mutants" not in f.relative_to(acc).parts:   # a mutants runner never runs the workspace's code
                assert imports_in_process(dl.read_text(f)) == [], f


def js_imports_outside(source: str) -> list[str]:
    """What, in a kit file of accept/ that runs in an asserting process, could load the workspace's code there: a
    dynamic import(), or an import of anything but a node: builtin, the kit's probe.mjs or a file of accept/."""
    bad = re.findall(r"\bimport\s*\(", source)
    for spec in re.findall(r"""^\s*(?:import|export)\b[^'"]*?\bfrom\s*['"]([^'"]+)['"]|^\s*import\s*['"]([^'"]+)['"]""",
                           source, re.M):
        s = spec[0] or spec[1]
        if not (s.startswith("node:") or s == "../../probe.mjs" or (s.startswith("./") and ".." not in s)):
            bad.append(s)
    return bad


def test_node_checks_reach_the_workspace_only_through_the_probe():
    assert js_imports_outside("import { split } from '../src/share.js';\n") == ["../src/share.js"]
    assert js_imports_outside("const m = await import(url);\n") == ["import("]
    assert js_imports_outside("export * from '../../reference/x.js';\n") == ["../../reference/x.js"]
    assert js_imports_outside("import { run } from './helpers.mjs';\n") == []   # a file of accept/, held here too
    assert js_imports_outside(SCENARIO_TEST) == [] and js_imports_outside(SCENARIO) == []
    # The asserting side's probe imports builtins only; probe-child.mjs, in a process of its own, is the one file
    # that imports the workspace.
    assert js_imports_outside(dl.read_text(DEMOS / "probe.mjs")) == []
    assert "import(" in dl.read_text(DEMOS / "probe-child.mjs")
    for name in dl.demo_names():
        acc = dl.load_demo(name).dir / "accept"
        for f in sorted([*acc.rglob("*.mjs"), *acc.rglob("*.js")]):
            if "mutants" not in f.relative_to(acc).parts:
                assert js_imports_outside(dl.read_text(f)) == [], f


@pytest.mark.parametrize("name", dl.demo_names())
def test_each_demo_json_and_skeleton_hold(name):
    demo = dl.load_demo(name)
    dl.skeleton_package(demo)
    dl.skeleton_ignores(demo)
    mutants_, legal = mutants.load_cases(demo)
    assert mutants_ or demo.mutants_runner != dl.KIT_MUTANTS, "the kit's engine needs a mutant list"
    bad, _ = mutants.coverage_problems(demo, mutants_)
    assert bad == []
    for case in mutants_ + legal:   # each find applies once to the reference as shipped
        with tempfile.TemporaryDirectory() as td:
            shutil.copytree(str(demo.dir / "reference"), str(Path(td) / "ref"))
            mutants.apply_edits(Path(td) / "ref", case)
    for part in ("skeleton", "reference"):
        assert check.kit_reference_problems(demo.dir / part, name) == [], part


def test_every_doc_the_demo_scripts_cite_exists():
    """The scripts' messages and docstrings send authors to demos/AUTHORING.md and readers to demos/MEASURING.md;
    AUTHORING.md was cited for a whole branch before it was written."""
    cited = set()
    for f in sorted([*DEMOS.glob("*.py"), *DEMOS.glob("*.mjs")]):
        text = dl.read_text(f)
        cited |= set(re.findall(r"\bdemos/([A-Z][A-Z_]*\.md)\b", text))
        cited |= {"AUTHORING.md"} & set(re.findall(r"\b[A-Z][A-Z_]*\.md\b", text))
    assert {"AUTHORING.md", "MEASURING.md"} <= cited
    assert [c for c in sorted(cited) if not (DEMOS / c).is_file()] == []


def job_block(workflow: str, name: str) -> str:
    """The lines of job `name`, up to the next line indented two spaces (the next job or its comment)."""
    lines = workflow.split("\n")
    start = lines.index(f"  {name}:") + 1
    end = next((i for i in range(start, len(lines)) if re.match(r"  \S", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def runs_at_the_floors(job: str) -> bool:
    """Whether a matrix job has a leg at Python PY_FLOOR and Node NODE_FLOOR exactly, and its setup steps use the
    leg's versions."""
    py, node = ".".join(map(str, dl.PY_FLOOR)), f"{dl.NODE_FLOOR_TEXT}.0"
    leg = re.search(rf'- os: \S+\n\s+python: "{re.escape(py)}"\n\s+node: "{re.escape(node)}"\n', job)
    return bool(leg) and "python-version: ${{ matrix.python }}" in job and "node-version: ${{ matrix.node }}" in job


def test_ci_runs_the_demo_tests_at_the_floors_too():
    """demos/tests once passed on the newest Node 22 in CI and failed at 22.13, where only a person running them
    by hand saw it."""
    job = job_block(dl.read_text(KIT / ".github" / "workflows" / "adapters.yml"), "demos")
    assert runs_at_the_floors(job), job
    assert "python -m pytest -q -rs demos/tests" in job
    planted = re.sub(r"\n\s+include:\n(?:\s+.*\n)+?(?=\s+steps:)", "\n", job)   # the leg dropped
    assert planted != job and not runs_at_the_floors(planted)


def test_ci_runs_every_demos_mutants_at_the_floors():
    wf = dl.read_text(KIT / ".github" / "workflows" / "adapters.yml")
    job = job_block(wf, "demo-mutants")
    assert 'python demos/mutants.py "${{ matrix.demo }}"' in job and "fromJSON(needs.demo-list" in job, job
    assert f'python-version: "{".".join(map(str, dl.PY_FLOOR))}"' in job
    assert f'node-version: "{dl.NODE_FLOOR_TEXT}.0"' in job and "node-version: \"22\"" not in job
    assert "python demos/mutants.py --list" in job_block(wf, "demo-list")
