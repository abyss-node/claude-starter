# For any coding agent asked to set this up

This repo is a starter kit for working with an AI coding agent: rules, review
agents, commands, guardrail skills and a commit guard. A user can give you only
the link `https://github.com/abyss-node/claude-starter` and say "Set this up for
me. Ask me starter or full, show me the plan, and wait for my yes before
installing anything." Do the steps below. They are the single full version; the
top of `README.md` carries a short copy.

You need to read and write files and run shell commands. If you cannot, explain
the steps to the user instead of claiming you did them.

Run each command yourself, except where a step says to stop and ask.

## Steps

1. **Identify yourself.** Tell the user which tool you are running in and which
   model you are.
2. **Check prerequisites.** Run `git --version` and `python --version`. Python
   must be 3.9 or newer. If `python` is not found, try `python3`, and on Windows
   `py`. Use whichever works for every command below. If git or Python is
   missing, tell the user how to install it for their OS and stop:
   - Windows: `winget install Git.Git` and `winget install Python.Python.3.12`
   - macOS: `xcode-select --install` (git) and `brew install python`
   - Linux: your package manager, for example `sudo apt install git python3`
3. **Clone to a stable location.**
   - macOS or Linux: `git clone https://github.com/abyss-node/claude-starter ~/.claude-starter`
   - PowerShell: `git clone https://github.com/abyss-node/claude-starter "$HOME\.claude-starter"`

   If the folder exists, update it: `git -C ~/.claude-starter pull` (PowerShell:
   `git -C "$HOME\.claude-starter" pull`).

   On Windows, prefer the PowerShell commands. In Git Bash, a user name with an
   apostrophe can make `~` paths misresolve: Git Bash leaves `/c/Users/...`
   unconverted and Windows reads it as `C:\c\Users\...`. The installer warns
   when it is running from such a path; re-clone with the PowerShell command.
4. **Detect and pick the tool.**
   - Run `python ~/.claude-starter/scripts/install.py --detect` (PowerShell:
     `python "$HOME\.claude-starter\scripts\install.py" --detect`). It lists the
     supported tools it finds and changes nothing.
   - Pick `--tool` = your own tool: `claude`, `opencode`, `codex`, `cursor`,
     `copilot`, `antigravity`, `junie`, or `generic`. Use `auto` only if you are
     unsure; it refuses when several tools are present.
   - Do not pick a tier or a commit-guard repo yourself.
5. **Preview, ask, and stop.** This approval is required, not an optional
   clarification.
   - Run the install with `--dry-run`, for example
     `python ~/.claude-starter/scripts/install.py --tool opencode --tier starter --dry-run`
     (PowerShell:
     `python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier starter --dry-run`).
     Use `--tier full` in the command if the user picks full. Claude Code takes
     no `--tier`: leave it out; `/starter:setup` asks it later.
   - Show the user the plan. Ask which tier, and recommend `starter`:
     - `starter`: a short rules file and a few agents. Right for most people.
       (Claude Code also gets the commit guard as a plugin hook; other tools get
       it only through the question below.)
     - `full`: also rules for choosing a model and effort per task and for
       coordinating several agents. Worth it on a plan that runs many agents at once.
   - Ask whether to install the commit guard git hooks in a repo they use. If
     yes, add `--guard-repo <path>`.
   - Then END YOUR TURN and wait for the user's reply. Do not run another
     command, and do not use an async or optional question tool and carry on.
6. **Install for real, only after the user's yes.** Run the same command with
   `--yes` in place of `--dry-run`:
   `python ~/.claude-starter/scripts/install.py --tool opencode --tier starter --yes`
   (PowerShell:
   `python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier starter --yes`).
   The installer checks every target first and writes nothing if one fails, backs
   up each file it changes, merges JSON settings without replacing the user's
   values, and checks the result. It ends with the
   `=== For you (the person at the keyboard) ===` block (step 8); the commands
   that repeat the install later, for bash and for PowerShell, print just above
   it.
7. **If it exits non-zero, stop.** Do not improvise a manual install and do not
   hand-edit the tool's config. What the installer left depends on the exit code:
   - **Exit 1: the install failed.** The installer saved a redacted report and
     printed its path and an issue link (or said on stderr that it could not
     build one). Show both to the user, tell them to read the file first, and
     ask whether they want to send it. Nothing is sent unless they say yes. A
     cause you can name and fix without touching the tool's config (the `claude`
     command not on PATH, for example) is worth fixing, then re-run from step 5.
   - **Exit 3: it cannot write to the tool's global config.** A sandboxed
     session (for example the Codex app) gets this. Nothing was written and no
     report was saved, on purpose: nothing failed. The refusal is printed to
     stderr, after the plan on stdout. Show the user the whole refusal,
     including the commands it gives for their own terminal, and end your turn.
     Never install into the project folder instead, and never hand-copy files:
     either would reach only this project or session, never the global config.
   - **Exit 2: the command was wrong** (for example `--tool auto` found several
     tools). Nothing was written and no report was saved. Fix the command as the
     message on stderr says, then re-run from step 5.
8. **If it succeeds (exit 0),** relay the installer's final
   `=== For you (the person at the keyboard) ===` block to the user word for
   word, including anything it says is not installed or is left to the user. The
   restart and the new-chat check come from it.
9. **Never claim a step you did not run.** End by saying what the installer
   checked, using the table below, and what it did not.

## Local or small models

Some local models cannot run these steps. Tested: qwen2.5-coder 7B through
Ollama in OpenCode printed its tool calls as text instead of calling the tools,
so nothing ran. If that happens, the user runs the three installer commands from
Install in `README.md` (`--detect`, `--dry-run`, then `--yes`) themselves. The
installer does the same work either way.

## Tool notes

| Tool | `--tool` | What the installer checks | Extra |
|---|---|---|---|
| Claude Code | `claude` | Verified against the real tool: `claude plugin list` shows the plugin enabled | Uses the `claude plugin` CLI, so Claude Code must be installed. The user then runs `/starter:setup` inside it. |
| OpenCode | `opencode` | Verified: OpenCode itself loads the agents, skills and commands | Restart OpenCode afterwards. |
| Codex | `codex` | Rules verified with `codex execpolicy`; agents and skills structural only | The installer notes that read-only agents are by instruction only. |
| Cursor | `cursor` | Structural only | No global rules file. Add `--project <repo>` to write the rules to that repo's `AGENTS.md`, or paste them in Cursor Settings as the installer says. |
| Copilot | `copilot` | Structural only | The installer names a VS Code settings file whose entries you merge by hand. |
| Antigravity | `antigravity` | Structural only | Rules file has a size cap; the installer checks it. |
| Junie | `junie` | Structural only | |
| Anything else | `generic` | Not checked | Needs `--config-dir <dir>`. Then follow `PORTING.md`. |

Structural only means the files parse and carry the fields the tool's docs
require. The real tool has not loaded them. Say so to the user.

If your tool is not in the table, or you are a non-Claude model in an unlisted
tool, `PORTING.md` is the last resort. It requires you to prove the tool loads the
result.

## If this kit misbehaves later

If the commit guard flags something it should not, or an agent, skill or command
from this kit does something wrong, build a report:

```
python ~/.claude-starter/scripts/report.py --kind guard-false-positive --step "what was happening" --tool opencode --error-file error.txt
```

PowerShell:

```
python "$HOME\.claude-starter\scripts\report.py" --kind guard-false-positive --step "what was happening" --tool opencode --error-file error.txt
```

`--kind` is `install-failure`, `guard-false-positive` or `agent-misbehaved`;
`--error "text"` replaces `--error-file` for a short error. It saves a redacted
file and sends nothing. Show the user the file, then offer to file it: add
`--submit` (needs the `gh` CLI), or point them to
https://github.com/abyss-node/claude-starter/issues. Do not pass `--submit` or
`--yes` without the user's yes.

## Rules for you

- Back up any existing file before changing it and ask before overwriting. The
  installer does this for the files it writes.
- Map the model roles in `MODELS.md` to the models the user has, if the tool needs
  that.
- Finish with a table of what went where and what has no equivalent in the tool.
