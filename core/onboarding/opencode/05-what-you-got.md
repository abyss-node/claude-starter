# What you got

The installer wrote the kit's rules into `~/.config/opencode/AGENTS.md`, inside
a block marked `BEGIN claude-starter rules`, and added the agents, commands and
skills below. It backed up every file it changed.

| Piece | Use it for |
|---|---|
| `/checkpoint` | After a change: runs the relevant checks, says what ran and what did not, proposes a commit message, waits for your yes |
| `verifier` agent | Re-runs build and tests on work reported as done, without editing anything |
| `code-reviewer` agent | Reviews a diff for the ways this project breaks (money, auth, time, data), not style |
| `consultant` agent | Answers a question about another part of the codebase so your session does not have to read it all |
| `/lanes` | Splits a repo with several stacks (say, a frontend and a backend) into lanes |
| `/starter-update` | Updates the kit: shows the plan, applies nothing until you say yes |
| Guardrail skills | Checks while writing endpoints, UI, data jobs and code that calls a model |
| Commit guard | In the project folders you gave the installer with `--guard-repo`: checks commits for secrets, personal data and a `Verified:` or `Unverified:` line |

To check it all loaded, run `opencode agent list` in a terminal and look for
the three agents. To add the commit guard to a project, run the installer
again with `--guard-repo` and the project's folder (use the tier you
installed). A folder that is not a git repo yet is made one with `git init`;
`--dry-run` changes nothing:
- bash: `python ~/.claude-starter/scripts/install.py --tool opencode --tier starter --guard-repo <project-folder> --dry-run`
- PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier starter --guard-repo <project-folder> --dry-run`
