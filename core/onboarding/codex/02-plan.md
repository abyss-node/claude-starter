# Your plan

Codex runs on a ChatGPT plan or on an OpenAI API key, and that decides how
fast you use up your limit, and so which rules tier fits you. Find yours:

{{plans}}

Why unconfirmed: OpenAI documents `/status` as showing context usage and rate
limits in the IDE extension, not that the Codex CLI shows your limits the same
way. If yours does not, check your usage on the ChatGPT or OpenAI website.

- **ChatGPT Plus:** stay on the starter tier, and use the `verifier` agent on
  work that matters rather than on every edit.
- **ChatGPT Pro, Business, Enterprise or Edu:** the full tier exists, but start
  on starter unless you already run several agents at once.
- **API key:** you pay for every token, so start on starter.

You chose the tier when you installed. To change it, run the installer again
with the other tier; `--dry-run` shows the plan and changes nothing:
- bash: `python ~/.claude-starter/scripts/install.py --tool codex --tier full --dry-run`
- PowerShell: `python "$HOME\.claude-starter\scripts\install.py" --tool codex --tier full --dry-run`
