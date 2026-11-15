# core/

What is written once for every tool. `python scripts/build_adapters.py` renders
it into each tool's build: `adapters/<tool>/` and, for Claude Code,
`plugins/starter/commands/onboard.md` and the root `ONBOARDING.md`. Edit here,
never the generated copies; CI fails when a copy differs from a fresh build.

- `commands/<name>.md`: a command every tool ships. It must be in
  `PORTED_COMMANDS` in the build, and its frontmatter must set
  `disable-model-invocation: true` (Claude Code's copy keeps the frontmatter as
  written). Its text names no tool. `{{tool_arg}}` renders as ` --tool <id>`
  in a tool whose copy is its own and as nothing in the copy shared in
  `~/.agents/skills`, which `{{tool_choice}}` tells to add the `--tool` the
  user typed; so the shared copies stay byte-identical, and every other copy
  asks the launcher for its own tool's walkthrough. Which copies are shared is
  `shared_commands` in `scripts/vocab.py`; the build checks it.
- `onboarding/`: the walkthrough, one `NN-name.md` file per step, each starting
  with a `# Title` line. `common/` holds the steps every tool shares. Every
  other step has a `default/` version that names no tool, and
  `onboarding/<tool>/` may replace it. `claude/` and `opencode/` replace every
  one; the build fails if either lacks a step.
- `plans.json`: the plans each tool's walkthrough offers, rendered where a step
  says `{{plans}}`. A meter command that is not confirmed renders as one that
  may work.
- `terms.json`: which tools own which words. A word in a tool's build that the
  tool does not own fails the build. `{{commands}}` in a pattern stands for any
  ported command's name. `terms.baseline` lists the leaks that predate the
  check; it may only shrink.

Tokens, in onboarding steps: `{{rules_file}}`, `{{tool}}` (the installer's
`--tool` id), `{{cmd:<command>}}` and `{{plans}}`. Each tool's words are in
`scripts/vocab.py`. An unknown token stops the build. `{{rules_file}}` must end
a clause (be followed by `.`, `;`, `:` or `)`), because a tool's rules file
can be a long phrase. No step may hold a `## Step N of M:` line, even in a code
block: the launcher splits the walkthrough on it.
