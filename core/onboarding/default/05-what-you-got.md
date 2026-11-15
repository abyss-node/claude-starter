# What you got

The kit's rules are in {{rules_file}}. The installer added the agents,
commands and skills below, and backed up every file it changed.

| Piece | Use it for |
|---|---|
| {{cmd:checkpoint}} | After a change: runs the relevant checks, says what ran and what did not, proposes a commit message, waits for your yes |
| `verifier` agent | Re-runs build and tests on work reported as done, without editing anything |
| `code-reviewer` agent | Reviews a diff for the ways this project breaks (money, auth, time, data), not style |
| `consultant` agent | Answers a question about another part of the codebase so your session does not have to read it all |
| {{cmd:lanes}} | Splits a repo with several stacks (say, a frontend and a backend) into lanes |
| {{cmd:starter-update}} | Updates the kit: shows the plan, applies nothing until you say yes |
| Guardrail skills | Checks while writing endpoints, UI, data jobs and code that calls a model |
| Commit guard | In repos you gave the installer with `--guard-repo`: checks commits for secrets, personal data and a `Verified:` or `Unverified:` line |

The agents are read-only by instruction; where your tool can enforce it, the
installer set that too, and its closing message said which. To add the commit
guard to a repo, run the installer again with `--guard-repo`, using the tier
you installed and any `--config-dir` or `--project` you used; `--dry-run`
changes nothing:
- bash: `python ~/.claude-starter/scripts/install.py --tool {{tool}} --tier starter --guard-repo <your-repo> --dry-run`
- PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool {{tool}} --tier starter --guard-repo <your-repo> --dry-run`
