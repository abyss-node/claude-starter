# Try it on a demo

Skip this step if you have a project of your own to practise on: the next step
uses it, and it need not be a git repo yet. If you have none, or want to see
the whole chain work before you trust the kit with your code, try a demo. A
demo is a small project your agent builds in a new folder from a brief, graded
by held-out checks kept in the kit, not in that folder.

1. **Pick one.** Run this in a terminal, or ask your agent to run it. It asks
   what you want to spend, then lists the demos with what each costs on your
   plan where that has been measured, and says so where it has not:
   - bash: `python ~/.claude-starter/scripts/starter.py demo pick --tool {{tool}}`
   - PowerShell: `python "$HOME\.claude-starter\scripts\starter.py" demo pick --tool {{tool}}`
2. **Start it.** The same launcher with `demo start <name> --tool {{tool}}`
   makes the folder `~/agent-demos/<name>`: a git repo whose commits the commit
   guard's git hooks check. It prints how to open a session there and what to
   type first.
3. **Watch the chain** in that new session: a plan, the build, its tests, the
   `verifier` agent, {{cmd:checkpoint}}, then a commit, which the demo's own
   commit guard hooks check. To grade the work yourself, run the launcher's
   `demo check <name>` line that the start step printed, not `npm test`, which
   the agent can change. It ends with `PASS` or `FAIL`. Like any grade made on
   your machine, it is feedback, not proof: the agent has a shell there too.
   A measured run counts only after the kit's CI re-grades the committed
   folder.

Deleting the folder undoes the demo, and nothing in it leaves your machine
unless you push it yourself.
