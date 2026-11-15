# Your first hour

Do this in a repo of your own with a clean `git status`. Make a branch first so
nothing lands on your main branch by accident.

1. **Open it.** Start your agent in the repo's folder.
2. **Give the repo its own rules.** If your tool has a command that drafts a
   rules file by reading the repo, run it; otherwise ask the agent to write an
   `AGENTS.md` that says how to run the tests, what the project is and what
   must never break. Read it and correct anything wrong. This file is worth
   more than any prompt you will type.
3. **Ask for a small change.** Pick something real and small: a confusing
   function to tidy, a missing test, a bug you already understand. Notice that
   the agent says how it classifies the task before it starts. If it guesses
   wrong, say so.
4. **Run {{cmd:checkpoint}}.** It runs the checks that cover the change, tells
   you what it did not run, shows the diff and proposes a commit message with
   a `Verified:` or `Unverified:` line. It stops and waits for you.
5. **Ask for an independent check.** Type something like: "Use the verifier
   agent to check that this change works." Compare its report with what the
   session claimed. Any gap between the two is the point of the exercise.
6. **Commit, if you are happy.** Approve the commit. Where the commit guard is
   installed, read any warning it gives and decide whether it is real.
