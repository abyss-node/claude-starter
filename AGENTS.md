# For any coding agent opened in this repo

This repo is a starter kit for working with an AI coding agent: rules, review
agents, commands, guardrail skills and a commit guard. It is packaged as a
Claude Code plugin, but it is meant to work in any agent tool.

If the user asks you to set this up, install it, or adopt it:

1. **Identify yourself.** Tell the user which tool you are running in and which
   model you are.
2. **If you are Claude Code on a Claude model**, use the plugin route in
   `README.md` (`/plugin marketplace add`, `/plugin install`, `/starter:setup`).
3. **Otherwise, follow `PORTING.md`.** Translate each piece into your own tool's
   conventions, confirmed from your tool's current documentation, and install it
   where your tool will load it. Map the model roles in `MODELS.md` to the models
   the user has.
4. **Walk the user through `ONBOARDING.md`** one step at a time, as it describes.
   Skip only its Claude Code install section; the rest applies to any tool.

You need to read and write files and run shell commands to do this. If you
cannot, explain the steps to the user instead of claiming you did them.

Back up any existing file before changing it, ask before overwriting, and finish
with a table of what went where and what has no equivalent in your tool.
