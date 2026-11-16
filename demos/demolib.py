"""What demos/start.py, check.py and pick.py share: the demo catalogue, the install record, Node, the hash of
the files that grade a demo, the originality denylist and the measured runs in costs.json.

A demo is a folder demos/<name>/ holding demo.json (what the picker and the scripts need to know), BRIEF.md
(the brief, then what the person at the keyboard watches for), skeleton/ (copied into the workspace),
accept/ (the held-out checks, run from the kit, never copied) and reference/ (one solution that passes
accept/; CI runs it, and check.py compares a workspace with it, but it is never copied either). <name> and
demo.json's `app` are what the workspace sees; `title` is the name the person picks it by, and it can say
what the demo tests, so it never reaches the workspace.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator, Optional

sys.dont_write_bytecode = True  # a check leaves the clone as it was: no __pycache__, no git objects, no index
DEMOS = Path(__file__).resolve().parent
KIT = DEMOS.parent
sys.path.insert(0, str(KIT / "scripts"))
import install  # noqa: E402
import vocab  # noqa: E402

# The oldest Node the demos support: 22.13, the first 22.x LTS whose permission model (`--permission`) is
# stable. probe.mjs runs the workspace's code under it; older 22.x builds spell the flag differently. CI's
# demos job runs on the newest 22.x.
NODE_FLOOR = (22, 13)
NODE_FLOOR_TEXT = ".".join(map(str, NODE_FLOOR))
TIERS = {"S": "small", "M": "medium", "L": "large", "teaching": "teaching"}
TIER_ORDER = ("S", "M", "L", "teaching")
NEEDS_NODE = {"browser": True, "node": True, "python": False}
DEMO_KEYS = {"title", "app", "tier", "stack", "summary", "kickoff", "not_checked", "accept_count"}
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# BRIEF.md holds the brief, this line, then what the person watches for. start.py copies the part above it into
# the workspace and prints the part below it, so the agent is not told what the person is watching for.
WATCH_MARK = "<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->"
# The files whose content decides a demo's grade. check.py hashes them (the RECORD's accept_hash), refuses to
# grade while they differ from the clone's last commit, and costs.json admits a run only when the hash
# matches the tree at the run's kit_sha.
GRADERS = ("demos/check.py", "demos/demolib.py", "demos/reporter.mjs", "demos/npm-test.mjs", "demos/probe.mjs",
           "demos/probe-child.mjs", "demos/denylist.txt")
SKIP_DIRS = {".git", "node_modules"}
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git's hash of a tree with nothing in it


class DemoError(Exception):
    """A demo's own files are wrong. The kit's fault, not the workspace's."""


@dataclass(frozen=True)
class Demo:
    name: str
    title: str
    app: str
    tier: str
    stack: str
    summary: str
    kickoff: str
    not_checked: str
    accept_count: int

    @property
    def dir(self) -> Path:
        return DEMOS / self.name

    @property
    def needs_node(self) -> bool:
        return NEEDS_NODE[self.stack]

    @property
    def size(self) -> str:
        return TIERS[self.tier]


def demo_names() -> list[str]:
    return sorted(p.parent.name for p in DEMOS.glob("*/demo.json"))


def load_demo(name: str) -> Demo:
    if not NAME.fullmatch(name or "") or not (DEMOS / name / "demo.json").is_file():
        raise KeyError(name)
    where = f"demos/{name}/demo.json"
    data = json.loads((DEMOS / name / "demo.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != DEMO_KEYS:
        raise DemoError(f"{where}: keys must be {', '.join(sorted(DEMO_KEYS))}")
    if data["tier"] not in TIERS or data["stack"] not in NEEDS_NODE:
        raise DemoError(f"{where}: tier is one of {', '.join(TIERS)} and stack one of {', '.join(NEEDS_NODE)}")
    if not isinstance(data["accept_count"], int) or data["accept_count"] < 1:
        raise DemoError(f"{where}: accept_count is the number of held-out checks in accept/")
    if not all(isinstance(data[k], str) and data[k] for k in DEMO_KEYS - {"accept_count"}):
        raise DemoError(f"{where}: every value but accept_count is a non-empty string")
    for part in ("BRIEF.md", "skeleton", "accept"):
        if not (DEMOS / name / part).exists():
            raise DemoError(f"demos/{name}/{part} is missing")
    return Demo(name=name, **data)


def all_demos() -> list[Demo]:
    return sorted((load_demo(n) for n in demo_names()), key=lambda d: (TIER_ORDER.index(d.tier), d.title))


def split_brief(demo: Demo) -> tuple[str, str]:
    """(the brief the agent reads, what the person watches for)."""
    text = (demo.dir / "BRIEF.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    if text.count(WATCH_MARK) != 1:
        raise DemoError(f"demos/{demo.name}/BRIEF.md must hold the line {WATCH_MARK!r} exactly once")
    brief, watch = text.split(WATCH_MARK)
    return brief.rstrip("\n") + "\n", watch.strip("\n")


def unknown_demo(name: str) -> str:
    return f"error: no demo called {name!r}. The demos are: {', '.join(demo_names())}."


# --------------------------------------------------------------------------
# The install record and the launcher
# --------------------------------------------------------------------------

def global_tools(rec: Optional[dict]) -> list[str]:
    """The tools the record says are installed globally. A Cursor install with --project reaches one repo only."""
    return sorted({i["tool"] for i in (rec or {}).get("installs") or [] if not i.get("project")})


def launcher(*words: str) -> tuple[str, str]:
    """(bash, PowerShell) for `python <kit>/scripts/starter.py <words>`."""
    return install.launcher_lines(*words)


def npm_test_files(root: Path) -> tuple[Path, Path]:
    """(npm-test.mjs, starter.py) of the kit at `root`: what a workspace's `test` script runs."""
    return root / "demos" / "npm-test.mjs", root / "scripts" / "starter.py"


def workspace_test_script(name: str, root: Path, python: str) -> str:
    """package.json's `test`: a bare `node` (npm on Windows cannot start a script with a quoted program) running
    the kit's npm-test.mjs, which starts the quoted launcher's `demo check <name>` with the quoted Python."""
    shim, starter = npm_test_files(root)
    return f'node "{shim}" "{python}" "{starter}" demo check {name}'


TEST_SCRIPT = re.compile(r'node "([^"]+)" "([^"]+)" "([^"]+)" demo check (\S+)')
PYTHON_NAME = re.compile(r"python(?:\d+(?:\.\d+)*)?(?:\.exe)?", re.I)


def test_script_problem(script: str, name: str, ws: Optional[Path], root: Optional[Path]) -> Optional[str]:
    """Why `script` is not a `test` that workspace_test_script could have written for demo `name`, or None.
    The kit's two files must be the ones at `root`, this kit by default; with root None (CI's re-grade of a
    workspace another clone made) they must sit in one absolute folder of that layout. The Python may be any
    absolute path named like one, outside the workspace: npm-test.mjs starts it, so a workspace file there
    would be a test runner of the agent's own."""
    m = TEST_SCRIPT.fullmatch(script)
    if not m or m.group(4) != name:
        return f"it is not the shape demos/start.py writes (node, npm-test.mjs, Python, starter.py, `demo check {name}`)"
    shim, python, starter = (Path(m.group(i)) for i in (1, 2, 3))
    if not (shim.is_absolute() and starter.is_absolute()):
        return "it names npm-test.mjs or starter.py by a relative path, not the kit's"
    if root is not None:
        want = npm_test_files(root.resolve())
        if (shim.resolve(), starter.resolve()) != want:
            return f"it runs {shim} and {starter}, not this kit's {want[0]} and {want[1]}"
    elif npm_test_files(shim.parent.parent) != (shim, starter):
        return f"{shim} and {starter} are not one kit's npm-test.mjs and starter.py"
    if not python.is_absolute() or not PYTHON_NAME.fullmatch(python.name):
        return f"its Python, {python}, is not an absolute path to a python program"
    if ws is not None and (python.resolve() == ws.resolve() or ws.resolve() in python.resolve().parents):
        return f"its Python, {python}, is inside the workspace"
    return None


def install_first_lines(tool: Optional[str]) -> list[str]:
    t = tool or "<your tool>"
    script = install.ROOT / "scripts" / "install.py"
    return ["Install the kit for it first, as the kit's AGENTS.md describes, then run this again. The plan, "
            "which changes nothing:",
            f"  bash:       python {shlex.quote(script.as_posix())} --tool {t} --tier starter --dry-run",
            f"  PowerShell: python {install._ps_quote(str(script))} --tool {t} --tier starter --dry-run"]


def load_record_or_none() -> tuple[Optional[dict], Optional[str]]:
    """(the install record or None, why it could not be read or None)."""
    try:
        return install.load_record(), None
    except (OSError, ValueError, RuntimeError) as e:
        return None, f"cannot read the install record ({install.record_path()}): {e}"


# --------------------------------------------------------------------------
# Node: a browser demo's tests run on it, and nothing here ever installs it
# --------------------------------------------------------------------------

NODE_INSTALL = {
    "win32": ["  Windows (PowerShell): winget install OpenJS.NodeJS.LTS",
              "  Then open a new terminal, so it finds `node`."],
    "darwin": ["  macOS: brew install node, or the installer from https://nodejs.org/en/download"],
    "linux": ["  Linux: the installer or binaries from https://nodejs.org/en/download. A distribution's own "
              f"package can be older than Node {NODE_FLOOR_TEXT}; check `node --version` afterwards."],
}

# Windows looks for a program in the current folder before PATH (cmd.exe, CreateProcess, and shutil.which up
# to Python 3.11), and a grade is often run from inside the workspace: a node.cmd the agent left there once
# replaced the test runner and printed a PASS. So exe() reads PATH's absolute folders only and the scripts start
# a program by its full path. The variable keeps cmd.exe, and Python 3.12's shutil.which, in the processes the
# scripts start from looking in the current folder either.
os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"


def exe(name: str) -> Optional[str]:
    """The full path of the program `name` from PATH's absolute folders, never the current folder, or None."""
    if os.name == "nt" and not os.path.splitext(name)[1]:
        exts = [e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep) if e]
    else:
        exts = [""]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip().strip('"')
        if not d or not os.path.isabs(d):  # "", "." and any relative entry mean the current folder
            continue
        for e in exts:
            p = os.path.join(d, name + e)
            if os.path.isfile(p) and (os.name == "nt" or os.access(p, os.X_OK)):
                return p
    return None


def node_version() -> Optional[tuple]:
    node = exe("node")
    if not node:
        return None
    try:
        r = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=60, cwd=tempfile.gettempdir())
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.match(r"v(\d+)\.(\d+)\.(\d+)", (r.stdout or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def node_problem(demo: Demo, called: Optional[str] = None) -> Optional[list[str]]:
    """None when the demo needs no Node or a new enough one is on PATH, else the lines that say how to get it,
    naming the demo `called` (default: its title)."""
    if not demo.needs_node:
        return None
    v = node_version()
    if v and v[:2] >= NODE_FLOOR:
        return None
    have = f"Node {'.'.join(map(str, v))} is installed" if v else "Node is not installed (no `node` on PATH)"
    os_key = "win32" if sys.platform.startswith("win") else "darwin" if sys.platform == "darwin" else "linux"
    return ([f"{have}, and {called or demo.title} needs Node {NODE_FLOOR_TEXT} or newer. Install it yourself, then run "
             "this again:"] + NODE_INSTALL[os_key]
            + ["Nothing was written. These scripts never install anything themselves."])


# --------------------------------------------------------------------------
# Git, and the hash of the files that grade a demo
# --------------------------------------------------------------------------

# Variables that point git at a repo, an index or an object store other than the one `-C <dir>` names. A git
# hook exports some of them, so a check run from one would otherwise read the hook's repo, not the kit.
REPO_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE")


def run_git(args: list[str], extra_env: Optional[dict] = None, stdin: Optional[str] = None,
            cwd: Path = KIT, strip: bool = True) -> tuple[int, str]:
    """(exit code, stdout, or stderr on failure) of `git -C cwd args`. --no-optional-locks keeps `git status`
    from rewriting the clone's index, which it otherwise does to cache file times."""
    env = {k: v for k, v in os.environ.items() if k not in REPO_ENV}
    env.update(extra_env or {})
    git = exe("git")
    if not git:
        return 1, "git is not on PATH"
    # Bytes both ways: a text-mode pipe on Windows writes CRLF, and `update-index --index-info` then reads every
    # path with a trailing CR, so the index came out empty and every commit hashed as the empty tree.
    try:
        r = subprocess.run([git, "--no-optional-locks", "-C", str(cwd), *args], capture_output=True,
                           input=None if stdin is None else stdin.encode("utf-8"), env=env, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"{type(e).__name__}: {e}"
    out = (r.stdout if r.returncode == 0 else r.stderr or r.stdout).decode("utf-8", errors="replace")
    out = out.replace("\r\n", "\n")
    return r.returncode, out.strip() if strip else out


def grading_paths(name: str) -> list[str]:
    return [f"demos/{name}/{p}" for p in ("accept", "reference", "skeleton", "BRIEF.md", "demo.json")] + list(GRADERS)


def hash_grading(name: str, rev: Optional[str] = None, kit: Path = KIT) -> tuple[Optional[str], str]:
    """(the git tree hash of the files that grade `name`, "") or (None, why it could not be made). The files
    are those in the working tree (rev None; untracked and ignored files included, so a planted test counts)
    or at commit `rev`. Equal content gives an equal hash, so CI can compare a RECORD's hash with the tree at
    its kit_sha.

    It writes nothing to the clone: the index and the object store are temporary, and the clone's store is
    only read, by ls-tree. Hashing into the clone's store once refused every grade where only the demo's folder
    could be written (a sandboxed session, a read-only clone), saying the files differed. The clone's store is
    not an alternate either, since git touches the time of an object it would write and finds there."""
    paths = grading_paths(name)
    try:
        td = tempfile.TemporaryDirectory(prefix="demo-index-")
    except OSError as e:
        return None, f"cannot make a temporary folder to hash in: {e}"
    with td:
        (Path(td.name) / "objects").mkdir()
        env = {"GIT_INDEX_FILE": str(Path(td.name) / "index"), "GIT_OBJECT_DIRECTORY": str(Path(td.name) / "objects")}
        if rev is None:
            present = [p for p in paths if (kit / p).exists()]
            step, (rc, out) = "add", run_git(["add", "-f", "--", *present], env, cwd=kit) if present else (0, "")
        else:
            step, (rc, out) = "ls-tree", run_git(["ls-tree", "-r", "--full-tree", rev, "--", *paths], cwd=kit)
            if rc == 0:
                step, (rc, out) = "update-index", run_git(["update-index", "--index-info"], env,
                                                          stdin=out + "\n" if out else "", cwd=kit)
        if rc == 0:
            # The blobs of a commit's tree are in the clone's store, not the temporary one; their hashes are
            # all a tree needs.
            step, (rc, out) = "write-tree", run_git(["write-tree", "--missing-ok"], env, cwd=kit)
        if rc:
            return None, f"git {step}: {next(iter(out.splitlines()), '') or f'exit {rc}'}"
        # A demo always has grading files, so the empty tree means the index was never filled: no answer.
        if not re.fullmatch(r"[0-9a-f]{40}", out) or out == EMPTY_TREE:
            return None, f"git write-tree gave {out[:60]!r}, not the tree of the grading files"
        return out, ""


def grading_tree(name: str, rev: Optional[str] = None, kit: Path = KIT) -> Optional[str]:
    """hash_grading's tree, or None when git cannot say."""
    return hash_grading(name, rev, kit)[0]


def changed_graders(name: str, kit: Path = KIT) -> list[str]:
    """The grading files `git status` lists as changed, added or ignored. -z, unstripped: each entry is
    `XY path`, and the X of the first entry can be a space."""
    rc, out = run_git(["status", "--porcelain", "-z", "--untracked-files=all", "--ignored", "--",
                       *grading_paths(name)], cwd=kit, strip=False)
    if rc:
        return []
    entries, paths = out.split("\0"), []
    i = 0
    while i < len(entries):
        e = entries[i]
        if len(e) > 3:
            paths.append(e[3:])
            if e[0] in "RC":  # a rename or copy: the next entry is the path it came from
                i += 1
        i += 1
    return paths


def head_sha(kit: Path = KIT) -> Optional[str]:
    rc, out = run_git(["rev-parse", "HEAD"], cwd=kit)
    return out if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", out) else None


# --------------------------------------------------------------------------
# Files in a workspace, and the originality denylist
# --------------------------------------------------------------------------

def walk(root: Path) -> Iterator[Path]:
    """Every file under root, outside .git and node_modules, in a stable order."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            yield Path(dirpath) / f


def is_link(p: Path) -> bool:
    """A symbolic link, or on Windows any reparse point (a junction too). Unreadable counts as one."""
    try:
        st = os.lstat(str(p))
    except OSError:
        return True
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)  # REPARSE_POINT


def copy_workspace(ws: Path, dest: Path) -> None:
    """Copy the workspace's plain files into `dest`, which check.py then grades, outside .git and node_modules
    and without any link: Node's permission model follows a symbolic link out of the folders it allows (its
    documentation says so), so one in the workspace could reach the kit's reference/ again."""
    for dirpath, dirnames, filenames in os.walk(ws):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not is_link(here / d))
        into = dest / here.relative_to(ws)
        into.mkdir(parents=True, exist_ok=True)
        for f in sorted(filenames):
            if not is_link(here / f):
                shutil.copyfile(str(here / f), str(into / f))


def read_text(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")


def fold(text: str) -> str:
    """Lower case without accents, so "Pokémon" and "pokemon" match one term."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


# What may sit between the letters of a term: "Spiro-Graph", "spiro_graph" and "S.P.I.R.O graph" all spell it.
SEPARATORS = r"[\s\-_.'’]*"


def load_denylist(path: Path = DEMOS / "denylist.txt") -> list[tuple[str, re.Pattern]]:
    terms = []
    for ln in read_text(path).split("\n"):
        term = ln.split("#", 1)[0].strip()
        if not term:
            continue
        letters = "".join(re.findall(r"[a-z0-9]+", fold(term)))
        if not letters:
            raise DemoError(f"{path.name}: {term!r} has no letters or digits")
        rx = re.compile(r"(?<![a-z0-9])" + SEPARATORS.join(map(re.escape, letters)) + r"(?:e?s)?(?![a-z0-9])")
        terms.append((term, rx))
    return terms


def denylist_hits(text: str, terms: list[tuple[str, re.Pattern]]) -> list[tuple[int, str]]:
    hits = []
    for n, ln in enumerate(fold(text).split("\n"), 1):
        hits += [(n, term) for term, rx in terms if rx.search(ln)]
    return hits


# --------------------------------------------------------------------------
# Measured runs: demos/costs.json
# --------------------------------------------------------------------------

COSTS = DEMOS / "costs.json"
ROW_KEYS = {"demo", "tool", "plan", "model", "effort", "tool_version", "kit_sha", "accept_hash", "workspace",
            "workspace_sha", "date", "mode", "meter_delta", "tokens", "wall_min", "sessions", "accept", "claimed_done",
            "verifier", "checkpoint", "no_commit"}
# A run's workspace, committed beside its row as a git bundle: demos/runs/<file>.bundle.
WORKSPACE = re.compile(r"runs/[A-Za-z0-9][A-Za-z0-9._-]*\.bundle")
REGRADE_TIMEOUT_S = 900
OPTIONAL_ROW_KEYS = {"synthetic", "note"}
ACCEPT = re.compile(r"(PASS|FAIL) (\d+)/(\d+)")
METER_KEY = {"share": "weekly_pct", "usd": "usd", "free": None}  # the meter_delta a plan's meter must carry
MAX_AGE_DAYS = 90


class CostsError(Exception):
    pass


def plans() -> dict[str, list[dict]]:
    """core/plans.json, through the build's own loader, which is its one schema check."""
    import build_adapters
    return build_adapters.load_plans()


def plan_row(tool: str, plan_id: Optional[str]) -> Optional[dict]:
    return next((r for r in plans().get(tool, []) if r["id"] == plan_id), None)


def accept_counts(s: str) -> tuple[bool, int, int]:
    m = ACCEPT.fullmatch(s)
    return m.group(1) == "PASS", int(m.group(2)), int(m.group(3))


def check_row(row: dict, where: str) -> None:
    if not isinstance(row, dict) or not ROW_KEYS <= set(row) <= ROW_KEYS | OPTIONAL_ROW_KEYS:
        raise CostsError(f"{where}: keys must be {', '.join(sorted(ROW_KEYS))} (optional: "
                         f"{', '.join(sorted(OPTIONAL_ROW_KEYS))})")
    if row["demo"] not in demo_names():
        raise CostsError(f"{where}: no demo called {row['demo']!r}")
    if row["tool"] not in vocab.VOCAB:
        raise CostsError(f"{where}: {row['tool']!r} is not a tool in scripts/vocab.py")
    plan = plan_row(row["tool"], row["plan"])
    if plan is None:
        raise CostsError(f"{where}: plan {row['plan']!r} is not a {row['tool']} plan in core/plans.json")
    for k in ("model", "effort", "tool_version"):
        if not isinstance(row[k], str) or not row[k]:
            raise CostsError(f"{where}: {k} is a non-empty string")
    for k in ("kit_sha", "accept_hash", "workspace_sha"):
        if not isinstance(row[k], str) or not re.fullmatch(r"[0-9a-f]{40}", row[k]):
            raise CostsError(f"{where}: {k} is a full 40-character git hash")
    if not isinstance(row["workspace"], str) or not WORKSPACE.fullmatch(row["workspace"]):
        raise CostsError(f"{where}: workspace is the run's git bundle in demos/, runs/<file>.bundle")
    try:
        date.fromisoformat(row["date"])
    except (TypeError, ValueError):
        raise CostsError(f"{where}: date is YYYY-MM-DD") from None
    if row["mode"] not in ("interactive", "exec"):
        raise CostsError(f"{where}: mode is interactive or exec")
    delta = row["meter_delta"]
    if not isinstance(delta, dict) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
                                              for v in delta.values()):
        raise CostsError(f"{where}: meter_delta maps each meter read to a number, zero or more")
    need = METER_KEY[plan["meter"]]
    if need and need not in delta:
        raise CostsError(f"{where}: a {plan['meter']} plan's meter_delta needs {need!r}")
    if not (row["tokens"] is None or isinstance(row["tokens"], int) and not isinstance(row["tokens"], bool)
            and row["tokens"] >= 0):
        raise CostsError(f"{where}: tokens is a whole number or null")
    if isinstance(row["wall_min"], bool) or not isinstance(row["wall_min"], (int, float)) or row["wall_min"] <= 0:
        raise CostsError(f"{where}: wall_min is a number of minutes above zero")
    if isinstance(row["sessions"], bool) or not isinstance(row["sessions"], int) or row["sessions"] < 1:
        raise CostsError(f"{where}: sessions is a whole number, one or more")
    if not isinstance(row["accept"], str) or not ACCEPT.fullmatch(row["accept"]):
        raise CostsError(f"{where}: accept is `PASS k/n` or `FAIL k/n`")
    ok, k, n = accept_counts(row["accept"])
    if k > n or ok != (k == n):
        raise CostsError(f"{where}: accept {row['accept']!r}: k is at most n, and PASS exactly when k equals n")
    for k_ in ("claimed_done", "no_commit"):
        if not isinstance(row[k_], bool):
            raise CostsError(f"{where}: {k_} is true or false")
    for k_ in ("verifier", "checkpoint"):
        if row[k_] not in ("ran", "not", "unknown"):
            raise CostsError(f"{where}: {k_} is ran, not or unknown (read from the transcript)")
    if "synthetic" in row and row["synthetic"] is not True:
        raise CostsError(f"{where}: synthetic is true or absent")


def admit(row: dict, where: str, strict: bool, kit: Path = KIT) -> None:
    """A measured run counts only when it was graded by the kit as committed: its accept_hash is the grading
    tree at its kit_sha, so a test edited and committed in the clone cannot count. Strict (CI, and the test of
    the shipped costs.json) also needs kit_sha on origin/main and re-grades the run (regrade), since a grade
    made on the measuring machine is only feedback: anything with a shell there could have changed it.
    Otherwise (pick.py on a user's machine, reading the costs.json CI admitted) this clone's HEAD or
    origin/main may reach kit_sha. MEASURING.md says the same for people."""
    refs = ["origin/main"] if strict else ["HEAD", "origin/main"]
    if not any(run_git(["merge-base", "--is-ancestor", row["kit_sha"], ref], cwd=kit)[0] == 0 for ref in refs):
        raise CostsError(f"{where}: kit_sha {row['kit_sha'][:12]} is not reachable from {' or '.join(refs)}")
    tree = grading_tree(row["demo"], row["kit_sha"], kit=kit)
    if tree != row["accept_hash"]:
        raise CostsError(f"{where}: accept_hash {row['accept_hash'][:12]} is not the grading tree of "
                         f"{row['demo']} at {row['kit_sha'][:12]} ({(tree or 'unknown')[:12]}), so these checks "
                         "are not the kit's")
    if strict:
        regrade(row, where, kit)


def regrade(row: dict, where: str, kit: Path = KIT) -> None:
    """Grade the run again, as CI does before it admits one: the workspace as committed (its bundle, checked out
    at workspace_sha) by the kit as committed at kit_sha (`git archive`, in a fresh folder), with an empty HOME,
    so nothing from the measuring machine takes part. Its verdict must be the row's accept."""
    bundle = kit / "demos" / row["workspace"]
    if not bundle.is_file():
        raise CostsError(f"{where}: its workspace, demos/{row['workspace']}, is not in the kit, so CI cannot "
                         "re-grade it")
    sha = row["kit_sha"]
    with tempfile.TemporaryDirectory(prefix="demo-regrade-") as td:
        t = Path(td)
        ws, clean, home = t / "ws", t / "kit", t / "home"
        home.mkdir()
        step, (rc, out) = "clone", run_git(["clone", "-q", "--no-checkout", str(bundle), str(ws)], cwd=t)
        if rc == 0:
            step, (rc, out) = "checkout", run_git(["checkout", "-q", "--detach", row["workspace_sha"]], cwd=ws)
        if rc == 0:
            step, (rc, out) = "archive", run_git(["archive", "--format=tar", "-o", str(t / "kit.tar"), sha], cwd=kit)
        if rc:
            raise CostsError(f"{where}: cannot re-grade it (git {step}: {next(iter(out.splitlines()), '')})")
        with tarfile.open(str(t / "kit.tar")) as tf:
            if hasattr(tarfile, "data_filter"):  # 3.12, and the 2023 security releases of 3.9 to 3.11
                tf.extractall(str(clean), filter="data")
            else:
                tf.extractall(str(clean))
        env = {k: v for k, v in os.environ.items()
               if k not in REPO_ENV and k != "NODE_OPTIONS" and not k.startswith(("npm_", "COMMIT_GUARD_", "CODEX_"))}
        env.update(HOME=str(home), USERPROFILE=str(home), GIT_CEILING_DIRECTORIES=str(t), PYTHONIOENCODING="utf-8")
        try:
            r = subprocess.run([sys.executable, str(clean / "demos" / "check.py"), row["demo"], "--dir", str(ws),
                                "--regrade"], cwd=str(t), env=env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", stdin=subprocess.DEVNULL, timeout=REGRADE_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise CostsError(f"{where}: cannot re-grade it ({type(e).__name__}: {e})") from None
    got = next((ln for ln in r.stdout.splitlines() if ACCEPT.fullmatch(ln)), None)
    if got != row["accept"]:
        said = got or f"no verdict (exit {r.returncode}: {next(iter(r.stderr.strip().splitlines()), '')})"
        raise CostsError(f"{where}: re-graded from a clean copy of the kit at {sha[:12]}, the committed workspace "
                         f"({row['workspace_sha'][:12]}) gives {said}, not the row's {row['accept']}")


def load_costs(path: Path = COSTS, strict: bool = False, kit: Path = KIT) -> list[dict]:
    """Every run in a costs file, each checked and admitted. Synthetic rows (made-up runs for the picker's
    tests) are refused in the kit's own demos/costs.json, which holds measured runs only."""
    try:
        data = json.loads(read_text(path))
    except (OSError, ValueError) as e:
        raise CostsError(f"{path}: {e}") from None
    if not isinstance(data, dict) or set(data) - {"_about"} != {"runs"} or not isinstance(data["runs"], list):
        raise CostsError(f"{path}: an object with `runs`, a list (and `_about`)")
    shipped = path.resolve() == (kit / "demos" / "costs.json").resolve()
    for i, row in enumerate(data["runs"], 1):
        where = f"{path.name} run {i}"
        check_row(row, where)
        if row.get("synthetic"):
            if shipped:
                raise CostsError(f"{where}: synthetic rows are for tests; demos/costs.json holds measured runs only")
            continue
        admit(row, where, strict, kit)
    return data["runs"]


def recent(rows: list[dict], today: date) -> list[dict]:
    return [r for r in rows if (today - date.fromisoformat(r["date"])).days <= MAX_AGE_DAYS]


def models_reviewed() -> Optional[date]:
    m = re.search(r"\*\*Reviewed: (\d{4}-\d\d-\d\d)\.\*\*", read_text(KIT / "MODELS.md"))
    return date.fromisoformat(m.group(1)) if m else None
