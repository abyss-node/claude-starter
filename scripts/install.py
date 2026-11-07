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
  - any failure saves a redacted report (scripts/report.py) and prints an issue link; nothing is sent.
Without --yes it asks on a terminal; with no terminal and no --yes it only prints the plan.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
ADAPTERS = ROOT / "adapters"
GUARD = ROOT / "plugins" / "starter" / "hooks" / "commit-guard" / "guard.py"
KIT_AGENTS = ("verifier", "code-reviewer", "consultant")

BEGIN = "<!-- BEGIN claude-starter rules (managed by scripts/install.py; a re-run replaces this block) -->"
END = "<!-- END claude-starter rules -->"
BEGIN_RX = re.compile(r"^<!-- BEGIN claude-starter rules\b.*-->$", re.M)
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
    kind: str                       # file | rules | json | guard
    status: str = ""                # create | update | merge | already installed | skipped | failed | ...
    detail: str = ""
    payload: bytes = b""            # final bytes to write (file/rules/json)
    src: Path | None = None
    notes: list[str] = field(default_factory=list)
    original: object = None         # json: the user's parsed config, checked to survive the merge

    @property
    def writes(self) -> bool:
        return self.status in ("create", "update", "merge", "run")


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
        s.status = "skipped"
        s.detail = (f"you use {jsonc.name}; merge {src.relative_to(ROOT).as_posix()} into it by hand "
                    "(comments are not parsed safely here)")
        return s
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


def plan_guard(repo: str) -> Step:
    p = Path(repo).expanduser().resolve()
    s = Step("commit guard (git hooks)", p, "guard")
    if not (p / ".git").exists():
        s.status, s.detail = "failed", "not a git repository (no .git)"
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


def check_file(tool: str, s: Step) -> str | None:
    """Return a problem with the installed file, or None."""
    p = s.dest
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

@dataclass
class Tool:
    config_dir: Callable[[], Path] | None       # None: --config-dir is required
    dirs: tuple[str, ...]                        # adapter subfolders copied as-is
    rules_file: str | None = "AGENTS.md"         # None: the tool has no global rules file
    json_merge: tuple[str, str] | None = None    # (adapter file, config file)
    load_check: Callable[[Path, list[Step]], tuple[bool, list[str], str]] | None = None
    shared_skills: bool = False                  # adapter skills/ go to ~/.agents/skills
    union: tuple[str, ...] = ()                  # JSON allowlists merged item by item
    rules_cap: int | None = None                 # bytes the tool reads from one rules file
    bins: tuple[str, ...] = ()                   # evidence for --detect
    marks: Callable[[], list[Path]] = lambda: []  # config dirs that are evidence for --detect
    after: Callable[[Path, argparse.Namespace], list[str]] | None = None
    needs_bin: str | None = None                 # the load check fails without it: checked before writing


def notes_codex(cfg: Path, args) -> list[str]:
    return ["Agents are READ-ONLY BY INSTRUCTION ONLY: Codex cannot enforce it (agent files ignore "
            "sandbox_mode). Consultant: shell tools disabled by feature flags (shell_tool and "
            "unified_exec = false); not verified that Codex honours [features] in agent files.",
            "checkpoint and lanes are skills (Codex prompts are deprecated). Codex documents no "
            "`disable-model-invocation`, so it may also start them on its own.",
            "Codex's commit attribution is undocumented since 2026-05-13; the commit guard is the check.",
            f"Allowlist: {cfg / 'rules' / 'claude-starter.rules'} allows only commands checked to stay "
            "read-only when arguments are appended (Codex matches prefixes); git diff/log/branch and "
            "ruff still ask."]


def notes_cursor(cfg: Path, args) -> list[str]:
    out = []
    if not args.project:
        src = ADAPTERS / "cursor" / f"AGENTS.{args.tier}.md"
        out += ["RULES ARE NOT INSTALLED YET. Cursor has no global rules file. Do one of:",
                f"  - Cursor Settings > Rules > User Rules: paste the whole of {src}",
                f"  - per repo: python {ROOT / 'scripts' / 'install.py'} --tool cursor --tier {args.tier} --yes "
                "--project <repo>   (writes <repo>/AGENTS.md inside a managed block)"]
    out.append("No git allow rule was added: Cursor's Shell(git) would allow every git command, push included.")
    try:
        att = json.loads((cfg / "cli-config.json").read_text(encoding="utf-8-sig")).get("attribution", {})
        if att.get("attributeCommitsToAgent") is not False or att.get("attributePRsToAgent") is not False:
            out.append(f"WARNING: your cli-config.json keeps attribution {json.dumps(att)}; the commit guard "
                       "will flag Cursor's 'Made with Cursor' trailer. Set both to false to stop it.")
    except (OSError, ValueError, AttributeError):
        pass
    return out


def notes_copilot(cfg: Path, args) -> list[str]:
    snippet = (ADAPTERS / "copilot" / "vscode-terminal-autoapprove.json").read_text(encoding="utf-8")
    return ["Read-only terminal commands for VS Code (not edited by this installer): open "
            "'Preferences: Open User Settings (JSON)' and merge in:", *snippet.rstrip().splitlines(),
            "The keys are anchored regexes, so each matches only that exact command. The Copilot CLI has no "
            "allowlist file; approve per session.",
            "Agents use `tools` (read, search; execute for verifier/code-reviewer) plus strict-tools-list, "
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


TOOLS: dict[str, Tool] = {
    "opencode": Tool(opencode_config_dir, ("skills", "agents", "commands"),
                     json_merge=("opencode.permission.json", "opencode.json"), load_check=opencode_check,
                     bins=("opencode",), marks=lambda: [opencode_config_dir()], needs_bin="opencode"),
    "codex": Tool(codex_home, ("skills", "agents", "rules"), load_check=codex_check, shared_skills=True,
                  bins=("codex",), marks=lambda: [codex_home()], after=notes_codex),
    "cursor": Tool(cursor_dir, ("skills", "agents"), rules_file=None,
                   json_merge=("cli-config.json", "cli-config.json"), load_check=structural_only("cursor"),
                   shared_skills=True, union=("permissions.allow", "permissions.deny"),
                   # The Cursor CLI binary is called `agent`, too generic a name to count as evidence.
                   bins=("cursor", "cursor-agent"), marks=lambda: [cursor_dir()], after=notes_cursor),
    "copilot": Tool(copilot_home, ("skills", "agents"), rules_file="copilot-instructions.md",
                    load_check=structural_only("copilot"), shared_skills=True,
                    bins=("copilot",), marks=lambda: [copilot_home()], after=notes_copilot),
    "antigravity": Tool(lambda: home() / ".gemini", ("config",),
                        json_merge=("antigravity-cli.settings.json", "antigravity-cli/settings.json"),
                        load_check=structural_only("antigravity"), union=("permissions.allow",),
                        rules_cap=ANTIGRAVITY_CAP, bins=("agy", "antigravity"),
                        marks=lambda: [home() / ".gemini" / "antigravity-cli", home() / ".gemini" / "config"],
                        after=notes_antigravity),
    "junie": Tool(lambda: home() / ".junie", ("skills", "agents", "commands"),
                  json_merge=("junie.allowlist.json", "allowlist.json"), load_check=structural_only("junie"),
                  shared_skills=True, union=("rules.executables.rules",),
                  bins=("junie",), marks=lambda: [home() / ".junie"], after=notes_junie),
    "generic": Tool(None, ("skills", "agents", "commands"), after=notes_generic),
}
CLAUDE = Tool(claude_config_dir, (), bins=("claude",), marks=lambda: [claude_config_dir()])
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
                "skipped": "SKIP", "failed": "CANNOT"}.get(s.status, s.status.upper())
        print(f"  {verb:<26} {s.piece:<34} -> {s.dest}" + (f"\n  {'':<26} {s.detail}" if s.detail else ""))
        for n in redact_lines(s.notes) if s.notes else []:
            print(f"  {'':<26}   note: {n}")


def table(rows: list[tuple[str, str, str]]) -> None:
    w = [max(len(r[i]) for r in rows) for i in range(3)]
    for i, r in enumerate(rows):
        print("  ".join(c.ljust(w[j]) for j, c in enumerate(r)).rstrip())
        if i == 0:
            print("  ".join("-" * x for x in w))


def confirm(args) -> int | None:
    """None to go ahead, else the exit code."""
    if args.dry_run:
        print("\ndry run: nothing written.")
        return 0
    if args.yes:
        return None
    no_tty = "\nno terminal and no --yes: dry run only, nothing written. Re-run with --yes to apply."
    if not sys.stdin.isatty():
        print(no_tty)
        return 0
    try:
        answer = input("\nApply this plan? [y/N] ")
    except EOFError:  # Windows reports NUL as a tty, so a redirected stdin can still land here
        print(no_tty)
        return 0
    if answer.strip().lower() not in ("y", "yes"):
        print("aborted; nothing written.")
        return 1
    return None


def piece_name(rel: Path) -> str:
    if rel.name == "SKILL.md":
        return f"skill {rel.parent.name}"
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


def update_commands(args) -> tuple[list[str], list[str]]:
    """The commands that repeat this install later, as (bash lines, PowerShell lines): every flag the
    install used, two separate commands per shell (Windows PowerShell 5.1 has no `&&`)."""
    words = [("--tool", args.tool)] + ([("--tier", args.tier)] if getattr(args, "tier", None) else [])
    paths = []
    if getattr(args, "config_dir", None):
        paths.append(("--config-dir", args.config_dir))
    if getattr(args, "project", None):
        paths.append(("--project", args.project))
    paths += [("--guard-repo", r) for r in getattr(args, "guard_repo", None) or []]
    paths = [(f, Path(v).expanduser().resolve()) for f, v in paths]
    script = ROOT / "scripts" / "install.py"
    bash_flags = [f"{f} {shlex.quote(v)}" for f, v in words] + [f"{f} {shlex.quote(v.as_posix())}" for f, v in paths]
    ps_flags = [f"{f} {_ps_quote(v)}" for f, v in words] + [f"{f} {_ps_quote(str(v))}" for f, v in paths]
    bash = [f"git -C {shlex.quote(ROOT.as_posix())} pull",
            " ".join(["python", shlex.quote(script.as_posix()), *bash_flags, "--yes"])]
    ps = [f"git -C {_ps_quote(str(ROOT))} pull", " ".join(["python", _ps_quote(str(script)), *ps_flags, "--yes"])]
    return bash, ps


def footer(args) -> None:
    print(f"\nkit location: {ROOT}")
    bash, ps = update_commands(args)
    print("update later (bash: macOS, Linux, Git Bash):")
    for ln in bash:
        print(f"  {ln}")
    print("update later (PowerShell):")
    for ln in ps:
        print(f"  {ln}")


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
                      ["Next: open Claude Code and run /starter:setup. It installs CLAUDE.md and merges settings, "
                       "asking before each change. This installer leaves those to it so they have one writer."], args)


def finish_run(tool: str, tier: str | None, steps: list[Step], ok_load: bool, load_lines: list[str],
               verdict: str, after: list[str], args) -> int:
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
    if after:
        print()
        for ln in after:
            print(ln)
    footer(args)
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
    args = ap.parse_args(argv)

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
    rules_src = src_dir / f"AGENTS.{args.tier}.md"
    if tool.rules_file:
        steps: list[Step] = [plan_rules(rules_src, cfg / tool.rules_file)]
    elif args.project:
        steps = [plan_rules(rules_src, args.project.expanduser().resolve() / "AGENTS.md")]
    else:
        steps = [Step(f"rules ({rules_src.name})", rules_src, "manual", status="manual",
                      detail=f"{args.tool} has no global rules file; instructions are printed at the end")]
    if tool.rules_cap and steps[0].kind == "rules" and steps[0].status != "failed":
        size = len(steps[0].payload) if steps[0].writes else steps[0].dest.stat().st_size
        if size > tool.rules_cap:
            steps[0].status = "failed"
            steps[0].detail = (f"the result would be {size} bytes; {args.tool} reads at most {tool.rules_cap} "
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
    steps += [plan_guard(r) for r in args.guard_repo]

    show_plan(steps, f"claude-starter -> {args.tool} ({args.tier} tier), config dir: {cfg}")
    if tool.shared_skills:
        print(f"  (skills go to the shared {shared_skills_dir()}, read by Codex, Cursor, Copilot, Junie and "
              "OpenCode; a second tool's install finds them already installed)")
    problems = preflight(steps, tool)
    if problems:
        return preflight_failed(problems)
    rc = confirm(args)
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
    after = tool.after(cfg, args) if tool.after else []
    if args.tool == "opencode":
        after.append("Restart opencode to pick the changes up (it reads config once at start).")
    return finish_run(args.tool, args.tier, steps, ok_load, load_lines, verdict, after, args)


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
