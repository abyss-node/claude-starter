---
description: "Set up lane configuration for this repo — boundaries, role commands, nested AGENTS.md files"
allowPromptArgument: true
---

Give this repository a lane structure, so that sessions stop holding two
specialisms at once.

The rule being set up: **editing is lane-bound, reading is not.** In a repo with
more than one stack, a session works one lane at a time, because a session told
to hold two specialisms behaves as a generalist across both. To learn something
about another lane it asks the `consultant` agent, which can read but not edit,
instead of reading its own way across the tree. If the answer means another lane
has to change, it says so and stops; that is a separate session.

Target: $prompt

## 1. Find the real seams

Read the tree and the build configuration before proposing anything. A lane is a
boundary where **the tooling and the idiom change**, not merely where a directory
does. Two directories built by the same toolchain, tested by the same runner and
written in the same idiom are one lane.

Ops is usually a lane even though it owns no single directory — CI config,
container files, compose, pre-commit, release ritual, environment templates. It
spans the root and gets a role command rather than a nested file.

Propose the lanes with the evidence for each — the toolchain, the test runner,
the linter — and **stop for approval before writing anything.**

## 2. Once approved, write it

- **Nested `AGENTS.md`** per directory-owning lane, holding the invariants true
  only of that stack. These load late — when a file in the subtree is read — so
  they are the safety net for an unhatted session.
- **A role command** per lane in `.junie/commands/`, stating: what it owns, what
  it never edits and which lane owns that instead, and what "done" means as
  specific commands actually run, ending with *name which of those you ran and
  which you only reasoned about.*
- **Move, do not copy.** Every rule that came out of the root file is deleted
  from it. A rule has one home. Report anything you found stated twice already —
  that is a pre-existing defect, and the copies will have drifted.
- **Leave the root file** holding only what is true of every lane.
- **A `.junie/README.md`** listing what exists and the failure each entry was
  added for.

### What a lane brief must settle, where it applies

These are repo-level and cannot live in the global file. Ask each one of each
lane; write the answer, or write that it does not apply.

- **Who owns the contract, and what defends it.** Name the source of truth and
  whether anything — codegen, a type-check, a CI job — fails when the two sides
  drift. If nothing does, say so plainly in the brief: an undefended contract is
  the single most valuable thing a session can know about a repo.
- **The error envelope.** A machine-readable code carries the meaning; the
  message is prose for humans. Callers branch on the code, never the sentence. A
  code that merely restates the HTTP status tells a client nothing it can act on.
- **Migration discipline**, where there are migrations: never edit an applied
  one; an added column gets a default or allows null; a removal or rename ships
  only after you have *verified* nothing reads it, rather than assumed it.
- **The canary suite** — name the one suite that may never be weakened, so
  everyone knows which green is load-bearing. Usually the one standing between a
  bug and a data leak, a wrong number, or a silent outage.
- **What "modern" means for this stack**, and which linter or hook refuses the
  dated construct. If nothing refuses it yet, that is a gap worth naming.

## 3. What to build sparingly

**A per-lane consultant only when it can say something the global one cannot.**
The global `consultant` is the default and covers most repos. Add a named one for
a lane only when this repo has a concrete artefact or habit worth hardcoding into
it: a generated schema or client that is the authoritative answer to shape
questions, a directory convention that makes a grep reliable, a CI check that
makes contract drift impossible. Write that specific into the agent, with the
path. A per-lane consultant whose instructions would be true of any repo is the
global one copied twice — delete it and rely on the default.

**No lane for a surface small enough to read in one pass.** Ops usually is not:
a compose file, a workflow and a Dockerfile are readable directly, so ops gets a
role command and no consultant.

Add on evidence, not in anticipation.
