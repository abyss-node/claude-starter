# Onboarding: working with Claude Code the way Arnuv does

## For Claude: how to run this walkthrough

You are guiding someone who may be new to Claude Code through this file. The
sections after this one are written for them; this section is for you.

- **First, check what you are.** This kit targets Claude Code running a Claude
  model. If you are not Claude Code, say so, then run the installer for your tool
  as `AGENTS.md` describes
  (https://github.com/abyss-node/claude-starter/blob/main/AGENTS.md) instead of
  translating anything by hand. Do not install Claude-specific files unchanged.
  Only if your tool is not one the installer supports, use `PORTING.md` as the
  last resort. Everything below still applies; only the install steps change.
- **One step at a time.** Cover one section, then stop and check in: ask whether
  it made sense and whether they want to go on, go deeper, or skip ahead. Never
  paste the whole file back at them.
- **Ask two things first:** which OS they are on (Windows, macOS, Linux) and which
  plan they have (Pro, Max, Team, or API). Adapt everything after that:
  - Windows: say which shell a command is for, and quote home paths, since they
    can contain spaces or apostrophes.
  - Pro: recommend the starter tier, and warn that the `verifier` agent runs on a
    larger model, so use it on work that matters rather than on every edit.
  - Max or Team: mention that the full tier exists, but start them on starter
    anyway unless they already use subagents.
- **Ask what they already know.** Skip the mental model for anyone who has used
  Claude Code for a while; offer it as reference instead.
- **Run nothing without asking.** For each install or setup step, show the
  command, say what it does, and let them run it or approve it.
- **Use their own repo** for the exercise, not a toy one. If they do not have one
  handy, help them pick a small project they care about.
- **Be plain.** Short answers, concrete examples from their repo, no hype.

---

## Who this is for

Friends of Arnuv who want to use Claude Code on real projects, including people
who have never used it. You will get a small plugin that sets up rules, a few
helper agents and a commit check, and a first hour of practice on your own code.

You do not need to read everything below. Claude will walk you through it.

## The 5-minute mental model

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
one's are `/starter:setup`, `/starter:checkpoint`, `/starter:lanes`.

**Subagents.** A separate Claude with its own context window, sent to do one job
and report back. Useful for wide searches (you get the answer, not fifty file
dumps) and for independent checking. Ask Claude "which agents do you have?", or
find them in `/plugin` under an installed plugin's details.

**Plugins.** Bundles of commands, agents and hooks, installed from a marketplace
with `/plugin`. This repo is a marketplace with one plugin, `starter`.

**Hooks.** Scripts that Claude Code itself runs at fixed moments, for example
just before a command. Claude cannot skip them, which makes them the place for
rules that must always hold. The commit guard in this plugin is a hook.

**Context and compaction.** Everything in the session (your messages, files
read, command output) shares one context window. When it fills, Claude Code
summarises older parts automatically. Run `/compact` yourself at a natural break,
or `/clear` when switching to an unrelated task, so stale detail does not crowd
out what matters now.

**Usage limits.** Plans have usage limits that reset over time. Long sessions,
large files, bigger models and many subagents all spend faster. `/model` shows
and changes the model. If you hit limits often, start fresh sessions more often
and send fewer agents.

## How Arnuv works

- **Classify the task first:** say whether it is a spike, a change to something
  that exists, or new architecture, because each needs a different amount of care.
- **Root cause before fix:** a fix for a bug you do not understand is a guess,
  and three failed fixes means the design is wrong.
- **Verify independently:** the agent that did the work does not get to declare
  it done; another one re-runs the checks.
- **Say what you ran versus what you reasoned:** "tests pass" means they ran and
  you read the output, and commits record which is which.
- **Simplest thing first:** no new dependency or service without evidence it is
  needed, built so the bigger option can replace it later.
- **Confirm before anything outward-facing:** pushes, deploys, messages and
  deletes wait for a yes, because they cannot be undone with git.

These are written into the `CLAUDE.md` that setup installs, each with the reason
it exists.

## Install

Inside Claude Code, run these one at a time:

```
/plugin marketplace add abyss-node/claude-starter
/plugin install starter@claude-starter
/starter:setup
```

The first line registers this repo as a plugin source. The second installs the
plugin. If `/starter:setup` is not found afterwards, run `/reload-plugins`; if it
is still missing, restart Claude Code.

Or let the installer do the first two lines. You need `git` and Python 3.9 or
newer. Claude, tell the user what each command does, and run them one at a time
with their yes:

```
git clone https://github.com/abyss-node/claude-starter ~/.claude-starter
python ~/.claude-starter/scripts/install.py --tool claude --dry-run
python ~/.claude-starter/scripts/install.py --tool claude --yes
```

In PowerShell, use `"$HOME\.claude-starter"` for the folder, and `py` if `python`
is not found. The dry run prints the plan and changes nothing. Afterwards,
restart Claude Code if it does not see the plugin, then run `/starter:setup`. If
the installer fails, it saves a redacted report and prints an issue link; show
both to the user and do not install by hand.

`/starter:setup` asks whether you want the **starter** or **full** rules, installs
a `CLAUDE.md`, merges a short list of read-only git and format-check commands into your settings,
and asks how strict the commit guard should be. It never overwrites a file you
already have; it shows the difference and backs up anything it changes. It is
safe to run again. Test and lint runners are deliberately not pre-approved: they
run code the repo controls (package scripts, test config, plugins), and some
linters rewrite files when configured to. Once you trust a repo, approve them in
that repo's `.claude/settings.json`.

What you get:

| Piece | Use it for |
|---|---|
| `/starter:checkpoint` | After a change: runs the relevant checks, says what ran and what did not, proposes a commit message, waits for your yes |
| `verifier` agent | Re-runs build and tests on work reported as done, without editing anything |
| `code-reviewer` agent | Reviews a diff for the ways this project breaks (money, auth, time, data), not style |
| `consultant` agent | Answers a question about another part of the codebase so your session does not have to read it all |
| `/starter:lanes` | Splits a repo with several stacks (say, a frontend and a backend) into lanes |
| Commit guard | Checks commits for secrets, personal data and a `Verified:` or `Unverified:` line |

Agents from the plugin may show up as `starter:verifier` and so on in `/plugin`
(installed plugin details). You call one by asking, for example "use the verifier
agent to check this".

## Your first hour

Do this in a repo of your own with a clean `git status`. Make a branch first so
nothing lands on your main branch by accident.

1. **Open it.** `cd` into the repo and run `claude`.
2. **Run `/init`.** Read the `CLAUDE.md` it writes. Correct anything wrong: how
   to run the tests, what the project is, what must never break. This file is
   worth more than any prompt you will type.
3. **Ask for a small change.** Pick something real and small: a confusing
   function to tidy, a missing test, a bug you already understand. Notice that
   Claude says how it classifies the task before it starts. If it guesses wrong,
   say so.
4. **Run `/starter:checkpoint`.** It runs the checks that cover the change, tells
   you what it did not run, shows the diff and proposes a commit message with a
   `Verified:` or `Unverified:` line. It stops and waits for you.
5. **Ask for an independent check.** Type something like: "Use the verifier agent
   to check that this change works." Compare its report with what the session
   claimed. Any gap between the two is the point of the exercise.
6. **Commit, if you are happy.** Approve the commit. If the commit guard warns
   about something, read the warning and decide whether it is real.

If anything confused you along the way, ask Claude about it right there. That is
usually faster than searching the docs.

## Where to go next

- **Add-ons:** `plugins/starter/ADDONS.md` lists optional plugins and skill packs,
  with when each is worth it and when to skip it. Add one when a task has gone
  badly twice, not in advance.
- **Graduate to full:** once you are on Max or Team and regularly run several
  agents at once, re-run `/starter:setup` and choose full. It adds rules for
  picking a model and effort level per task and for coordinating agents.
- **A repo with two stacks:** run `/starter:lanes` once in it.
- **Make the rules yours:** edit `~/.claude/CLAUDE.md`. Keep a rule only while
  you can say what failure it prevents; delete it when you cannot.
- **Something misbehaved:** if the commit guard flags something it should not, or
  an agent or skill from this kit does something wrong, run
  `python ~/.claude-starter/scripts/report.py --kind guard-false-positive --step "what happened"`
  (`--kind` can also be `agent-misbehaved`). It saves a redacted report and sends
  nothing unless you add `--submit` and confirm.
