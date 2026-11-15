# The 5-minute mental model

Skip this if you have used OpenCode for a while; it is here as reference.

**Sessions.** Each time you run `opencode` in a folder, you start a session: a
conversation with that folder as its workspace. The agent can read files there
and, as your permissions allow, edit them and run commands. `/new` starts a
fresh session, `/sessions` switches between them, and `opencode --continue`
picks up the last one.

**AGENTS.md.** A plain text file of standing instructions OpenCode reads at the
start of every session. `~/.config/opencode/AGENTS.md` applies to all your
projects; an `AGENTS.md` in a repo applies to that repo. `/init` writes a first
draft of one for a repo by reading it. This is where house rules go.

**Agents.** `Tab` switches between the Build agent, which makes changes, and
the Plan agent, which is restricted to researching and proposing. The kit adds
three subagents: `verifier`, `code-reviewer` and `consultant`. Type
`@verifier` (or ask for the verifier agent) to send one off on a job; it works
in its own context and reports back.

**Permissions.** The `permission` setting in `opencode.json` decides, per tool,
whether the agent may go ahead (`allow`), must ask you first (`ask`) or may
never (`deny`). The kit added `allow` rules only for a few read-only git
commands. Its subagents are denied editing.

**Commands.** Typed shortcuts that run a saved prompt. OpenCode's own include
`/init`, `/new`, `/compact`, `/models`, `/connect` and `/undo`. The kit's are
`/checkpoint`, `/lanes`, `/onboard` and `/starter-update`.

**Skills.** Checklists the agent loads only when the work matches, such as the
kit's backend and frontend guardrails. `opencode debug skill` lists them.

**Context and compaction.** Everything in the session (your messages, files
read, command output) shares one context window. When it fills, OpenCode
summarises older parts. Run `/compact` yourself at a natural break, or `/new`
when switching to an unrelated task, so stale detail does not crowd out what
matters now. `/undo` takes back the last message and the file changes it made.

**Usage.** Long sessions, large files, bigger models and many subagents all
spend faster, on a plan's limit or on your API bill.
