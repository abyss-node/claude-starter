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

   If the folder exists, the kit is already installed: follow Updating, below,
   instead. Do not pull, except the one time Updating describes for a clone
   that has no `scripts/starter.py`.

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
   - Do not pick a tier or a commit-guard folder yourself.
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
   - Ask which project folder they work in, for the commit guard's git hooks.
     If it is not a git repo yet, the installer makes it one (`git init`, in
     the `--yes` run of step 6); a folder inside a repo means that repo. If
     they have no folder yet, suggest `~/projects/<name>`, which the installer
     creates. Do not ask them for a repo, and do not run `git init` yourself
     first: the installer does it after their yes. Add `--guard-repo <folder>`
     with their answer, or `--no-guard` if they want none. An install with
     `--yes` and neither exits 2 and writes nothing, so never leave the
     question unasked.
     The installer refuses, with exit 2, the home folder and any folder that
     holds it, the Desktop, Documents and Downloads folders, the Windows folder,
     a drive root and the kit's clone.
   - Ask "Get a notice when a new kit version is out?" and recommend yes. This
     question is required too: without it the notice stays off and unchosen.
     When on, it prints one line, at most once a day, when a newer release is
     out, and it never updates anything. You record the answer in step 8; the
     installer takes no flag for it.
   - Then END YOUR TURN and wait for the user's reply. Do not run another
     command, and do not use an async or optional question tool and carry on.
6. **Install for real, only after the user's yes.** Run the same command with
   `--yes` in place of `--dry-run`, and `--guard-repo <folder>` in place of
   `--no-guard` if they named a project folder for the commit guard:
   `python ~/.claude-starter/scripts/install.py --tool opencode --tier starter --yes --no-guard`
   (PowerShell:
   `python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier starter --yes --no-guard`).
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
     tools, or `--guard-repo` named the home folder, a drive root or another
     folder it refuses). Nothing was written and no report was saved. Fix the
     command as the message on stderr says, asking the user again where it
     needs their answer, then re-run from step 5.
8. **If it succeeds (exit 0),** relay the installer's final
   `=== For you (the person at the keyboard) ===` block to the user word for
   word, including anything it says is not installed or is left to the user. The
   restart and the new-chat check come from it. Then record the user's
   update-notice answer from step 5 with the line the block's "Update notices"
   item gives for it: `python ~/.claude-starter/scripts/starter.py notices on`,
   or `notices off` for no (PowerShell:
   `python "$HOME\.claude-starter\scripts\starter.py" notices on`). Say which you
   ran. The item is not printed when an answer is already recorded.
9. **Never claim a step you did not run.** End by saying what the installer
   checked, using the table below, and what it did not.

## Updating

When the user asks to update this kit, run the `starter-update` command
(`/starter:starter-update` in Claude Code, `/starter-update` in OpenCode, the
`starter-update` skill elsewhere, or follow `plugins/starter/commands/starter-update.md`).
It replaces `git pull` and a re-run of the installer. In short:

0. **Once, for a clone from v0.3.x or earlier.** Those clones have no
   `scripts/starter.py` and no `starter-update` command. If
   `~/.claude-starter/scripts/starter.py` does not exist, pull the clone once:
   `git -C ~/.claude-starter pull --ff-only` (PowerShell:
   `git -C "$HOME\.claude-starter" pull --ff-only`). It changes the clone only,
   nothing in any tool's config. Then go on with step 1, following
   `~/.claude-starter/plugins/starter/commands/starter-update.md`: the install
   has no `starter-update` command until this update adds it.
1. `python ~/.claude-starter/scripts/starter.py status` (PowerShell:
   `python "$HOME\.claude-starter\scripts\starter.py" status`) reads the install
   record and uses no network.
2. `python ~/.claude-starter/scripts/starter.py update` (PowerShell:
   `python "$HOME\.claude-starter\scripts\starter.py" update`) fetches the newest
   release and prints the plan. It writes nothing. Exit codes mean what they
   mean for the installer (step 7 above). If `status` said no install is
   recorded, run this anyway: an install made before v0.4.0 has no record, and
   the plan lists it as `adopted` from its markers. Only if this step says
   "Nothing to update" is there nothing installed to update.
3. Show the user the whole plan, ask, and END YOUR TURN.
4. After their yes, run the apply command the plan printed, exactly as printed,
   with its `--to <sha>` and `--plan <id>`. If the plan asked about the commit
   guard, the answer is part of the plan: ask which project folder they work in
   (one that is not a git repo yet is made one), run step 2 again with
   `--guard-repo <folder>` or `--no-guard` added, as the user answered, show the
   new plan, and run the apply command it prints. If the plan changed since, it
   exits 2: show the new plan and ask again.

`--yes` without `--plan <id>` exits 2 when the plan holds a migration, a move,
a delete or a git step; a plain reinstall still works with `--yes`. The plan id
proves that a plan was printed, not that the user saw it. Only you can make sure
they did, so show it in full.

**Update notice.** It is off until the user chooses. Step 5 asks and step 8
records the answer; until one is recorded, the installer's closing block prints
the commands, `/starter:setup` asks, and `checkpoint` prints a one-line reminder
(an install made before v0.4.0 has no record, so it counts as unchosen).
`python ~/.claude-starter/scripts/starter.py notices on` turns it on and
`notices off` turns it off (PowerShell: `python "$HOME\.claude-starter\scripts\starter.py" notices on`).
When on, `update_check.py` prints at most one line a day when a newer release
is out, and never updates anything. Claude Code shows it at session start; the
`checkpoint` and `lanes` commands in other tools run it first. Relay the line;
do not start an update because of it.

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
