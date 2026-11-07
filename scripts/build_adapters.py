#!/usr/bin/env python3
"""Generate adapters/<tool>/ from the Claude Code sources in plugins/starter/.

Every non-Claude tool gets a ready-to-install copy of the kit, produced by code
rather than by a model translating files by hand. A hand translation once copied
Claude agent frontmatter (`tools: Read, Grep, Glob, Bash`) into OpenCode, which
made OpenCode's whole configuration invalid, and still reported success.

    python scripts/build_adapters.py            # regenerate adapters/
    python scripts/build_adapters.py --check    # exit 1 if adapters/ differs from a fresh build
    python scripts/build_adapters.py --tool opencode

Adding a tool: write one `emit_<tool>(src) -> dict[relpath, text]` function and
add it to EMITTERS. The shared pieces (Sources, Rewriter, lint) do the rest.

Each emitter's rewrites must all fire: a rewrite that matches nothing means the
source changed under it, and the build stops instead of shipping a stale
translation. After rewriting, FORBIDDEN patterns (Claude-only names) must be
gone from every emitted file, so a new Claude-ism in the sources fails the build
until an emitter handles it. Output is deterministic: sorted, UTF-8, LF only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "starter"
OUT = ROOT / "adapters"

# Commands that carry over. `setup` writes Claude Code settings; scripts/install.py replaces it.
PORTED_COMMANDS = ("checkpoint", "lanes")
TIERS = ("starter", "full")


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
    commands: dict[str, Doc]
    bash_allow: list[str]          # read-only shell commands from settings.starter.json


def load_sources() -> Sources:
    rules = {t: read(PLUGIN / "templates" / f"CLAUDE.{t}.md") for t in TIERS}
    skills = {p.parent.name: read(p) for p in sorted((PLUGIN / "skills").glob("*/SKILL.md"))}
    agents = {}
    for p in sorted((PLUGIN / "agents").glob("*.md")):
        meta, body = split_frontmatter(read(p), str(p))
        agents[p.stem] = Doc(meta, body)
    commands = {}
    for name in PORTED_COMMANDS:
        p = PLUGIN / "commands" / f"{name}.md"
        meta, body = split_frontmatter(read(p), str(p))
        commands[name] = Doc(meta, body)
    settings = json.loads(read(PLUGIN / "templates" / "settings.starter.json"))
    bash_allow = []
    for entry in settings["permissions"]["allow"]:
        m = re.fullmatch(r"Bash\((.+)\)", entry)
        if not m:
            raise SystemExit(f"settings.starter.json: no adapter mapping for permission {entry!r}")
        bash_allow.append(m.group(1).replace(":*", " *"))
    return Sources(rules, skills, agents, commands, bash_allow)


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


# Claude-only names that must not survive into any adapter.
FIELD = "Claude frontmatter field"
TOOL_NAME = "Claude Code tool name"
FORBIDDEN = [
    (re.compile(r"/starter:"), "plugin-namespaced command"),
    (re.compile(r"CLAUDE(\.starter|\.full)?\.md"), "Claude Code rules file name"),
    (re.compile(r"Claude Code"), "Claude Code reference"),
    (re.compile(r"\.claude/"), "Claude Code config folder"),
    (re.compile(r"(?<![\w-])/plugin\b"), "Claude Code /plugin command"),
    (re.compile(r"settings\.json"), "Claude Code settings file"),
    (re.compile(r"CLAUDE_PLUGIN_ROOT|AskUserQuestion"), "Claude Code runtime name"),
    (re.compile(r"`(Read|Grep|Glob|Bash|Edit|Write)`"), TOOL_NAME),
    (re.compile(r"\b(Max/Team|Max or Team|Pro plans?)\b"), "Claude subscription plan"),
    (re.compile(r"^(tools|model|effort|allowed-tools):", re.M), FIELD),
    # Never allowed, even where a tool has its own `tools:`/`model:` field: the Claude spellings.
    (re.compile(r"^tools:\s*[A-Z]\w*(\s*,\s*[A-Z]\w*)+\s*$", re.M), "Claude `tools:` string"),
    (re.compile(r"^model:\s*(opus|sonnet|haiku|fable)\b", re.M), "Claude model alias"),
]


def lint(tool: str, files: dict[str, str], fields: tuple[str, ...] = (),
         exempt: tuple[str, ...] = ()) -> None:
    """`fields`: frontmatter fields this tool really has (e.g. its own `tools:` list).
    `exempt`: FORBIDDEN descriptions that are this tool's own vocabulary (Junie's tool groups are
    literally named Read, Grep, Glob, Bash)."""
    problems = []
    for rel, text in files.items():
        for rx, what in FORBIDDEN:
            if what in exempt:
                continue
            for m in rx.finditer(text):
                if what == FIELD and m.group(1) in fields:
                    continue
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"  {tool}/{rel}:{line}: {what}: {m.group(0)!r}")
    if problems:
        raise SystemExit(f"{tool}: Claude-only names left after rewriting:\n" + "\n".join(problems))


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
         "The `starter`\ncommit guard, installed as git hooks, checks this on every commit (see its\n"
         "README for warn and block modes)."),
        ("`/starter:checkpoint` writes", f"{cmd('checkpoint')} writes"),
        ("`/starter:lanes` sets this up", f"{cmd('lanes')[0].upper()}{cmd('lanes')[1:]} sets this up"),
        ("Claude Code's session scratchpad, where available", "your tool's session scratchpad, where available"),
        ("Everything under `.claude/` is loaded", f"Everything under {tool_config} is loaded"),
        ("Not for editing Claude Code config, CLAUDE.md, or skills.",
         "Not for editing your coding tool's config, AGENTS.md, or skills."),
        ("nested CLAUDE.md files", "nested AGENTS.md files"),
        ("a `CLAUDE.md` names a skill", "an `AGENTS.md` names a skill"),
        ("`CLAUDE.md`", "`AGENTS.md`"),
        ("CLAUDE.md", "AGENTS.md"),
    ]


def finish(tool: str, rw: Rewriter, files: dict[str, str], fields: tuple[str, ...] = (),
           exempt: tuple[str, ...] = ()) -> dict[str, str]:
    rw.assert_all_fired(tool)
    lint(tool, files, fields, exempt)
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
    for name, doc in src.commands.items():
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
    for name, doc in src.commands.items():
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
CONSULTANT_HOLDS = "you hold `Read`, `Grep` and `Glob` and\nnothing else, deliberately."
CODEX_SHELL_FLAGS = "shell tools disabled by feature flags; not verified that Codex honours [features] in agent files"
VERIFIER_HOLDS = "you hold `Read`, `Grep`, `Glob` and\n`Bash`, and no way to edit, deliberately."
RULES_CONSULTANT = "It holds `Read`, `Grep`, `Glob` and nothing\nelse,"
NO_PIN = ("No model is pinned, so the agent runs on the session's model. The Claude source pins `{model}` at "
          "{effort} effort; MODELS.md maps that role to a model.")


def skill_files(src: Sources, rw: Rewriter, command_fm: list[str] | None,
                prefix: str = "skills") -> dict[str, str]:
    """The guardrail skills, plus checkpoint/lanes as user-invoked skills when `command_fm` is given."""
    files = {f"{prefix}/{n}/SKILL.md": rw(t) for n, t in src.skills.items()}
    if command_fm is not None:
        for n, doc in src.commands.items():
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


# --------------------------------------------------------------------------

def emit_codex(src: Sources) -> dict[str, str]:
    """Codex CLI: ~/.codex (CODEX_HOME). Agents are TOML; Codex ignores sandbox_mode in agent files, so
    read-only is an instruction, not a restriction. Prompts are deprecated, so commands become skills."""
    rw = Rewriter(common_rewrites(lambda n: f"the `{n}` skill", "`~/.codex/` and `~/.agents/`")
                  + NEUTRAL_COMMAND_DIR + [
        (RULES_CONSULTANT, "It can only read and search (its\nshell tools are disabled by feature flags, "
                           "and it does not edit, by instruction),"),
        SKILL_TARGET,
        (CONSULTANT_HOLDS, "you read and search files and\nnothing else, deliberately: your shell "
                           "tools are disabled by feature flags,\nand you do not edit (by instruction only; "
                           "Codex cannot enforce that for an\nagent)."),
        (VERIFIER_HOLDS, "you read, search and run\ncommands, and you do not edit, deliberately (by "
                         "instruction only; Codex cannot\nenforce that for an agent)."),
    ])
    files = rules_files(src, rw)
    files.update(skill_files(src, rw, ["disable-model-invocation: true", "user-invocable: true"]))
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
        SKILL_TARGET,
        (CONSULTANT_HOLDS, "you run in Cursor's read-only\nmode and use only reading and searching, "
                           "deliberately."),
        (VERIFIER_HOLDS, "you run in Cursor's read-only\nmode: you can read, search and run commands that "
                         "change nothing, and you cannot\nedit, deliberately."),
    ])
    files = rules_files(src, rw)
    files.update(skill_files(src, rw, ["disable-model-invocation: true", "user-invocable: true"]))
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
        SKILL_TARGET,
        (CONSULTANT_HOLDS, "you hold `read` and `search` and\nnothing else, deliberately."),
        (VERIFIER_HOLDS, "you hold `read`, `search` and\n`execute`, and no way to edit, deliberately."),
    ])
    files = rules_files(src, rw)
    files.update(skill_files(src, rw, ["disable-model-invocation: true", "user-invocable: true"]))
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
        SKILL_TARGET,
        (CONSULTANT_HOLDS, "you hold `view_file` and\n`grep_search` and nothing else, deliberately."),
        (VERIFIER_HOLDS, "you hold `view_file` and\n`grep_search`, and no way to edit or to run commands."),
    ])
    files = rules_files(src, rw)
    for tier in src.rules:
        size = len(files[f"AGENTS.{tier}.md"].encode("utf-8"))
        if size > ANTIGRAVITY_RULES_CAP:
            raise SystemExit(f"antigravity: the {tier} rules are {size} bytes; Antigravity reads at most "
                             f"{ANTIGRAVITY_RULES_CAP} bytes per rules file")
    files.update(skill_files(src, rw, [], prefix="config/skills"))
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
    files.update(skill_files(src, rw, None))
    for name, doc in src.agents.items():
        denied(name, doc)
        tools, _ = map_tools(name, doc, JUNIE_TOOLS)
        fm = ["---", f"name: {yaml_str(name)}", f"description: {yaml_str(rw(doc.meta['description']))}",
              f"tools: {json.dumps(tools)}",
              "# " + NO_PIN.format(model=doc.meta.get("model", "?"), effort=doc.meta.get("effort", "?")),
              "---", "", ""]
        files[f"agents/{name}.md"] = "\n".join(fm) + rw(doc.body)
    for name, doc in src.commands.items():
        fm = ["---", f"description: {yaml_str(rw(doc.meta['description']))}"]
        if "$ARGUMENTS" in doc.body:
            fm.append("allowPromptArgument: true")
        files[f"commands/{name}.md"] = "\n".join(fm + ["---", "", ""]) + rw(doc.body)
    keep, _ = prefix_allow(src)
    allow = {"rules": {"executables": {"rules": [{"prefix": c, "action": "allow"} for c in keep]}}}
    files["junie.allowlist.json"] = json.dumps(allow, indent=2) + "\n"
    return finish("junie", rw, files, fields=("tools",), exempt=(TOOL_NAME,))


EMITTERS: dict[str, Callable[[Sources], dict[str, str]]] = {
    "opencode": emit_opencode,
    "generic": emit_generic,
    "codex": emit_codex,
    "cursor": emit_cursor,
    "copilot": emit_copilot,
    "antigravity": emit_antigravity,
    "junie": emit_junie,
}


# --------------------------------------------------------------------------
# Build / check
# --------------------------------------------------------------------------

def index(tools: list[str], built: dict[str, dict[str, str]]) -> str:
    lines = ["# adapters (generated)", "",
             "Do not edit files here. They are generated from `plugins/starter/` by",
             "`python scripts/build_adapters.py`, and CI fails when they drift from a fresh build.",
             "Install one with `python scripts/install.py --tool <tool> --tier <starter|full>`;",
             "`python scripts/install.py --help` lists every flag. To have an AI agent do it for you,",
             "give it the repo link and see `AGENTS.md` at the repo root. `generic` is the starting",
             "point for a tool the installer does not support (`--config-dir` is required; see `PORTING.md`).", "",
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


def build_all(tools: list[str]) -> dict[str, str]:
    src = load_sources()
    built = {t: EMITTERS[t](src) for t in tools}
    check_shared_skills(built)
    out: dict[str, str] = {}
    for t in tools:
        for rel, text in built[t].items():
            if "\r" in text:
                raise SystemExit(f"{t}/{rel}: CR in output")
            out[f"{t}/{rel}"] = text if text.endswith("\n") else text + "\n"
    if tools == sorted(EMITTERS):
        out["README.md"] = index(tools, built)
    return dict(sorted(out.items()))


def existing(scope: list[Path]) -> dict[str, bytes]:
    found = {}
    for base in scope:
        if base.is_file():
            found[base.relative_to(OUT).as_posix()] = base.read_bytes()
        elif base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    found[p.relative_to(OUT).as_posix()] = p.read_bytes()
    return found


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # tool output carries non-ASCII; never crash printing it
        stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if adapters/ differs from a fresh build")
    ap.add_argument("--tool", choices=sorted(EMITTERS), action="append",
                    help="limit to one tool (repeatable); default all")
    args = ap.parse_args(argv)
    tools = sorted(set(args.tool)) if args.tool else sorted(EMITTERS)
    want = {k: v.encode("utf-8") for k, v in build_all(tools).items()}
    scope = [OUT / t for t in tools] + ([OUT / "README.md"] if "README.md" in want else [])
    have = existing(scope)

    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    changed = sorted(k for k in set(want) & set(have) if want[k] != have[k])

    if args.check:
        if missing or extra or changed:
            for k in missing:
                print(f"missing:  adapters/{k}")
            for k in extra:
                print(f"extra:    adapters/{k}")
            for k in changed:
                print(f"differs:  adapters/{k}")
            print(f"adapters/ is out of date ({len(missing)} missing, {len(extra)} extra, {len(changed)} differ). "
                  "Run: python scripts/build_adapters.py", file=sys.stderr)
            return 1
        print(f"adapters/ up to date ({len(want)} files, tools: {', '.join(tools)})")
        return 0

    for k in extra:
        (OUT / k).unlink()
    for k in missing + changed:
        p = OUT / k
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
