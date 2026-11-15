# How this kit works

The rules ask your agent to work like this:

- **Classify the task first:** say whether it is a spike, a change to something
  that exists, or new architecture, because each needs a different amount of
  care.
- **Root cause before fix:** a fix for a bug you do not understand is a guess,
  and three failed fixes means the design is wrong.
- **Verify independently:** the agent that did the work does not get to declare
  it done; another one re-runs the checks.
- **Say what you ran versus what you reasoned:** "tests pass" means they ran and
  someone read the output, and commits record which is which.
- **Simplest thing first:** no new dependency or service without evidence it is
  needed, built so the bigger option can replace it later.
- **Confirm before anything outward-facing:** pushes, deploys, messages and
  deletes wait for your yes, because git cannot undo them.

Each rule is written down with the reason it exists, in {{rules_file}}.
Keep a rule only while you can say what failure it prevents.
