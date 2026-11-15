# Your plan

In OpenCode you connect one or more providers, and each one bills its own way.
Type `/connect` to add one, and `/models` to see the models your connected
providers offer. A model is named `provider/model`, for example
`anthropic/<model>`. Find the providers you use:

{{plans}}

On a plan with a usage limit, stay on the starter tier, and use the `verifier`
agent on work that matters rather than on every edit. On an API key you pay for
every token: starter is still the place to start, and `opencode stats` in a
terminal shows what you have spent. A small local model may print its tool
calls as text instead of running them; if that happens, use a hosted model for
the kit's agents.

You chose the tier when you installed. To change it, run the installer again
with the other tier; `--dry-run` shows the plan and changes nothing:
- bash: `python ~/.claude-starter/scripts/install.py --tool opencode --tier full --dry-run`
- PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool opencode --tier full --dry-run`
