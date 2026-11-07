---
description: Install the starter CLAUDE.md, merge read-only settings, and choose the commit guard mode. Backs up before any change; asks before replacing anything; safe to re-run.
allowed-tools: Read, Glob, Grep, AskUserQuestion
---

Set up this user's global Claude Code configuration from the `starter` plugin.
Only reads are pre-approved; every write goes through a normal permission prompt
so the user sees it. Work through the steps in order and stop if one fails.

## Ground rules for this command

- **Never replace a file the user already has without asking.** Show what would
  change and let them choose merge, replace or skip. Their existing configuration
  was written for reasons you cannot see.
- **Back up before any change** to an existing file: copy it with a shell command
  (`cp` or `Copy-Item`, paths quoted) to `<name>.bak-<YYYY-MM-DD>` in the same
  folder. If that name is taken, add `-<HHMM>`. Then confirm the copy is
  identical (equal byte size, or equal hash) before editing the original. Never
  make a backup by reading the file and writing it back out: that can silently
  alter encoding, line endings or a trailing newline. The shell commands are
  deliberately not in `allowed-tools`, so the user approves each copy.
- **Idempotent.** Each step first checks whether its piece is already in place,
  and if so reports "already set up" for it and moves on.
- **Paths.** Define once: `CONFIG_DIR` = `$CLAUDE_CONFIG_DIR` if that variable is
  set, else `~/.claude` (on Windows, `%USERPROFILE%\.claude`). Use `CONFIG_DIR`
  for every path below; without it a user with a relocated config gets files
  written to the wrong place. Home paths can contain spaces or apostrophes, so
  always quote them in shell commands.

## 0. Locate the plugin's files

The templates are in `${CLAUDE_PLUGIN_ROOT}/templates/`. Claude Code substitutes
that path into this text when the command loads; the variable is not set in the
Bash tool's environment, so use the substituted path as written here, not
`$CLAUDE_PLUGIN_ROOT` in a shell command.

If the path above still reads literally `${CLAUDE_PLUGIN_ROOT}`, or the folder
does not exist, find it instead: glob for `**/templates/CLAUDE.starter.md` under
`CONFIG_DIR/plugins/cache/` and take the newest match's `templates/` folder. If
nothing is found, stop and tell the user to reinstall the plugin.

You need three files from there: `CLAUDE.starter.md`, `CLAUDE.full.md`,
`settings.starter.json`. The commit guard's documentation is at
`hooks/commit-guard/README.md` under the same plugin root.

## 1. Explain, in three lines

Tell the user, in about these words:

1. This installs a global `CLAUDE.md` (standing rules Claude reads in every
   project) and merges a few safe settings into `settings.json`.
2. Nothing you already have is overwritten; every changed file is backed up first.
3. It also sets the commit guard, which checks commits for secrets and for a
   note of what was verified.

## 2. Choose the tier

Ask with AskUserQuestion, one question, two options:

- **Starter (recommended)**: about 80 lines of rules that cost no extra usage.
  Good on any plan, and the right choice if you are new to Claude Code.
- **Full**: adds rules for running several agents at once and choosing a model
  and effort per task. Spends usage fast on Pro; best on Max or Team.

## 3. Install `CLAUDE.md`

Read the chosen template and `CONFIG_DIR/CLAUDE.md`.

- **No existing file**: write the template there. Report "installed".
- **Existing file already contains every `## ` heading of the chosen template**:
  report "already set up" and change nothing.
- **Existing file was installed from the other tier** (its first lines contain
  "Starter version" or "Full version"): the user may have added sections of their
  own since. Compare it line by line with both templates and collect the sections
  and lines that are in neither. Show them, then ask with AskUserQuestion (back up
  first in every case):
  - **Replace and re-append (default)**: write the chosen tier, then append the
    user's added sections at the end under a line
    `<!-- Kept from your previous CLAUDE.md on <date> -->`.
  - **Replace outright**: write the chosen tier and drop their additions (they
    remain in the backup).
  - **Skip**: change nothing.
  If nothing of theirs is in neither template, say so and ask only replace or skip.
- **Any other existing file**: list the template's `## ` sections that are missing
  from it, show their headings and line counts, and ask with AskUserQuestion:
  - **Merge**: back up, then append only the missing sections at the end, under a
    line `<!-- Added by /starter:setup on <date> -->`. Never edit or reorder the
    user's own sections. If one of their sections contradicts a template rule,
    point it out and leave theirs in place.
  - **Skip**: change nothing.

## 4. Merge settings

Read `settings.starter.json` and `CONFIG_DIR/settings.json`.

- **No existing file**: write `settings.starter.json` there as is.
- **Existing file is not valid JSON**: stop this step, change nothing, and tell
  the user which line fails to parse.
- **Otherwise** work out the merge and show it before writing:
  - `permissions.allow`: the union of both lists. Never remove or reorder an
    existing entry; append the missing ones. The starter list is read-only git
    and `ruff format --check` only. Test and lint runners (`pytest`, `npm test`,
    `ruff check`, `mypy`) are left out on purpose: they execute code the repo
    controls (package scripts, conftest, plugins), and `ruff check` rewrites files
    when the config sets `fix = true`. The user can approve them per repo in that
    repo's `.claude/settings.json` once they trust it.
  - Every other key (`$schema`, `autoCompactEnabled`, `attribution`): add it only
    if the user's file lacks it. If the user already sets it to something else,
    keep their value and list it as "kept yours".
  - Never touch `hooks`, `model`, `permissions.deny`, `permissions.ask`,
    `permissions.defaultMode`, `env` or `enabledPlugins`.
  - If nothing would change, report "already set up".

  Say in one line why `attribution` is there: it stops Claude Code adding its own
  co-author line to commits, which the commit guard would otherwise flag on every
  commit. If the user's team requires AI disclosure in commits, they should say
  so and you leave `attribution` out.

  If the user already has a non-empty `attribution.commit` or
  `includeCoAuthoredBy: true`, keep their value and warn in one line: the commit
  guard will flag `ai-coauthor` on every Claude commit (and block in block mode);
  the guard README's per-repo allowlist is the way to accept that.

  Ask to apply. On yes: back up, write the merged file as strict JSON (no
  comments, no trailing commas, two-space indent), then check it twice. First,
  parse it again to confirm it is valid. Second, compare it with the original
  structurally: every key and value in the original must still be present and
  unchanged, and the only differences must be the additions you showed. If either
  check fails, restore the backup (shell copy, then confirm identical) and report
  the failure.

## 5. Commit guard mode

Read `hooks/commit-guard/README.md` under the plugin root. It is the authority
for where the guard keeps its config (under `CONFIG_DIR/commit-guard/`) and what
the mode values are; follow it rather than this text if they differ.

Report the current mode (warn by default), then ask with AskUserQuestion:

- **Keep warn (recommended to start)**: the guard prints what it found and lets
  the commit through. Good while you learn what it flags.
- **Switch to block**: a finding stops the commit until it is fixed.

If the chosen mode is already set, report "already set up". Otherwise back up the
config file if it exists, write the change exactly as the README describes, and
read it back. If the README is missing or does not say how to change the mode,
skip this step and say so rather than guessing a file format.

## 6. Report

Print three short lists:

- **Changed**: each file written, with its backup path.
- **Already set up**: pieces that needed nothing.
- **Skipped**: pieces the user declined or that failed, with the reason.

Then say which of the above you checked by reading the file back and which you
only assumed. End with exactly this line:

`try: /starter:checkpoint after your next change`
