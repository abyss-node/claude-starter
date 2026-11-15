# The 5-minute mental model

Skip this if you have used Claude Code for a while; it is here as reference.

**Sessions.** Each time you run `claude` in a folder, you start a session: a
conversation with that folder as its workspace. Claude can read files there and,
with your permission, edit them and run commands. `/clear` starts fresh;
`claude --continue` picks up the last session.

**CLAUDE.md.** A plain text file of standing instructions Claude reads at the
start of every session. `~/.claude/CLAUDE.md` applies to all your projects; a
`CLAUDE.md` in a repo applies to that repo. `/init` writes a first draft of one
for a repo by reading it. This is where house rules go.

**Permissions and modes.** By default Claude asks before it edits files or runs
most commands. Read-only commands like `git status` or `ls` run without asking.
`Shift+Tab` cycles through modes, including one that accepts edits without
asking and a plan mode where Claude researches and proposes before touching
anything. Settings can pre-approve specific commands you trust.

**Slash commands.** Typed shortcuts that run a saved prompt: `/init`, `/clear`,
`/compact`, `/config`, `/model`. Plugin commands carry the plugin's name, so this
one's are `/starter:setup`, `/starter:checkpoint`, `/starter:lanes`,
`/starter:onboard` and `/starter:starter-update`.

**Subagents.** A separate Claude with its own context window, sent to do one job
and report back. Useful for wide searches (you get the answer, not fifty file
dumps) and for independent checking. Ask Claude "which agents do you have?", or
find them in `/plugin` under an installed plugin's details.

**Plugins.** Bundles of commands, agents and hooks, installed from a marketplace
with `/plugin`. This kit is a marketplace with one plugin, `starter`.

**Hooks.** Scripts that Claude Code itself runs at fixed moments, for example
just before a command. Claude cannot skip them, which makes them the place for
rules that must always hold. The commit guard in this plugin is a hook.

**Context and compaction.** Everything in the session (your messages, files
read, command output) shares one context window. When it fills, Claude Code
summarises older parts automatically. Run `/compact` yourself at a natural break,
or `/clear` when switching to an unrelated task, so stale detail does not crowd
out what matters now.

**Usage limits.** Long sessions, large files, bigger models and many subagents
all spend your limit faster. If you hit it often, start fresh sessions more
often and send fewer agents.
