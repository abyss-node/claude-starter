# claude-starter

A Claude Code plugin that packages one person's working setup so a beginner can
start from something that has already been debugged. It is opinionated: it
assumes you want claims of "done" checked, commits that say what was verified,
and a small configuration.

## Install

```
/plugin marketplace add abyss-node/claude-starter
/plugin install starter@claude-starter
/starter:setup
```

`/starter:setup` walks you through the rest. Read `ONBOARDING.md` first if you
are new to Claude Code.

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

## More

- `ONBOARDING.md`: a first-hour walkthrough.
- `plugins/starter/ADDONS.md`: optional add-ons and when each is worth installing.
- `PORTING.md`: using this kit on another tool (OpenCode, Codex and others) or a non-Claude model. An agent that isn't Claude Code follows it to translate each piece.
