# Where to go next

- **Graduate to full:** once you regularly run several agents at once, install
  the full tier. It adds rules for picking a model and effort level per task
  and for coordinating agents. `--dry-run` shows the plan first; add the
  `--config-dir` or `--project` you used, if any:
  - bash: `python ~/.claude-starter/scripts/install.py --tool {{tool}} --tier full --dry-run`
  - PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool {{tool}} --tier full --dry-run`
- **Pick models per role:** `MODELS.md` in the kit says which role each agent
  plays. Map those roles to models your tool offers.
- **A repo with two stacks:** run {{cmd:lanes}} once in it.
- **Make the rules yours:** edit your rules file, outside the block marked
  `BEGIN claude-starter rules`; an update replaces that block. Keep a rule only
  while you can say what failure it prevents.
- **Keep it current:** {{cmd:starter-update}} shows what a new release changes
  and applies nothing until you say yes.
- **Something misbehaved:** if the commit guard flags something it should not,
  or an agent or skill from this kit does something wrong, run this in a
  terminal. It saves a redacted report and sends nothing unless you add
  `--submit` and confirm (`--kind` can also be `agent-misbehaved`):
  - bash: `python ~/.claude-starter/scripts/report.py --kind guard-false-positive --tool {{tool}} --step "what happened"`
  - PowerShell: `python "$HOME\.claude-starter\scripts\report.py" --kind guard-false-positive --tool {{tool}} --step "what happened"`
