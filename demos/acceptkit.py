"""What a demo's Python accept runner (demo.json's accept_runner, a .py file in accept/) is built from.

check.py starts the runner as `<DEMO_PYTHON> -I -S -B -X utf8 <kit>/demos/<name>/accept/<runner>.py`, from a
temporary folder, with DEMO_WORKSPACE naming a copy of the workspace that sits outside the workspace and the kit.
-I keeps the runner's own folder off sys.path, so the runner puts this folder and its own there itself:

    import sys
    from pathlib import Path
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)]
    import acceptkit as ak
    import test_mine                      # the held-out checks, next to the runner
    ak.main(test_mine.TESTS)              # [(name, function), ...]; exits

The checks never import the workspace's code into their own process: it could replace assert, or anything else
the checks use, and pass every one. They run it in processes of its own (run(), with python_argv() and
child_env()) and assert on what comes back. Python has no permission model like Node's, so the workspace's code
can read and run any file the person at the keyboard can, the kit's reference/ included. The copy in a temporary
folder, no variable naming the clone (demolib.scrubbed_env), child_env()'s empty HOME and no DEMO_ variable, and
check.py's rule against code that names the kit's files make that a step, not a wall: demos/MEASURING.md
("Python code that finds the kit") says what still leads there, and that only reading the workspace's code
catches it.

The results go to check.py as one line per check on stdout, tagged with DEMO_RESULT_TOKEN, which no process of the
workspace's is given, so a line the workspace prints is not a result. The exit code must agree with them: 0 when
every check passed, 1 when any failed, 2 when the checks could not run (check.py then counts each as not run).
Python 3.9+, standard library only.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Optional, Sequence

sys.dont_write_bytecode = True   # a __pycache__ in the kit's accept/ would change its grading hash

_SCRATCH: list = []


def workspace() -> Path:
    """The copy of the workspace under grade. Exits 2 when DEMO_WORKSPACE is not an absolute folder."""
    ws = os.environ.get("DEMO_WORKSPACE", "")
    if not ws or not os.path.isabs(ws) or not os.path.isdir(ws):
        print(f"DEMO_WORKSPACE must be the absolute path of a folder (got {ws!r}); run this through demos/check.py",
              file=sys.stderr)
        sys.exit(2)
    return Path(ws)


def program(name: str) -> str:
    """The full path check.py found for `name` (python, node or git: DEMO_PYTHON, DEMO_NODE, DEMO_GIT), never
    one looked up on PATH, which on Windows starts with the current folder. Exits 2 when there is none."""
    var = {"python": "DEMO_PYTHON", "node": "DEMO_NODE", "git": "DEMO_GIT"}[name]
    p = os.environ.get(var, "")
    if not p or not os.path.isabs(p) or not os.path.isfile(p):
        print(f"{var} must be the absolute path of {name} (got {p!r}); run this through demos/check.py",
              file=sys.stderr)
        sys.exit(2)
    return p


def python() -> str:
    """The validated Python, by absolute path (DEMO_PYTHON)."""
    return program("python")


def python_argv(*args: str, stdlib_only: bool = False) -> list:
    """argv that runs the workspace's Python: no user site-packages, no bytecode written into the copy. With
    stdlib_only, -S too: no site-packages at all, so a third-party import fails, as does the `exit()` builtin that
    the site module adds (a brief that uses it must say to use sys.exit)."""
    return [python(), "-s", "-B", *(["-S"] if stdlib_only else []), *args]


def scratch() -> Path:
    """A new empty folder outside the copy, removed when the runner exits: a cwd, a HOME, an --out folder."""
    d = Path(tempfile.mkdtemp(prefix="demo-scratch-"))
    _SCRATCH.append(d)
    return d


@atexit.register
def _cleanup() -> None:
    for d in _SCRATCH:
        shutil.rmtree(str(d), ignore_errors=True)


def child_env(**extra: str) -> dict:
    """The environment for a process of the workspace's: none of the DEMO_ variables (DEMO_RESULT_TOKEN among
    them), none that load code into Python or Node, git kept to the copy, and HOME pointing at an empty folder."""
    home = scratch()
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("DEMO_", "PYTHON", "NPM_")) and k not in ("NODE_OPTIONS", "NODE_PATH")}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    env.update(extra)
    return env


def run(argv: Sequence[str], timeout: float, cwd: Optional[Path] = None, env: Optional[dict] = None,
        input: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a process of the workspace's and capture its output (never inherit the runner's stdout, where results
    go), from `cwd` (default: a scratch folder, never the copy), with child_env() unless `env` is given. A process
    still running after `timeout` seconds is killed and raises subprocess.TimeoutExpired."""
    return subprocess.run(list(argv), cwd=str(cwd or scratch()), env=child_env() if env is None else env,
                          input=input, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=None if input is not None else subprocess.DEVNULL, timeout=timeout)


def result_line(name: str, ok: bool, detail: str = "") -> str:
    """One check's result as check.py reads it (the shape demos/reporter.mjs writes for node --test)."""
    return json.dumps({"demo_event": "test", "token": os.environ.get("DEMO_RESULT_TOKEN"), "ok": bool(ok),
                       "name": name, "nesting": 0, "kind": "test", "file": None, "error": None if ok else detail})


def _why(exc: BaseException) -> str:
    if isinstance(exc, AssertionError):
        return str(exc).strip() or "assertion failed"
    return traceback.format_exception_only(type(exc), exc)[-1].strip()


def main(tests: Sequence, failfast: Optional[bool] = None) -> None:
    """Run each (name, function) in order, print one result line for each and exit 0 or 1. A function passes
    when it returns, and fails on any exception, its first line the reason. With DEMO_FAILFAST set (the mutants
    engine sets it when only a FAIL matters) the checks after the first failure are not run; check.py counts
    them as not run, which is still a FAIL. A name may hold no line break; each must differ."""
    workspace()
    names = [n for n, _ in tests]
    if not names or len(set(names)) != len(names) or any("\n" in n for n in names):
        print("the checks need one distinct name each", file=sys.stderr)
        sys.exit(2)
    stop = bool(os.environ.get("DEMO_FAILFAST")) if failfast is None else failfast
    failed = False
    for name, fn in tests:
        try:
            fn()
            ok, why = True, ""
        except Exception as exc:  # a crash in the workspace's code or in a check is that check's failure
            ok, why = False, _why(exc)
        print(result_line(name, ok, why.split("\n")[0][:500]), flush=True)
        failed = failed or not ok
        if failed and stop:
            break
    sys.exit(1 if failed else 0)
