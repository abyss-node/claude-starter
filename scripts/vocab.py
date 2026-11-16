"""The words that differ per tool, shared by the build, the launcher and the demos.

scripts/build_adapters.py renders core/onboarding/ with them, scripts/starter.py uses them to name each
tool's next onboarding command at run time, so both always agree on what the user types, and demos/start.py
and demos/pick.py use them for the repo rules file and the command that opens a session. Vocab has no
defaults: a tool added without one of its words cannot be constructed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Vocab:
    name: str              # the tool as its user knows it
    rules_file: str        # where the installed global rules live, as Markdown
    typed: Optional[str]   # what the user types to run a kit command, "{}" standing for the command's name.
                           # None: the tool has no command mechanism, so a kit command is a prompt file
    shared_commands: bool  # the kit's commands are skills in the shared ~/.agents/skills, one copy for several
                           # tools, so that copy cannot name its tool and the launcher takes it from the install
                           # record. False: the tool's copy is its own and always passes `--tool <id>`
    repo_rules: str        # the file a repo's own rules go in, at the repo root (demos/start.py writes one)
    open_cmd: Optional[str]  # the terminal command that starts a session in a folder, "{dir}" standing for the
                             # quoted folder; without "{dir}" it runs inside the folder. None: no command is
                             # confirmed, so the user opens the folder in the tool

    def cmd(self, name: str) -> str:
        """How the user runs the kit command `name`, as Markdown."""
        if self.typed is None:
            return f"the `{name}` prompt (`commands/{name}.md`)"
        return f"`{self.typed.format(name)}`"


# rules_file ends a clause wherever a step uses it (the build checks), because Cursor's is a long phrase.
# open_cmd: `claude` starts in the current folder; `codex -C <dir>` and `opencode <dir>` are from their --help
# (0.167.0 and 1.19.5). No other tool's command for this was checked.
VOCAB = {
    "claude": Vocab("Claude Code", "`~/.claude/CLAUDE.md`", "/starter:{}", False, "CLAUDE.md", "claude"),
    "opencode": Vocab("OpenCode", "`~/.config/opencode/AGENTS.md`", "/{}", False, "AGENTS.md", "opencode {dir}"),
    # Codex runs a skill when its name is typed after `$` (https://learn.chatgpt.com/docs/build-skills).
    "codex": Vocab("Codex", "`~/.codex/AGENTS.md`", "${}", True, "AGENTS.md", "codex -C {dir}"),
    "cursor": Vocab("Cursor", "Cursor Settings > Rules, if you pasted them there, or `AGENTS.md` in the repo "
                              "you gave `--project`", "/{}", True, "AGENTS.md", None),
    "copilot": Vocab("Copilot", "`~/.copilot/copilot-instructions.md`", "/{}", True, "AGENTS.md", None),
    "antigravity": Vocab("Antigravity", "`~/.gemini/AGENTS.md`", "/{}", False, "AGENTS.md", None),
    "junie": Vocab("Junie", "`~/.junie/AGENTS.md`", "/{}", False, "AGENTS.md", None),
    "generic": Vocab("any other tool", "`AGENTS.md` in the config folder you installed into", None, False,
                     "AGENTS.md", None),
}

# The heading that opens each step of a rendered walkthrough. The launcher splits on it without regard to
# code fences, so a step's own text may never contain it, fenced or not (the build refuses one that does).
STEP_HEADING = re.compile(r"^## Step (\d+) of (\d+): \S.*$", re.M)


def walkthrough_path(tool: str) -> str:
    """The rendered walkthrough, relative to the kit root. Claude's is the root ONBOARDING.md, so GitHub
    shows a readable copy at the top of the repo."""
    return "ONBOARDING.md" if tool == "claude" else f"adapters/{tool}/ONBOARDING.md"


def next_line(tool: str, step: int, total: int) -> str:
    """The last line of step `step`: the exact command that comes next."""
    v = VOCAB[tool]
    if step < total:
        if v.typed is None:
            return f"Next: run {v.cmd('onboard')} with `{step + 1}`."
        return f"Next: type `{v.typed.format('onboard')} {step + 1}` to go on."
    verb = "run" if v.typed is None else "type"
    return f"That was the last step. Next: after your next change, {verb} {v.cmd('checkpoint')}."


def with_tool(line: str, tool: str) -> str:
    """A next line whose command also names `--tool <tool>`: for a tool whose command copy is shared
    (shared_commands) on a machine where the install record does not name exactly one tool."""
    spans = list(re.finditer(r"`([^`]*)`", line))
    if not spans:
        raise ValueError(f"no command in {line!r}")
    last = spans[-1]
    return f"{line[:last.start()]}`{last.group(1)} --tool {tool}`{line[last.end():]}"
