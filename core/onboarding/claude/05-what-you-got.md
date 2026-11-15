# What you got

`/starter:setup` installed a `CLAUDE.md`, merged a short list of read-only git
and format-check commands into your settings, and set how strict the commit
guard is. It never overwrites a file you already have, and it is safe to run
again. Test and lint runners are deliberately not pre-approved: they run code
the repo controls, and some rewrite files. Once you trust a repo, approve them
in that repo's `.claude/settings.json`.

| Piece | Use it for |
|---|---|
| `/starter:checkpoint` | After a change: runs the relevant checks, says what ran and what did not, proposes a commit message, waits for your yes |
| `verifier` agent | Re-runs build and tests on work reported as done, without editing anything |
| `code-reviewer` agent | Reviews a diff for the ways this project breaks (money, auth, time, data), not style |
| `consultant` agent | Answers a question about another part of the codebase so your session does not have to read it all |
| `/starter:lanes` | Splits a repo with several stacks (say, a frontend and a backend) into lanes |
| `/starter:starter-update` | Updates the kit: shows the plan, applies nothing until you say yes |
| Commit guard | Checks commits for secrets, personal data and a `Verified:` or `Unverified:` line |

The plugin's hook runs the commit guard on Claude's own commits. Agents from
the plugin may show up as `starter:verifier` and so on in `/plugin` (installed
plugin details). You call one by asking, for example "use the verifier agent to
check this".
