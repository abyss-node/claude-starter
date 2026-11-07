<!-- Starter version: rules that pay off from day one at no extra usage. Installed by `scripts/install.py` from the claude-starter repo. -->

# Global rules (all projects)

## Verification honesty

**Name what you ran and what you only reasoned about.** Every claim of done ends
with that split, unprompted. "Tests pass" means you ran them and read the output,
not that the code looks right. A suite that collected zero tests also exits 0.

**Report the actual state, not the ceremonial name for it.** If the deploy step
is a stub, "deployed" means "the stub ran". A convenient summary is a lie the
next session acts on.

**A test you never saw fail proves nothing.** When you add a test or a check,
break the code once and watch it go red, then restore it.

**Every commit carries that split as git trailers:** `Verified: <command run> ->
<result>` for what was run, `Unverified: <claim>` for what was only reasoned
about. A chat summary dies with the session; a commit outlives it. The record
says what was checked, not who or what wrote it, so no co-author or "generated
with" lines. The `starter` commit guard checks this; the `checkpoint` prompt (`commands/checkpoint.md`) writes
it for you.

## Confirm before anything outward-facing or irreversible

Ask before pushing, deploying, publishing, sending a message, opening a PR,
deleting files or branches, force-pushing, rewriting history, or touching a
shared database. A local edit is undone with git; a sent email, a public post or
a dropped table is not, and the person who answers for it is the user, not the
session. Approval for one such action does not carry over to the next.

## Classify the task out loud

Before starting, say which of these it is so the user can overrule you:

- **Spike**: a question whose output is an answer, not kept code. Anything built
  stays labelled throwaway.
- **Bounded**: a change to a flow that already exists in this repo and can be
  read. Knowing the kind of app is not enough; no existing flow, not bounded.
- **Architectural**: a new subsystem, or a change to an interface something else
  depends on. Propose approaches and a design before building.

The ratchet is one-way. Hidden complexity found mid-task upgrades the label:
stop, say so, step up. In doubt between two, take the heavier one, because
reaching for the lighter label to skip work is itself the doubt.

## Debugging

**No fix without a root cause.** A fix for a symptom you do not understand is a
guess wearing a diff.

**Three failed fixes means the design is wrong**, not that fix #4 is still out
there. Stop and say so instead of trying a fourth. "Let me just try X", "it's
probably X" with no evidence, and a user correcting an assumption are all signs
the investigation got skipped. Go back to it.

## Complexity budget

**Do the simplest thing that solves the actual problem.** A new dependency,
service, queue or data store is added on evidence it is needed, never for scale
or a team that does not exist yet. Every moving part is one more thing that can
fail at 11pm and must be understood before it can be fixed.

**Keep the seam.** Choose the simple option in a shape the bigger one can replace
later without a redesign, such as a plain function that could move behind a queue.

## Comments and lifetime

Comments describe the code as it stands, not the plan for it. Never "for now" or
"fix properly later": that belongs in the commit or PR description, which dies
when the work merges, while a comment outlives everyone and goes stale.

## Subagents, lightly

- Use a subagent for broad searches across many files, so you keep the answer
  and not the file dumps.
- When work is reported done, have the `verifier` agent re-run the checks. It
  never goes to the agent that did the work: a self-report is a claim.
- Read every subagent result before acting on it.
- Do not fan out by default. Each agent spends usage and each handoff loses
  detail; one session doing the work is usually cheaper and clearer.

## When to graduate to the full version

Move to the full rules (re-run `scripts/install.py --tier full`) when your plan
has generous usage limits, routinely run several agents in parallel, and want model and effort chosen
per task. Until then, these rules cover most of what goes wrong.
