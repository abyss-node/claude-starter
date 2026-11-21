---
description: "Verify, summarise and commit the current unit of work"
---

Before anything else, check for an update notice:
`python ~/.claude-starter/scripts/update_check.py --remind` (PowerShell:
`python "$HOME\.claude-starter\scripts\update_check.py" --remind`). It prints one line when
a newer release of this kit is out and nothing otherwise, and it never updates
anything. If it prints a line, pass that line on to the user, then carry on. If
the file does not exist, skip this.

While the user has not chosen whether to get that notice, the line is instead a
one-line reminder that they have not. Pass it on and carry on with the
checkpoint: do not wait for an answer. If they answer, record it with
`python ~/.claude-starter/scripts/starter.py notices on` (or `off`; PowerShell:
`python "$HOME\.claude-starter\scripts\starter.py" notices on`). Once recorded,
the reminder stops. If that command exits 2 (no install recorded yet), pass on
what it printed.

A checkpoint, not a code dump. In order:

0. **No repo yet? Make one.** If `git rev-parse --show-toplevel` fails, or
   names the home folder (a dotfiles repo), the folder has no repo of its own:
   run `git init` there and tell the user you did (it is local; deleting the
   `.git` folder undoes it). Do not ask them for a repo. Never do this where
   the rules' "No repo yet" section forbids it: the home folder or a folder
   that holds it, the Desktop, Documents or Downloads folder, the Windows
   folder, a drive root, or the kit's clone (`~/.claude-starter`). There,
   propose a project folder such as `~/projects/<name>` instead. With a fresh
   repo, step 3 shows every file as new, and step 5 is its first commit: if
   `git config user.name` or `user.email` is empty, ask the user for them
   before it.
1. **Run the checks that actually cover what changed** — targeted tests over full
   suites, the linter, the type-checker, and a build only if the built thing
   moved. If a schema or serializer changed, regenerate whatever is generated
   from it.
2. **Report precisely what passed and what you did not run.** Do not claim
   coverage you did not exercise.
3. **Show `git status` and `git diff --stat`**, and confirm nothing from `tmp/`,
   no scratch file and no secret is staged.
4. **Propose a Conventional Commit message** written for someone reading it in a
   year with no memory of the ticket: what changed and why, not how. End it with a last paragraph of trailers:
   `Verified: <command run> -> <result>` for each thing actually run,
   `Unverified: <claim>` for anything only reasoned about. No AI co-author lines.
   Where the commit guard is installed as git hooks (installer `--guard-repo`),
   it checks for this; elsewhere nothing does. A chat summary dies with the
   session while a commit outlives it.
5. **Stop and wait for approval before committing.** Do not push unless asked.
   Once the commit is made, a repo with no GitHub remote gets the offer in the
   rules' "No repo yet" section (`gh auth status` first, `gh repo create` only
   on the user's yes), never a push on your own. Not before: `gh repo create
   --push` fails on a repo with no commits.

If the work is not at a coherent stopping point, say so and name what is left
rather than committing a partial state.
