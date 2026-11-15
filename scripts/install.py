#!/usr/bin/env python3
"""Install a generated adapter (adapters/<tool>/) into a tool's global config.

    python scripts/install.py --tool opencode --tier starter              # show the plan, ask y/N
    python scripts/install.py --tool opencode --tier starter --dry-run    # show the plan only
    python scripts/install.py --tool opencode --tier full --yes --guard-repo ~/code/myrepo
    python scripts/install.py --tool generic --tier starter --config-dir ~/my-agent-config
    python scripts/install.py --detect                                    # which tools are here
    python scripts/install.py --tool auto --tier starter --yes            # the one tool detected
    python scripts/install.py --tool claude --yes                         # Claude Code plugin, via its CLI
    python scripts/install.py --tool cursor --tier starter --yes --project ~/code/myrepo

Tools: opencode, codex, cursor, copilot, antigravity, junie, generic, claude. Codex, Cursor, Copilot
and Junie share ~/.agents/skills, so skills are written there once.

Copies files; it translates nothing (scripts/build_adapters.py did that). Safety rules:
  - before anything is written, every target is checked (existing JSON parses, text files are UTF-8,
    the tool binary a load check needs is on PATH); if any check fails, nothing is written;
  - every existing file it changes is first copied to <file>.bak-<YYYYMMDD-HHMMSS> and the copy is
    compared byte for byte before the original is touched;
  - an identical file is reported "already installed" and left alone, so re-runs are no-ops;
  - the rules go into AGENTS.md inside one BEGIN/END claude-starter block: a re-run replaces the
    block, never appends a second one, and every line outside it keeps its exact bytes;
  - JSON config is merged, never replaced: missing keys are added, the user's values always win, and
    every value the user already set differently is reported. The file is re-serialised, keeping its
    BOM and dominant line ending;
  - after installing, the tool's own loader must accept the result, or the run fails. Where no
    offline loader exists, the installed files are checked structurally and the output says that
    nothing was verified against the real tool;
  - just before writing, every destination folder is tried by creating and deleting one file in it; if
    any cannot be written (a sandboxed agent session, say) nothing is written and the run exits 3,
    naming the folder. It never falls back to installing into the project folder;
  - any other failure saves a redacted report (scripts/report.py) and prints an issue link; nothing is sent;
  - a successful install ends with a "For you" block: what the person at the keyboard does next, what
    was left to them, and the install's limits. An agent relays only that block, so each item in it
    is self-contained and nothing in it points at text printed above.
Without --yes it asks on a terminal; with no terminal and no --yes it only prints the plan. Both that
run and a dry run end on a line telling an agent to stop and ask the user.
"""
from __future__ import annotations

import argparse
import filecmp
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

sys.dont_write_bytecode = True  # report and migrations are imported lazily; a plan leaves the clone as it was
ROOT = Path(__file__).resolve().parent.parent
ADAPTERS = ROOT / "adapters"
GUARD = ROOT / "plugins" / "starter" / "hooks" / "commit-guard" / "guard.py"
KIT_AGENTS = ("verifier", "code-reviewer", "consultant")

# Only the block this installer writes carries RULES_MARK, so the Codex self-check looks for it. The kit's
# own AGENTS.md mentions "claude-starter" too, and a check for that passed with no rules installed.
RULES_MARK = "BEGIN claude-starter rules"
BEGIN = f"<!-- {RULES_MARK} (managed by scripts/install.py; a re-run replaces this block) -->"
END = "<!-- END claude-starter rules -->"
BEGIN_RX = re.compile(rf"^<!-- {re.escape(RULES_MARK)}\b.*-->$", re.M)
END_RX = re.compile(r"^<!-- END claude-starter rules -->$", re.M)
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")


# --------------------------------------------------------------------------
# Plan model
# --------------------------------------------------------------------------

@dataclass
class Step:
    piece: str
    dest: Path | None
    kind: str                       # file | rules | json | guard | cli | delete | move | git
    status: str = ""                # create | update | merge | already installed | skipped | failed | ...
    detail: str = ""
    payload: bytes = b""            # final bytes to write (file/rules/json)
    src: Path | None = None
    notes: list[str] = field(default_factory=list)
    original: object = None         # json: the user's parsed config, checked to survive the merge
    migration: str | None = None    # the migration ID that planned this step, if any
    argv: list = field(default_factory=list)  # git: the arguments after `git -C <dest>`; move: [new path]

    @property
    def writes(self) -> bool:
        # Every planned status that changes something. A status missing here is never applied, probed or
        # pinned: a migration's `git` step once went unrun while its migration was recorded as applied.
        return self.status in ("create", "update", "merge", "run", "delete", "move", "git")


def backup_path(p: Path) -> Path:
    b = p.with_name(f"{p.name}.bak-{STAMP}")
    n = 1
    while b.exists():
        b = p.with_name(f"{p.name}.bak-{STAMP}-{n}")
        n += 1
    return b


def make_backup(p: Path) -> Path:
    b = backup_path(p)
    shutil.copy2(p, b)
    if not filecmp.cmp(p, b, shallow=False):
        b.unlink(missing_ok=True)
        raise RuntimeError(f"backup of {p} is not byte-identical; nothing changed")
    return b


def lf(text: str) -> bytes:
    return text.replace("\r\n", "\n").encode("utf-8")


def decode_text(data: bytes) -> tuple[str | None, str | None]:
    """(text, None) for UTF-8 (a BOM stays in the text), else (None, what is wrong)."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in data[:400]:
        return None, "UTF-16 encoded (PowerShell 5.1 writes that); save it as UTF-8 and re-run; nothing written"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError as e:
        return None, f"not UTF-8 ({e.reason} at byte {e.start}); save it as UTF-8 and re-run; nothing written"


def dominant_eol(text: str) -> str:
    crlf = text.count("\r\n")
    return "\r\n" if crlf > text.count("\n") - crlf else "\n"


def blocked_parent(dest: Path) -> str | None:
    """A problem if `dest` cannot be written: it is a folder, or a parent folder is a file."""
    if dest.is_dir():
        return f"{dest} is a folder; expected a file"
    for parent in dest.parents:
        if parent.exists():
            return None if parent.is_dir() else f"{parent} is a file, so {dest.name} cannot be created under it"
    return None


# --------------------------------------------------------------------------
# Planning each kind of piece
# --------------------------------------------------------------------------

def plan_file(piece: str, src: Path, dest: Path) -> Step:
    data = src.read_bytes()
    s = Step(piece, dest, "file", src=src, payload=data)
    problem = blocked_parent(dest)
    if problem:
        s.status, s.detail = "failed", problem + "; nothing written"
        return s
    if not dest.exists():
        s.status = "create"
    elif dest.read_bytes() == data:
        s.status, s.detail = "already installed", ""
    else:
        s.status, s.detail = "update", f"differs; backup to {backup_path(dest).name}, then replace"
    return s


def plan_rules(src: Path, dest: Path) -> Step:
    rules = src.read_bytes().decode("utf-8").replace("\r\n", "\n").rstrip("\n") + "\n"
    block_lines = [BEGIN, *rules.rstrip("\n").split("\n"), END]
    s = Step(f"rules ({src.name})", dest, "rules", src=src)
    problem = blocked_parent(dest)
    if problem:
        s.status, s.detail = "failed", problem + "; nothing written"
        return s
    if not dest.exists():
        s.status, s.detail = "create", "new file with the kit's block"
        s.payload = ("\n".join(block_lines) + "\n").encode("utf-8")
        return s
    cur, problem = decode_text(dest.read_bytes())
    if problem:
        s.status, s.detail = "failed", problem
        return s
    if cur.replace("\r\n", "\n") == rules:
        s.status, s.detail = "already installed", "file is exactly the kit's rules"
        return s
    # Work on the raw lines so every line outside the block keeps its exact bytes, mixed endings
    # included; the block itself takes the file's dominant line ending.
    eol = dominant_eol(cur)
    block = eol.join(block_lines) + eol
    lines = re.split(r"(?<=\n)", cur)
    if lines and lines[-1] == "":
        lines.pop()
    bare = [ln.rstrip("\n").rstrip("\r") for ln in lines]
    if bare:
        bare[0] = bare[0].lstrip("\ufeff")
    begins = [i for i, ln in enumerate(bare) if BEGIN_RX.fullmatch(ln)]
    ends = [i for i, ln in enumerate(bare) if END_RX.fullmatch(ln)]
    if not begins and not ends:
        norm = cur.replace("\r\n", "\n")
        sep = "" if norm.endswith("\n\n") else (eol if norm.endswith("\n") else eol + eol)
        s.payload = (cur + sep + block).encode("utf-8")
        s.status = "merge"
        s.detail = f"backup to {backup_path(dest).name}; append claude-starter block (your text untouched)"
        return s
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        s.status = "failed"
        s.detail = (f"{len(begins)} BEGIN / {len(ends)} END claude-starter markers; expected one pair. "
                    "Fix the markers by hand; nothing written")
        return s
    b, e = begins[0], ends[0]
    if bare[b:e + 1] == block_lines:
        s.status, s.detail = "already installed", "claude-starter block is current"
        return s
    bom = "﻿" if b == 0 and lines[0].startswith("﻿") else ""  # the BOM rode on the replaced line
    s.payload = (bom + "".join(lines[:b]) + block + "".join(lines[e + 1:])).encode("utf-8")
    s.status = "merge"
    s.detail = f"backup to {backup_path(dest).name}; replace the existing claude-starter block only"
    return s


def wildcard(pattern: str) -> re.Pattern:
    """OpenCode-style pattern: `*` any run, `?` one char, a trailing ` *` also matches no arguments."""
    rx = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
    if rx.endswith(r"\ .*"):
        rx = rx[:-4] + r"(\ .*)?"
    return re.compile(rx + r"\Z", re.S)


def without_allows(ours):
    """`ours` with every "allow" value removed, and any object left empty by that dropped."""
    if not isinstance(ours, dict):
        return ours
    out = {}
    for k, v in ours.items():
        if v == "allow":
            continue
        v = without_allows(v)
        if v != {}:
            out[k] = v
    return out


def deep_merge(theirs, ours, path: str, kept: list[str], union: tuple[str, ...] = ()):
    """Union: add what `theirs` lacks, never change a value they set. A list at a path in `union` is
    an allowlist: the kit's missing items are appended after the user's, which stay first."""
    if path in union and isinstance(theirs, list) and isinstance(ours, list):
        return theirs + [x for x in ours if x not in theirs]
    if path == "permission" and without_allows(ours) != ours:
        # OpenCode's top-level permission, "deny" or {"*": "deny"} (or "ask"), covers every tool, and a
        # more specific kit allow under it would punch a hole in it.
        star = theirs if isinstance(theirs, str) else theirs.get("*") if isinstance(theirs, dict) else None
        if star in ("deny", "ask"):
            kept.append(f"{path}: kept your " + ("'*' " if isinstance(theirs, dict) else "permission ")
                        + f"= {star}; kit allows not added")
            if isinstance(theirs, str):
                return theirs
            ours = without_allows(ours)
    if isinstance(theirs, dict) and isinstance(ours, dict):
        out = dict(theirs)
        star = theirs.get("*") if path.endswith("permission.bash") else None
        if star in ("deny", "ask") and any(k not in theirs and v == "allow" for k, v in ours.items()):
            # OpenCode applies the last matching rule, so every allow appended after the user's
            # catch-all would punch a hole in it.
            kept.append(f"{path}: kept your '*' = {star}; kit allows not added")
        for k, v in ours.items():
            if k not in out:
                if star in ("deny", "ask") and v == "allow":
                    continue
                if path.endswith("permission.bash") and v == "allow":
                    blockers = [p for p, a in theirs.items()
                                if a in ("deny", "ask") and p != "*" and wildcard(p).match(k)]
                    if blockers:
                        # OpenCode applies the last matching rule, so an appended allow would
                        # silently override the user's narrower deny/ask for this command.
                        kept.append(f"{path}.{k}: not added; your rule {blockers[-1]!r}="
                                    f"{theirs[blockers[-1]]!r} covers it and stays in force")
                        continue
                out[k] = v
            else:
                out[k] = deep_merge(out[k], v, f"{path}.{k}" if path else k, kept, union)
        return out
    if theirs != ours:
        kept.append(f"{path}: kept yours ({json.dumps(theirs)}), kit wanted {json.dumps(ours)}")
    return theirs


def contains(big, small) -> bool:
    if isinstance(small, dict):
        return isinstance(big, dict) and all(k in big and contains(big[k], v) for k, v in small.items())
    if isinstance(small, list) and isinstance(big, list):  # a merged allowlist keeps the user's items first
        return big[:len(small)] == small
    return big == small


def plan_json(src: Path, dest: Path, union: tuple[str, ...] = ()) -> Step:
    ours = json.loads(src.read_text(encoding="utf-8"))
    s = Step(f"settings ({src.name})", dest, "json", src=src)
    jsonc = dest.with_suffix(".jsonc")
    if not dest.exists() and jsonc.exists():
        text, problem = decode_text(jsonc.read_bytes())
        plain = not problem
        if plain:
            try:
                json.loads(text.lstrip("﻿"))
            except json.JSONDecodeError:
                plain = False
        if not plain:
            s.status = "skipped"
            s.detail = (f"you use {jsonc.name}; merge {src.relative_to(ROOT).as_posix()} into it by hand "
                        "(comments are not parsed safely here)")
            return s
        # A .jsonc with no comments or trailing commas is plain JSON. OpenCode writes exactly
        # such a one-line $schema stub on first run, so a fresh install merges into it.
        dest = jsonc
        s = Step(f"settings ({src.name})", dest, "json", src=src)
    problem = blocked_parent(dest)
    if problem:
        s.status, s.detail = "failed", problem + "; nothing written"
        return s
    if not dest.exists():
        s.status, s.payload, s.detail = "create", (json.dumps(ours, indent=2) + "\n").encode(), ""
        return s
    text, problem = decode_text(dest.read_bytes())
    if problem:
        s.status, s.detail = "failed", problem
        return s
    bom = text.startswith("\ufeff")
    text = text[1:] if bom else text
    try:
        theirs = json.loads(text)
    except json.JSONDecodeError as e:
        s.status, s.detail = "failed", f"not valid JSON (line {e.lineno}: {e.msg}); nothing written"
        return s
    if not isinstance(theirs, dict):
        s.status, s.detail = "failed", "top level is not an object; nothing written"
        return s
    kept: list[str] = []
    merged = deep_merge(theirs, ours, "", kept, union)
    s.notes = kept
    if merged == theirs:
        s.status = "already installed"
        s.detail = f"{len(kept)} value(s) kept as yours" if kept else ""
        return s
    eol = dominant_eol(text)
    out = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"  # JSON strings hold no raw newline
    s.payload = (("\ufeff" if bom else "") + out.replace("\n", eol)).encode("utf-8")
    added = len(json.dumps(merged)) - len(json.dumps(theirs))
    s.status = "merge"
    s.detail = (f"backup to {backup_path(dest).name}; add missing keys only (+{added} chars), "
                f"{len(kept)} value(s) kept as yours; file is re-serialised with 2-space indent "
                f"({'UTF-8 BOM kept, ' if bom else ''}{'CRLF' if eol == chr(13) + chr(10) else 'LF'} "
                "line endings kept; your formatting and key spacing are not)")
    s.original = theirs
    return s


def guard_data_dir() -> Path:
    """Where guard.py install copies itself (mirrors guard.py's DATA_DIR)."""
    return Path(os.environ.get("COMMIT_GUARD_DIR")
                or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "commit-guard")


def guard_hooks_current(repo: Path) -> bool:
    """True when `guard.py install repo` would change nothing: every hook it writes holds exactly the
    bytes this kit's guard.py writes (and is executable outside Windows), and the copy the hooks call is
    this guard.py byte for byte. The hook text comes from guard.py itself, so the two cannot disagree."""
    try:
        spec = importlib.util.spec_from_file_location("starter_commit_guard", str(GUARD))
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)  # defines names only; sys.dont_write_bytecode keeps the clone as it was
        copy = Path(g.INSTALLED_GUARD)
        if not copy.is_file() or copy.read_bytes() != GUARD.read_bytes():
            return False
        hooks = guard_hooks_dir(repo)
        for name in g.HOOK_NAMES:
            hook = hooks / name
            if not hook.is_file() or hook.read_bytes() != g.hook_script(name).encode("utf-8"):
                return False
            if os.name != "nt" and not hook.stat().st_mode & 0o111:
                return False
    except (OSError, ImportError, SyntaxError, AttributeError):
        return False
    return True


def plan_guard(repo: str) -> Step:
    p = Path(repo).expanduser().resolve()
    s = Step("commit guard (git hooks)", p, "guard")
    if not (p / ".git").exists():
        s.status, s.detail = "failed", "not a git repository (no .git)"
        return s
    if guard_hooks_current(p):
        # A re-run with the same --guard-repo must write nothing, like every other piece.
        s.status, s.detail = "already installed", "hooks and the guard.py copy they call are current"
        return s
    s.status = "run"
    s.detail = f"python guard.py install {p} (writes .git/hooks; copies guard.py to {guard_data_dir()})"
    return s


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

def opencode_config_dir() -> Path:
    # Mirrors OpenCode: OPENCODE_CONFIG_DIR, else $XDG_CONFIG_HOME/opencode, else ~/.config/opencode
    # (also on Windows; confirm with `opencode debug paths`).
    if os.environ.get("OPENCODE_CONFIG_DIR"):
        return Path(os.environ["OPENCODE_CONFIG_DIR"])
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "opencode"


def _run(cmd: list[str], env: dict, cwd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return 124, f"timed out: {' '.join(cmd)}"
    out = (r.stdout + r.stderr).decode("utf-8", errors="replace")
    return r.returncode, ANSI.sub("", out)


def denied_keys(agent_file: Path) -> list[str]:
    text = agent_file.read_text(encoding="utf-8")
    fm = text.split("\n---", 1)[0]
    return re.findall(r"^  (\w+): deny$", fm, re.M)


def opencode_load_check(config_dir: Path, steps: list[Step]) -> tuple[bool, list[str]]:
    exe = shutil.which("opencode")
    if not exe:
        return False, ["`opencode` not found on PATH, so the install could not be load-checked"]
    env = dict(os.environ)
    if config_dir.resolve() != opencode_config_dir().resolve():
        env["OPENCODE_CONFIG_DIR"] = str(config_dir)
    lines: list[str] = []
    with tempfile.TemporaryDirectory(prefix="starter-loadcheck-") as cwd:
        rc, out = _run([exe, "agent", "list"], env, cwd)
        if rc != 0:
            return False, [f"`opencode agent list` exited {rc}:", *out.strip().splitlines()[:20]]
        found = dict(re.findall(r"^(\S+) \((primary|subagent|all)\)\s*$", out, re.M))
        missing = [a for a in KIT_AGENTS if a not in found]
        if missing:
            return False, [f"`opencode agent list` loaded but is missing: {', '.join(missing)}"]
        lines.append(f"`opencode agent list` OK: {', '.join(f'{a} ({found[a]})' for a in KIT_AGENTS)}")

        # The read-only restriction is the point of these agents: confirm OpenCode applied it.
        for a in KIT_AGENTS:
            rc, out = _run([exe, "debug", "agent", a], env, cwd)
            try:
                tools = json.loads(out[out.index("{"):])["tools"]
            except (ValueError, KeyError):
                return False, [f"`opencode debug agent {a}` exited {rc} without readable JSON:",
                               *out.strip().splitlines()[:10]]
            want_off = set()
            for k in denied_keys(config_dir / "agents" / f"{a}.md"):
                want_off |= {"edit", "write"} if k == "edit" else {k}
            still_on = sorted(k for k in want_off if tools.get(k, False))
            if still_on or "edit" not in want_off:
                return False, [f"agent {a}: denied in its file but enabled by OpenCode: {still_on or ['edit']}"]
            lines.append(f"agent {a}: tools off as written ({', '.join(sorted(want_off))})")

        rc, out = _run([exe, "debug", "skill"], env, cwd)
        try:
            names = {sk["name"] for sk in json.loads(out[out.index("["):])}
        except ValueError:
            return False, [f"`opencode debug skill` exited {rc} without readable JSON"]
        want = {st.dest.parent.name for st in steps if st.dest and st.dest.name == "SKILL.md"}
        if want - names:
            return False, [f"skills not loaded: {', '.join(sorted(want - names))}"]
        lines.append(f"skills loaded: {', '.join(sorted(want))}")

        rc, out = _run([exe, "debug", "config"], env, cwd)
        try:
            cmds = set(json.loads(out[out.index("{"):]).get("command") or {})
        except ValueError:
            return False, [f"`opencode debug config` exited {rc} without readable JSON"]
        want = {st.dest.stem for st in steps if st.dest and st.dest.parent.name == "commands"}
        if want - cmds:
            return False, [f"commands not loaded: {', '.join(sorted(want - cmds))}"]
        lines.append(f"commands loaded: {', '.join('/' + c for c in sorted(want))}")
    return True, lines


def opencode_check(config_dir: Path, steps: list[Step]) -> tuple[bool, list[str], str]:
    ok, lines = opencode_load_check(config_dir, steps)
    return ok, lines, "passed (loaded by opencode)" if ok else "FAILED"


# --------------------------------------------------------------------------
# Config locations of the other tools (from their docs; the env vars relocate them for tests)
# --------------------------------------------------------------------------

def home() -> Path:
    return Path.home()  # USERPROFILE on Windows, HOME elsewhere


def codex_home() -> Path:
    return Path(os.environ["CODEX_HOME"]) if os.environ.get("CODEX_HOME") else home() / ".codex"


def cursor_dir() -> Path:
    return Path(os.environ["CURSOR_CONFIG_DIR"]) if os.environ.get("CURSOR_CONFIG_DIR") else home() / ".cursor"


def copilot_home() -> Path:
    return Path(os.environ["COPILOT_HOME"]) if os.environ.get("COPILOT_HOME") else home() / ".copilot"


def claude_config_dir() -> Path:
    return Path(os.environ["CLAUDE_CONFIG_DIR"]) if os.environ.get("CLAUDE_CONFIG_DIR") else home() / ".claude"


def shared_skills_dir() -> Path:
    """Read by Codex, Cursor, Copilot, Junie (and OpenCode): one copy serves them all."""
    return home() / ".agents" / "skills"


# --------------------------------------------------------------------------
# Structural check: for tools with no offline loader, check the installed files' shape instead
# --------------------------------------------------------------------------

STRUCTURAL = "structurally checked; not verified against the real tool"
FM_LINE = re.compile(r"([A-Za-z][\w-]*):\s*(.*)")
JUNIE_GROUPS = {"Read", "Bash", "Glob", "Grep", "Write", "Edit", "WebSearch", "AskUserQuestion"}
AGENT_SPECS = {  # required frontmatter, tool names the docs give, values that make the agent read-only
    "cursor": {"required": ("name", "description", "readonly"), "values": {"readonly": "true"}},
    "copilot": {"required": ("name", "description", "tools"), "tools": {"read", "search", "execute"},
                "never": {"edit"}},
    "antigravity": {"required": ("name", "description", "tools"), "tools": {"view_file", "grep_search"}},
    "junie": {"required": ("description",), "tools": JUNIE_GROUPS, "never": {"Edit", "Write"}},
}
ANTIGRAVITY_CAP = 24_000


def parse_frontmatter(text: str) -> dict:
    """The YAML subset the adapters write: `key: value`, `# comments`, folded `>-` blocks, and
    JSON-style quoted strings and flow lists. Raises ValueError on anything else."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError("no `---` frontmatter block")
    end = lines.index("---", 1)
    fm: dict = {}
    i = 1
    while i < end:
        ln = lines[i]
        if not ln.strip() or ln.lstrip().startswith("#"):
            i += 1
            continue
        m = FM_LINE.fullmatch(ln)
        if not m:
            raise ValueError(f"frontmatter line not understood: {ln!r}")
        key, val = m.group(1), m.group(2).strip()
        if key in fm:
            raise ValueError(f"duplicate key {key!r}")
        i += 1
        if val in (">", ">-", "|", "|-"):
            block = []
            while i < end and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            val = " ".join(b for b in block if b)
        elif val.startswith(("[", '"')):
            try:
                val = json.loads(val)
            except json.JSONDecodeError as e:
                raise ValueError(f"{key}: not a valid quoted string or list ({e.msg})") from None
        fm[key] = val
    return fm


CODEX_SKILL_KEYS = {  # agents/openai.yaml, from https://learn.chatgpt.com/docs/build-skills (2026-11-15)
    "interface": {"display_name", "short_description", "icon_small", "icon_large", "brand_color", "default_prompt"},
    "policy": {"allow_implicit_invocation"},
}


def parse_skill_metadata(text: str) -> dict:
    """The subset of YAML a Codex skill's agents/openai.yaml is written in here: top-level `section:`
    lines, each holding two-space-indented `key: value` scalars (true/false, a quoted or a plain
    string), and `# comments`. Raises ValueError on anything else, `dependencies` included: the kit
    writes none, so one here was not written by it."""
    out: dict = {}
    section = None
    for n, ln in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        top = re.fullmatch(r"([a-z_]+):\s*", ln)
        sub = re.fullmatch(r"  ([a-z_]+):\s*(\S.*?)\s*", ln)
        if top:
            section = top.group(1)
            if section not in CODEX_SKILL_KEYS:
                raise ValueError(f"line {n}: section {section!r} is not one this kit writes "
                                 f"({', '.join(sorted(CODEX_SKILL_KEYS))})")
            if section in out:
                raise ValueError(f"line {n}: duplicate section {section!r}")
            out[section] = {}
        elif sub and section:
            key, raw = sub.groups()
            if key not in CODEX_SKILL_KEYS[section] or key in out[section]:
                raise ValueError(f"line {n}: {section}.{key} is unknown or repeated")
            if raw in ("true", "false"):
                val: object = raw == "true"
            elif raw.startswith('"'):
                try:
                    val = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValueError(f"line {n}: {section}.{key}: not a valid quoted string ({e.msg})") from None
            else:
                val = raw
            out[section][key] = val
        else:
            raise ValueError(f"line {n}: not understood: {ln!r}")
    return out


def check_skill_metadata(p: Path) -> str | None:
    """A ported command's agents/openai.yaml: it parses, and it keeps Codex from starting the skill."""
    data = parse_skill_metadata(p.read_text(encoding="utf-8"))
    if not (p.parent.parent / "SKILL.md").is_file():
        return f"no SKILL.md beside {p.parent.name}/ in {p.parent.parent}"
    if any(not isinstance(v, str) for v in data.get("interface", {}).values()):
        return "interface values must be strings"
    allow = data.get("policy", {}).get("allow_implicit_invocation")
    if allow is not False:
        return (f"policy.allow_implicit_invocation is {allow!r}, expected false (Codex's default is true, "
                "which lets it start the skill on its own)")
    return None


def check_file(tool: str, s: Step) -> str | None:
    """Return a problem with the installed file, or None."""
    p = s.dest
    if p.name == "openai.yaml" and p.parent.name == "agents" and p.parent.parent.parent.name == "skills":
        return check_skill_metadata(p)  # skills/<name>/agents/openai.yaml: Codex's skill metadata, not an agent
    if s.kind == "rules":
        text = p.read_bytes().decode("utf-8").replace("\r\n", "\n")
        b, e = len(BEGIN_RX.findall(text)), len(END_RX.findall(text))
        if (b, e) != (1, 1) and text.rstrip("\n") != s.src.read_text(encoding="utf-8").rstrip("\n"):
            return f"{b} BEGIN / {e} END claude-starter markers"
        if tool == "antigravity" and p.stat().st_size > ANTIGRAVITY_CAP:
            return f"{p.stat().st_size} bytes; Antigravity reads at most {ANTIGRAVITY_CAP} per rules file"
        return None
    if s.kind == "json":
        json.loads(p.read_text(encoding="utf-8-sig"))
        return None
    if p.suffix == ".rules":
        return None if "prefix_rule(" in p.read_text(encoding="utf-8") else "no prefix_rule() in the file"
    if p.suffix == ".toml":
        if sys.version_info < (3, 11):
            return None  # tomllib arrived in 3.11; the build already parsed these files
        import tomllib
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        missing = [k for k in ("name", "description", "developer_instructions") if not data.get(k)]
        if missing:
            return f"missing {', '.join(missing)}"
        if data["name"] != p.stem:
            return f"name {data['name']!r} does not match the file name"
        if not data["developer_instructions"].startswith("READ-ONLY"):
            return "developer_instructions lost its read-only instruction"
        return None
    fm = parse_frontmatter(p.read_text(encoding="utf-8"))
    if p.name == "SKILL.md":
        if not fm.get("description"):
            return "skill has no description"
        if fm.get("name", p.parent.name) != p.parent.name:
            return f"skill name {fm.get('name')!r} does not match its folder {p.parent.name!r}"
        return None
    if p.parent.name == "commands":
        return None if fm.get("description") else "command has no description"
    if p.parent.name == "agents":
        spec = AGENT_SPECS[tool]
        missing = [k for k in spec["required"] if fm.get(k) in (None, "", [])]
        if missing:
            return f"missing {', '.join(missing)}"
        stem = p.name.split(".")[0]
        if fm.get("name", stem) != stem:
            return f"name {fm.get('name')!r} does not match the file name"
        if tool == "junie" and not re.fullmatch(r"[a-z][a-z0-9_-]*", fm.get("name", stem)):
            return "Junie agent names must match [a-z][a-z0-9_-]*"
        for k, v in spec.get("values", {}).items():
            if str(fm.get(k)).lower() != v:
                return f"{k} is {fm.get(k)!r}, expected {v}"
        if "tools" in spec:
            tools = fm.get("tools")
            if not isinstance(tools, list) or not tools:
                return "tools is not a non-empty list (an empty or missing list grants everything)"
            unknown = sorted(set(tools) - spec["tools"])
            if unknown:
                return f"tool names the docs do not give: {', '.join(unknown)}"
            if set(tools) & spec.get("never", set()):
                return f"grants editing: {sorted(set(tools) & spec['never'])}"
        return None
    return None


def structural_check(tool: str, steps: list[Step]) -> tuple[bool, list[str]]:
    bad, n = [], 0
    for s in steps:
        if not s.dest or s.kind == "guard" or s.status in ("failed", "skipped", "manual"):
            continue
        n += 1
        try:
            problem = check_file(tool, s)
        except (ValueError, OSError, UnicodeDecodeError) as e:
            problem = f"{type(e).__name__}: {e}"
        if problem:
            bad.append(f"{s.piece} ({s.dest}): {problem}")
    if bad:
        return False, bad
    return True, [f"{n} installed files parse and carry the fields the {tool} docs require"]


def structural_only(tool: str) -> Callable[[Path, list[Step]], tuple[bool, list[str], str]]:
    def check(cfg: Path, steps: list[Step]) -> tuple[bool, list[str], str]:
        ok, lines = structural_check(tool, steps)
        return ok, lines + [f"no offline validator exists for {tool}: {STRUCTURAL}"], STRUCTURAL if ok else "FAILED"
    return check


def codex_check(cfg: Path, steps: list[Step]) -> tuple[bool, list[str], str]:
    ok, lines = structural_check("codex", steps)
    if not ok:
        return False, lines, "FAILED"
    warning = codex_override_warning(cfg)
    if warning:  # a warning, not a failure: the files are installed and load once the override goes
        lines.append(warning)
    rules = next((s.dest for s in steps if s.dest and s.dest.suffix == ".rules"), None)
    exe = shutil.which("codex")
    if not exe:
        lines.append("not verified: codex not installed (`codex execpolicy check` would test the rules)")
        return True, lines, STRUCTURAL + " (codex not installed)"
    env = dict(os.environ, CODEX_HOME=str(cfg))
    with tempfile.TemporaryDirectory(prefix="starter-loadcheck-") as cwd:
        for cmd, want in (("git status", True), ("git push", False), ("git branch new-branch", False),
                          ("ruff format --check --cache-dir x", False)):
            rc, out = _run([exe, "execpolicy", "check", "--rules", str(rules), "--", *cmd.split()], env, cwd)
            js = [ln for ln in out.splitlines() if ln.startswith("{")]
            if rc != 0 or not js:
                return False, lines + [f"`codex execpolicy check -- {cmd}` exited {rc}:",
                                       *out.strip().splitlines()[:20]], "FAILED"
            decision = json.loads(js[-1]).get("decision")
            if (decision == "allow") != want:
                return False, lines + [f"`{cmd}`: codex says {decision or 'no match'}, expected "
                                       f"{'allow' if want else 'not allowed'}"], "FAILED"
            lines.append(f"`codex execpolicy check -- {cmd}`: {decision or 'no rule matched, so not allowed'}")
    lines.append("agents and skills: Codex has no offline loader for them, so they are only structurally checked")
    return True, lines, "rules verified with `codex execpolicy`; agents and skills " + STRUCTURAL


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

Hook = Callable[[Path, argparse.Namespace], list[str]]


@dataclass
class Tool:
    config_dir: Callable[[], Path] | None       # None: --config-dir is required
    dirs: tuple[str, ...]                        # adapter subfolders copied as-is
    # Both hooks are required, so a tool cannot be added without deciding what its user is told.
    # A Codex install once ended on caveats with no restart step, and the user never got the rules.
    after: Hook                                  # caveats: the last item of the "For you" block
    next_steps: Hook                             # what to do next: the first items of that block
    rules_file: str | None = "AGENTS.md"         # None: the tool has no global rules file
    json_merge: tuple[str, str] | None = None    # (adapter file, config file)
    load_check: Callable[[Path, list[Step]], tuple[bool, list[str], str]] | None = None
    shared_skills: bool = False                  # adapter skills/ go to ~/.agents/skills
    union: tuple[str, ...] = ()                  # JSON allowlists merged item by item
    rules_cap: int | None = None                 # bytes the tool reads from one rules file
    bins: tuple[str, ...] = ()                   # evidence for --detect
    marks: Callable[[], list[Path]] = lambda: []  # config dirs that are evidence for --detect
    needs_bin: str | None = None                 # the load check fails without it: checked before writing


def notes_codex(cfg: Path, args) -> list[str]:
    return ["Agents are READ-ONLY BY INSTRUCTION ONLY: Codex cannot enforce it (agent files ignore "
            "sandbox_mode). Consultant: shell tools disabled by feature flags (shell_tool and "
            "unified_exec = false); not verified that Codex honours [features] in agent files.",
            "checkpoint, lanes, onboard and starter-update are skills (Codex prompts are deprecated). Each one's "
            "agents/openai.yaml sets policy.allow_implicit_invocation: false, which Codex documents as keeping "
            "it from starting the skill on its own; run them by name ($checkpoint). Checked structurally, not "
            "against Codex.",
            "Codex's commit attribution is undocumented since 2026-05-13. Only repos given to "
            "--guard-repo have the commit guard to flag it.",
            f"Allowlist: {cfg / 'rules' / 'claude-starter.rules'} allows only commands checked to stay "
            "read-only when arguments are appended (Codex matches prefixes); git diff/log/branch and "
            "ruff still ask."]


def notes_cursor(cfg: Path, args) -> list[str]:
    out = ["No git allow rule was added: Cursor's Shell(git) would allow every git command, push included."]
    try:
        att = json.loads((cfg / "cli-config.json").read_text(encoding="utf-8-sig")).get("attribution", {})
        if att.get("attributeCommitsToAgent") is not False or att.get("attributePRsToAgent") is not False:
            out.append(f"WARNING: your cli-config.json keeps attribution {json.dumps(att)}; in repos with "
                       "the commit guard (--guard-repo), it flags Cursor's 'Made with Cursor' trailer. Set both "
                       "to false to stop it.")
    except (OSError, ValueError, AttributeError):
        pass
    return out


def notes_copilot(cfg: Path, args) -> list[str]:
    return ["Agents use `tools` (read, search; execute for verifier/code-reviewer) plus strict-tools-list, "
            "which GitHub's configuration reference does not list: unconfirmed."]


def notes_antigravity(cfg: Path, args) -> list[str]:
    size = (cfg / "AGENTS.md").stat().st_size if (cfg / "AGENTS.md").exists() else 0
    return ["verifier and code-reviewer have NO SHELL: Antigravity documents no tool name for running "
            "commands, so they ask the calling session to run commands and judge the output.",
            f"{cfg / 'AGENTS.md'} is {size} of {ANTIGRAVITY_CAP} bytes Antigravity reads per rules file.",
            "Allowlist: word-prefix rules, so only commands checked to stay read-only when arguments are "
            "appended were added; your own deny and ask rules outrank them (deny > ask > allow)."]


def notes_generic(cfg: Path, args) -> list[str]:
    return ["Agents are READ-ONLY BY INSTRUCTION ONLY: the generic adapter writes plain prompt files, and "
            "nothing in them stops an agent from editing. If your tool can restrict an agent's tools, do it "
            "there (PORTING.md).",
            f"Nothing was load-checked: confirm your tool reads {cfg} before relying on it (PORTING.md)."]


def notes_junie(cfg: Path, args) -> list[str]:
    return ["Allowlist rules were appended after yours; Junie applies the first matching rule, so yours win.",
            "defaultBehavior and allowReadonlyCommands were not set: Junie does not document their values."]


def no_notes(cfg: Path, args) -> list[str]:
    return []


def codex_override_warning(cfg: Path) -> str | None:
    """Codex reads AGENTS.override.md in its home instead of AGENTS.md when that file has content."""
    override = cfg / "AGENTS.override.md"
    try:
        if not override.is_file() or override.stat().st_size == 0:
            return None
    except OSError:
        return None
    return (f"WARNING: {override} is not empty. Codex reads it instead of {cfg / 'AGENTS.md'}, so the kit's "
            "rules will not load. Move what you need from it into AGENTS.md and delete it (or empty it).")


def onboard_line(tool: str, where: str) -> str:
    """The For-you item that starts the onboarding walkthrough. A Codex user once got a walkthrough asking
    which Claude plan they had; each tool's onboard command prints that tool's own copy (core/onboarding/)."""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import vocab  # the one home of what each tool's user types to run a kit command
    return (f"Then type {vocab.VOCAB[tool].cmd('onboard')} {where} for a short walkthrough of the kit: one step at "
            "a time, each ending with the command for the next.")


def next_opencode(cfg: Path, args) -> list[str]:
    return ["Restart opencode to pick the changes up (it reads config once at start).",
            "Check it took: run `opencode agent list` and look for verifier, code-reviewer and consultant.",
            onboard_line("opencode", "in opencode")]


def next_codex(cfg: Path, args) -> list[str]:
    out = [f"Quit and restart Codex, or open a new chat. Codex reads {cfg / 'AGENTS.md'} once per session, "
           "so the chat that ran this installer does not have the rules.",
           'Check it took: in the new chat ask "what rules are you following?", or run '
           f'`codex debug prompt-input "x"` in a terminal and look for "{RULES_MARK}" in the output '
           "(only the block this installer wrote contains that line).",
           onboard_line("codex", "in the new chat")]
    warning = codex_override_warning(cfg)
    return out + ([warning] if warning else [])


def next_cursor(cfg: Path, args) -> list[str]:
    out = ["Restart Cursor, or open a new chat, so it picks up the agents and skills."]
    if not args.project:
        src = ADAPTERS / "cursor" / f"AGENTS.{args.tier}.md"
        out.append("\n".join([
            "The rules are NOT installed: Cursor has no global rules file. Do one of these:",
            f"- In Cursor Settings > Rules > User Rules, paste the whole of {src}",
            "- Or write them into one repo's AGENTS.md, inside a managed block: run this in your own terminal, "
            "with <your-repo> replaced by the repo's folder:",
            *(f"  {ln}" for ln in install_lines(args, " --project <your-repo> --yes"))]))
    return out


def next_copilot(cfg: Path, args) -> list[str]:
    snippet = ADAPTERS / "copilot" / "vscode-terminal-autoapprove.json"
    return ["Restart VS Code or the Copilot CLI, or open a new chat, so it picks up the rules, agents and skills.",
            "\n".join([
                "The VS Code terminal allowlist is NOT installed (optional; this installer does not edit VS Code's "
                "settings). To add it, run 'Preferences: Open User Settings (JSON)' in VS Code and merge in the "
                "\"chat.tools.terminal.autoApprove\" entries from this file:",
                f"  {snippet}",
                "Each key is an anchored regex, so it matches only that exact command. The Copilot CLI has no "
                "allowlist file; approve commands per session there."])]


def next_antigravity(cfg: Path, args) -> list[str]:
    return ["Restart Antigravity, or open a new chat, so it picks up the rules and settings."]


def next_junie(cfg: Path, args) -> list[str]:
    return ["Restart Junie, or open a new session, so it picks up the rules, agents, skills and commands."]


def next_generic(cfg: Path, args) -> list[str]:
    return [f"Point your tool at {cfg} and confirm it loads the rules, agents and skills (PORTING.md). "
            "Nothing here was checked against your tool."]


def next_claude(cfg: Path, args) -> list[str]:
    return ["Next: open Claude Code and run /starter:setup. It installs CLAUDE.md and merges settings, "
            "asking before each change. This installer leaves those to it so they have one writer.",
            onboard_line("claude", "after setup")]


TOOLS: dict[str, Tool] = {
    "opencode": Tool(opencode_config_dir, ("skills", "agents", "commands"), after=no_notes,
                     next_steps=next_opencode,
                     json_merge=("opencode.permission.json", "opencode.json"), load_check=opencode_check,
                     bins=("opencode",), marks=lambda: [opencode_config_dir()], needs_bin="opencode"),
    "codex": Tool(codex_home, ("skills", "agents", "rules"), after=notes_codex, next_steps=next_codex,
                  load_check=codex_check, shared_skills=True, bins=("codex",), marks=lambda: [codex_home()]),
    "cursor": Tool(cursor_dir, ("skills", "agents"), after=notes_cursor, next_steps=next_cursor, rules_file=None,
                   json_merge=("cli-config.json", "cli-config.json"), load_check=structural_only("cursor"),
                   shared_skills=True, union=("permissions.allow", "permissions.deny"),
                   # The Cursor CLI binary is called `agent`, too generic a name to count as evidence.
                   bins=("cursor", "cursor-agent"), marks=lambda: [cursor_dir()]),
    "copilot": Tool(copilot_home, ("skills", "agents"), after=notes_copilot, next_steps=next_copilot,
                    rules_file="copilot-instructions.md", load_check=structural_only("copilot"),
                    shared_skills=True, bins=("copilot",), marks=lambda: [copilot_home()]),
    "antigravity": Tool(lambda: home() / ".gemini", ("config",), after=notes_antigravity,
                        next_steps=next_antigravity,
                        json_merge=("antigravity-cli.settings.json", "antigravity-cli/settings.json"),
                        load_check=structural_only("antigravity"), union=("permissions.allow",),
                        rules_cap=ANTIGRAVITY_CAP, bins=("agy", "antigravity"),
                        marks=lambda: [home() / ".gemini" / "antigravity-cli", home() / ".gemini" / "config"]),
    "junie": Tool(lambda: home() / ".junie", ("skills", "agents", "commands"), after=notes_junie,
                  next_steps=next_junie,
                  json_merge=("junie.allowlist.json", "allowlist.json"), load_check=structural_only("junie"),
                  shared_skills=True, union=("rules.executables.rules",),
                  bins=("junie",), marks=lambda: [home() / ".junie"]),
    "generic": Tool(None, ("skills", "agents", "commands"), after=notes_generic, next_steps=next_generic),
}
CLAUDE = Tool(claude_config_dir, (), after=no_notes, next_steps=next_claude, bins=("claude",),
              marks=lambda: [claude_config_dir()])
ALL_TOOLS = sorted([*TOOLS, "claude"])


def detect() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name in ALL_TOOLS:
        t = CLAUDE if name == "claude" else TOOLS[name]
        ev = [f"`{b}` on PATH ({shutil.which(b)})" for b in t.bins if shutil.which(b)]
        ev += [f"{d} exists" for d in t.marks() if d.is_dir()]
        if name == "claude" and os.environ.get("CLAUDECODE") == "1":
            ev.append("running inside Claude Code (CLAUDECODE=1)")
        if name != "generic":
            found[name] = ev
    return found


# --------------------------------------------------------------------------
# Execute
# --------------------------------------------------------------------------

def apply(s: Step, repo_python: str) -> None:
    try:
        if s.kind in ("file", "rules"):
            if s.dest.exists():
                s.notes.append(f"backup: {make_backup(s.dest)}")
            s.dest.parent.mkdir(parents=True, exist_ok=True)
            s.dest.write_bytes(s.payload)
            s.status = {"create": "installed", "update": "updated", "merge": "merged"}[s.status]
        elif s.kind == "json":
            theirs = s.original
            b = make_backup(s.dest) if s.dest.exists() else None
            if b:
                s.notes.insert(0, f"backup: {b}")
            s.dest.parent.mkdir(parents=True, exist_ok=True)
            s.dest.write_bytes(s.payload)
            try:
                written = json.loads(s.dest.read_text(encoding="utf-8-sig"))
                if theirs is not None and not contains(written, theirs):
                    raise ValueError("a value you had set is missing after the merge")
            except ValueError as e:
                if b:
                    shutil.copy2(b, s.dest)
                    ok = filecmp.cmp(b, s.dest, shallow=False)
                    s.notes.append(f"restored from backup ({'identical' if ok else 'NOT identical, check by hand'})")
                else:
                    s.dest.unlink(missing_ok=True)
                s.status, s.detail = "failed", f"re-parse check failed: {e}"
                return
            s.status = "installed" if b is None else "merged"
        elif s.kind == "delete":
            s.notes.append(f"backup: {make_backup(s.dest)}")
            s.dest.unlink()
            s.status = "deleted"
        elif s.kind == "move":
            new = Path(s.argv[0])
            if new.exists():
                raise RuntimeError(f"{new} exists; nothing moved")
            new.parent.mkdir(parents=True, exist_ok=True)
            s.dest.rename(new)
            s.status = "moved"
        elif s.kind == "git":
            r = subprocess.run(["git", "-C", str(s.dest), *s.argv], capture_output=True, timeout=300)
            s.notes.extend((r.stdout + r.stderr).decode("utf-8", errors="replace").strip().splitlines())
            s.status = "done" if r.returncode == 0 else "failed"
            if r.returncode:
                s.detail = f"git {' '.join(s.argv)} exited {r.returncode}"
        elif s.kind == "guard":
            r = subprocess.run([repo_python, str(GUARD), "install", str(s.dest)], capture_output=True)
            out = (r.stdout + r.stderr).decode("utf-8", errors="replace").strip()
            s.notes.extend(out.splitlines())
            s.status = "installed" if r.returncode == 0 else "failed"
            if r.returncode:
                s.detail = f"guard.py install exited {r.returncode}"
    except (OSError, RuntimeError) as e:
        s.status, s.detail = "failed", str(e)


def show_plan(steps: list[Step], header: str) -> None:
    print(header)
    for s in steps:
        verb = {"create": "CREATE", "update": "BACKUP+REPLACE", "merge": "BACKUP+MERGE",
                "run": "RUN", "already installed": "SKIP (already installed)", "manual": "BY HAND",
                "skipped": "SKIP", "failed": "CANNOT", "delete": "BACKUP+DELETE", "move": "MOVE",
                "git": "GIT"}.get(s.status, s.status.upper())
        print(f"  {verb:<26} {s.piece:<34} -> {s.dest}" + (f"\n  {'':<26} {s.detail}" if s.detail else ""))
        for n in redact_lines(s.notes) if s.notes else []:
            print(f"  {'':<26}   note: {n}")


def table(rows: list[tuple[str, str, str]]) -> None:
    w = [max(len(r[i]) for r in rows) for i in range(3)]
    for i, r in enumerate(rows):
        print("  ".join(c.ljust(w[j]) for j, c in enumerate(r)).rstrip())
        if i == 0:
            print("  ".join("-" * x for x in w))


def agent_stop_line(args) -> str:
    """The last line an agent reads before it decides whether to apply. An agent once read the bare
    "Re-run with --yes to apply." as its next step and installed without asking the user anything."""
    ask = ("ask whether to add the commit guard to a repo" if args.tool == "claude"
           else "ask which tier (starter or full) and whether to add the commit guard to a repo")
    return (f"If you are an AI agent: stop here. Show the user this plan, {ask}, and end your turn. "
            "Run with --yes only after they reply.")


def install_lines(args, tail: str = " --yes") -> list[str]:
    """This install as one command per shell, for a person to run in their own terminal. `tail` takes
    the place of the closing --yes, to add a flag whose <placeholder> the person fills in. A tail that
    adds --guard-repo is itself the guard answer, so --no-guard is left out of that line."""
    bash, ps = update_commands(args, guard="--guard-repo" not in tail)
    cut = len(" --yes")
    return [f"  bash:       {bash[1][:-cut]}{tail}", f"  PowerShell: {ps[1][:-cut]}{tail}"]


def no_terminal(args) -> None:
    # Without a terminal the reader is almost always an agent (a person gets the y/N prompt), so no
    # ready-to-run --yes command follows the stop line.
    print("\nno terminal and no --yes: dry run only, nothing written.")
    print(agent_stop_line(args))


def confirm(args) -> int | None:
    """None to go ahead, else the exit code."""
    if args.dry_run:
        print("\ndry run: nothing written.")
        print(agent_stop_line(args))
        return 0
    if args.yes:
        return guard_choice_missing(args)
    if not sys.stdin.isatty():
        no_terminal(args)
        return 0
    try:
        answer = input("\nApply this plan? [y/N] ")
    except EOFError:  # Windows reports NUL as a tty, so a redirected stdin can still land here
        no_terminal(args)
        return 0
    if answer.strip().lower() not in ("y", "yes"):
        print("aborted; nothing written.")
        return 1
    return guard_choice_missing(args)


def guard_choice_missing(args) -> int | None:
    """2 when an apply names neither --guard-repo nor --no-guard, else None. The record keeps the
    answer, so an apply that skipped the question would otherwise turn into a permanent no."""
    if getattr(args, "guard_repo", None) or getattr(args, "no_guard", False):
        return None
    print("\nerror: choose the commit guard before applying: add --guard-repo <repo> to install its git hooks "
          "in a repo, or --no-guard to install without it. Nothing was written.", file=sys.stderr)
    return 2


def piece_name(rel: Path) -> str:
    if rel.name == "SKILL.md":
        return f"skill {rel.parent.name}"
    if rel.name == "openai.yaml" and rel.parent.name == "agents":
        return f"skill {rel.parent.parent.name} policy"
    return f"{rel.parent.name.rstrip('s') or 'file'} {rel.name.split('.')[0]}"


def _report():
    """scripts/report.py, or None when it cannot load (it refuses to run without the commit guard)."""
    here = str(Path(__file__).resolve().parent)
    try:
        if here not in sys.path:
            sys.path.insert(0, here)
        import report
        return report
    except (Exception, SystemExit):  # noqa: BLE001 - callers fall back to printing less
        return None


def redact_lines(lines: list[str]) -> list[str]:
    """Tool output can echo the raw config, so it is redacted before it reaches the console."""
    rep = _report()
    if rep is None:
        return [f"({len(lines)} line(s) of tool output withheld: the redactor could not be loaded)"]
    return rep.redact("\n".join(lines)).split("\n")


# Failure context for the report hook; main fills it in as it goes.
# `touched` turns true once the install writes into the tool's config or runs the tool: only then may
# the failure report run `<tool> --version`, which can itself write into the tool's home.
CTX: dict = {"tool": None, "tier": None, "step": "starting the installer", "touched": False}


def _ps_quote(s: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_.-]+", s):
        return s
    for q in ("'", "\u2018", "\u2019", "\u201a", "\u201b"):  # PowerShell treats all of these as quotes
        s = s.replace(q, q + q)
    return f"'{s}'"


def update_commands(args, guard: bool = True) -> tuple[list[str], list[str]]:
    """The commands that repeat this install later, as (bash lines, PowerShell lines): every flag the
    install used, two separate commands per shell (Windows PowerShell 5.1 has no `&&`). An apply exits 2
    without a guard answer, so --no-guard is carried when this run gave it (unless `guard` is False)."""
    words = [("--tool", args.tool)] + ([("--tier", args.tier)] if getattr(args, "tier", None) else [])
    paths = []
    if getattr(args, "config_dir", None):
        paths.append(("--config-dir", args.config_dir))
    if getattr(args, "project", None):
        paths.append(("--project", args.project))
    paths += [("--guard-repo", r) for r in getattr(args, "guard_repo", None) or []]
    paths = [(f, Path(v).expanduser().resolve()) for f, v in paths]
    script = ROOT / "scripts" / "install.py"
    flags = (["--no-guard"] if guard and getattr(args, "no_guard", False) and not getattr(args, "guard_repo", None)
             else [])
    bash_flags = ([f"{f} {shlex.quote(v)}" for f, v in words] + [f"{f} {shlex.quote(v.as_posix())}" for f, v in paths]
                  + flags)
    ps_flags = [f"{f} {_ps_quote(v)}" for f, v in words] + [f"{f} {_ps_quote(str(v))}" for f, v in paths] + flags
    bash = [f"git -C {shlex.quote(ROOT.as_posix())} pull",
            " ".join(["python", shlex.quote(script.as_posix()), *bash_flags, "--yes"])]
    ps = [f"git -C {_ps_quote(str(ROOT))} pull", " ".join(["python", _ps_quote(str(script)), *ps_flags, "--yes"])]
    return bash, ps


def launcher_lines(*words: str) -> tuple[str, str]:
    """(bash, PowerShell) for `python <kit>/scripts/starter.py <words>`, the clone's own launcher."""
    script = cmd_root() / "scripts" / "starter.py"
    return (" ".join(["python", shlex.quote(script.as_posix()), *(shlex.quote(w) for w in words)]),
            " ".join(["python", _ps_quote(str(script)), *(_ps_quote(w) for w in words)]))


def footer(args) -> None:
    print(f"\nkit location: {cmd_root()}")
    bash, ps = launcher_lines("update")
    print("update later (bash: macOS, Linux, Git Bash); it shows the plan and changes nothing until you say yes:")
    print(f"  {bash}")
    print("update later (PowerShell):")
    print(f"  {ps}")


def install_claude(args) -> int:
    """Claude Code: install the plugin through the `claude` CLI. CLAUDE.md and settings are left to
    /starter:setup inside Claude Code, so that one writer owns them (it asks before each change)."""
    CTX["step"] = "installing the Claude Code plugin"
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("`claude` not found on PATH; install Claude Code first (see README.md)")
    env = dict(os.environ)
    cfg = args.config_dir.expanduser().resolve() if args.config_dir else claude_config_dir()
    if args.config_dir:
        env["CLAUDE_CONFIG_DIR"] = str(cfg)
    local = (ROOT / ".claude-plugin" / "marketplace.json").is_file()
    source = str(ROOT) if local else "abyss-node/claude-starter"
    plugin = "starter@claude-starter"

    with tempfile.TemporaryDirectory(prefix="starter-claude-") as cwd:  # no project settings in scope
        def cli(*a: str) -> tuple[int, str]:
            return _run([exe, "plugin", *a], env, cwd)

        def listed(*a: str) -> list:
            rc, out = cli(*a, "--json")
            try:
                return json.loads(out[out.index("["):])
            except ValueError:
                raise RuntimeError(f"`claude plugin {' '.join(a)} --json` exited {rc}:\n{out.strip()}") from None

        CTX["touched"] = True
        markets = {m.get("name"): m for m in listed("marketplace", "list")}
        plugins = {p.get("id"): p for p in listed("list")}
        m = Step("marketplace claude-starter", cfg, "cli", detail=f"claude plugin marketplace add {source}")
        if "claude-starter" in markets:
            have = markets["claude-starter"]
            m.status = "already installed"
            m.detail = f"from {have.get('path') or have.get('repo') or have.get('url') or have.get('source')}"
        else:
            m.status = "run"
        p = Step(f"plugin {plugin}", cfg, "cli")
        if plugin not in plugins:
            p.status, p.detail = "run", f"claude plugin install {plugin}"
        elif not plugins[plugin].get("enabled"):
            p.status, p.detail = "run", f"claude plugin enable {plugin} (installed but disabled)"
        else:
            p.status = "already installed"
        steps = [m, p] + [plan_guard(r) for r in args.guard_repo]
        show_plan(steps, f"claude-starter -> claude (plugin), config dir: {cfg}")
        problems = preflight(steps, None)
        if problems:
            return preflight_failed(problems)
        rc = confirm(args)
        if rc is None:
            rc = check_writable(steps, args)
        if rc is not None:
            return rc
        for s in steps:
            if s.kind == "cli" and s.status == "run":
                CTX["step"] = s.detail
                argv = s.detail.split()[2:]
                if argv[:2] == ["marketplace", "add"]:
                    argv = ["marketplace", "add", source]  # the path may contain spaces
                code, out = cli(*argv, "--json")
                s.notes.extend(ln for ln in out.strip().splitlines() if ln.strip())
                s.status = "installed" if code == 0 else "failed"
                if code:
                    s.detail = f"exited {code}"
            elif s.writes:
                apply(s, sys.executable)
        CTX["step"] = "load check: claude plugin list"
        now = {x.get("id"): x for x in listed("list")}
        ok = bool(now.get(plugin, {}).get("enabled"))
        check = [f"`claude plugin list`: {plugin} " + ("enabled" if ok else f"NOT enabled ({now.get(plugin)})")]
    return finish_run("claude", None, steps, ok, check,
                      "passed (claude plugin list shows it enabled)" if ok else "FAILED",
                      CLAUDE.after(cfg, args), args, CLAUDE.next_steps(cfg, args),
                      record=lambda: record_install("claude", None, cfg, steps, args))


def finish_run(tool: str, tier: str | None, steps: list[Step], ok_load: bool, load_lines: list[str],
               verdict: str, after: list[str], args, next_steps: list[str],
               record: Callable[[], dict] | None = None) -> int:
    print()
    rows = [("piece", "destination", "status")]
    for s in steps:
        rows.append((s.piece, str(s.dest), s.status + (f" ({s.detail})" if s.status == "failed" else "")))
    rows.append(("load check", tool, verdict))
    table(rows)
    notes = [f"{s.piece}: {n}" for s in steps for n in s.notes]
    for ln in redact_lines(notes) if notes else []:  # tool output and the user's own values land in notes
        print(f"  {ln}")
    if load_lines:
        print("\nload check:" if ok_load else "\nload check FAILED:")
        for ln in redact_lines(load_lines):
            print(f"  {ln}")
    failed = [s for s in steps if s.status == "failed"]
    if failed or not ok_load:
        print(f"\nFAILED: {len(failed)} piece(s) failed" + ("" if ok_load else "; the load check failed"),
              file=sys.stderr)
        CTX["step"] = ", ".join(s.piece for s in failed) or "load check"
        error = [f"{s.piece} -> {s.dest}: {s.detail}" for s in failed]
        if not ok_load:
            error += ["load check:", *load_lines]
        report_failure("\n".join(error))
        return 1
    rec = record() if record else None
    footer(args)
    # Last, so it is what the user and any agent read last; the caveats print nowhere else.
    print_for_you([*next_steps, guard_status(args), *notice_item(rec), *limits_item(after)])
    return 0


def report_failure(error_text: str, version_note: str | None = None) -> None:
    """Save a redacted report and print how to send it. Never sends anything."""
    if version_note is None and not CTX.get("touched"):
        version_note = "version not probed (failed before the install touched the tool)"
    try:
        report = _report()
        if report is None:
            raise RuntimeError("scripts/report.py could not be loaded")
        rendered = report.render_markdown(report.build_report(
            "install-failure", CTX["step"], error_text, extra={"tier": CTX["tier"] or "-"}, tool=CTX["tool"],
            version_note=version_note))
        out_dir = Path(tempfile.gettempdir()) / "claude-starter-reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = report.save_report(rendered, str(out_dir / f"install-failure-{STAMP}.md"))
        err = out_dir / f"install-failure-{STAMP}.error.txt"
        with open(err, "w", encoding="utf-8", newline="\n") as f:
            f.write(rendered.sections["error"] + "\n")
        url, truncated = report.issue_url(rendered)
    except Exception as e:  # noqa: BLE001 - a broken reporter must not hide the original failure
        print(f"\n(could not build a failure report: {type(e).__name__}: {e})", file=sys.stderr)
        return
    print(f"\nA redacted failure report was saved: {path}")
    print("Read it first; it would become public if you post it.")
    print(f"Pre-filled issue{' (shortened; paste the saved file instead)' if truncated else ''}:\n{url}")
    step = CTX["step"].replace('"', "'")
    print(f"Nothing was sent. To report: open the URL, or run `python \"{ROOT / 'scripts' / 'report.py'}\" "
          f"--submit --kind install-failure --tool {CTX['tool']} --step \"{step}\" --error-file \"{err}\"`")


def preflight(steps: list[Step], tool: Tool | None) -> list[str]:
    """Every reason the install cannot complete, found before anything is written."""
    problems = [f"{s.piece} -> {s.dest}: {s.detail}" for s in steps if s.status == "failed"]
    if tool and tool.needs_bin and not shutil.which(tool.needs_bin):
        problems.append(f"`{tool.needs_bin}` not found on PATH: the install is only accepted once "
                        f"{tool.needs_bin} itself loads it. Install {tool.needs_bin} (or fix PATH) and re-run")
    return problems


def preflight_failed(problems: list[str]) -> int:
    print("\npreflight FAILED; nothing was written:", file=sys.stderr)
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    CTX["step"] = "preflight"
    report_failure("preflight failed; nothing written:\n" + "\n".join(problems),
                   version_note="version not probed (preflight failure)")
    return 1


# --------------------------------------------------------------------------
# Write probe: a sandboxed agent session can read the tool's config but not write it
# --------------------------------------------------------------------------

UNWRITABLE = 3  # exit code: a destination cannot be written; nothing was written
# Set in the shell of a Codex agent (codex-rs exec_env.rs and spawn.rs, 0.167.0). They only pick the
# message: whether a folder can be written is found by trying, since no variable proves a sandbox.
CODEX_MARKERS = ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED")


def guard_hooks_dir(repo: Path) -> Path:
    """Where guard.py install writes the hooks: git's hooks path, else <repo>/.git/hooks."""
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "hooks"],
                           capture_output=True, timeout=60)
        out = r.stdout.decode("utf-8", errors="replace").strip()
        if r.returncode == 0 and out:
            p = Path(out)
            return p if p.is_absolute() else repo / p
    except (OSError, subprocess.TimeoutExpired):
        pass
    return repo / ".git" / "hooks"


def write_targets(steps: list[Step]) -> tuple[list[Path], list[Path]]:
    """(every folder the plan writes into, every existing file it changes), each once, in plan order."""
    dirs: list[Path] = []
    files: list[Path] = []
    for s in steps:
        if not s.writes or s.dest is None:
            continue
        if s.kind in ("file", "rules", "json"):
            found = [s.dest.parent]
            if s.dest.is_file():
                files.append(s.dest)
        elif s.kind == "guard":
            found = [guard_hooks_dir(s.dest), guard_data_dir()]
        elif s.kind == "cli":
            found = [s.dest]
        elif s.kind == "git":
            found = [git_dir(s.dest)]  # git -C <dest> writes into the repo's git dir
        elif s.kind == "delete":
            found = [s.dest.parent]  # the backup lands beside it, then it is unlinked
        elif s.kind == "move":
            found = [s.dest.parent, Path(s.argv[0]).parent]
        else:
            raise ValueError(f"{s.piece}: no write target known for step kind {s.kind!r}")
        dirs += [d for d in found if d not in dirs]
    return dirs, files


def git_dir(repo: Path) -> Path:
    """The git dir of the repo at `repo` (its .git folder, or what a .git file points to)."""
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"], capture_output=True,
                           timeout=60)
        out = r.stdout.decode("utf-8", errors="replace").strip()
        if r.returncode == 0 and out:
            return Path(out)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return repo / ".git"


def probe_dir(d: Path) -> OSError | None:
    """Make `d` the way apply would, create, write and delete one uniquely named file in it, then
    remove every folder the probe made. None when all of that worked; the probe leaves no trace."""
    made: list[Path] = []
    try:
        for m in reversed([p for p in (d, *d.parents) if not p.exists()]):
            m.mkdir()
            made.append(m)
        probe = d / f".claude-starter-write-probe-{os.getpid()}-{uuid.uuid4().hex}"
        fd = os.open(str(probe), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, b"x")
        finally:
            os.close(fd)
        os.unlink(str(probe))
        return None
    except OSError as e:
        return e
    finally:
        for m in reversed(made):
            try:
                m.rmdir()
            except OSError:
                pass


def unwritable(steps: list[Step]) -> list[tuple[Path, OSError]]:
    """Every destination the plan cannot write, found by trying, before anything is written."""
    dirs, files = write_targets(steps)
    bad = [(d, e) for d, e in ((d, probe_dir(d)) for d in dirs) if e is not None]
    for f in files:
        try:
            with open(f, "r+b"):  # opened for writing, nothing written
                pass
        except OSError as e:
            bad.append((f, e))
    return bad


def refuse_unwritable(bad: list[tuple[Path, OSError]], args) -> int:
    """Refuse the whole install. A partial or project-local install never reaches the global config,
    which once left a Codex user pasting the kit's link into every new chat."""
    err = sys.stderr
    print("\nCANNOT WRITE; nothing was written:", file=err)
    for path, e in bad:
        print(f"  {path}: {type(e).__name__}: {e}", file=err)
    markers = [k for k in CODEX_MARKERS if os.environ.get(k)]
    if markers:
        print(f"\nThis looks like a Codex sandbox ({', '.join(markers)} is set). It lets this session write "
              "to its own workspace, not to your tool's global config. A Codex cloud task runs in a temporary "
              "container, so an install there would not reach your machine either.", file=err)
    else:
        print("\nThis looks like a sandboxed agent session, or a folder you cannot write to.", file=err)
    print("Installing into the project folder, or copying the files by hand, would reach only this "
          "project or this session, not your tool's global config, so the installer does neither.", file=err)
    print("To install, run this in your own terminal (not through the agent):", file=err)
    for ln in install_lines(args):
        print(ln, file=err)
    if markers:
        print("Or approve running it outside the sandbox when Codex asks, or give the session write access "
              "to the folders above (Full access, or sandbox_workspace_write.writable_roots in Codex's "
              "config.toml) and run it again.", file=err)
    else:
        print("Or make the folders above writable and run it again.", file=err)
    print("If you are an AI agent: do not work around this. Show the user this message and end your turn.",
          file=err)
    return UNWRITABLE


def check_writable(steps: list[Step], args) -> int | None:
    """None when every destination can be written, else the exit code after refusing."""
    CTX["step"] = "checking that every destination can be written"
    bad = unwritable(steps)
    err = probe_dir(record_dir())
    if err is not None:
        bad.append((record_dir(), err))
    return refuse_unwritable(bad, args) if bad else None


# --------------------------------------------------------------------------
# The "For you" block: what the person at the keyboard does next, printed last
# --------------------------------------------------------------------------

FOR_YOU = "=== For you (the person at the keyboard) ==="


def guard_status(args) -> str:
    repos = [str(Path(r).expanduser().resolve()) for r in getattr(args, "guard_repo", None) or []]
    if repos:
        return "Commit guard: installed as git hooks in " + ", ".join(repos) + "."
    inside = " Inside Claude Code the plugin's hook still checks Claude's own commits." if args.tool == "claude" else ""
    return "\n".join([f"Commit guard: NOT installed in any repo.{inside} To add it to a repo, run this in your "
                      "own terminal, with <your-repo> replaced by the repo's folder:",
                      *install_lines(args, " --guard-repo <your-repo> --yes")])


def limits_item(after: list[str]) -> list[str]:
    """The tool's caveats as one last item. They live inside the block because an agent relays only
    the block: printed above it, the Codex read-only caveat never reached the user."""
    if not after:
        return []
    return ["\n".join(["Limits of this install:", *("- " + ln.replace("\n", "\n  ") for ln in after)])]


def print_for_you(items: list[str]) -> None:
    print()
    print(FOR_YOU)
    for i, item in enumerate(items, 1):
        first, *rest = item.split("\n")
        print(f"{i}. {first}")
        for ln in rest:
            print(f"   {ln}")


# --------------------------------------------------------------------------
# Install record: ~/.agents/starter/installs.json, one per machine, outside the clone
# --------------------------------------------------------------------------

RECORD_SCHEMA = 1
_CMD_ROOT: list = []  # set by --plan-update: commands it prints name the real clone, not the snapshot


def cmd_root() -> Path:
    return _CMD_ROOT[0] if _CMD_ROOT else ROOT


def record_dir() -> Path:
    return home() / ".agents" / "starter"


def record_path() -> Path:
    return record_dir() / "installs.json"


def kit_version(root: Path = ROOT) -> str | None:
    """The kit's version, from its one home, kit.json at the repo root."""
    try:
        v = json.loads((root / "kit.json").read_text(encoding="utf-8")).get("version")
        return v if isinstance(v, str) else None
    except (OSError, ValueError, AttributeError):
        return None


def git(root: Path, *a: str, timeout: int = 120) -> tuple[int, str]:
    """(exit code, stdout) of `git -C root ...`; stderr instead of stdout when it fails."""
    try:
        r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"{type(e).__name__}: {e}"
    out = r.stdout if r.returncode == 0 else r.stderr or r.stdout
    return r.returncode, out.decode("utf-8", errors="replace").strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_record() -> dict | None:
    p = record_path()
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != RECORD_SCHEMA:
        raise RuntimeError(f"{p} has schema {data.get('schema') if isinstance(data, dict) else '?'!r}; "
                           f"this installer reads schema {RECORD_SCHEMA}")
    return data


def new_record() -> dict:
    return {"schema": RECORD_SCHEMA, "kit": {"kit_root": None, "remote": None, "version": None, "sha": None},
            "plan": None, "onboarded_at": None, "scope": None, "notices": {"update": None}, "installs": []}


def kit_facts(root: Path, sha: str | None = None) -> dict:
    rc, remote = git(root, "remote", "get-url", "origin")
    if sha is None:
        rc_head, head = git(root, "rev-parse", "HEAD")
        sha = head if rc_head == 0 else None
    return {"kit_root": str(root), "remote": remote if rc == 0 else None, "version": kit_version(root), "sha": sha}


def save_record(rec: dict) -> bool:
    """Write the record atomically, after a byte-checked .bak of the old one. False when unchanged."""
    p = record_path()
    text = json.dumps(rec, indent=2) + "\n"
    if p.is_file() and p.read_text(encoding="utf-8") == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        make_backup(p)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(str(tmp), str(p))
    return True


def find_install(rec: dict, tool: str, cfg: Path) -> dict | None:
    return next((i for i in rec["installs"] if i["tool"] == tool and i["config_dir"] == str(cfg)), None)


def recorded_files(steps: list[Step]) -> dict:
    """dest -> sha256 for whole files the kit owns. Rules and JSON files are shared with the user, so
    only the kit's part of them is named (the managed block; the merged keys)."""
    out = {}
    for s in steps:
        if s.dest is None or s.status in ("failed", "skipped", "manual"):
            continue
        if s.kind == "file" and s.dest.is_file():
            out[str(s.dest)] = sha256(s.dest.read_bytes())
        elif s.kind == "rules":
            out[str(s.dest)] = "managed block"
        elif s.kind == "json":
            out[str(s.dest)] = "merged keys"
    return out


def guard_option(args, old: dict | None) -> dict | None:
    """The guard answer this run gives, merged with the recorded one; None when never asked."""
    repos = sorted({str(Path(r).expanduser().resolve()) for r in getattr(args, "guard_repo", None) or []}
                   | set((old or {}).get("repos") or []))
    if getattr(args, "guard_repo", None):
        return {"state": "installed", "repos": repos}
    if getattr(args, "no_guard", False):
        return {"state": "installed" if repos else "declined", "repos": repos}
    return old


def record_install(tool: str, tier: str | None, cfg: Path, steps: list[Step], args) -> dict:
    """Add or refresh this install in the record and return the record. A fresh install is at the
    kit's current layout, so every migration this kit ships counts as applied to it."""
    rec = load_record() or new_record()
    rec["kit"] = kit_facts(ROOT)
    entry = find_install(rec, tool, cfg)
    if entry is None:
        entry = {"tool": tool, "tier": tier, "config_dir": str(cfg), "adopted": False,
                 "migrations_applied": [m.ID for m in load_migrations()], "files": {}, "options": {}}
        rec["installs"].append(entry)
    entry["tier"] = tier
    entry["files"] = recorded_files(steps)
    if getattr(args, "project", None):
        entry["project"] = str(Path(args.project).expanduser().resolve())
    g = guard_option(args, entry["options"].get("guard"))
    if g is not None:
        entry["options"]["guard"] = g
    save_record(rec)
    return rec


def notice_item(rec: dict | None) -> list[str]:
    """The For-you item that asks about update notices while the record says they were never chosen."""
    if not rec or (rec.get("notices") or {}).get("update") is not None:
        return []
    on_b, on_p = launcher_lines("notices", "on")
    off_b, off_p = launcher_lines("notices", "off")
    tools = {i["tool"] for i in rec.get("installs") or []}
    where = (["a new Claude Code session"] if "claude" in tools else []) + (
        ["the checkpoint and lanes commands" + (" in your other tools" if "claude" in tools else "")]
        if tools - {"claude"} else [])
    return ["\n".join([
        f"Update notices: choose whether to get one. When on, {' and '.join(where) or 'a new session'} "
        f"print{'s' if where in ([], ['a new Claude Code session']) else ''} one line when a newer version of the kit is out, at most once "
        "a day (it never updates anything). Run one of these in your own terminal:",
        f"  on,  bash:       {on_b}", f"  on,  PowerShell: {on_p}",
        f"  off, bash:       {off_b}", f"  off, PowerShell: {off_p}"])]


def kit_root_mismatch() -> int | None:
    """2 when the record names a different clone: two clones updating one record would undo each other."""
    try:
        rec = load_record()
    except (OSError, ValueError, RuntimeError):
        return None
    root = (rec or {}).get("kit", {}).get("kit_root")
    if root and Path(root).resolve() != ROOT.resolve():
        print(f"error: this machine's install record ({record_path()}) belongs to the clone at {root}, not "
              f"{ROOT}. Run that clone's installer, or remove the record to start again. Nothing was written.",
              file=sys.stderr)
        return 2
    return None


# --------------------------------------------------------------------------
# Migrations: scripts/migrations/NNNN_slug.py (the interface is in scripts/migrations/__init__.py)
# --------------------------------------------------------------------------

def load_migrations() -> list:
    here = str(ROOT / "scripts")
    if here not in sys.path:
        sys.path.insert(0, here)
    import migrations
    return migrations.discover(ROOT / "scripts" / "migrations")


def migration_ctx(entry: dict) -> SimpleNamespace:
    return SimpleNamespace(tool=entry["tool"], tier=entry.get("tier"), config_dir=Path(entry["config_dir"]),
                           home=home(), kit_root=cmd_root(), entry=entry, Step=Step, plan_file=plan_file,
                           backup_path=backup_path)


# --------------------------------------------------------------------------
# Adoption: installs made before the record existed
# --------------------------------------------------------------------------

def rules_block(path: Path) -> str | None:
    try:
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return None
    b, e = BEGIN_RX.search(text), END_RX.search(text)
    return text[b.end():e.start()].strip("\n") if b and e and e.start() > b.end() else None


def git_bytes(*a: str) -> bytes | None:
    """Raw stdout of `git -C <clone> ...`, None when it fails. The clone, not ROOT: a plan runs from a
    snapshot that has no .git."""
    try:
        r = subprocess.run(["git", "-C", str(cmd_root()), *a], capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def release_tags() -> list[str]:
    """The clone's vX.Y.Z tags, newest first."""
    out = git_bytes("tag", "--list", "v*", "--sort=-v:refname") or b""
    return [t for t in out.decode("utf-8", "replace").split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]


def blob_ids(data: bytes) -> set:
    """Git's blob id of these bytes, as written and with CRLF turned to LF (a checkout may convert)."""
    return {hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest() for d in (data, data.replace(b"\r\n", b"\n"))}


def adopted_version(name: str, tier: str, block: str | None, tags: list[str]) -> str:
    """This kit's version when the block is the one it ships, else the newest release tag whose block
    matches exactly, else the oldest the record can say."""
    def norm(text: str) -> str:
        return text.replace("\r\n", "\n").strip("\n")
    shipped = ADAPTERS / name / f"AGENTS.{tier}.md"
    if block is not None and shipped.is_file() and block == norm(shipped.read_text(encoding="utf-8")):
        return kit_version() or "unknown"
    for t in tags if block is not None else []:
        data = git_bytes("show", f"{t}:adapters/{name}/AGENTS.{tier}.md")
        if data is not None and norm(data.decode("utf-8", "replace")) == block:
            return t[1:]
    return "<=0.3.1 or edited"


def adopted_files(name: str, tool: Tool, cfg: Path, tags: list[str]) -> dict:
    """dest -> sha256 for each file in a tool's config whose bytes match a file some release tag shipped
    for that tool, so one no longer shipped is planned as an orphan. A file that matches no shipped
    bytes is left out, so an edited file is never deleted."""
    shipped: dict = {}
    for t in tags:
        out = git_bytes("ls-tree", "-r", "-z", t, "--", f"adapters/{name}/") or b""
        for row in filter(None, out.split(b"\0")):
            meta, _, path = row.decode("utf-8", "replace").partition("\t")
            fields, parts = meta.split(), Path(path).parts[2:]  # path: adapters/<tool>/...
            if len(fields) == 3 and fields[1] == "blob" and len(parts) > 1 and parts[0] in tool.dirs:
                shipped.setdefault(Path(*parts), set()).add(fields[2])
    files: dict = {}
    for rel, ids in sorted(shipped.items()):
        dests = [cfg / rel]
        if tool.shared_skills and rel.parts[0] == "skills":
            dests.insert(0, shared_skills_dir() / Path(*rel.parts[1:]))
        for d in dests:
            if str(d) not in files and d.is_file() and blob_ids(d.read_bytes()) & ids:
                files[str(d)] = sha256(d.read_bytes())
    return files


def adopt(rec: dict | None) -> dict:
    """The record plus every non-Claude install found at a tool's standard config dir that the record
    lacks, marked adopted. In memory only; an apply writes it."""
    rec = json.loads(json.dumps(rec)) if rec else new_record()
    tags: list | None = None
    for name, tool in TOOLS.items():
        if tool.config_dir is None:
            continue  # generic: custom --config-dir installs cannot be found
        cfg = tool.config_dir()
        if find_install(rec, name, cfg):
            continue
        block = rules_block(cfg / tool.rules_file) if tool.rules_file else None
        agents = cfg / "agents"
        has_agents = agents.is_dir() and any(p.name.split(".")[0] in KIT_AGENTS for p in agents.iterdir())
        if block is None and not has_agents:
            continue
        tier = "full" if block and "Full version" in block else "starter"
        tags = release_tags() if tags is None else tags
        rec["installs"].append({"tool": name, "tier": tier, "config_dir": str(cfg), "adopted": True,
                                "adopted_version": adopted_version(name, tier, block, tags),
                                "migrations_applied": [], "files": adopted_files(name, tool, cfg, tags),
                                "options": {"guard": {"state": "unknown", "repos": []}}})
    return rec


# --------------------------------------------------------------------------
# --update: plan every recorded install from the target commit, pin the plan, apply on one yes
# --------------------------------------------------------------------------

PIN_KINDS = ("delete", "move", "git")


def plan_installs(rec: dict, guard_repos: list = ()) -> list[Step]:
    """Migrations, reinstall and orphans for every install in `rec`, the commit guard copy, and the
    guard's git hooks for each `guard_repos` entry (this run's --guard-repo)."""
    mods = load_migrations()
    planned: set = set()
    per_install = []
    for entry in rec["installs"]:
        if entry["tool"] == "claude":
            continue  # its plugin loads from the clone, so the fast-forward is its update
        mig: list[Step] = []
        done = set(entry.get("migrations_applied") or [])
        for m in mods:
            if m.ID in done:
                continue
            for s in m.plan(migration_ctx(entry)) or []:
                s.migration = m.ID
                mig.append(s)
        project = Path(entry["project"]) if entry.get("project") else None
        re_steps = plan_tool(entry["tool"], entry.get("tier") or "starter", Path(entry["config_dir"]), project, [])
        planned |= {str(s.dest) for s in re_steps if s.dest}
        per_install.append((entry, mig, re_steps))
    steps: list[Step] = []
    seen: set = set()
    for entry, mig, re_steps in per_install:
        for s in mig + re_steps:
            key = (str(s.dest), s.kind, s.migration)
            if key not in seen:  # tools sharing ~/.agents/skills plan the same file once
                seen.add(key)
                steps.append(s)
        for dest, h in sorted((entry.get("files") or {}).items()):
            p = Path(dest)
            if dest in planned or not p.is_file() or len(h) != 64 or (dest, "delete", None) in seen:
                continue
            seen.add((dest, "delete", None))
            if sha256(p.read_bytes()) == h:
                steps.append(Step(f"orphan {p.name}", p, "delete", status="delete",
                                  detail=f"no longer shipped; backup to {backup_path(p).name}, then delete"))
            else:
                steps.append(Step(f"orphan {p.name}", p, "delete", status="skipped",
                                  detail="no longer shipped, but you edited it, so it stays"))
    data_guard = guard_data_dir() / "guard.py"
    hooked = any(((e.get("options") or {}).get("guard") or {}).get("repos") for e in rec["installs"])
    if data_guard.is_file() or hooked:
        # Hooked repos call this copy by absolute path and skip the guard when it is missing, so it is
        # refreshed, or put back, for every one of them.
        steps.append(plan_file("commit guard copy", GUARD, data_guard))
    for r in dict.fromkeys(str(Path(r).expanduser().resolve()) for r in guard_repos):
        steps.append(plan_guard(r))
    return steps


def plan_id(sha: str, rec: dict, steps: list[Step]) -> str:
    """Pins a plan: the target commit, the record (all but the notice setting, which no step reads),
    and each step's dest, kind, status and payload."""
    body = {"sha": sha, "record": {k: v for k, v in rec.items() if k != "notices"},
            "steps": [[str(s.dest), s.kind, s.status, sha256(s.payload), s.migration, s.argv] for s in steps]}
    return sha256(json.dumps(body, sort_keys=True).encode("utf-8"))[:16]


def needs_pin(steps: list[Step]) -> bool:
    return any(s.writes and (s.migration or s.kind in PIN_KINDS) for s in steps)


def version_key(v: str | None) -> tuple:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else (-1,)


def newer_changelog(root: Path, have: str | None) -> list[str]:
    try:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return []
    out, keep = [], False
    for ln in text.splitlines():
        m = re.match(r"^## \[?v?(\d+\.\d+\.\d+)", ln)
        if m:
            keep = have is None or version_key(m.group(1)) > version_key(have)
        elif ln.startswith("## "):
            keep = False
        if keep:
            out.append(ln)
    return out


def update_stop_line() -> str:
    return ("If you are an AI agent: stop here. Show the user this plan and end your turn. Apply it only after "
            "they reply yes.")


def guard_flags(args) -> list[str]:
    out = ["--no-guard"] if getattr(args, "no_guard", False) else []
    for r in getattr(args, "guard_repo", None) or []:
        out += ["--guard-repo", str(Path(r).expanduser().resolve())]
    return out


def pinned_lines(sha: str, pid: str, args) -> list[str]:
    bash, ps = launcher_lines("update", "--yes", "--to", sha, "--plan", pid, *guard_flags(args))
    return [f"  bash:       {bash}", f"  PowerShell: {ps}"]


def print_update_plan(rec: dict, steps: list[Step], sha: str, pid: str, args, snapshot_root: Path) -> None:
    """Header with the id, what changed, migrations, the file plan, never-asked options, the pinned
    apply command, and the agent stop line last."""
    kit = rec.get("kit") or {}
    print(f"claude-starter update, plan {pid}: {kit.get('version') or 'unknown'} "
          f"({(kit.get('sha') or '?')[:12]}) -> {kit_version(snapshot_root) or 'unknown'} ({sha[:12]})")
    news = newer_changelog(snapshot_root, kit.get("version"))
    if news:
        print("\nwhat changed (CHANGELOG.md):")
        for ln in news:
            print(f"  {ln}")
    titles = {m.ID: m.TITLE for m in load_migrations()}
    migs = sorted({s.migration for s in steps if s.migration and s.writes})
    if migs:
        print("\nmigrations:")
        for i in migs:
            print(f"  {i}: {titles.get(i, '')}")
    for e in rec["installs"]:
        if e.get("adopted") and not e.get("migrations_applied"):
            print(f"\nadopted: {e['tool']} at {e['config_dir']} (tier {e['tier']}, version "
                  f"{e.get('adopted_version')}); installs at a custom --config-dir are not found")
    print()
    show_plan([s for s in steps if s.status != "already installed"], "file plan:")
    print(f"  ({sum(1 for s in steps if s.status == 'already installed')} file(s) already current)")
    unasked = [e for e in rec["installs"] if e["tool"] != "claude" and "guard" not in (e.get("options") or {})]
    notices = (rec.get("notices") or {}).get("update")
    if unasked or notices is None:
        print("\nnever asked:")
        for e in unasked:
            # The answer is part of the plan (--guard-repo adds a step, so it changes the id): it goes into
            # a new plan, never into this plan's apply command.
            print(f"  commit guard for {e['tool']}: ask the user, then make the plan again with their answer "
                  "added, --guard-repo <repo> or --no-guard, and apply the command that plan prints")
        if notices is None and not record_path().is_file():
            print("  update notices: the apply's closing block asks (no install is recorded yet)")
        elif notices is None:
            on_b, on_p = launcher_lines("notices", "on")
            print("  update notices: in your own terminal, any time (it does not change this plan):\n"
                  f"    bash:       {on_b}\n    PowerShell: {on_p}\n    (or the same with off)")
    print("\nTo apply exactly this plan, after the user's yes, run:")
    for ln in pinned_lines(sha, pid, args):
        print(ln)
    print("(The plan id proves that this plan was printed, not that anyone read it.)")
    print(update_stop_line())


def refuse_update(title: str, bad: list[tuple[Path, object]]) -> int:
    """Exit 3 with the launcher command for the person's own terminal; never a project-local copy."""
    err = sys.stderr
    print(f"\n{title}; nothing was written:", file=err)
    for path, e in bad:
        print(f"  {path}: {type(e).__name__ + ': ' if isinstance(e, OSError) else ''}{e}", file=err)
    markers = [k for k in CODEX_MARKERS if os.environ.get(k)]
    if markers:
        print(f"\nThis looks like a Codex sandbox ({', '.join(markers)} is set).", file=err)
    print("Updating a project-local copy would not reach your tool's global config, so the updater does not.",
          file=err)
    bash, ps = launcher_lines("update")
    print("Run this in your own terminal (not through the agent):", file=err)
    print(f"  bash:       {bash}\n  PowerShell: {ps}", file=err)
    print("If you are an AI agent: do not work around this. Show the user this message and end your turn.",
          file=err)
    return UNWRITABLE


def update_targets_writable(steps: list[Step]) -> int | None:
    CTX["step"] = "checking that every destination can be written"
    bad: list = list(unwritable(steps))
    e = probe_dir(record_dir())
    if e is not None:
        bad.append((record_dir(), e))
    return refuse_update("CANNOT WRITE", bad) if bad else None


def plan_update_child(args) -> int:
    """Runs inside the snapshot of the target commit: plan, or verify a plan id. Writes nothing."""
    if not args.kit_root or not args.to:
        print("error: --plan-update needs --kit-root and --to", file=sys.stderr)
        return 2
    kit_root = args.kit_root.resolve()
    _CMD_ROOT[:] = [kit_root]
    rec = load_record()
    if rec and rec["kit"].get("kit_root") and Path(rec["kit"]["kit_root"]).resolve() != kit_root:
        print(f"error: the record names the clone {rec['kit']['kit_root']}, not {kit_root}", file=sys.stderr)
        return 2
    rec = adopt(rec)
    steps = plan_installs(rec, args.guard_repo)
    pid = plan_id(args.to, rec, steps)
    rc = update_targets_writable(steps)
    if rc is not None:
        return rc
    if args.plan and args.plan != pid:
        print(f"error: the plan changed since {args.plan} was printed (now {pid}); nothing was written. "
              "Show the user the new plan:", file=sys.stderr)
        print_update_plan(rec, steps, args.to, pid, args, ROOT)
        return 2
    if args.plan:
        print(f"plan {pid} verified against {args.to[:12]}")
        return 0
    print_update_plan(rec, steps, args.to, pid, args, ROOT)
    return 0


def snapshot_plan(kit_root: Path, sha: str, args, verify: str | None) -> int:
    """`git archive <sha>` into a temp folder and let that commit's installer plan (or verify `verify`).
    It writes nothing: test_update.py hashes HOME and the clone around it."""
    with tempfile.TemporaryDirectory(prefix="starter-snapshot-") as tmp:
        r = subprocess.run(["git", "-C", str(kit_root), "archive", "--format=tar", sha], capture_output=True,
                           timeout=300)
        if r.returncode:
            print(f"error: git archive {sha} failed: {r.stderr.decode('utf-8', 'replace').strip()}",
                  file=sys.stderr)
            return 1
        tar_path = Path(tmp) / "snap.tar"
        tar_path.write_bytes(r.stdout)
        snap = Path(tmp) / "kit"
        snap.mkdir()
        with tarfile.open(str(tar_path)) as tf:
            if hasattr(tarfile, "data_filter"):
                tf.extractall(str(snap), filter="data")
            else:
                tf.extractall(str(snap))
        cmd = [sys.executable, str(snap / "scripts" / "install.py"), "--plan-update", "--kit-root", str(kit_root),
               "--to", sha, *guard_flags(args)] + (["--plan", verify] if verify else [])
        sys.stdout.flush()
        return subprocess.run(cmd).returncode


def update_target(kit_root: Path, args) -> tuple[str | None, str]:
    """(target sha, "") or (None, why). The newest vX.Y.Z tag, or HEAD when HEAD is not behind it."""
    rc, head = git(kit_root, "rev-parse", "HEAD")
    if rc:
        return None, f"{kit_root} is not a git clone: {head}"
    if args.to:
        rc, sha = git(kit_root, "rev-parse", "--verify", "--quiet", f"{args.to}^{{commit}}")
        return (sha, "") if rc == 0 else (None, f"--to {args.to}: no such commit in {kit_root}")
    if args.offline:
        return head, ""
    rc, tags = git(kit_root, "tag", "--list", "v*", "--sort=-v:refname")
    tag = next((t.strip() for t in tags.splitlines() if re.fullmatch(r"v\d+\.\d+\.\d+", t.strip())), None)
    if not tag:
        return head, ""
    rc, sha = git(kit_root, "rev-parse", f"{tag}^{{commit}}")
    if rc:
        return None, sha
    if git(kit_root, "merge-base", "--is-ancestor", sha, head)[0] == 0:
        return head, ""  # already at or past the newest release
    return sha, ""


def run_update(args) -> int:
    CTX["tool"], CTX["step"] = "update", "planning the update"
    if args.dry_run:
        # --dry-run wins over --yes, as it does for an install: plan only, whatever else was passed.
        args.yes = False
        print("dry run: planning only; nothing is written.")
    rec = load_record()
    kit_root = Path(rec["kit"]["kit_root"]) if rec and rec["kit"].get("kit_root") else ROOT
    if kit_root.resolve() != ROOT.resolve():
        print(f"error: the install record ({record_path()}) names the clone {kit_root}, not {ROOT}. Run that "
              "clone's scripts/starter.py update. Nothing was written.", file=sys.stderr)
        return 2
    if not adopt(rec)["installs"]:
        print("Nothing to update: no install is recorded here and none was found at a tool's standard config "
              "dir. Install first (README.md).", file=sys.stderr)
        return 2
    # Writable first: the record dir and the clone, before the fetch writes into the clone.
    bad = [(d, e) for d, e in ((d, probe_dir(d)) for d in (record_dir(), kit_root / ".git")) if e is not None]
    if bad:
        return refuse_update("CANNOT WRITE", bad)
    rc, dirty = git(kit_root, "status", "--porcelain", "--untracked-files=no")
    if rc or dirty:
        print(f"error: {kit_root} has changed tracked files; commit or discard them first. Nothing was "
              f"written.\n{dirty}", file=sys.stderr)
        return 2
    if not args.offline:
        rc, out = git(kit_root, "fetch", "--tags", "--quiet", "origin", timeout=120)
        if rc:
            return refuse_update("CANNOT FETCH", [(kit_root, out or f"git fetch exited {rc}")])
        rc, local = git(kit_root, "rev-list", "HEAD", "--not", "--remotes", "--tags")
        if rc == 0 and local:
            print(f"error: {kit_root} has local commits that are on no remote; the updater only fast-forwards. "
                  "Nothing was written.", file=sys.stderr)
            return 2
    sha, why = update_target(kit_root, args)
    if sha is None:
        print(f"error: {why}. Nothing was written.", file=sys.stderr)
        return 2
    head = git(kit_root, "rev-parse", "HEAD")[1]
    if sha == head:
        return apply_update_here(rec, sha, args)
    if git(kit_root, "merge-base", "--is-ancestor", head, sha)[0] != 0:
        print(f"error: {sha[:12]} is not ahead of the clone's HEAD {head[:12]}; the updater only fast-forwards. "
              "Nothing was written.", file=sys.stderr)
        return 2
    if not args.yes:
        return snapshot_plan(kit_root, sha, args, None)
    if not args.to or not args.plan:
        print("error: this update moves the clone to a new commit (a git step), so --yes applies it only with "
              "--to <sha> --plan <id> from the printed plan. Nothing was written. The plan:", file=sys.stderr)
        return snapshot_plan(kit_root, sha, args, None) or 2
    rc = snapshot_plan(kit_root, sha, args, args.plan)
    if rc:
        return rc
    rc, out = git(kit_root, "merge", "--ff-only", "--quiet", sha)
    if rc:
        print(f"error: git merge --ff-only {sha[:12]} failed: {out}. Nothing else was written.", file=sys.stderr)
        return 1
    # The new commit's installer applies. subprocess, never os.exec*: on Windows exec hands the caller
    # exit 0 before the child finishes (bpo-19124), which would hide a failed apply.
    sys.stdout.flush()
    return subprocess.run([sys.executable, str(kit_root / "scripts" / "install.py"), "--update", "--offline",
                           "--yes", "--to", sha, "--plan", args.plan, *guard_flags(args)]).returncode


def apply_update_here(rec: dict | None, sha: str, args) -> int:
    """Plan against this clone at `sha`, its HEAD, and with --yes apply."""
    prev = ((rec or {}).get("kit") or {}).get("sha")
    recorded = rec is not None
    rec = adopt(rec)
    steps = plan_installs(rec, args.guard_repo)
    pid = plan_id(sha, rec, steps)
    if not args.yes:
        if not any(s.writes for s in steps) and prev == sha:
            print(f"Nothing to update: every recorded install is current at {sha[:12]} "
                  f"({kit_version() or 'unknown version'}).")
            return 0
        rc = update_targets_writable(steps)
        if rc is not None:
            return rc
        print_update_plan(rec, steps, sha, pid, args, ROOT)
        return 0
    if args.plan and args.plan != pid:
        print(f"error: the plan changed since {args.plan} was printed (now {pid}); nothing was written. Show "
              "the user the new plan:", file=sys.stderr)
        print_update_plan(rec, steps, sha, pid, args, ROOT)
        return 2
    if needs_pin(steps) and not args.plan:
        print("error: this plan holds a migration, move, delete or git step, so --yes applies it only with "
              "--plan <id> from the printed plan. Nothing was written. The plan:", file=sys.stderr)
        print_update_plan(rec, steps, sha, pid, args, ROOT)
        return 2
    unasked = [e for e in rec["installs"] if e["tool"] != "claude" and "guard" not in (e.get("options") or {})]
    if unasked and not (args.guard_repo or args.no_guard):
        print("\nerror: the plan asks about the commit guard. Make the plan again with the user's answer added, "
              "--guard-repo <repo> or --no-guard, and apply the command that plan prints. Nothing was written.",
              file=sys.stderr)
        return 2
    rc = update_targets_writable(steps)
    if rc is not None:
        return rc
    CTX["touched"] = True
    changes = any(s.writes for s in steps)  # before apply, which turns each status into what it did
    for s in steps:
        if s.writes:
            CTX["step"] = f"writing {s.piece}"
            apply(s, sys.executable)
    failed = [s for s in steps if s.status == "failed"]
    ok_all, load_lines = True, []
    shipped = {m.ID for m in load_migrations()}
    for entry in rec["installs"]:
        if entry["tool"] == "claude":
            continue
        cfg = Path(entry["config_dir"])
        mine = plan_tool(entry["tool"], entry.get("tier") or "starter", cfg,
                         Path(entry["project"]) if entry.get("project") else None, [])
        bad_mig = {s.migration for s in failed if s.migration}
        entry["migrations_applied"] = sorted(set(entry.get("migrations_applied") or []) | (shipped - bad_mig))
        entry["files"] = recorded_files(mine)
        g = guard_option(args, (entry.get("options") or {}).get("guard"))
        if g is not None:
            entry.setdefault("options", {})["guard"] = g
        tool = TOOLS[entry["tool"]]
        if tool.load_check and any(s.status in ("installed", "updated", "merged") for s in steps):
            ok, lines, verdict = tool.load_check(cfg, mine)
            ok_all = ok_all and ok
            load_lines += [f"{entry['tool']}: {verdict}", *lines]
    print()
    rows = [("piece", "destination", "status")] + [
        (s.piece, str(s.dest), s.status + (f" ({s.detail})" if s.status == "failed" else ""))
        for s in steps if s.status != "already installed"]
    if len(rows) > 1:
        table(rows)
    for ln in redact_lines(load_lines) if load_lines else []:
        print(f"  {ln}")
    if failed or not ok_all:
        print(f"\nFAILED: {len(failed)} piece(s) failed" + ("" if ok_all else "; a load check failed")
              + "; the record was not advanced.", file=sys.stderr)
        report_failure("\n".join(f"{s.piece} -> {s.dest}: {s.detail}" for s in failed) or "load check failed")
        return 1
    rec["kit"] = kit_facts(ROOT, sha)
    wrote_record = save_record(rec)
    if changes or prev != sha:
        items = [f"Updated to {kit_version() or 'an unknown version'} ({sha[:12]}). Restart your tools, or "
                 "open a new chat, so they pick the changes up."]
    else:
        items = [f"Nothing to update: every install is current at {kit_version() or 'an unknown version'} "
                 f"({sha[:12]}); no file was changed" + ("." if recorded or not wrote_record else
                                                         f", and the installs found are now recorded in "
                                                         f"{record_path()}.")]
    if prev and prev != sha:
        items.append("\n".join(["To go back to the previous version, run this in your own terminal:",
                                f"  bash:       git -C {shlex.quote(ROOT.as_posix())} checkout {prev}",
                                f"  PowerShell: git -C {_ps_quote(str(ROOT))} checkout {prev}"]))
    print_for_you([*items, *notice_item(rec)])
    return 0


def plan_tool(name: str, tier: str, cfg: Path, project: Path | None, guard_repos: list) -> list[Step]:
    """Every step that installs `name` at `tier` into `cfg`, from this kit's adapters. A fresh install
    and an update plan the same way: an install is an update from nothing."""
    tool = TOOLS[name]
    src_dir = ADAPTERS / name
    rules_src = src_dir / f"AGENTS.{tier}.md"
    if tool.rules_file:
        steps: list[Step] = [plan_rules(rules_src, cfg / tool.rules_file)]
    elif project:
        steps = [plan_rules(rules_src, project.expanduser().resolve() / "AGENTS.md")]
    else:
        steps = [Step(f"rules ({rules_src.name})", rules_src, "manual", status="manual",
                      detail=f"{name} has no global rules file; instructions are printed at the end")]
    if tool.rules_cap and steps[0].kind == "rules" and steps[0].status != "failed":
        size = len(steps[0].payload) if steps[0].writes else steps[0].dest.stat().st_size
        if size > tool.rules_cap:
            steps[0].status = "failed"
            steps[0].detail = (f"the result would be {size} bytes; {name} reads at most {tool.rules_cap} "
                               "per rules file. Shorten your own text in it, or use --tier starter")
    for d in tool.dirs:
        for f in sorted((src_dir / d).rglob("*")):
            if f.is_file():
                rel = f.relative_to(src_dir)
                if tool.shared_skills and rel.parts[0] == "skills":
                    steps.append(plan_file(piece_name(rel) + " (shared)", f,
                                           shared_skills_dir() / Path(*rel.parts[1:])))
                else:
                    steps.append(plan_file(piece_name(rel), f, cfg / rel))
    if tool.json_merge:
        steps.append(plan_json(src_dir / tool.json_merge[0], cfg / tool.json_merge[1], tool.union))
    steps += [plan_guard(r) for r in guard_repos]

    return steps


def run(argv: list[str] | None) -> int:
    ap = argparse.ArgumentParser(description="Install a claude-starter adapter into a coding tool.")
    ap.add_argument("--tool", choices=[*ALL_TOOLS, "auto"],
                    help="the tool to install into; `auto` picks the one tool --detect finds")
    ap.add_argument("--tier", choices=("starter", "full"), help="rules tier (not used by --tool claude)")
    ap.add_argument("--detect", action="store_true", help="list the supported tools found here; change nothing")
    ap.add_argument("--config-dir", type=Path, help="install here instead of the tool's global config dir")
    ap.add_argument("--project", type=Path, metavar="PATH",
                    help="cursor only: write the rules to PATH/AGENTS.md (Cursor has no global rules file)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; change nothing")
    ap.add_argument("--yes", action="store_true", help="apply without asking")
    ap.add_argument("--guard-repo", action="append", default=[], metavar="PATH",
                    help="also install the commit guard git hooks into this repo (repeatable)")
    ap.add_argument("--no-guard", action="store_true",
                    help="install without the commit guard git hooks (an apply needs this or --guard-repo)")
    ap.add_argument("--update", action="store_true",
                    help="update every recorded install: fetch, show the plan, apply only with --yes --to --plan")
    ap.add_argument("--plan-update", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--kit-root", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--to", metavar="SHA", help="with --update: the commit the printed plan was made from")
    ap.add_argument("--plan", metavar="ID", help="with --update: the id of the printed plan to apply")
    ap.add_argument("--offline", action="store_true", help="with --update: no fetch; plan against the clone's HEAD")
    args = ap.parse_args(argv)
    if args.plan_update:
        return plan_update_child(args)
    if args.update:
        return run_update(args)
    rc = kit_root_mismatch()
    if rc is not None:
        return rc

    if args.detect:
        for name, ev in detect().items():
            print(f"{name:<12} " + ("found: " + "; ".join(ev) if ev else "not found"))
        return 0
    if not args.tool:
        ap.error("--tool is required (or use --detect)")
    if args.tool == "auto":
        found = {n: ev for n, ev in detect().items() if ev}
        if len(found) > 1:
            print("Several supported tools are present; pass --tool explicitly (an agent should pass its own "
                  "tool's name):", file=sys.stderr)
            for n, ev in found.items():
                print(f"  {n:<12} {'; '.join(ev)}", file=sys.stderr)
            return 2
        if not found and not args.config_dir:
            print("auto: no supported tool was detected here, so nothing was installed. Next step: name your "
                  f"tool with --tool <name> ({', '.join(n for n in ALL_TOOLS if n != 'generic')}), or for a tool "
                  "the installer does not support, use --tool generic --config-dir <dir> and follow PORTING.md.",
                  file=sys.stderr)
            return 2
        args.tool = next(iter(found), "generic")
        print(f"auto: using {args.tool}" + (f" ({'; '.join(found[args.tool])})" if found
                                            else " (no supported tool detected)"))
    CTX["tool"], CTX["tier"] = args.tool, args.tier
    if args.tool == "claude":
        if args.tier:
            print("note: --tier is not used for claude; /starter:setup asks which tier to install.")
        return install_claude(args)
    if not args.tier:
        ap.error(f"--tier is required for --tool {args.tool}")

    tool = TOOLS[args.tool]
    if args.project and tool.rules_file:
        ap.error(f"--project is only for tools with no global rules file (cursor), not {args.tool}")
    src_dir = ADAPTERS / args.tool
    if not src_dir.is_dir():
        print(f"error: {src_dir} missing; run python scripts/build_adapters.py", file=sys.stderr)
        return 2
    if args.config_dir:
        cfg = args.config_dir.expanduser().resolve()
    elif tool.config_dir:
        cfg = tool.config_dir()
    else:
        print(f"error: --tool {args.tool} has no standard config dir; pass --config-dir", file=sys.stderr)
        return 2

    CTX["step"] = "planning the install"
    steps = plan_tool(args.tool, args.tier, cfg, args.project, args.guard_repo)
    show_plan(steps, f"claude-starter -> {args.tool} ({args.tier} tier), config dir: {cfg}")
    if tool.shared_skills:
        print(f"  (skills go to the shared {shared_skills_dir()}, read by Codex, Cursor, Copilot, Junie and "
              "OpenCode; a second tool's install finds them already installed)")
    problems = preflight(steps, tool)
    if problems:
        return preflight_failed(problems)
    rc = confirm(args)
    if rc is None:
        rc = check_writable(steps, args)
    if rc is not None:
        return rc

    CTX["step"], CTX["touched"] = "writing files", True
    for s in steps:
        if s.writes:
            CTX["step"] = f"writing {s.piece}"
            apply(s, sys.executable)

    CTX["step"] = "load check"
    ok_load, load_lines, verdict = True, [], "n/a (no loader to ask)"
    if tool.load_check:
        ok_load, load_lines, verdict = tool.load_check(cfg, steps)
    return finish_run(args.tool, args.tier, steps, ok_load, load_lines, verdict, tool.after(cfg, args), args,
                      tool.next_steps(cfg, args),
                      record=lambda: record_install(args.tool, args.tier, cfg, steps, args))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # tool output carries non-ASCII; never crash printing it
        stream.reconfigure(errors="replace")
    rep = _report()
    warning = rep.misconverted_warning([__file__, ROOT]) if rep else None
    if warning:
        print(warning, file=sys.stderr)
    try:
        return run(argv)
    except Exception:  # noqa: BLE001 - any crash gets the same redacted report as a failed piece
        import traceback
        tb = traceback.format_exc()
        for ln in redact_lines([*tb.rstrip("\n").split("\n"), "", f"FAILED while {CTX['step']}"]):
            print(ln, file=sys.stderr)
        report_failure(tb)
        return 1


if __name__ == "__main__":
    sys.exit(main())
