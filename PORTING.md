# Porting: using this on another tool or another model

This kit is built for Claude Code running Claude models. The ideas in it are not
tied to either. If you, the agent reading this, are a different tool (OpenCode,
Codex CLI, Cursor, Gemini CLI, Aider, or anything else) or a non-Claude model,
translate each piece into your own conventions before installing it. Do not copy
Claude-specific files into place unchanged and assume they work.

## Rules for the agent doing the translation

- **Identify yourself first.** Work out which tool you are running in and which
  model you are, and tell the user both before changing anything.
- **Confirm conventions from your own tool's current documentation**, not from
  memory and not from the examples below. Folder names, file names and
  frontmatter fields change between versions. If you cannot confirm one, say so
  and ask the user.
- **Keep the meaning, change the form.** A rule, check or prompt carries over word
  for word. Only paths, file names, frontmatter fields and tool names change.
- **Never drop a piece silently.** If your tool has no equivalent, tell the user
  what is lost and suggest the nearest substitute.
- **Same safety rules as `/starter:setup`.** Back up any file before changing it,
  never overwrite without asking, and show what you changed at the end.
- **Report the translation.** Finish with a table of each piece, where it went,
  what changed, and what has no equivalent.

## Piece by piece

| Piece | Source in this repo | Translate to |
|---|---|---|
| Rules | `plugins/starter/templates/CLAUDE.starter.md` or `CLAUDE.full.md` | Your tool's global instruction file. Many tools read `AGENTS.md`; some also read `CLAUDE.md`. Replace `/starter:*` command names and agent names with whatever you install them as. |
| Skills | `plugins/starter/skills/*/SKILL.md` | Your tool's skills folder, if it loads `SKILL.md` skills (a shared format several tools now use). If it does not, fold the checks into a rules file scoped to the matching work, or keep them as reference docs the rules point to. |
| Agents | `plugins/starter/agents/*.md` | Your tool's subagent format. Keep the prompt body unchanged. Translate the frontmatter: `tools` to your tool's permission fields, keeping the read-only agents read-only (that restriction is the point of `verifier` and `consultant`); `model` and `effort` per the model mapping below. With no subagent support, turn each one into a command or prompt the user runs in a fresh session. |
| Commands | `plugins/starter/commands/*.md` | Your tool's custom command or prompt format. `checkpoint` and `lanes` carry over. `setup` writes Claude Code settings, so rewrite it for your tool's config, or skip it and do its steps by hand. |
| Commit guard | `plugins/starter/hooks/commit-guard/` | Use the git-hook path, which works with any tool: from a clone of this repo, run `python plugins/starter/hooks/commit-guard/guard.py install <repo>`. It fires on every commit regardless of who makes it. Do not try to port `hooks.json`; it is Claude Code's hook protocol. |
| Settings | `plugins/starter/templates/settings.starter.json` | Your tool's permission config. Carry over only the read-only git allowlist, and turn off any automatic AI co-author line in commits, since the commit guard flags it. |
| Packaging | `.claude-plugin/` | Claude Code only. Install the pieces above directly. |

## Model mapping

The rules and agents name Claude tiers: `opus` > `sonnet` > `haiku`, plus an
`effort` level. On another model family, map by role, not by name:

- **Top tier** (`opus`): the most capable model available to the user. It plans,
  judges and verifies.
- **Middle tier** (`sonnet`): a solid general model for routine implementation.
- **Bottom tier** (`haiku`): the cheapest model that follows instructions
  reliably, for lookups and boilerplate.
- **Effort**: map to the model's reasoning-effort or thinking setting where it
  has one. Drop it where it has none.

Ask the user which models they can use and what each costs before choosing. If
only one model is available, the tier rules collapse to one rule: still never
let the agent that did the work verify it. Use a fresh session as the verifier.

The same mapping applies inside Claude Code when it runs a non-Claude model
through a compatible endpoint. The plugin installs as normal there, but agents
pinned to `model: opus` need their `model` field changed to a model that endpoint
serves.

## What to expect from a different model

- **Shorter rule files hold better.** Many models follow a long instruction file
  less reliably than Claude does. Prefer the starter rules, and lean on checks the
  machine enforces, like the commit guard as a git hook, over rules that rely on
  the model remembering.
- **Verification matters more, not less.** The less you know about a model, the
  less its "done" is worth. Re-running the tests is the one part of this kit that
  does not depend on the model at all.
