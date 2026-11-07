# claude-starter

## If you are an AI agent asked to set this up

Follow these steps in order. Run each command yourself. Full steps: `AGENTS.md`.

1. Tell the user which tool and which model you are.
2. Run `git --version` and `python --version` (3.9 or newer; also try `python3`, and `py` on Windows). If either is missing, tell the user how to install it for their OS, then stop.
3. Clone to a stable place: `git clone https://github.com/abyss-node/claude-starter ~/.claude-starter`. If it exists, run `git -C ~/.claude-starter pull`. On Windows, prefer PowerShell: `git clone https://github.com/abyss-node/claude-starter "$HOME\.claude-starter"`, or `git -C "$HOME\.claude-starter" pull` if it exists. In Git Bash, a user name with an apostrophe can make `~` paths misresolve (to `C:\c\Users\...`); the installer warns when that happened.
4. Run `python ~/.claude-starter/scripts/install.py --detect` (PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --detect`). Pick `--tool` from the table below: your own tool (use `auto` only if you are unsure). Ask the user: `starter` (recommended; short rules, a small setup) or `full` (adds rules for choosing models and coordinating many agents). Run `python ~/.claude-starter/scripts/install.py --tool <tool> --tier <starter|full> --dry-run` (PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool <tool> --tier <starter|full> --dry-run`), show the user the plan, and get a yes.
5. Run the same command with `--yes` instead of `--dry-run`: `python ~/.claude-starter/scripts/install.py --tool <tool> --tier <starter|full> --yes` (PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool <tool> --tier <starter|full> --yes`). Claude Code takes no `--tier`.
6. If it exits non-zero, do not improvise a manual install. Show the user the report path and issue link it printed, and ask if they want to send it. Nothing is sent unless they say yes.
7. If it succeeds, relay the notes it printed, tell the user to restart their tool, then walk them through `ONBOARDING.md`. For Claude Code, the user then runs `/starter:setup` inside it.
8. Never claim a step you did not run. Say what the installer checked (last column below).

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

The easy way: give your AI coding agent the link `https://github.com/abyss-node/claude-starter` and say "set this up for me". The agent follows the steps at the top of this page.

To do it yourself, you need `git` and Python 3.9 or newer.

macOS or Linux:

```
git clone https://github.com/abyss-node/claude-starter ~/.claude-starter
python3 ~/.claude-starter/scripts/install.py --detect
python3 ~/.claude-starter/scripts/install.py --tool opencode --tier starter --dry-run
python3 ~/.claude-starter/scripts/install.py --tool opencode --tier starter --yes
```

Windows PowerShell (use `py` if `python` is not found). On Windows, use these rather than Git Bash: when the user name contains an apostrophe, Git Bash can leave `~` paths unconverted, and Windows then reads them as `C:\c\Users\...`:

```
git clone https://github.com/abyss-node/claude-starter "$HOME\.claude-starter"
python "$HOME\.claude-starter\scripts\install.py" --detect
python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier starter --dry-run
python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier starter --yes
```

Swap `opencode` for your tool (see the table above). Choose `--tier starter` or `--tier full`; start with starter. `--dry-run` prints the plan and changes nothing. The installer backs up every file it changes, merges JSON settings without replacing your values, and checks the result afterwards. To update later: `git -C ~/.claude-starter pull` (PowerShell: `git -C "$HOME\.claude-starter" pull`), then run the install again; an install that is already current changes nothing. A successful install prints both commands for bash and for PowerShell, with every flag it used.

Optional: `--guard-repo <path>` also installs the commit guard as git hooks in that repo (repeat it for more repos).

### Local or small models

Some local models cannot run the setup. Tested: qwen2.5-coder 7B through Ollama in OpenCode printed its tool calls as text instead of calling the tools, so nothing ran. If yours does that, run the three installer commands above yourself (`--detect`, `--dry-run`, then `--yes`). The installer does the same work either way.

### Claude Code, by hand

Inside Claude Code you can skip the installer and run:

```
/plugin marketplace add abyss-node/claude-starter
/plugin install starter@claude-starter
/starter:setup
```

`/starter:setup` walks you through the rest. Read `ONBOARDING.md` first if you are new to Claude Code. The installer's `--tool claude` does the first two lines for you.

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

## Something broke?

If the installer fails, the commit guard flags something it should not, or an agent or skill from this kit does something wrong, build a report:

```
python ~/.claude-starter/scripts/report.py --kind install-failure --step "what you were doing" --tool opencode --error-file error.txt
```

PowerShell:

```
python "$HOME\.claude-starter\scripts\report.py" --kind install-failure --step "what you were doing" --tool opencode --error-file error.txt
```

`--kind` is `install-failure`, `guard-false-positive` or `agent-misbehaved`. Use `--error "text"` instead of `--error-file` for a short error. The report is redacted (secrets, personal data, your user name, host name and home path) and saved to a file in the current folder, or where `--out` says. Nothing is sent unless you choose: add `--submit` to file a public issue with the `gh` CLI after a confirmation, or open https://github.com/abyss-node/claude-starter/issues and paste the saved file. Redaction removes common secrets and personal details, but it cannot be complete: read the report before you send it. It becomes public if you post it, and the tool shows it to you first for that reason. A failed install already saves a report and prints a pre-filled issue link.

## More

- `ONBOARDING.md`: a first-hour walkthrough.
- `AGENTS.md`: the full steps for an agent setting this up.
- `plugins/starter/ADDONS.md`: optional add-ons and when each is worth installing.
- `MODELS.md`: the one place that names models, with a review date. Rules and agents describe roles, so a new model release means editing this file only.
- `PORTING.md`: the last resort for a tool the installer does not support.
- `adapters/`: the generated per-tool files the installer copies. Do not edit them; `python scripts/build_adapters.py` rebuilds them.
