# adapters (generated)

Do not edit files here. They are generated from `core/` and `plugins/starter/` by
`python scripts/build_adapters.py`, and CI fails when they drift from a fresh build.
Install one with `python scripts/install.py --tool <tool> --tier <starter|full>`;
`python scripts/install.py --help` lists every flag. To have an AI agent do it for you,
give it the repo link and see `AGENTS.md` at the repo root. `generic` is the starting
point for a tool the installer does not support (`--config-dir` is required; see `PORTING.md`).
Each tool's `ONBOARDING.md` is its onboarding walkthrough; the installer does not copy it, and
the `onboard` command prints it one step at a time from here.

| Tool | Files |
|---|---|
| `antigravity` | 15 |
| `codex` | 19 |
| `copilot` | 15 |
| `cursor` | 15 |
| `generic` | 14 |
| `junie` | 15 |
| `opencode` | 15 |

codex, copilot, cursor, junie install their skills into the shared `~/.agents/skills`;
the build checks that they emit byte-identical files there.
