#!/usr/bin/env python3
"""Generate every tool's copy of the kit: adapters/<tool>/, and Claude Code's generated files.

Every tool gets a ready-to-install copy of the kit, produced by code rather than by a model
translating files by hand. A hand translation once copied Claude agent frontmatter
(`tools: Read, Grep, Glob, Bash`) into OpenCode, which made OpenCode's whole configuration
invalid, and still reported success.

    python scripts/build_adapters.py            # regenerate every generated file
    python scripts/build_adapters.py --check    # exit 1 if any differs from a fresh build
    python scripts/build_adapters.py --tool opencode

Two sources feed it. `core/` holds what is written once for every tool: commands in
core/commands/, the onboarding walkthrough in core/onboarding/, the plans in core/plans.json,
rendered per tool with the words in scripts/vocab.py. `plugins/starter/` holds the Claude Code
sources the other tools get through literal rewrites (Rewriter). Claude Code's own build is only
the files rendered from core/ (emit_claude); the rest of plugins/starter/ is hand-written.

Each tool's build is a manifest: a dict of paths to text. A write or --check touches only manifest
paths, and deletes only inside adapters/<tool>/, which is generated whole, so a hand-written plugin
file beside a generated one is never removed.

Each emitter's rewrites must all fire: a rewrite that matches nothing means the source changed
under it, and the build stops instead of shipping a stale translation. Then two checks run over
every manifest. CONTENT_LINTS catch Claude-only frontmatter and claims in other tools' output. The
two-way term check (core/terms.json) fails when one tool's output holds another tool's vocabulary,
in either direction. Output is deterministic: sorted, UTF-8, LF only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "starter"
CORE = ROOT / "core"
OUT = ROOT / "adapters"
sys.path.insert(0, str(ROOT / "scripts"))
from vocab import STEP_HEADING, VOCAB, next_line, walkthrough_path  # noqa: E402

# Commands that carry over. `setup` writes Claude Code settings; scripts/install.py replaces it. A
# command whose source is in core/commands/ is rendered for Claude Code too (emit_claude); the others
# are read from plugins/starter/commands/.
PORTED_COMMANDS = ("checkpoint", "lanes", "onboard", "starter-update")
TIERS = ("starter", "full")

# Built-in commands per tool, which a ported command must never be named. A custom command can replace
# a built-in (https://opencode.ai/docs/commands/), and OpenCode's built-in /update updates OpenCode
# itself, so a kit command named `update` would hide it or be hidden by it. OpenCode's list is from
# https://opencode.ai/docs/tui (read 2026-11-15), aliases included. A tool missing here has no list
# taken from its docs yet, so nothing is checked for it.
BUILTIN_COMMANDS: dict[str, tuple[str, ...]] = {
    "opencode": ("connect", "compact", "summarize", "editor", "exit", "quit", "q", "export", "help",
                 "init", "models", "new", "clear", "redo", "sessions", "resume", "continue", "themes",
                 "thinking", "undo", "update"),
}


# Tokens a command in core/commands/ may hold, per tool. A tool whose command copy is its own (vocab
# shared_commands False) names itself to the launcher, so the walkthrough it prints is always its own even
# when the install record lists another tool: a Claude Code plugin installed by hand writes no record, and
# a copy that asked the record once printed OpenCode's walkthrough inside Claude Code. The copy shared in
# ~/.agents/skills cannot name a tool; it renders the same text for every tool sharing it, so it stays
# byte-identical, and the user adds `--tool` only where the record does not name exactly one tool.
def command_tokens(tool: str) -> dict[str, str]:
    if VOCAB[tool].shared_commands:
        return {"tool_arg": "", "tool_choice": ", and add `--tool <id>` only if they typed it"}
    return {"tool_arg": f" --tool {tool}", "tool_choice": ""}


def render_command(text: str, tool: str, where: str) -> str:
    """`text` with each {{token}} of command_tokens(tool) replaced. Anything else in braces stops the build."""
    known = command_tokens(tool)

    def sub(m: re.Match) -> str:
        if m.group(1) in known:
            return known[m.group(1)]
        raise SystemExit(f"{where}: unknown token {m.group(0)} (a command knows "
                         f"{', '.join('{{' + k + '}}' for k in sorted(known))})")

    out = TOKEN.sub(sub, text)
    if "{{" in out or "}}" in out:
        raise SystemExit(f"{where}: a malformed token is left in the {tool} output")
    return out


def check_builtin_collisions(names, builtins: dict[str, tuple[str, ...]] = BUILTIN_COMMANDS) -> None:
    clashes = [f"  {n!r} is a built-in {tool} command" for tool, b in sorted(builtins.items())
               for n in names if n in b]
    if clashes:
        raise SystemExit("ported command names collide with built-ins:\n" + "\n".join(clashes))


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

def read(p: Path) -> str:
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n")


def split_frontmatter(text: str, where: str) -> tuple[dict[str, str], str]:
    """Parse the flat `key: value` frontmatter used by agents and commands."""
    lines = text.split("\n")
    if lines[0] != "---":
        raise SystemExit(f"{where}: no frontmatter")
    end = lines.index("---", 1)
    fm: dict[str, str] = {}
    for ln in lines[1:end]:
        m = re.fullmatch(r"([A-Za-z_-]+):\s*(.*)", ln)
        if not m:
            raise SystemExit(f"{where}: frontmatter line not understood: {ln!r}")
        fm[m.group(1)] = m.group(2).strip()
    return fm, "\n".join(lines[end + 1:]).lstrip("\n")


@dataclass
class Doc:
    meta: dict[str, str]
    body: str


@dataclass
class Sources:
    rules: dict[str, str]          # tier -> text
    skills: dict[str, str]         # name -> full SKILL.md (frontmatter is the shared SKILL.md format)
    agents: dict[str, Doc]
    commands: dict[str, Doc]       # as written; commands_for() renders the core ones for a tool
    bash_allow: list[str]          # read-only shell commands from settings.starter.json
    core_commands: dict[str, str]  # name -> core/commands/<name>.md as written, for Claude Code's copy
    onboarding: dict[str, dict[str, str]]  # core/onboarding/<folder> -> step name -> text
    plans: dict[str, list[dict]]   # tool -> its plans, from core/plans.json


def load_sources() -> Sources:
    rules = {t: read(PLUGIN / "templates" / f"CLAUDE.{t}.md") for t in TIERS}
    skills = {p.parent.name: read(p) for p in sorted((PLUGIN / "skills").glob("*/SKILL.md"))}
    agents = {}
    for p in sorted((PLUGIN / "agents").glob("*.md")):
        meta, body = split_frontmatter(read(p), str(p))
        agents[p.stem] = Doc(meta, body)
    check_builtin_collisions(PORTED_COMMANDS)
    in_core = {p.stem: read(p) for p in sorted((CORE / "commands").glob("*.md"))}
    stray = sorted(set(in_core) - set(PORTED_COMMANDS))
    if stray:
        raise SystemExit(f"core/commands/: {', '.join(stray)} not in PORTED_COMMANDS, so no tool would get it")
    commands = {}
    for name in PORTED_COMMANDS:
        p = CORE / "commands" / f"{name}.md" if name in in_core else PLUGIN / "commands" / f"{name}.md"
        meta, body = split_frontmatter(read(p), str(p))
        commands[name] = Doc(meta, body)
    settings = json.loads(read(PLUGIN / "templates" / "settings.starter.json"))
    bash_allow = []
    for entry in settings["permissions"]["allow"]:
        m = re.fullmatch(r"Bash\((.+)\)", entry)
        if not m:
            raise SystemExit(f"settings.starter.json: no adapter mapping for permission {entry!r}")
        bash_allow.append(m.group(1).replace(":*", " *"))
    return Sources(rules, skills, agents, commands, bash_allow, in_core, load_onboarding(), load_plans())


def commands_for(src: Sources, tool: str) -> dict[str, Doc]:
    """The ported commands for `tool`: those from core/commands/ with their tokens rendered."""
    return {n: Doc(d.meta, render_command(d.body, tool, f"core/commands/{n}.md") if n in src.core_commands
                   else d.body) for n, d in src.commands.items()}


# --------------------------------------------------------------------------
# Shared machinery
# --------------------------------------------------------------------------

class Rewriter:
    """Ordered literal rewrites; every one must fire at least once across the build."""

    def __init__(self, pairs: list[tuple[str, str]]):
        self.pairs = pairs
        self.hits = [0] * len(pairs)

    def __call__(self, text: str) -> str:
        for i, (old, new) in enumerate(self.pairs):
            n = text.count(old)
            if n:
                self.hits[i] += n
                text = text.replace(old, new)
        return text

    def assert_all_fired(self, tool: str) -> None:
        dead = [old for (old, _), h in zip(self.pairs, self.hits) if h == 0]
        if dead:
            raise SystemExit(f"{tool}: rewrites matched nothing (the source changed under them):\n"
                             + "\n".join(f"  {d!r}" for d in dead))


# A sentence saying the commit guard checks commits, with no condition. Inside Claude Code the plugin's
# hook does check; any other tool has the guard only in repos passed to the installer's --guard-repo.
# A Codex checkpoint skill once said "The commit guard checks for this" after an install whose own
# output said the guard was not installed in any repo.
GUARD_CLAIM = re.compile(r"(?<![\w`])(?:[Tt]he|plugin's)\s+(?:`starter`\s+)?commit\s+guard\s+"
                         r"(?:checks|is\s+the\s+check)\b")

# Claude-only frontmatter and claims that must not survive into any other tool's output. These are about
# what a file says, not whose words it uses, so they are lints here rather than rows in core/terms.json.
FIELD = "Claude frontmatter field"
CONTENT_LINTS = [
    (re.compile(r"^(tools|model|effort|allowed-tools):", re.M), FIELD),
    # Never allowed, even where a tool has its own `tools:`/`model:` field: the Claude spellings.
    (re.compile(r"^tools:\s*[A-Z]\w*(\s*,\s*[A-Z]\w*)+\s*$", re.M), "Claude `tools:` string"),
    (re.compile(r"^model:\s*(opus|sonnet|haiku|fable)\b", re.M), "Claude model alias"),
    (GUARD_CLAIM, "unconditional commit guard claim (true only inside Claude Code)"),
]


def lint(tool: str, files: dict[str, str], fields: tuple[str, ...] = ()) -> None:
    """`fields`: frontmatter fields this tool really has (e.g. its own `tools:` list)."""
    problems = []
    for rel, text in files.items():
        for rx, what in CONTENT_LINTS:
            for m in rx.finditer(text):
                if what == FIELD and m.group(1) in fields:
                    continue
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"  {tool}/{rel}:{line}: {what}: {m.group(0)!r}")
    if problems:
        raise SystemExit(f"{tool}: Claude-only content left after rewriting:\n" + "\n".join(problems))


# --------------------------------------------------------------------------
# Two-way term check: core/terms.json says which tools own which words
# --------------------------------------------------------------------------
# A one-way deny list ran only on non-Claude output, so nothing stopped another tool's words reaching
# Claude Code, and a Codex user's onboarding asked which Claude plan they had. Each row now names the
# tools a word belongs to, and a match in any other tool's build fails.

@dataclass(frozen=True)
class Term:
    pattern: str
    rx: re.Pattern
    owners: tuple[str, ...]
    why: str
    allow: tuple[str, ...]


# `{{commands}}` in a terms.json pattern stands for any ported command's name, so a command added to
# PORTED_COMMANDS is covered by the command-syntax rows without anyone remembering to add it there.
COMMANDS_TOKEN = "{{commands}}"


def load_terms(path: Path | None = None) -> list[Term]:
    path = path or CORE / "terms.json"
    rows = json.loads(read(path))["rows"]
    names = "(?:" + "|".join(re.escape(n) for n in PORTED_COMMANDS) + ")"
    terms, seen = [], set()
    for i, row in enumerate(rows):
        where = f"{path.name} row {i + 1}"
        if set(row) != {"pattern", "owners", "why", "allow"}:
            raise SystemExit(f"{where}: keys must be pattern, owners, why and allow, not {sorted(row)}")
        unknown = [o for o in row["owners"] if o not in VOCAB]
        if not row["owners"] or unknown or len(set(row["owners"])) != len(row["owners"]):
            raise SystemExit(f"{where}: owners must be distinct tools from scripts/vocab.py; unknown: {unknown}")
        bad_allow = [a for a in row["allow"] if not re.fullmatch(r"\S+:\d+", a)]
        if bad_allow:
            raise SystemExit(f"{where}: allow entries are <path>:<line>, not {bad_allow}")
        if row["pattern"] in seen:
            raise SystemExit(f"{where}: pattern {row['pattern']!r} is listed twice")
        seen.add(row["pattern"])
        try:
            rx = re.compile(row["pattern"].replace(COMMANDS_TOKEN, names))
        except re.error as e:
            raise SystemExit(f"{where}: pattern {row['pattern']!r} does not compile: {e}") from None
        terms.append(Term(row["pattern"], rx, tuple(row["owners"]), row["why"], tuple(row["allow"])))
    return terms


def load_baseline(path: Path | None = None) -> dict[tuple[str, str, str], int]:
    path = path or CORE / "terms.baseline"
    return parse_baseline(read(path), path.name)


def parse_baseline(text: str, name: str = "terms.baseline") -> dict[tuple[str, str, str], int]:
    """`count<TAB>tool/file<TAB>pattern<TAB>match` per line; # starts a comment."""
    out: dict[tuple[str, str, str], int] = {}
    for n, ln in enumerate(text.split("\n"), 1):
        if not ln.strip() or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) != 4 or not parts[0].isdigit() or int(parts[0]) < 1 or parts[1].split("/", 1)[0] not in VOCAB:
            raise SystemExit(f"{name}:{n}: expected count<TAB>tool/file<TAB>pattern<TAB>match, got {ln!r}")
        key = (parts[1], parts[2], parts[3])
        if key in out:
            raise SystemExit(f"{name}:{n}: {key} is listed twice")
        out[key] = int(parts[0])
    return out


def term_hits(built: dict[str, dict[str, str]], terms: list[Term]):
    """(tool, file, line, term, matched text) for every word in a build its tool does not own."""
    for t in sorted(built):
        for rel, text in sorted(built[t].items()):
            for term in terms:
                if t in term.owners:
                    continue
                for m in term.rx.finditer(text):
                    yield t, rel, text.count("\n", 0, m.start()) + 1, term, m.group(0)


def check_terms(built: dict[str, dict[str, str]], terms: list[Term],
                baseline: dict[tuple[str, str, str], int], full: bool) -> None:
    """Fail on any word a build's tool does not own, unless an `allow` names its place or the baseline
    still lists it. A baseline line the build no longer needs fails too, so the baseline only shrinks;
    on a full build (`full`) so does an allow that matches nothing."""
    seen: Counter = Counter()
    lines: dict[tuple[str, str, str], list[str]] = {}
    used = set()
    for t, rel, ln, term, match in term_hits(built, terms):
        spot = f"{t}/{rel}:{ln}"  # an allow is a suffix of it: `<file>:<line>` in every build, or `<tool>/...`
        allowed = next((a for a in term.allow if ("/" + spot).endswith("/" + a)), None)
        if allowed:
            used.add((term.pattern, allowed))
            continue
        key = (f"{t}/{rel}", term.pattern, match)
        seen[key] += 1
        lines.setdefault(key, []).append(
            f"  {t}/{rel}:{ln}: {term.why}: {match!r} (a word of {', '.join(term.owners)} only)")
    problems = []
    for key, n in sorted(seen.items()):
        if n > baseline.get(key, 0):
            problems += lines[key] + ([f"    (core/terms.baseline allows {baseline[key]} of these)"]
                                      if key in baseline else [])
    for key, n in sorted(baseline.items()):
        if key[0].split("/", 1)[0] in built and seen.get(key, 0) < n:
            problems.append(f"  core/terms.baseline lists {n} of {key[2]!r} ({key[1]}) in {key[0]}, the build has "
                            f"{seen.get(key, 0)}: lower or delete that line (the baseline may only shrink)")
    if full:
        for term in terms:
            problems += [f"  core/terms.json: allow {a!r} for {term.pattern!r} matches nothing; remove it"
                         for a in term.allow if (term.pattern, a) not in used]
    if problems:
        raise SystemExit("two-way term check (core/terms.json) failed:\n" + "\n".join(problems))


# --------------------------------------------------------------------------
# Onboarding: core/onboarding/ rendered per tool, one step per section
# --------------------------------------------------------------------------
# common/ holds the steps every tool shares. Every other step is tool-specific: default/ has a version
# that names no tool, and core/onboarding/<tool>/ may replace it. Claude Code and OpenCode replace every
# one: their walkthroughs were Claude-specific and OpenCode-specific from the start, and a fallback that
# names no tool would hide a missing page behind text that looks complete.
ONBOARDING = CORE / "onboarding"
FULL_OVERLAY = ("claude", "opencode")
STEP_FILE = re.compile(r"(\d\d)-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
TOKEN = re.compile(r"\{\{([^{}]*)\}\}")
PLAN_KEYS = {"id", "label", "meter", "meter_cmd", "meter_cmd_confirmed", "pay_past_limit", "provider"}
METER = {"share": "a usage limit that resets", "usd": "billed per token",
         "free": "runs on your own machine, free per token"}
PAY = {"possible": " Past the limit: paid credits, if you turn them on, or wait for the reset.",
       "unknown": " Whether you can pay past the limit is unconfirmed; plan on waiting for the reset.",
       "n/a": ""}
GENERATED = ("<!-- Generated by scripts/build_adapters.py from core/onboarding/. Edit those files and rebuild; "
             "CI fails when this copy differs from a fresh build. -->")


def load_onboarding(root: Path | None = None) -> dict[str, dict[str, str]]:
    root = root or ONBOARDING
    if not root.is_dir():
        raise SystemExit(f"{root}: missing; every tool's onboarding walkthrough is rendered from it")
    folders: dict[str, dict[str, str]] = {}
    for d in sorted(root.iterdir()):
        if not d.is_dir() or (d.name not in ("common", "default") and d.name not in VOCAB):
            raise SystemExit(f"core/onboarding/{d.name}: only common/, default/ and one folder per tool "
                             f"({', '.join(sorted(VOCAB))}) belong here")
        steps = {}
        for p in sorted(d.iterdir()):
            if not p.is_file() or not STEP_FILE.fullmatch(p.name):
                raise SystemExit(f"core/onboarding/{d.name}/{p.name}: not a step file (NN-name.md)")
            steps[p.name[:-3]] = read(p)
        folders[d.name] = steps
    return folders


def onboarding_steps(tool: str, folders: dict[str, dict[str, str]]) -> list[tuple[str, str, str]]:
    """(step name, folder it comes from, text) for each step of `tool`'s walkthrough, in order."""
    common, default = folders.get("common", {}), folders.get("default", {})
    both = sorted(set(common) & set(default))
    if both:
        raise SystemExit(f"core/onboarding/: {', '.join(both)} in both common/ and default/; a step has one home")
    for t, own in folders.items():
        stray = sorted(set(own) - set(default)) if t not in ("common", "default") else []
        if stray:
            raise SystemExit(f"core/onboarding/{t}/: {', '.join(stray)} has no default/ version, so it is not a "
                             "tool-specific step; add one to default/, or move it to common/")
    own = folders.get(tool, {})
    if tool in FULL_OVERLAY:
        missing = sorted(set(default) - set(own))
        if missing:
            raise SystemExit(f"core/onboarding/{tool}/ lacks {', '.join(m + '.md' for m in missing)}: {tool} has "
                             "its own version of every tool-specific step, with no fallback to default/")
    names = sorted(set(common) | set(default))
    numbers = [n[:2] for n in names]
    if len(set(numbers)) != len(numbers):
        raise SystemExit(f"core/onboarding/: two steps share a number: {', '.join(names)}")
    if not names:
        raise SystemExit("core/onboarding/: no steps")
    return [(n, "common", common[n]) if n in common else (n, tool, own[n]) if n in own else (n, "default", default[n])
            for n in names]


def load_plans(path: Path | None = None) -> dict[str, list[dict]]:
    path = path or CORE / "plans.json"
    data = json.loads(read(path))
    out = {}
    for tool, rows in data.items():
        if tool.startswith("_"):
            continue
        if tool not in VOCAB:
            raise SystemExit(f"{path.name}: {tool!r} is not a tool in scripts/vocab.py")
        ids = [r.get("id") for r in rows]
        if not rows or len(set(ids)) != len(ids):
            raise SystemExit(f"{path.name}: {tool} needs at least one plan, each with its own id")
        for r in rows:
            where = f"{path.name}: {tool} plan {r.get('id')!r}"
            if set(r) != PLAN_KEYS:
                raise SystemExit(f"{where}: keys must be {', '.join(sorted(PLAN_KEYS))}")
            if r["meter"] not in METER or r["pay_past_limit"] not in PAY:
                raise SystemExit(f"{where}: meter is one of {sorted(METER)} and pay_past_limit one of {sorted(PAY)}")
            if not (r["meter_cmd"] is None or isinstance(r["meter_cmd"], str) and r["meter_cmd"]):
                raise SystemExit(f"{where}: meter_cmd is a command or null")
            if not (isinstance(r["meter_cmd_confirmed"], bool) if r["meter_cmd"] else r["meter_cmd_confirmed"] is None):
                raise SystemExit(f"{where}: meter_cmd_confirmed is true or false when meter_cmd is a command, "
                                 "and null when it is null")
            if not all(isinstance(r[k], str) and r[k] for k in ("id", "label", "provider")):
                raise SystemExit(f"{where}: id, label and provider are non-empty strings")
        out[tool] = rows
    return out


def plan_list(tool: str, plans: dict[str, list[dict]], where: str) -> str:
    if tool not in plans:
        raise SystemExit(f"{where}: {{{{plans}}}} is used, but core/plans.json has no plans for {tool}")
    several = len({r["provider"] for r in plans[tool]}) > 1
    out = []
    for r in plans[tool]:
        s = f"- **{r['label']}**" + (f" (provider `{r['provider']}`)" if several else "") + f": {METER[r['meter']]}"
        if r["meter_cmd"]:
            what = "how much is left" if r["meter"] == "share" else "what you spent"
            s += (f"; `{r['meter_cmd']}` shows {what}." if r["meter_cmd_confirmed"]
                  else f"; `{r['meter_cmd']}` may show {what}, which is unconfirmed.")
        elif r["meter"] == "share":
            s += "; no command in the tool shows how much is left."
        elif r["meter"] == "usd":
            s += "; your provider's usage page shows what you spent."
        else:
            s += "."
        out.append(s + PAY[r["pay_past_limit"]])
    return "\n".join(out)


def render_tokens(text: str, tool: str, plans: dict[str, list[dict]], where: str) -> str:
    """Replace {{rules_file}}, {{tool}}, {{cmd:<ported command>}} and {{plans}} with `tool`'s words.
    Anything else in braces stops the build, so a misspelt token never ships as literal text."""
    v = VOCAB[tool]

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key == "rules_file":
            return v.rules_file
        if key == "tool":
            return tool
        if key == "plans":
            return plan_list(tool, plans, where)
        if key.startswith("cmd:") and key[4:] in PORTED_COMMANDS:
            return v.cmd(key[4:])
        raise SystemExit(f"{where}: unknown token {m.group(0)} (known: {{{{rules_file}}}}, {{{{tool}}}}, "
                         f"{{{{plans}}}}, {{{{cmd:<one of {', '.join(PORTED_COMMANDS)}>}}}})")

    out = TOKEN.sub(sub, text)
    if "{{" in out or "}}" in out:
        raise SystemExit(f"{where}: a malformed token is left in the {tool} output")
    return out


def render_step(text: str, tool: str, plans: dict[str, list[dict]], where: str) -> tuple[str, str]:
    """(title, body) of one step file: a `# Title` line, then the body. Outside a code fence the body may
    not hold a level 1 or 2 heading or a line starting `Next:`, which belong to the walkthrough around it.
    A line that opens a step (vocab.STEP_HEADING) is refused even inside a fence, in the source and in the
    rendered text: the launcher splits on it without regard to fences. {{rules_file}} must end a clause,
    because a tool's rules file may be a long phrase (Cursor's is) that swallows the words after it."""
    first, _, rest = text.partition("\n")
    if not first.startswith("# ") or not first[2:].strip():
        raise SystemExit(f"{where}: the first line must be `# <title>`")
    body = rest.strip("\n")
    fence = False
    for n, ln in enumerate(body.split("\n"), 2):
        if STEP_HEADING.match(ln):
            raise SystemExit(f"{where}:{n}: a step may not hold a line that opens a step (`## Step N of M:`), even "
                             "in a code block: the launcher splits the walkthrough on it")
        if ln.startswith("```"):
            fence = not fence
        elif not fence and (ln.startswith(("# ", "## ")) or ln.startswith("Next:")):
            raise SystemExit(f"{where}:{n}: a step may not hold a `#`/`##` heading or a `Next:` line")
    for m in TOKEN.finditer(text):
        if m.group(1) == "rules_file" and text[m.end():m.end() + 1] not in (".", ";", ":", ")"):
            raise SystemExit(f"{where}:{text.count(chr(10), 0, m.start()) + 1}: {{{{rules_file}}}} must end a "
                             "clause (be followed by . ; : or ), not by more words): a tool's rules file can be "
                             "a long phrase, and words after it read as part of it")
    if not body:
        raise SystemExit(f"{where}: empty step")
    title, out = render_tokens(first[2:].strip(), tool, plans, where), render_tokens(body, tool, plans, where)
    if STEP_HEADING.search(out):
        raise SystemExit(f"{where}: a token renders a line that opens a step (`## Step N of M:`) in the {tool} "
                         "output; the launcher splits the walkthrough on it")
    return title, out


def walkthrough(tool: str, src: Sources) -> str:
    """The whole walkthrough for `tool`: a short head for a reader of the file, then each step under a
    `## Step N of M:` heading and ending with the command that comes next (vocab.next_line). The
    launcher prints one step at a time from this file."""
    v = VOCAB[tool]
    steps = onboarding_steps(tool, src.onboarding)
    how = (f"Type {v.cmd('onboard')} there and your agent shows it one step at a time" if v.typed is not None
           else f"Give your agent {v.cmd('onboard')} and it shows this one step at a time")
    head = [GENERATED, "", "# Onboarding: your first hour with this kit", "",
            f"This copy is for {v.name}. {how}; you can also read it all here."]
    if tool == "claude":
        others = ", ".join(f"[{t}]({walkthrough_path(t)})" for t in sorted(VOCAB) if t != "claude")
        head += ["", f"Not using Claude Code? Every other tool has its own copy: {others}."]
    parts = ["\n".join(head)]
    for i, (name, folder, text) in enumerate(steps, 1):
        title, body = render_step(text, tool, src.plans, f"core/onboarding/{folder}/{name}.md")
        parts.append(f"## Step {i} of {len(steps)}: {title}\n\n{body}\n\n{next_line(tool, i, len(steps))}")
    return "\n\n".join(parts) + "\n"


def yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a valid YAML double-quoted scalar


# Claude tool name -> OpenCode permission keys it grants.
CLAUDE_TOOLS = {
    "Read": ["read"], "Grep": ["grep"], "Glob": ["glob", "list"], "Bash": ["bash"],
    "Edit": ["edit"], "Write": ["edit"], "MultiEdit": ["edit"], "NotebookEdit": ["edit"],
    "WebFetch": ["webfetch"], "WebSearch": ["websearch"], "Task": ["task"], "Agent": ["task"],
    "TodoWrite": ["todowrite"], "Skill": ["skill"],
}
# Capabilities an agent only gets when its `tools:` line grants them. `task` is gated because a
# subagent that may delegate can hand an edit to an agent that is allowed to make it.
GATED = ["edit", "bash", "task", "webfetch", "websearch"]
PLAIN = {"edit": "edit files", "bash": "run shell commands", "task": "delegate to other agents",
         "webfetch": "fetch web pages", "websearch": "search the web"}


def granted(agent: str, doc: Doc) -> set[str]:
    out: set[str] = set()
    for t in (x.strip() for x in doc.meta["tools"].split(",")):
        if t not in CLAUDE_TOOLS:
            raise SystemExit(f"agents/{agent}.md: no adapter mapping for tool {t!r}")
        out.update(CLAUDE_TOOLS[t])
    return out


def denied(agent: str, doc: Doc) -> list[str]:
    g = granted(agent, doc)
    if "edit" in g:
        raise SystemExit(f"agents/{agent}.md grants editing; the adapters only know read-only agents")
    return [k for k in GATED if k not in g]


# --------------------------------------------------------------------------
# Rewrites shared by every non-Claude tool, then per-tool tables
# --------------------------------------------------------------------------

# The last paragraph of commands/starter-update.md is about Claude Code's marketplace install, which no
# other tool has; every adapter drops it.
MARKETPLACE_UPDATE = (
    "\n\nInstalled the plugin from the GitHub marketplace instead of a clone? Then there\n"
    "is no record to read. In Claude Code, run\n"
    "`claude plugin marketplace update claude-starter` and then\n"
    "`claude plugin update starter@claude-starter` in your own terminal, and restart.\n")


def common_rewrites(cmd: Callable[[str], str], tool_config: str) -> list[tuple[str, str]]:
    """`cmd(name)` renders how a ported command is invoked in the target tool."""
    return [
        ("Installed by /starter:setup.",
         "Installed by `scripts/install.py` from the claude-starter repo."),
        ("Move to `CLAUDE.full.md` (re-run `/starter:setup`) when you are on a Max or Team\nplan,",
         "Move to the full rules (re-run `scripts/install.py --tier full`) when your plan\n"
         "has generous usage limits,"),
        ("spends usage fast on Pro plans; best on Max/Team.",
         "spends usage fast on small plans; best with generous usage limits."),
        ("Orchestration: Agent dispatch (or Workflow, where available), sequencing,\n  conflict coordination",
         "Orchestration: subagent dispatch, sequencing, conflict coordination"),
        ("**Delegate via the Agent `model` + `effort` params — two separate choices.**",
         "**Choose a model and an effort level for each delegated task — two separate choices.**"),
        ("The `starter`\nplugin's commit guard checks this on agent commits (see its README for warn and\n"
         "block modes). If you also use non-Claude coding tools, put the same trailer rule\n"
         "in an `AGENTS.md` in each repo so they follow it too.",
         "Where the commit guard is installed as git hooks (installer `--guard-repo`), it\n"
         "checks this on every commit (see its README for warn and block modes). Where it\n"
         "is not installed, nothing checks it but you."),
        ("The `starter` commit guard checks this;",
         "Where the commit guard is installed (installer `--guard-repo`) it checks this;"),
        ("The commit guard checks for this, and a chat summary dies with the session\n"
         "   while a commit outlives it.",
         "Where the commit guard is installed as git hooks (installer `--guard-repo`),\n"
         "   it checks for this; elsewhere nothing does. A chat summary dies with the\n"
         "   session while a commit outlives it."),
        ("`/starter:checkpoint` writes", f"{cmd('checkpoint')} writes"),
        ("`/starter:lanes` sets this up", f"{cmd('lanes')[0].upper()}{cmd('lanes')[1:]} sets this up"),
        (MARKETPLACE_UPDATE, "\n"),
        ("Claude Code's session scratchpad, where available", "your tool's session scratchpad, where available"),
        ("Everything under `.claude/` is loaded", f"Everything under {tool_config} is loaded"),
        ("Not for editing Claude Code config, CLAUDE.md, or skills.",
         "Not for editing your coding tool's config, AGENTS.md, or skills."),
        ("nested CLAUDE.md files", "nested AGENTS.md files"),
        ("a `CLAUDE.md` names a skill", "an `AGENTS.md` names a skill"),
        ("`CLAUDE.md`", "`AGENTS.md`"),
        ("CLAUDE.md", "AGENTS.md"),
    ]


def finish(tool: str, rw: Rewriter, files: dict[str, str], fields: tuple[str, ...] = ()) -> dict[str, str]:
    rw.assert_all_fired(tool)
    lint(tool, files, fields)
    return files


# --------------------------------------------------------------------------
# Emitters
# --------------------------------------------------------------------------

def emit_opencode(src: Sources) -> dict[str, str]:
    """OpenCode 1.19.5. Schema confirmed by loading candidates with `opencode agent list` and
    `opencode debug agent`: per-agent `permission:` object keyed by tool (last matching rule wins);
    a `permissions:` array is ignored and a Claude `tools:` string makes the whole config invalid."""
    rw = Rewriter(common_rewrites(lambda n: f"`/{n}`", "`.opencode/` and `~/.config/opencode/`") + [
        ("in `.claude/commands/`", "in `.opencode/commands/`"),
        ("A `.claude/README.md`", "A `.opencode/README.md`"),
        ("`Read`", "`read`"), ("`Grep`", "`grep`"), ("`Glob`", "`glob`"), ("`Bash`", "`bash`"),
    ])
    files: dict[str, str] = {}
    for tier, text in src.rules.items():
        files[f"AGENTS.{tier}.md"] = rw(text)
    for name, text in src.skills.items():
        files[f"skills/{name}/SKILL.md"] = rw(text)
    for name, doc in src.agents.items():
        deny = denied(name, doc)
        fm = ["---",
              f"description: {yaml_str(rw(doc.meta['description']))}",
              "mode: subagent",
              "# No model is pinned, so the agent runs on the session's model. The Claude source pins",
              f"# `{doc.meta.get('model', '?')}` at {doc.meta.get('effort', '?')} effort; MODELS.md maps that role"
              " to a model. To pin one, add `model: provider/model-id`.",
              "permission:"] + [f"  {k}: deny" for k in deny] + ["---", "", ""]
        files[f"agents/{name}.md"] = "\n".join(fm) + rw(doc.body)
    for name, doc in commands_for(src, "opencode").items():
        fm = ["---", f"description: {yaml_str(rw(doc.meta['description']))}", "---", "", ""]
        files[f"commands/{name}.md"] = "\n".join(fm) + rw(doc.body)
    perm = {"$schema": "https://opencode.ai/config.json",
            "permission": {"bash": {c: "allow" for c in src.bash_allow}}}
    files["opencode.permission.json"] = json.dumps(perm, indent=2) + "\n"
    return finish("opencode", rw, files)


def emit_generic(src: Sources) -> dict[str, str]:
    """Any tool that reads AGENTS.md: plain prompt files, no tool-specific frontmatter."""
    rw = Rewriter(common_rewrites(lambda n: f"the `{n}` prompt (`commands/{n}.md`)",
                                  "your tool's config folders") + [
        ("in `.claude/commands/`", "in your tool's project command folder"),
        ("A `.claude/README.md`", "A README in your tool's project config folder"),
        ("`Read`", "`read`"), ("`Grep`", "`search`"), ("`Glob`", "`find-files`"), ("`Bash`", "`shell`"),
    ])
    files: dict[str, str] = {}
    for tier, text in src.rules.items():
        files[f"AGENTS.{tier}.md"] = rw(text)
    for name, text in src.skills.items():
        files[f"skills/{name}/SKILL.md"] = rw(text)
    for name, doc in src.agents.items():
        deny = denied(name, doc)
        may = ["read and search files"] + [PLAIN[k] for k in GATED if k not in deny]
        head = [
            "Run this as a fresh read-only session if your tool has no subagents.",
            "",
            f"**Agent:** {name}",
            f"**Use when:** {rw(doc.meta['description'])}",
            f"**May:** {', '.join(may)}. **May not:** {', '.join(PLAIN[k] for k in deny)}.",
            "",
            "---",
            "",
        ]
        files[f"agents/{name}.md"] = "\n".join(head) + rw(doc.body)
    for name, doc in commands_for(src, "generic").items():
        head = [f"<!-- Prompt: {rw(doc.meta['description'])}. Paste it, or point your tool at this"
                " file; replace $ARGUMENTS with your input. -->", ""]
        files[f"commands/{name}.md"] = "\n".join(head) + rw(doc.body)
    return finish("generic", rw, files)


# --------------------------------------------------------------------------
# Pieces shared by Codex, Cursor, Copilot, Antigravity and Junie
# --------------------------------------------------------------------------
# Formats come from each tool's official docs (2026-11). Where the docs give no name for a field or a
# tool, nothing is invented: the piece is left out and the generated file says so.

# The Claude source allows exact commands (`Bash(git branch)` has no `:*`). Codex, Antigravity and
# Junie match a rule against a command PREFIX: `codex execpolicy check` showed ["git", "branch"]
# allowing `git branch newb`, which creates a branch. So a command reaches those tools only when it was
# checked with arguments appended and none of them made it write (`git branch --show-current` exits 129
# with -d/-D/-m/-c/-u and ignores a trailing name), and a new source command stops the build until it is
# classified.
PREFIX_SAFE = {  # command -> a near miss that writes; used as the rule's must-not-match example
    "git status": "git stash",
    "git branch --show-current": "git branch -D main",
}
PREFIX_UNSAFE = {
    "ruff format --check": "`--cache-dir <dir>` writes a cache directory wherever it points",
    "ruff format --check .": "`--cache-dir <dir>` writes a cache directory wherever it points",
    "git diff": "`git diff --output=<file>` writes a file",
    "git diff --stat": "`--output=<file>` writes a file",
    "git diff --staged": "`--output=<file>` writes a file",
    "git diff --cached": "`--output=<file>` writes a file",
    "git log --oneline": "`--output=<file>` writes a file",
    "git branch": "`git branch <name>` creates a branch and `-D` deletes one",
}


def prefix_allow(src: Sources) -> tuple[list[str], list[str]]:
    """(commands safe to allow as prefixes, notes on what was left out and why)."""
    notes = []
    for c in src.bash_allow:
        if c in PREFIX_UNSAFE:
            notes.append(f"{c}: left out, {PREFIX_UNSAFE[c]}")
        elif c not in PREFIX_SAFE:
            raise SystemExit(f"settings.starter.json: {c!r} is in neither PREFIX_SAFE nor PREFIX_UNSAFE; "
                             "decide whether it stays read-only with any arguments appended")
    safe = [c for c in src.bash_allow if c in PREFIX_SAFE]
    keep = []
    for c in safe:
        cover = next((s for s in safe if s != c and c.split()[:len(s.split())] == s.split()), None)
        if cover:
            notes.append(f"{c}: already covered by `{cover}`")
        else:
            keep.append(c)
    return keep, notes


# Codex, Copilot, Cursor and Junie all read ~/.agents/skills, so each installs its skills there once.
# Every one of them must then emit byte-identical files for a shared name; build_all checks it.
SHARED_SKILLS_TOOLS = ("codex", "copilot", "cursor", "junie")
NEUTRAL_COMMAND_DIR = [
    ("in `.claude/commands/`", "in your tool's project commands or skills folder"),
    ("A `.claude/README.md`", "A README in your tool's project config folder"),
]
SKILL_TARGET = ("Target: $ARGUMENTS",
                "Target: the part of the repo the user named when invoking this skill (the whole repo if\n"
                "they named none).")
# A skill gets no $ARGUMENTS; onboard's first step already says to use what the user typed after its name.
ONBOARD_ARGS = ("The user typed: $ARGUMENTS\n\n", "")
CONSULTANT_HOLDS = "you hold `Read`, `Grep` and `Glob` and\nnothing else, deliberately."
CODEX_SHELL_FLAGS = "shell tools disabled by feature flags; not verified that Codex honours [features] in agent files"
VERIFIER_HOLDS = "you hold `Read`, `Grep`, `Glob` and\n`Bash`, and no way to edit, deliberately."
RULES_CONSULTANT = "It holds `Read`, `Grep`, `Glob` and nothing\nelse,"
NO_PIN = ("No model is pinned, so the agent runs on the session's model. The Claude source pins `{model}` at "
          "{effort} effort; MODELS.md maps that role to a model.")


def skill_files(src: Sources, tool: str, rw: Rewriter, command_fm: list[str] | None,
                prefix: str = "skills") -> dict[str, str]:
    """The guardrail skills, plus the ported commands as user-invoked skills when `command_fm` is given."""
    files = {f"{prefix}/{n}/SKILL.md": rw(t) for n, t in src.skills.items()}
    if command_fm is not None:
        for n, doc in commands_for(src, tool).items():
            if n in src.skills:
                raise SystemExit(f"command {n!r} and skill {n!r} would share one skill folder")
            fm = ["---", f"name: {n}", f"description: {yaml_str(rw(doc.meta['description']))}",
                  *command_fm, "---", "", ""]
            files[f"{prefix}/{n}/SKILL.md"] = "\n".join(fm) + rw(doc.body)
    return files


def map_tools(agent: str, doc: Doc, names: dict[str, str | None]) -> tuple[list[str], list[str]]:
    """Map the agent's granted capabilities to a tool's names. Returns (names, capabilities the tool
    documents no name for). `names[k] = None` marks a capability the tool has no documented name for."""
    out, missing = [], []
    for k in sorted(granted(agent, doc), key=["read", "grep", "glob", "list", "bash"].index):
        if k not in names:
            raise SystemExit(f"agents/{agent}.md: no mapping for capability {k!r}")
        if names[k] is None:
            missing.append(k)
        elif names[k] not in out:
            out.append(names[k])
    return out, missing


def rules_files(src: Sources, rw: Rewriter) -> dict[str, str]:
    return {f"AGENTS.{tier}.md": rw(text) for tier, text in src.rules.items()}


def toml_ml(s: str) -> str:
    if "'''" not in s and not re.search(r"[\x00-\x08\x0b-\x1f\x7f]", s):
        return "'''\n" + s + "'''"  # literal: no escapes needed; TOML drops the first newline
    return '"""\n' + s.replace("\\", "\\\\").replace('"""', '\\"""') + '"""'


# A command ported to Codex is a skill, and Codex starts a skill on its own unless the skill's
# agents/openai.yaml sets policy.allow_implicit_invocation to false (default true; an explicit $name still
# runs it): https://learn.chatgpt.com/docs/build-skills, read 2026-11-15. scripts/install.py checks the shape.
CODEX_SKILL_POLICY = """\
# Codex skill metadata, generated by claude-starter (scripts/build_adapters.py).
# Run this skill by name (${name}): this policy tells Codex not to start it on its own.
policy:
  allow_implicit_invocation: false
"""


# --------------------------------------------------------------------------

def emit_codex(src: Sources) -> dict[str, str]:
    """Codex CLI: ~/.codex (CODEX_HOME). Agents are TOML; Codex ignores sandbox_mode in agent files, so
    read-only is an instruction, not a restriction. Prompts are deprecated, so commands become skills."""
    rw = Rewriter(common_rewrites(lambda n: f"the `{n}` skill", "`~/.codex/` and `~/.agents/`")
                  + NEUTRAL_COMMAND_DIR + [
        (RULES_CONSULTANT, "It can only read and search (its\nshell tools are disabled by feature flags, "
                           "and it does not edit, by instruction),"),
        SKILL_TARGET, ONBOARD_ARGS,
        (CONSULTANT_HOLDS, "you read and search files and\nnothing else, deliberately: your shell "
                           "tools are disabled by feature flags,\nand you do not edit (by instruction only; "
                           "Codex cannot enforce that for an\nagent)."),
        (VERIFIER_HOLDS, "you read, search and run\ncommands, and you do not edit, deliberately (by "
                         "instruction only; Codex cannot\nenforce that for an agent)."),
    ])
    files = rules_files(src, rw)
    files.update(skill_files(src, "codex", rw, ["disable-model-invocation: true", "user-invocable: true"]))
    for name in src.commands:
        # The SKILL.md stays byte-identical across the tools sharing ~/.agents/skills, so Codex's own policy
        # goes in this Codex-only file beside it; no other tool emits the path.
        files[f"skills/{name}/agents/openai.yaml"] = CODEX_SKILL_POLICY.format(name=name)
    for name, doc in src.agents.items():
        deny = denied(name, doc)
        by_word = [PLAIN[k] for k in deny if k != "bash"]
        instr = ("READ-ONLY BY INSTRUCTION ONLY. You may not " + ", ".join(by_word[:-1]) + f" or {by_word[-1]}"
                 + ". Codex cannot enforce this for an agent (agent files ignore sandbox_mode), so it rests on"
                 " you following it."
                 + (" Your shell tools are disabled by feature flags (features.shell_tool and"
                    " features.unified_exec = false); " + CODEX_SHELL_FLAGS.split("; ", 1)[1] + "."
                    if "bash" in deny else "")
                 + "\n\n" + rw(doc.body))
        lines = [
            "# Codex subagent, generated by claude-starter (scripts/build_adapters.py).",
            "# READ-ONLY BY INSTRUCTION ONLY: Codex cannot enforce it. Agent files ignore sandbox_mode, so",
            "# the only guard is the instruction in developer_instructions.",
            *(["# Consultant: " + CODEX_SHELL_FLAGS + "."] if "bash" in deny else []),
            "# " + NO_PIN.format(model=doc.meta.get("model", "?"), effort=doc.meta.get("effort", "?")),
            "# To pin one, add model = \"...\" and model_reasoning_effort = \"...\".",
            f"name = {json.dumps(name)}",
            f"description = {json.dumps(rw(doc.meta['description']), ensure_ascii=False)}",
            f"developer_instructions = {toml_ml(instr)}",
        ]
        if "bash" in deny:
            lines += ["", "[features]", "shell_tool = false", "unified_exec = false"]
        files[f"agents/{name}.toml"] = "\n".join(lines) + "\n"
    keep, notes = prefix_allow(src)
    out = ["# claude-starter: read-only commands Codex may run without asking.",
           "# Generated by scripts/build_adapters.py. Codex matches `pattern` against a PREFIX of the",
           "# command (anything may follow it), so a command is allowed here only after it was checked",
           "# with arguments appended and none of them made it write. Left out:"] + [f"#   {n}" for n in notes] + [
           "# Codex checks match/not_match when it loads this file. Test it offline with:",
           "#   codex execpolicy check --rules <this file> -- git status", ""]
    for c in keep:
        out += ["prefix_rule(",
                f"    pattern = {json.dumps(c.split())},",
                '    decision = "allow",',
                '    justification = "read-only command (claude-starter)",',
                f"    match = {json.dumps([c])},",
                f"    not_match = {json.dumps([PREFIX_SAFE[c]])},",
                ")", ""]
    files["rules/claude-starter.rules"] = "\n".join(out)
    if sys.version_info >= (3, 11):  # the agent files must parse, and parse back to what was meant
        import tomllib
        for name in src.agents:
            data = tomllib.loads(files[f"agents/{name}.toml"])
            if data["name"] != name or not data["developer_instructions"].startswith("READ-ONLY"):
                raise SystemExit(f"codex/agents/{name}.toml does not parse back to what was written")
    return finish("codex", rw, files)


def emit_cursor(src: Sources) -> dict[str, str]:
    """Cursor (editor and `agent` CLI): ~/.cursor (CURSOR_CONFIG_DIR). No global rules file: the
    installer prints how to paste the rules into Settings > Rules, or writes a project AGENTS.md."""
    rw = Rewriter(common_rewrites(lambda n: f"`/{n}`", "`.cursor/` and `~/.cursor/`") + NEUTRAL_COMMAND_DIR + [
        (RULES_CONSULTANT, "It runs read-only and only reads and\nsearches,"),
        SKILL_TARGET, ONBOARD_ARGS,
        (CONSULTANT_HOLDS, "you run in Cursor's read-only\nmode and use only reading and searching, "
                           "deliberately."),
        (VERIFIER_HOLDS, "you run in Cursor's read-only\nmode: you can read, search and run commands that "
                         "change nothing, and you cannot\nedit, deliberately."),
    ])
    files = rules_files(src, rw)
    files.update(skill_files(src, "cursor", rw, ["disable-model-invocation: true", "user-invocable: true"]))
    for name, doc in src.agents.items():
        denied(name, doc)
        fm = ["---", f"name: {name}", f"description: {yaml_str(rw(doc.meta['description']))}",
              "# " + NO_PIN.format(model=doc.meta.get("model", "?"), effort=doc.meta.get("effort", "?")),
              "model: inherit",
              "# readonly: Cursor blocks file edits and state-changing shell commands for this agent.",
              "readonly: true", "---", "", ""]
        files[f"agents/{name}.md"] = "\n".join(fm) + rw(doc.body)
    # Shell(git) would allow every git command including push, so no allow rule is added. Attribution is
    # turned off because the commit guard flags the "Made with Cursor" trailer Cursor adds by default.
    cfg = {"version": 1, "editor": {"vimMode": False}, "permissions": {"allow": [], "deny": []},
           "attribution": {"attributeCommitsToAgent": False, "attributePRsToAgent": False}}
    files["cli-config.json"] = json.dumps(cfg, indent=2) + "\n"
    return finish("cursor", rw, files, fields=("model",))


COPILOT_TOOLS = {"read": "read", "grep": "search", "glob": "search", "list": "search", "bash": "execute"}


def emit_copilot(src: Sources) -> dict[str, str]:
    """GitHub Copilot CLI: ~/.copilot (COPILOT_HOME). Tool aliases read/search/execute are from GitHub's
    custom-agents configuration reference. VS Code settings are never edited: the installer prints the
    terminal auto-approve snippet."""
    rw = Rewriter(common_rewrites(lambda n: f"`/{n}`", "`~/.copilot/` and `.github/`") + NEUTRAL_COMMAND_DIR + [
        (RULES_CONSULTANT, "It holds `read` and `search` and nothing\nelse,"),
        SKILL_TARGET, ONBOARD_ARGS,
        (CONSULTANT_HOLDS, "you hold `read` and `search` and\nnothing else, deliberately."),
        (VERIFIER_HOLDS, "you hold `read`, `search` and\n`execute`, and no way to edit, deliberately."),
    ])
    files = rules_files(src, rw)
    files.update(skill_files(src, "copilot", rw, ["disable-model-invocation: true", "user-invocable: true"]))
    for name, doc in src.agents.items():
        denied(name, doc)
        tools, _ = map_tools(name, doc, COPILOT_TOOLS)
        fm = ["---", f"name: {name}", f"description: {yaml_str(rw(doc.meta['description']))}",
              f"tools: {json.dumps(tools)}",
              "# strict-tools-list is listed for the CLI by the research notes but missing from GitHub's",
              "# configuration reference; if Copilot ignores it, `tools` still limits the agent.",
              "strict-tools-list: true",
              "# " + NO_PIN.format(model=doc.meta.get("model", "?"), effort=doc.meta.get("effort", "?")),
              "---", "", ""]
        files[f"agents/{name}.agent.md"] = "\n".join(fm) + rw(doc.body)

    def js_rx(c: str) -> str:
        return "/^" + re.sub(r"([\\^$.|?*+()\[\]{}/])", r"\\\1", c) + "$/"
    # VS Code documents /regex/ keys, so every command is anchored and matches only exactly.
    snippet = {"chat.tools.terminal.autoApprove": {js_rx(c): True for c in src.bash_allow}}
    files["vscode-terminal-autoapprove.json"] = json.dumps(snippet, indent=2) + "\n"
    return finish("copilot", rw, files, fields=("tools",))


ANTIGRAVITY_TOOLS = {"read": "view_file", "grep": "grep_search", "glob": None, "list": None, "bash": None}
ANTIGRAVITY_RULES_CAP = 24_000  # bytes per rules file, from the Antigravity docs


def emit_antigravity(src: Sources) -> dict[str, str]:
    """Google Antigravity: ~/.gemini. Only documented tool names are used: the docs warn a misspelt name
    can hang the agent, and they give none for running commands, so no agent here has a shell."""
    no_shell = ("> **No shell in Antigravity.** Its docs name no tool for running commands, so this agent "
                "cannot\n> run the build, the tests or git itself. Ask the session that called you to run each "
                "command\n> and give you the full output; judge that output, and say which results you did not "
                "run.\n\n")
    rw = Rewriter(common_rewrites(lambda n: f"`/{n}`", "`~/.gemini/`") + NEUTRAL_COMMAND_DIR + [
        (RULES_CONSULTANT, "It holds `view_file` and `grep_search` and\nnothing else,"),
        SKILL_TARGET, ONBOARD_ARGS,
        (CONSULTANT_HOLDS, "you hold `view_file` and\n`grep_search` and nothing else, deliberately."),
        (VERIFIER_HOLDS, "you hold `view_file` and\n`grep_search`, and no way to edit or to run commands."),
    ])
    files = rules_files(src, rw)
    for tier in src.rules:
        size = len(files[f"AGENTS.{tier}.md"].encode("utf-8"))
        if size > ANTIGRAVITY_RULES_CAP:
            raise SystemExit(f"antigravity: the {tier} rules are {size} bytes; Antigravity reads at most "
                             f"{ANTIGRAVITY_RULES_CAP} bytes per rules file")
    files.update(skill_files(src, "antigravity", rw, [], prefix="config/skills"))
    for name, doc in src.agents.items():
        denied(name, doc)
        tools, missing = map_tools(name, doc, ANTIGRAVITY_TOOLS)
        fm = ["---", f"name: {name}", f"description: {yaml_str(rw(doc.meta['description']))}",
              f"tools: {json.dumps(tools)}",
              f"# Not granted (no documented tool name): {', '.join(missing)}." if missing else
              "# Only documented tool names are listed.",
              "# " + NO_PIN.format(model=doc.meta.get("model", "?"), effort=doc.meta.get("effort", "?")),
              "model: inherit", "---", "", ""]
        files[f"config/agents/{name}.md"] = "\n".join(fm) + (no_shell if "bash" in missing else "") + rw(doc.body)
    keep, _ = prefix_allow(src)
    perm = {"permissions": {"allow": [f"command({c})" for c in keep]}}
    files["antigravity-cli.settings.json"] = json.dumps(perm, indent=2) + "\n"
    return finish("antigravity", rw, files, fields=("tools", "model"))


JUNIE_TOOLS = {"read": "Read", "grep": "Grep", "glob": "Glob", "list": "Glob", "bash": "Bash"}


def emit_junie(src: Sources) -> dict[str, str]:
    """JetBrains Junie: ~/.junie. Tool group names (Read, Grep, Glob, Bash) are from the Junie CLI
    subagents page; `tools` is an allowlist, so unlisted groups (Edit, Write, ...) are banned."""
    rw = Rewriter(common_rewrites(lambda n: f"`/{n}`", "`.junie/` and `~/.junie/`") + [
        ("in `.claude/commands/`", "in `.junie/commands/`"),
        ("A `.claude/README.md`", "A `.junie/README.md`"),
        ("$ARGUMENTS", "$prompt"),
    ])
    files = rules_files(src, rw)
    files.update(skill_files(src, "junie", rw, None))
    for name, doc in src.agents.items():
        denied(name, doc)
        tools, _ = map_tools(name, doc, JUNIE_TOOLS)
        fm = ["---", f"name: {yaml_str(name)}", f"description: {yaml_str(rw(doc.meta['description']))}",
              f"tools: {json.dumps(tools)}",
              "# " + NO_PIN.format(model=doc.meta.get("model", "?"), effort=doc.meta.get("effort", "?")),
              "---", "", ""]
        files[f"agents/{name}.md"] = "\n".join(fm) + rw(doc.body)
    for name, doc in commands_for(src, "junie").items():
        fm = ["---", f"description: {yaml_str(rw(doc.meta['description']))}"]
        if "$ARGUMENTS" in doc.body:
            fm.append("allowPromptArgument: true")
        files[f"commands/{name}.md"] = "\n".join(fm + ["---", "", ""]) + rw(doc.body)
    keep, _ = prefix_allow(src)
    allow = {"rules": {"executables": {"rules": [{"prefix": c, "action": "allow"} for c in keep]}}}
    files["junie.allowlist.json"] = json.dumps(allow, indent=2) + "\n"
    return finish("junie", rw, files, fields=("tools",))


EMITTERS: dict[str, Callable[[Sources], dict[str, str]]] = {
    "opencode": emit_opencode,
    "generic": emit_generic,
    "codex": emit_codex,
    "cursor": emit_cursor,
    "copilot": emit_copilot,
    "antigravity": emit_antigravity,
    "junie": emit_junie,
}

# The plugin mixes generated and hand-written files, so a generated one says where its source is.
CLAUDE_GENERATED = ("<!-- Generated by scripts/build_adapters.py from core/commands/{n}.md. Edit that file and "
                    "rebuild. -->")


def emit_claude(src: Sources) -> dict[str, str]:
    """Claude Code: the plugin commands whose source is in core/commands/, frontmatter as written there.
    Paths are relative to the repo root; every other plugin file is hand-written and not in this manifest.

    Claude Code may run a command file on its own unless its frontmatter sets disable-model-invocation
    (https://code.claude.com/docs/en/slash-commands, read 2026-11-15), and the Codex, Cursor and Copilot
    copies of a ported command already set it, so a core command without it stops the build. Tokens are
    rendered for Claude Code (render_command)."""
    files = {}
    for name, text in src.core_commands.items():
        where = f"core/commands/{name}.md"
        fm, sep, body = render_command(text, "claude", where).partition("\n---\n")
        if not text.startswith("---\n") or not sep:
            raise SystemExit(f"{where}: no frontmatter")
        if src.commands[name].meta.get("disable-model-invocation") != "true":
            raise SystemExit(f"{where}: needs `disable-model-invocation: true`, so Claude Code runs it only when "
                             "the user types it, as Codex, Cursor and Copilot do")
        files[f"plugins/starter/commands/{name}.md"] = (f"{fm}\n---\n\n{CLAUDE_GENERATED.format(n=name)}\n\n"
                                                        + body.lstrip("\n"))
    return files


BUILDS = ("claude", *sorted(EMITTERS))  # every tool with a build; vocab.VOCAB names the same set
# Where each tool's build puts a ported command. Antigravity reads its own config/skills, not the shared
# ~/.agents/skills, so a check of the shared copies alone would miss it. Claude Code's build holds only
# the commands rendered from core/; its other commands are hand-written plugin files.
COMMAND_PATHS = {
    "claude": "plugins/starter/commands/{n}.md",
    "opencode": "commands/{n}.md", "generic": "commands/{n}.md", "junie": "commands/{n}.md",
    "codex": "skills/{n}/SKILL.md", "cursor": "skills/{n}/SKILL.md", "copilot": "skills/{n}/SKILL.md",
    "antigravity": "config/skills/{n}/SKILL.md",
}


def check_commands_everywhere(built: dict[str, dict[str, str]], core_commands) -> None:
    """Every build ships every ported command. A tool once had starter-update in every build but its own."""
    problems = []
    for t, files in sorted(built.items()):
        names = sorted(core_commands) if t == "claude" else PORTED_COMMANDS
        problems += [f"  {t}: no {COMMAND_PATHS[t].format(n=n)}" for n in names
                     if COMMAND_PATHS[t].format(n=n) not in files]
    if problems:
        raise SystemExit("a ported command is missing from a build:\n" + "\n".join(problems))


def out_path(tool: str, rel: str) -> str:
    """Where a build's file goes, relative to the repo root."""
    return rel if tool == "claude" else f"adapters/{tool}/{rel}"


# --------------------------------------------------------------------------
# Build / check
# --------------------------------------------------------------------------

def index(tools: list[str], built: dict[str, dict[str, str]]) -> str:
    lines = ["# adapters (generated)", "",
             "Do not edit files here. They are generated from `core/` and `plugins/starter/` by",
             "`python scripts/build_adapters.py`, and CI fails when they drift from a fresh build.",
             "Install one with `python scripts/install.py --tool <tool> --tier <starter|full>`;",
             "`python scripts/install.py --help` lists every flag. To have an AI agent do it for you,",
             "give it the repo link and see `AGENTS.md` at the repo root. `generic` is the starting",
             "point for a tool the installer does not support (`--config-dir` is required; see `PORTING.md`).",
             "Each tool's `ONBOARDING.md` is its onboarding walkthrough; the installer does not copy it, and",
             "the `onboard` command prints it one step at a time from here.", "",
             "| Tool | Files |", "|---|---|"]
    for t in tools:
        lines.append(f"| `{t}` | {len(built[t])} |")
    lines += ["", f"{', '.join(SHARED_SKILLS_TOOLS)} install their skills into the shared `~/.agents/skills`;",
              "the build checks that they emit byte-identical files there."]
    return "\n".join(lines) + "\n"


def check_shared_skills(built: dict[str, dict[str, str]]) -> None:
    seen: dict[str, tuple[str, str]] = {}
    for t in SHARED_SKILLS_TOOLS:
        for rel, text in built.get(t, {}).items():
            if not rel.startswith("skills/"):
                continue
            if rel in seen and seen[rel][1] != text:
                raise SystemExit(f"{rel}: {seen[rel][0]} and {t} would write different files to the shared "
                                 "~/.agents/skills; make their rewrites of skill text identical")
            seen.setdefault(rel, (t, text))


def check_vocab_matches_builds() -> None:
    """scripts/vocab.py names the same tools as the builds, and says a tool's commands are shared exactly
    when its build puts them in the shared ~/.agents/skills. A tool marked shared that is not would ask the
    install record for its tool, which is how a Claude Code user was once shown OpenCode's walkthrough."""
    if set(VOCAB) != set(BUILDS):
        raise SystemExit(f"scripts/vocab.py names {sorted(VOCAB)} but the builds are {sorted(BUILDS)}")
    wrong = [t for t in BUILDS
             if VOCAB[t].shared_commands != (t in SHARED_SKILLS_TOOLS and COMMAND_PATHS[t].startswith("skills/"))]
    if wrong:
        raise SystemExit(f"scripts/vocab.py: shared_commands is wrong for {', '.join(wrong)}; it is True exactly "
                         f"for the tools whose commands are skills in the shared ~/.agents/skills")


def build_tools(tools: list[str], src: Sources | None = None) -> dict[str, dict[str, str]]:
    """Each tool's manifest (path relative to its output folder -> text), checked: shared skills agree,
    every build has every ported command, and the two-way term check passes."""
    check_vocab_matches_builds()
    src = src or load_sources()
    built = {}
    for t in tools:
        files = emit_claude(src) if t == "claude" else EMITTERS[t](src)
        files["ONBOARDING.md"] = walkthrough(t, src)
        if t != "claude":
            lint(t, {"ONBOARDING.md": files["ONBOARDING.md"]})
        built[t] = files
    check_shared_skills(built)
    check_commands_everywhere(built, src.core_commands)
    check_terms(built, load_terms(), load_baseline(), full=set(tools) == set(BUILDS))
    return built


def build_all(tools: list[str]) -> dict[str, str]:
    """Every file the build writes, by path relative to the repo root."""
    built = build_tools(tools)
    out: dict[str, str] = {}
    for t in tools:
        for rel, text in built[t].items():
            if "\r" in text:
                raise SystemExit(f"{t}/{rel}: CR in output")
            out[out_path(t, rel)] = text if text.endswith("\n") else text + "\n"
    adapter_tools = [t for t in tools if t != "claude"]
    if adapter_tools == sorted(EMITTERS):
        out["adapters/README.md"] = index(adapter_tools, built)
    return dict(sorted(out.items()))


def existing(scope: list[Path]) -> dict[str, bytes]:
    found = {}
    for base in scope:
        if base.is_file():
            found[base.relative_to(ROOT).as_posix()] = base.read_bytes()
        elif base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    found[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    return found


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # tool output carries non-ASCII; never crash printing it
        stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a generated file differs from a fresh build")
    ap.add_argument("--tool", choices=BUILDS, action="append", help="limit to one tool (repeatable); default all")
    args = ap.parse_args(argv)
    tools = sorted(set(args.tool)) if args.tool else list(BUILDS)
    want = {k: v.encode("utf-8") for k, v in build_all(tools).items()}
    # Only adapters/<tool>/ is generated whole, so only there can a file be extra; elsewhere the build
    # owns exactly the paths in its manifest.
    scope = [OUT / t for t in tools if t != "claude"] + ([OUT / "README.md"] if "adapters/README.md" in want else [])
    have = existing(scope)
    have.update({k: (ROOT / k).read_bytes() for k in want if k not in have and (ROOT / k).is_file()})

    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    changed = sorted(k for k in set(want) & set(have) if want[k] != have[k])

    if args.check:
        if missing or extra or changed:
            for k in missing:
                print(f"missing:  {k}")
            for k in extra:
                print(f"extra:    {k}")
            for k in changed:
                print(f"differs:  {k}")
            print(f"generated files are out of date ({len(missing)} missing, {len(extra)} extra, {len(changed)} "
                  "differ). Run: python scripts/build_adapters.py", file=sys.stderr)
            return 1
        print(f"generated files up to date ({len(want)} files, tools: {', '.join(tools)})")
        return 0

    for k in extra:
        (ROOT / k).unlink()
    for k in missing + changed:
        p = ROOT / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(want[k])
    for d in sorted((p for p in OUT.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    print(f"wrote {len(missing)} new, {len(changed)} changed, removed {len(extra)}; "
          f"{len(want)} files for: {', '.join(tools)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
