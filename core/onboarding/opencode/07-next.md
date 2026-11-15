# Where to go next

- **Graduate to full:** once you regularly run several agents at once, install
  the full tier. It adds rules for picking a model and effort level per task
  and for coordinating agents. `--dry-run` shows the plan first; restart
  OpenCode after the install:
  - bash: `python ~/.claude-starter/scripts/install.py --tool opencode --tier full --dry-run`
  - PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier full --dry-run`
- **Pin a model to an agent:** the kit's agents run on the session's model. To
  pin one, add `model: provider/model` to its file in
  `~/.config/opencode/agents/`. `MODELS.md` in the kit says which role each
  agent plays.
- **A repo with two stacks:** run `/lanes` once in it.
- **Make the rules yours:** edit `~/.config/opencode/AGENTS.md`, outside the
  block marked `BEGIN claude-starter rules`; an update replaces that block.
  Keep a rule only while you can say what failure it prevents.
- **Keep it current:** `/starter-update` shows what a new release changes and
  applies nothing until you say yes.
- **Something misbehaved:** if the commit guard flags something it should not,
  or an agent or skill from this kit does something wrong, run this in a
  terminal. It saves a redacted report and sends nothing unless you add
  `--submit` and confirm (`--kind` can also be `agent-misbehaved`):
  - bash: `python ~/.claude-starter/scripts/report.py --kind guard-false-positive --tool opencode --step "what happened"`
  - PowerShell: `python "$HOME\.claude-starter\scripts\report.py" --kind guard-false-positive --tool opencode --step "what happened"`
