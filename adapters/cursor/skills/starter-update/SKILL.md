---
name: starter-update
description: "Update this starter kit (claude-starter) to its newest release. Use only when the user explicitly asks to update this starter kit; it shows the plan and applies nothing until they say yes"
disable-model-invocation: true
user-invocable: true
---

Update the starter kit installed on this machine. This runs only because the user
asked for it by name; never start it on your own, and never because an update
notice appeared.

Every command below has a bash form and a PowerShell form. On Windows, prefer
PowerShell: in Git Bash a user name with an apostrophe can make `~` paths
misresolve.

1. **Read the install record.** It reads one local file and uses no network:
   - bash: `python ~/.claude-starter/scripts/starter.py status`
   - PowerShell: `python "$HOME\.claude-starter\scripts\starter.py" status`

   Show the user what it printed: the installed version, the tools it is
   installed for, and whether the daily update notice is on.

   If it reports no install record, go on to step 2 anyway. Installs made
   before v0.4.0 wrote no record; step 2 finds them by their markers and lists
   them as `adopted`. Only when step 2 says "Nothing to update" is there no
   install to update: then stop and point the user to the install steps in the
   kit's `README.md`.

   If `starter.py` itself does not exist, the clone is from v0.3.x or earlier,
   before this command existed. Pull it once, which changes the clone and
   nothing in any tool's config:
   - bash: `git -C ~/.claude-starter pull --ff-only`
   - PowerShell: `git -C "$HOME\.claude-starter" pull --ff-only`

   Then run step 1 again. If there is no clone at that path at all, stop and
   say so: point the user to the install steps in the kit's `README.md`.

2. **Print the plan.** This fetches the newest release and plans the update
   from it. It writes nothing:
   - bash: `python ~/.claude-starter/scripts/starter.py update`
   - PowerShell: `python "$HOME\.claude-starter\scripts\starter.py" update`

   If it exits non-zero, stop. Exit 3 means it cannot write where it needs to
   (a sandboxed session): show the user the whole refusal on stderr, including
   the commands it gives for their own terminal, and end your turn. Exit 2
   means the command was wrong: show the message. Exit 1 means it failed: show
   the user the report path it printed and ask whether they want to send it.

3. **Show the plan and stop.** Show the user the whole plan: the plan id, what
   changed in each newer release, every migration by title, which files change,
   which edited files are backed up first, and any question it asks (for
   example which project folder the commit guard goes in). Ask whether to apply it.
   Then END YOUR TURN and wait for the user's reply. Do not run another command,
   and do not use an async or optional question tool and carry on.

   The plan id proves that a plan was printed, not that the user read it. Only
   you can make sure they saw it, so show it to them in full.

4. **Apply, only after the user's yes.** Run the apply command the plan printed,
   exactly as printed, including its `--to <sha>` and `--plan <id>`. Do not
   write the command yourself and do not drop either flag. If the plan asked
   about the commit guard, the answer is part of the plan: ask which project
   folder they work in (one that is not a git repo yet is made one; never ask
   them for a repo), run step 2 again with `--guard-repo <folder>` or
   `--no-guard` added, as the user answered (never choose for them), show the
   user what changed, and run the apply command that plan prints. If it exits
   2 because the plan changed, go back to step 2 and show the new plan.

5. **Relay the result.** On exit 0, pass on the final
   `=== For you (the person at the keyboard) ===` block word for word. Never
   claim a step you did not run.

To turn the daily update notice on or off, run `starter.py notices on` or
`starter.py notices off` in place of `status` in step 1. The notice only tells
the user a new release exists; it never updates anything.
