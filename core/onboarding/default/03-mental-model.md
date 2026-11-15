# The 5-minute mental model

Skip this if you have used your coding agent for a while; it is here as
reference. Your tool's docs give the exact keys and commands.

**Sessions.** Each time you start your agent in a folder, you start a session:
a conversation with that folder as its workspace. The agent can read files
there and, as your permissions allow, edit them and run commands. Starting a
new session gives it a fresh memory of the conversation.

**Rules files.** Plain text files of standing instructions the agent reads at
the start of every session. This kit's rules are in {{rules_file}}.
Most tools also read an `AGENTS.md` at the root of a repo, for that repo alone.
This is where house rules go.

**Permissions.** Your tool decides, per action, whether the agent goes ahead,
asks you first, or never may. Keep edits and commands on asking until you
trust the agent in a repo.

**Commands.** Saved prompts you run by name. The kit's are
{{cmd:checkpoint}}, {{cmd:lanes}}, {{cmd:onboard}} and {{cmd:starter-update}}.

**Subagents.** A separate agent with its own context, sent to do one job and
report back. The kit adds three: `verifier`, `code-reviewer` and `consultant`.
You call one by asking, for example "use the verifier agent to check this".

**Skills.** Checklists the agent loads only when the work matches, such as the
kit's backend and frontend guardrails.

**Context.** Everything in the session (your messages, files read, command
output) shares one context window. When it fills, older detail gets summarised
or dropped. Start a fresh session when you switch to an unrelated task, so
stale detail does not crowd out what matters now.

**Usage.** Long sessions, large files, bigger models and many subagents all
spend faster, on a plan's limit or on your API bill.
