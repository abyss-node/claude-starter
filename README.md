# claude-starter

## If you are an AI agent asked to set this up

Follow these steps in order. Run each command yourself, except where a step says to stop and ask. Full steps: `AGENTS.md`.

1. Tell the user which tool and which model you are.
2. Run `git --version` and `python --version` (3.9 or newer; also try `python3`, and `py` on Windows). If either is missing, tell the user how to install it for their OS, then stop.
3. Clone to a stable place: `git clone https://github.com/abyss-node/claude-starter ~/.claude-starter`. If it exists, the kit is already installed: follow Updating in `AGENTS.md` instead. Pull it only when `~/.claude-starter/scripts/starter.py` is missing (a clone from v0.3.x or earlier), as Updating says. On Windows, prefer PowerShell: `git clone https://github.com/abyss-node/claude-starter "$HOME\.claude-starter"`. In Git Bash, a user name with an apostrophe can make `~` paths misresolve (to `C:\c\Users\...`); the installer warns when that happened.
4. Run `python ~/.claude-starter/scripts/install.py --detect` (PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --detect`). Pick `--tool` from the table below: your own tool (use `auto` only if you are unsure). Do not pick a tier yourself.
5. STOP AND ASK. Run `python ~/.claude-starter/scripts/install.py --tool <tool> --tier starter --dry-run` (PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool <tool> --tier starter --dry-run`; use `--tier full` in the command if the user picks full; Claude Code takes no `--tier`, so leave it out) and show the user the plan. Ask: `starter` (recommended; short rules, a small setup) or `full` (adds rules for choosing models and coordinating many agents), and which project folder they work in, for the commit guard (`--guard-repo <folder>`, or `--no-guard` for none). Do not ask them for a repo: a folder that is not a git repo yet is made one by the installer (`git init`, in the `--yes` run after their yes), a folder inside a repo means that repo, and with no folder yet, suggest `~/projects/<name>`, which the installer creates. Then END YOUR TURN and wait for the user's reply. Do not run anything else, and do not use an async or optional question tool and carry on. This approval is required, not an optional clarification.
6. Only after the user has answered, run the same command with `--yes` instead of `--dry-run`, plus their commit guard answer: `python ~/.claude-starter/scripts/install.py --tool <tool> --tier <starter|full> --yes --no-guard` (PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool <tool> --tier <starter|full> --yes --no-guard`). If they named a project folder for the guard, put `--guard-repo <folder>` in place of `--no-guard`; `--yes` with neither exits 2. Claude Code takes no `--tier`.
7. If it exits non-zero, stop and do not improvise a manual install. What it left depends on the exit code:
   - Exit 1, the install failed: it saved a redacted report and printed the path and an issue link (or said on stderr that it could not build one). Show the user both and ask if they want to send it. Nothing is sent unless they say yes.
   - Exit 3, it cannot write to the tool's global config (a sandboxed session, for example the Codex app): nothing was written and no report was saved. The refusal is on stderr, after the plan on stdout. Show the user the whole refusal, including the commands it gives for their own terminal, and end your turn. Never install into the project folder instead, and never hand-copy files.
   - Exit 2, the command was wrong (for example `--tool auto` found several tools, or `--guard-repo` named the home folder, a drive root or the kit's clone): nothing was written and no report was saved. Fix the command as the stderr message says, asking the user again where it needs their answer, then go back to step 5.
8. If it succeeds (exit 0), relay the installer's final "=== For you (the person at the keyboard) ===" block to the user word for word. The restart and the new-chat check come from it.
9. Never claim a step you did not run. Say what the installer checked (last column below).

| Tool | `--tool` | What the installer checks |
|---|---|---|
| Claude Code | `claude` | Verified against the real tool (`claude plugin list`). Uses the `claude plugin` CLI. |
| OpenCode | `opencode` | Verified: OpenCode itself loads the agents, skills and commands. |
| Codex | `codex` | Rules verified with `codex execpolicy`; agents and skills checked structurally only. |
| Cursor | `cursor` | Structural only. Add `--project <repo>` to write rules (no global rules file). |
| Copilot | `copilot` | Structural only. |
| Antigravity | `antigravity` | Structural only. |
| Junie | `junie` | Structural only. |
| Anything else | `generic` | Not checked. Needs `--config-dir <dir>`; then follow `PORTING.md`. |

Structural only means the files parse and carry the fields the tool's docs require. The real tool has not loaded them.

---

A starter kit for working with an AI coding agent. It packages one person's working setup so a beginner can start from something that has already been debugged. It is opinionated: it assumes you want claims of "done" checked, commits that say what was verified, and a small configuration. It is built as a Claude Code plugin and installs into other tools through generated adapters.

## Install

The easy way: give your AI coding agent the link `https://github.com/abyss-node/claude-starter` and say "Set this up for me. Ask me starter or full, show me the plan, and wait for my yes before installing anything." The agent follows the steps at the top of this page.

To do it yourself, you need `git` and Python 3.9 or newer.

macOS or Linux:

```
git clone https://github.com/abyss-node/claude-starter ~/.claude-starter
python3 ~/.claude-starter/scripts/install.py --detect
python3 ~/.claude-starter/scripts/install.py --tool opencode --tier starter --dry-run
python3 ~/.claude-starter/scripts/install.py --tool opencode --tier starter --yes --no-guard
```

Windows PowerShell (use `py` if `python` is not found). On Windows, use these rather than Git Bash: when the user name contains an apostrophe, Git Bash can leave `~` paths unconverted, and Windows then reads them as `C:\c\Users\...`:

```
git clone https://github.com/abyss-node/claude-starter "$HOME\.claude-starter"
python "$HOME\.claude-starter\scripts\install.py" --detect
python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier starter --dry-run
python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier starter --yes --no-guard
```

Swap `opencode` for your tool (see the table above). Choose `--tier starter` or `--tier full`; start with starter. `--dry-run` prints the plan and changes nothing. The installer backs up every file it changes, merges JSON settings without replacing your values, and checks the result afterwards. To update later, ask your agent to run `starter-update` (see Updating below); an install that is already current changes nothing. A successful install prints both commands for bash and for PowerShell, with every flag it used.

After installing, ask for the walkthrough: type `/starter:onboard` in Claude Code (after `/starter:setup`), `/onboard` in OpenCode, `$onboard` in Codex, `/onboard` in Cursor, Copilot, Antigravity and Junie, or run `commands/onboard.md` elsewhere. It shows your tool's own copy one step at a time, and each step ends with the command for the next. It needs the clone at `~/.claude-starter`.

The commit guard needs an answer with `--yes`: `--guard-repo <folder>` installs it as git hooks in that project (repeat it for more), and `--no-guard` installs it in none. With neither, the install exits 2 and writes nothing, so a question nobody asked never turns into a permanent no. You need no repo first: a folder that is not a git repo yet is made one with `git init` (local, no remote; deleting its `.git` folder undoes it), one that does not exist yet is created, and a folder inside a repo means that repo. The home folder and any folder that holds it, the Desktop, Documents and Downloads folders, the Windows folder, a drive root and the kit's own clone are refused, since a repo there would track everything under it (the kit's clone because the updater moves it).

### Updating

Ask your agent to run `starter-update`: `/starter:starter-update` in Claude Code, `/starter-update` in OpenCode, the `starter-update` skill in Codex, Cursor, Copilot and Antigravity, or `commands/starter-update.md` anywhere else. It replaces the old `git pull` and re-run. It runs `python ~/.claude-starter/scripts/starter.py update` (PowerShell: `python "$HOME\.claude-starter\scripts\starter.py" update`), which fetches the newest release and prints the plan: what changed, each migration, which files change and which edited files are backed up. It changes nothing. The agent shows you the plan and stops; after your yes it runs the apply command the plan printed, which is pinned to that release (`--to <sha>`) and to that plan (`--plan <id>`).

**Updating from v0.3.x or earlier.** Those clones have no `scripts/starter.py`, and those installs have no `starter-update` command. Pull the clone once: `git -C ~/.claude-starter pull --ff-only` (PowerShell: `git -C "$HOME\.claude-starter" pull --ff-only`). That changes only the clone, nothing in your tools. Then ask your agent to follow `~/.claude-starter/plugins/starter/commands/starter-update.md`. Those versions wrote no install record, so `status` reports none; the plan finds the install by its markers and lists it as `adopted`. The update installs the `starter-update` command, so every later update is just `starter-update`.

The plan id proves that a plan was printed, not that you read it. An agent can run the plan and the apply in one go; read the plan before you say yes.

**Update notice (opt-in).** `python ~/.claude-starter/scripts/starter.py notices on` (PowerShell: `python "$HOME\.claude-starter\scripts\starter.py" notices on`) turns on a one-line notice when a newer release is out; `notices off` turns it off. The installer's closing block asks you to choose. It checks the release tags at most once a day, gives up silently after 3 seconds offline, and never updates anything. Claude Code shows it at session start; other tools show it when you run `checkpoint` or `lanes`.

### Local or small models

Some local models cannot run the setup. Tested: qwen2.5-coder 7B through Ollama in OpenCode printed its tool calls as text instead of calling the tools, so nothing ran. If yours does that, run the three installer commands above yourself (`--detect`, `--dry-run`, then `--yes`). The installer does the same work either way.

### Claude Code, by hand

Inside Claude Code you can skip the installer and run:

```
/plugin marketplace add abyss-node/claude-starter
/plugin install starter@claude-starter
/starter:setup
```

`/starter:setup` walks you through the rest. If you are new to Claude Code, read `ONBOARDING.md`; `/starter:onboard` shows it one step at a time, but only from a clone. The installer's `--tool claude` does the first two lines for you.

### A tool the installer does not support

Use `--tool generic --config-dir <dir>` and then follow `PORTING.md`. That is the last resort: the installer cannot check that your tool loads the result, so you have to.

## What is inside

| Piece | What it does | Failure it exists for |
|---|---|---|
| `verifier` agent | Re-runs build and tests on work reported as done, read-only | A "done" claim from the agent that did the work is not evidence |
| `code-reviewer` agent | Reviews a diff against this project's failure modes, not style | Generic review finds nothing that matters and misses the money, auth and time bugs |
| `consultant` agent | Answers questions about another part of the codebase, read-only | Reading across an unfamiliar stack fills the context window |
| `/starter:checkpoint` | Runs relevant checks, reports what ran, proposes a commit message, waits | Commits made without knowing what was actually verified |
| `/starter:lanes` | Splits a multi-stack repo into lanes with nested rules | One session acting as a generalist across two stacks |
| Commit guard hook | Checks commits carry `Verified:` / `Unverified:` trailers | A chat summary of what was checked dies with the session |
| Templates | Starting `CLAUDE.md` and related files, installed by setup | Starting from an empty configuration |
| `backend-build-guardrails` skill | Checks while writing endpoints, queries, auth, jobs, caches, outbound calls | Code that works on the happy path but misses authorization, timeouts, idempotency or SSRF |
| `frontend-build-guardrails` skill | Checks while building interactive UI, forms, client fetching, Next.js server code | UI that breaks on real data, excludes keyboard and screen-reader users, or leaks secrets to the browser |
| `data-pipeline-guardrails` skill | Checks while writing jobs and scrapers that save data and may be re-run | Re-runs that duplicate rows, and scrapers that save a block page as data |
| `llm-app-guardrails` skill | Checks while writing code that calls a model API | Prompt injection, API keys in the browser, runaway cost, no evals |
| Demos (`demos/`) | Small projects your agent builds in a new folder, graded by held-out checks kept in the kit (`starter.py demo pick`, then `demo start <name>`) | Without a repo to hand nothing runs the whole chain, and a cost an agent cannot measure gets invented |

## Something broke?

If the installer fails, the commit guard flags something it should not, or an agent or skill from this kit does something wrong, build a report:

```
python ~/.claude-starter/scripts/report.py --kind install-failure --step "what you were doing" --tool opencode --error-file error.txt
```

PowerShell:

```
python "$HOME\.claude-starter\scripts\report.py" --kind install-failure --step "what you were doing" --tool opencode --error-file error.txt
```

`--kind` is `install-failure`, `guard-false-positive` or `agent-misbehaved`. Use `--error "text"` instead of `--error-file` for a short error. The report is redacted (secrets, personal data, your user name, host name and home path) and saved to a file in the current folder, or where `--out` says. Nothing is sent unless you choose: add `--submit` to file a public issue with the `gh` CLI after a confirmation, or open https://github.com/abyss-node/claude-starter/issues and paste the saved file. Redaction removes common secrets and personal details, but it cannot be complete: read the report before you send it. It becomes public if you post it, and the tool shows it to you first for that reason. A failed install (exit 1) already saves a report and prints a pre-filled issue link. An installer that refuses because it cannot write to the tool's config (exit 3) saves none, since nothing failed; it prints the commands to run in your own terminal instead.

## More

- `ONBOARDING.md`: the first-hour walkthrough for Claude Code. Every other tool's copy is `adapters/<tool>/ONBOARDING.md`; the `onboard` command prints yours one step at a time. All are generated from `core/onboarding/`.
- `AGENTS.md`: the full steps for an agent setting this up.
- `plugins/starter/ADDONS.md`: optional add-ons and when each is worth installing.
- `MODELS.md`: the one place that names models, with a review date. Rules and agents describe roles, so a new model release means editing this file only.
- `PORTING.md`: the last resort for a tool the installer does not support.
- `adapters/`: the generated per-tool files the installer copies. Do not edit them; `python scripts/build_adapters.py` rebuilds them.
