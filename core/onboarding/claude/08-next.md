# Where to go next

- **Add-ons:** `plugins/starter/ADDONS.md` in the kit lists optional plugins and
  skill packs, with when each is worth it and when to skip it. Add one when a
  task has gone badly twice, not in advance.
- **Graduate to full:** once you are on a larger plan and regularly run
  several agents at once, re-run `/starter:setup` and choose full. It adds rules for
  picking a model and effort level per task and for coordinating agents.
- **A repo with two stacks:** run `/starter:lanes` once in it.
- **Make the rules yours:** edit `~/.claude/CLAUDE.md`. Keep a rule only while
  you can say what failure it prevents; delete it when you cannot.
- **Keep it current:** `/starter:starter-update` shows what a new release
  changes and applies nothing until you say yes.
- **Something misbehaved:** if the commit guard flags something it should not,
  or an agent or skill from this kit does something wrong, run this in a
  terminal. It saves a redacted report and sends nothing unless you add
  `--submit` and confirm (`--kind` can also be `agent-misbehaved`):
  - bash: `python ~/.claude-starter/scripts/report.py --kind guard-false-positive --step "what happened"`
  - PowerShell: `python "$HOME\.claude-starter\scripts\report.py" --kind guard-false-positive --step "what happened"`
