# Porting: the last resort for tools the installer does not support

Try the installer first. `python ~/.claude-starter/scripts/install.py --detect`
lists the tools it supports: Claude Code, OpenCode, Codex, Cursor, Copilot,
Antigravity and Junie. For those, follow `AGENTS.md` and do not hand-translate.
Hand translation is slower and breaks things; a live test of it left a tool's
config broken while the agent reported success.

Use this file only if your tool is not on that list, or you are a non-Claude
model in a tool the kit has no adapter for (Gemini CLI, Aider, or anything else).
You, the agent reading this, translate the pieces yourself and then prove that
the tool loads them.

## Start from the generic adapter

Do not translate from `plugins/starter/` if you can avoid it. Start from the
generic adapter, which has already been rewritten into plain, tool-neutral files
(skills, agents, commands and a rules file):

```
python ~/.claude-starter/scripts/install.py --tool generic --tier starter --config-dir <dir> --dry-run
```

Pick `<dir>` as your tool's own config folder, or a scratch folder you then copy
from. Show the user the plan, get a yes, then run it with `--yes`. In PowerShell
write the script path as `"$HOME\.claude-starter\scripts\install.py"`. The
installer backs up what it changes and does not check your tool's format: that is
your job, below.

Then adjust only what your tool needs: paths, file names, frontmatter fields and
tool names. If the generic files do not fit at all, fall back to the table below.

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
- **Prove it loads. This step is mandatory.** After translating, show that your
  tool loads the config, and fix every error before you report. Use your tool's
  own list, validate or debug command (for example one that lists agents, skills
  or commands, or prints the resolved config), or start the tool
  non-interactively and read its output. Check that the read-only agents are
  still read-only as the tool sees them. A file that exists is not a file that
  loads.
- **If you cannot prove it, say so.** Report "installed but unverified" and name
  what you could not check. Do not write "done" or "installed successfully".
- **Report the translation.** Finish with a table of each piece, where it went,
  what changed, what has no equivalent, and for each piece whether it was proven
  loaded or is unverified.

## Piece by piece

Source paths are inside your clone of this repo. Generic-adapter equivalents are in
`adapters/generic/`.

| Piece | Source in this repo | Translate to |
|---|---|---|
| Rules | `plugins/starter/templates/CLAUDE.starter.md` or `CLAUDE.full.md` | Your tool's global instruction file. Many tools read `AGENTS.md`; some also read `CLAUDE.md`. Replace `/starter:*` command names and agent names with whatever you install them as. |
| Skills | `plugins/starter/skills/*/SKILL.md` | Your tool's skills folder, if it loads `SKILL.md` skills (a shared format several tools now use). If it does not, fold the checks into a rules file scoped to the matching work, or keep them as reference docs the rules point to. |
| Agents | `plugins/starter/agents/*.md` | Your tool's subagent format. Keep the prompt body unchanged. Translate the frontmatter: `tools` to your tool's permission fields, keeping the read-only agents read-only (that restriction is the point of `verifier` and `consultant`); `model` and `effort` per the model mapping below. With no subagent support, turn each one into a command or prompt the user runs in a fresh session. |
| Commands | `plugins/starter/commands/*.md` | Your tool's custom command or prompt format. `checkpoint` and `lanes` carry over. `setup` writes Claude Code settings, so rewrite it for your tool's config, or skip it and do its steps by hand. |
| Commit guard | `plugins/starter/hooks/commit-guard/` | Use the git-hook path, which works with any tool: `python ~/.claude-starter/scripts/install.py --tool generic --tier starter --config-dir <dir> --guard-repo <repo>` or, from a clone of this repo, `python plugins/starter/hooks/commit-guard/guard.py install <repo>`. It fires on every commit regardless of who makes it. Do not try to port `hooks.json`; it is Claude Code's hook protocol. |
| Settings | `plugins/starter/templates/settings.starter.json` | Your tool's permission config. Carry over only the read-only git allowlist, and turn off any automatic AI co-author line in commits, since the commit guard flags it. Merge into an existing config; never replace it. |
| Packaging | `.claude-plugin/` | Claude Code only. Install the pieces above directly. |

## Model mapping

The rules and agents name Claude tiers by alias (`opus`, `sonnet`, `haiku`) plus
an `effort` level. `MODELS.md` holds the current ranking and its review date; it
changes with model releases, so check it rather than trusting any copy. On
another model family, map by role, not by name, and record the result in the
same table:

- **Top tier** (`opus`): the most capable model available to the user. It plans,
  judges and verifies.
- **Middle tier** (`sonnet`): a solid general model for routine implementation,
  boilerplate and one-file scripts.
- **Bottom tier** (`haiku`): the cheapest model that follows instructions
  reliably, for lookups and formatting.
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

## If it goes wrong

If your translation breaks the tool or the config, restore from the backups you
made, then build a report with
`python ~/.claude-starter/scripts/report.py --kind agent-misbehaved --step "porting to <tool>" --tool <tool> --error-file <file>`.
It is redacted and sends nothing unless the user adds `--submit` and agrees.
