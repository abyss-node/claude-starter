# Your first hour

Do this in a project folder of your own. If it is not a git repo yet, the
agent runs `git init` there and says so: the repo stays on your machine, and
deleting its `.git` folder undoes it. After the first commit, it offers to
put the project on GitHub, and does nothing there without your yes. In a repo
that already has commits, start from a clean `git status` and make a branch
first, so nothing lands on your main branch by accident.

1. **Open it.** `cd` into the project's folder and run `claude`.
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
