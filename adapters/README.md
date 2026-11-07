# adapters (generated)

Do not edit files here. They are generated from `plugins/starter/` by
`python scripts/build_adapters.py`, and CI fails when they drift from a fresh build.
Install one with `python scripts/install.py --tool <tool> --tier <starter|full>`;
`python scripts/install.py --help` lists every flag. To have an AI agent do it for you,
give it the repo link and see `AGENTS.md` at the repo root. `generic` is the starting
point for a tool the installer does not support (`--config-dir` is required; see `PORTING.md`).

| Tool | Files |
|---|---|
| `antigravity` | 12 |
| `codex` | 12 |
| `copilot` | 12 |
| `cursor` | 12 |
| `generic` | 11 |
| `junie` | 12 |
| `opencode` | 12 |

codex, copilot, cursor, junie install their skills into the shared `~/.agents/skills`;
the build checks that they emit byte-identical files there.
