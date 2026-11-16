# Changelog

Notable changes to claude-starter, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). The version lives in `kit.json`;
`plugin.json` and `marketplace.json` must match it, and a test checks that.

Every migration a release ships is listed under it by ID, so `starter-update`
can show what each one does before it runs.

## [0.6.0] - unreleased

### Added

- Demos (`demos/`): small projects your agent builds in a new folder from a
  brief, graded by held-out checks kept in the kit, for trying the whole chain
  (plan, build, test, verifier, checkpoint, guarded commit) without a repo of
  your own. Two ship: Roulette Loom (rolling-circle curves drawn by an animated
  pen, in the browser) and Break the verifier (an app reported finished whose
  own tests pass, so the verifier has to find out it is not). The launcher
  gains `demo pick`, `demo start <name>` and `demo check <name>`.
  - `demo start` makes `~/agent-demos/<name>` (or `--dir`): the skeleton, the
    brief, the tool's repo rules file, a `package.json` whose `test` runs the
    held-out check, a git repo with one commit, and the commit guard's git
    hooks. What it writes names the demo by its id and its app (`fair-share`,
    Fair Share), never by a title that says what the demo tests. It refuses
    before writing anything: a folder that is not empty, a path the `test`
    script cannot quote, or a tool with no install recorded exits 2, a folder
    or `.git/hooks` it cannot write exits 3 with the command for your own
    terminal, and with no Node 22.13 or newer it prints this OS's install
    command and stops. It never runs a package manager. Outward steps (a private
    GitHub repo, a push) are printed, each for its own yes, and so is the
    `demo check` line you grade it with yourself, since the agent can change
    what `npm test` runs.
  - `demo check` grades a copy of the workspace's plain files: the kit's
    `demos/<name>/accept/`, then four rules: one test entry point (`test` must
    name this kit's own files), no binary assets (base64 wrapped across lines
    included), original names (`demos/denylist.txt`) and no verbatim copy of
    the reference solution (a paraphrase passes). The workspace's code runs in
    Node processes of its own, never in the one that asserts, under Node's
    permission model, so it can read only that copy: a module that re-exports
    the kit's reference fails to load. Node and git are started by full path,
    never from the workspace. It prints `PASS k/n` or `FAIL k/n`, a
    `NOT CHECKED:` line, a line saying that a local grade is feedback, not
    proof, and a `RECORD:` line in the shape of a `Verified:` trailer with the
    kit's commit and the hash of the files that grade the demo. It refuses to
    grade while those files differ from the clone's last commit, and it hashes
    them in a temporary object store, so it writes nothing to the clone.
  - `demo pick` asks how many dollars you want to spend, then says what a demo
    really costs on your plan (`core/plans.json`), with numbers only from runs
    measured on that tool and plan (`demos/costs.json`, empty in this release).
    Unmeasured, it says "not measured yet" and suggests a small demo.
    `demos/MEASURING.md` says how a run is measured. A run is admitted to
    `costs.json` only after CI re-grades its committed workspace (a git bundle
    in `demos/runs/`) with a clean copy of the kit at the run's commit, since
    anything with a shell on the measuring machine could have changed the
    local grade.
- Onboarding gains step 6 of 8, "Try it on a demo", and its welcome now offers
  practice on your own repo, or on a demo if you have none or want to test the
  install first.
- CI runs the demos' tests on the newest Node 22, on Ubuntu and Windows: each
  reference solution passes its checks, each skeleton fails them, and a planted
  off-by-one in a reference fails them.

### Changed

- `MODELS.md` is the only file that recommends models; `demos/costs.json`
  names the model each measured run used.
- `scripts/vocab.py` gains each tool's repo rules file and the command that
  opens a session in a folder, and `install.py`'s stop line and write refusal
  take their wording from the caller, so the demo scripts end the same way the
  installer does.

## [0.5.1] - 2026-11-15

### Fixed

- `install.py --tool opencode` failed on OpenCode 2 (`@opencode/cli` 2.x)
  after writing every file: its load check ran `opencode agent list`, which
  2.x removed, and exited 1 with "load check FAILED". The check now reads
  the version from `opencode --version` and asks each major its own way. 1.x
  is checked as before. 2.x is asked through `opencode api` (`agent.list`,
  `skill.list`, `command.list`) against a private `opencode serve` the check
  starts on a loopback port with a fresh password and stops afterwards, so it
  never reads a background service that started with another config. It
  re-reads each list until two answers agree, because a 2.x server's first
  answers come before discovery finishes. It matches each skill by the file
  this install wrote as well as by name: 2.x also loads `~/.claude/skills`,
  one skill per name, so a same-named skill there could stand in for a
  missing kit skill. Project config is off for the check, so a `.opencode` or
  `.claude` folder above its working directory does not count. A major other
  than 1 or 2 fails the check and names the version. Every opencode call has
  a timeout, and a process left behind cannot stall one.
- The check's summary line names the OpenCode version:
  `passed (loaded by opencode) version 2.3.0`.
- The closing block's self-check named `opencode agent list` only. It now
  gives `opencode debug agents` for 2.x as well.

## [0.5.0] - 2026-11-15

### Added

- `onboard`: an onboarding walkthrough for every tool, one step per run. It is
  `/starter:onboard` in Claude Code, `$onboard` in Codex, `/onboard` in OpenCode,
  Cursor, Copilot, Antigravity and Junie, and `commands/onboard.md` elsewhere.
  It runs `starter.py onboard <n>`, which prints step `<n>` of that tool's own
  walkthrough and ends with the command for the next step. Each tool's copy
  passes its own `--tool`, except the copy Codex, Cursor and Copilot share in
  `~/.agents/skills`: that one takes the tool from the install record, and
  with several installed it lists each one's command and stops for
  `--tool <id>`. Claude Code's copy sets `disable-model-invocation: true`, and
  Codex's ships `agents/openai.yaml` with `allow_implicit_invocation: false`.
  Showing the last step sets the record's `onboarded_at`. The installer's
  closing block names the command for Claude Code, OpenCode and Codex.
- `core/`, the one source for what is written once for every tool: the
  `onboard` command, the walkthrough (`core/onboarding/`: steps shared by every
  tool, plus each tool's own; Claude Code and OpenCode have their own version of
  every tool-specific step) and the plans each tool's walkthrough offers
  (`core/plans.json`). The build renders them per tool, and renders
  `plugins/starter/commands/onboard.md` and the root `ONBOARDING.md` for Claude
  Code; it never deletes a hand-written plugin file.
- A two-way term check (`core/terms.json`) in every build, `--check` included:
  a word that belongs to some tools fails the build when it shows up in another
  tool's output. It covers each tool's name, CLI and config folder, Claude model
  names, `ChatGPT`, `AGENTS.md`, and every form of a kit command (`/starter:x`,
  `/x`, `$x` and the prompt file). Leaks that predate it are listed in
  `core/terms.baseline`, which may only shrink.

### Changed

- `ONBOARDING.md` is generated, with a neutral title, and is Claude Code's copy
  of the walkthrough; it links every other tool's copy.
- The adapter build's one-way deny list is gone: its vocabulary rows moved to
  `core/terms.json`, and its frontmatter and commit-guard checks stay as lints.

### Fixed (from the Codex field report)

- A Codex user's onboarding asked which Claude plan they had. Each tool's
  walkthrough now offers only its own plans: Pro, Max, Ultra, Team or
  Enterprise, or an API key in Claude Code; a ChatGPT plan or an API key in
  Codex; connected providers in OpenCode.

## [0.4.0] - 2026-11-15

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
