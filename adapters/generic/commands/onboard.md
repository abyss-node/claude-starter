<!-- Prompt: Show this starter kit's onboarding walkthrough, one step per run. Use only when the user asks for the walkthrough by name; it prints one step and stops. Paste it, or point your tool at this file; replace $ARGUMENTS with your input. -->
Show the user one step of this starter kit's onboarding walkthrough. The kit's
launcher prints the step. Your whole job is to run it, show what it printed, and
stop.

The user typed: $ARGUMENTS

1. **Run the launcher.** Put the step number the user typed in place of `1`
   (keep `1` if they typed none):
   - bash: `python ~/.claude-starter/scripts/starter.py onboard 1 --tool generic`
   - PowerShell: `python "$HOME\.claude-starter\scripts\starter.py" onboard 1 --tool generic`

   On Windows, prefer PowerShell: in Git Bash a user name with an apostrophe
   can make `~` paths misresolve.
2. **Show the user everything it printed, word for word,** whatever its exit
   code. Do not summarise it, add steps of your own, or answer its questions
   for the user.
3. **END YOUR TURN.** Do not run the next step, and do not re-run the launcher
   with flags of your own. The step ends with the command for the next one;
   the user types it when they are ready.

If `starter.py` does not exist, the walkthrough needs the kit's clone at
`~/.claude-starter`: say so, point the user to the install steps in the kit's
`README.md`, and stop.
