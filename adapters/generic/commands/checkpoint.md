<!-- Prompt: Verify, summarise and commit the current unit of work. Paste it, or point your tool at this file; replace $ARGUMENTS with your input. -->
A checkpoint, not a code dump. In order:

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
   The commit guard checks for this, and a chat summary dies with the session
   while a commit outlives it.
5. **Stop and wait for approval before committing.** Do not push unless asked.

If the work is not at a coherent stopping point, say so and name what is left
rather than committing a partial state.
