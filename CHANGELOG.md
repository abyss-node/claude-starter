# Changelog

Notable changes to claude-starter, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). The version lives in `kit.json`;
`plugin.json` and `marketplace.json` must match it, and a test checks that.

Every migration a release ships is listed under it by ID, so `starter-update`
can show what each one does before it runs.

## [0.4.0] - unreleased

### Added

- `starter-update`: one command, in every supported tool, that updates the kit.
  It is `/starter:starter-update` in Claude Code, `/starter-update` in OpenCode, and a
  `starter-update` skill in Codex, Cursor, Copilot and Antigravity. It reads
  the install record, prints a plan from the newest release, stops, and applies
  only after a yes, pinned to that release (`--to <sha>`) and that plan
  (`--plan <id>`). The plan id proves a plan was printed, not that anyone read
  it.
- An install record at `~/.agents/starter/installs.json` and a launcher,
  `scripts/starter.py` (`status`, `update`, `notices on|off`).
- `install.py --update`, `--plan-update --kit-root`, `--to`, `--plan`,
  `--offline` and `--no-guard`.
- An opt-in update notice (`scripts/update_check.py`): at most one line a day
  when a newer release is out; silent offline; it never updates anything.
  Claude Code runs it at session start; `checkpoint` and `lanes` run it first
  in every other tool.
- `kit.json`, the one home of the kit's name and version.
- The adapter build refuses a ported command named like a tool's built-in
  command (OpenCode's `/update` updates OpenCode itself).
- CI: an install made by v0.3.1's installer is updated by the current one, and
  a second update writes nothing.
- Codex: the `checkpoint`, `lanes` and `starter-update` skills each ship an
  `agents/openai.yaml` with `policy.allow_implicit_invocation: false`, so Codex
  does not start them on its own; the installer checks its shape.

### Changed

- Updating is `starter-update`, not `git pull` and a re-run of the installer.
- `--yes` needs an answer about the commit guard: `--guard-repo <path>` or
  `--no-guard`. With neither the install exits 2 and writes nothing.
- `--yes` without `--plan <id>` exits 2 when the plan holds a migration, a move,
  a delete or a git step. A plain reinstall still works with `--yes`.
- A re-run with the same `--guard-repo` leaves the repo's hooks alone when they
  and the guard copy they call are current.
- `--dry-run` wins over `--yes` for `--update` too: it only plans.

### Fixed (from the Codex field report)

- An agent could install without asking which tier. The dry run now ends with
  a stop line telling the agent to show the plan, ask, and end its turn.
- A sandboxed session could install into one chat's environment. Every
  destination is probed first; if one is not writable the installer writes
  nothing and exits 3. It never falls back to a project-local install.
- Every successful install ends with a "For you (the person at the keyboard)"
  block: restart, how to check the rules loaded, and whether the commit guard
  is installed.
- Codex warns when a non-empty `AGENTS.override.md` would hide the rules.
- Non-Claude builds no longer claim the commit guard checks commits unless it
  was installed with `--guard-repo`; a lint rejects the unconditional claim.
- The full tier gains the confirm-before-outward-facing rules; a test lists the
  rule headings both tiers must carry.
- `report.py` asks before submitting an issue.
- The full rules raise the model and effort ladder one rung and pace usage
  across the week.

### Migrations

None.
