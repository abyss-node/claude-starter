# Your plan

Your plan decides how fast you use up your limit, and so which rules tier fits
you. Your tool's own settings or docs say which plan you are on and where it
shows your usage.

- **A plan with a usage limit that resets:** stay on the starter tier, and use
  the `verifier` agent on work that matters rather than on every edit.
- **A larger plan with generous limits:** the full tier exists, but start on
  starter unless you already run several agents at once.
- **An API key, paid per token:** start on starter; the full tier's rules send
  more agents, and each one spends.

You chose the tier when you installed. To change it, run the installer again
with the other tier, adding the `--config-dir` or `--project` you used, if
any; `--dry-run` shows the plan and changes nothing:
- bash: `python ~/.claude-starter/scripts/install.py --tool {{tool}} --tier full --dry-run`
- PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool {{tool}} --tier full --dry-run`
