# Measuring a demo run

`demos/pick.py` prints a number only from a run measured this way and recorded
in `demos/costs.json`. An agent cannot read your usage meter, so without a
measured run it says "not measured yet" and names no figure. This file is the
one home of how a run is measured.

A **cell** is one tool, one plan (an id from `core/plans.json`) and one demo.
Three runs make a cell; the picker shows the range across them, failed runs
included, so its top figure is the worst run seen. Large briefs take hours a
run. Measure the two small briefs first, on Claude Code and on OpenCode, then
Codex on ChatGPT Plus. Every other cell reads "not measured yet" until someone
measures it.

## A run

1. **One session at a time**, and nothing else on the account while it runs,
   or the meter counts both. Read the meter before you start:
   - Claude Code: `/usage`.
   - Codex: `/status`; where it does not show your limits, the usage page on
     the ChatGPT website.
   - OpenCode on an API key: `opencode stats`.
2. **Start the demo** with `demo start <name> --tool <tool>`, open a new
   session in its folder as it says, and send the kickoff it prints. Answer
   only from the card below, never from the workspace or from what you know
   about the demo.
3. **Codex: run it with `codex exec --json`** throughout, and give each answer
   with `codex exec resume`, so the usage is the documented
   `turn.completed.usage`. Exec's approval and sandbox defaults differ from an
   interactive session, so its rows say `mode: exec`.
4. **When the agent stops** (it says it is done, or it asks for something the
   card does not answer), read the meter again and grade the folder yourself
   with the `demo check` line that `demo start` printed in its step 5:
   - bash: `python ~/.claude-starter/scripts/starter.py demo check <name> --dir <folder>`
   - PowerShell: `python "$HOME\.claude-starter\scripts\starter.py" demo check <name> --dir <folder>`

   Not `npm test`: the agent can change what that runs. Its `RECORD:` line
   gives `accept`, `kit_sha` and `accept_hash`; a line with `recordable=no`
   cannot be a row. This grade is feedback, not proof: the agent ran with a
   shell on this machine, as you, and anything that can do that can tamper
   with the kit's clone or with the grade. So it is not what admits the run;
   CI's re-grade is (below).
5. **Keep the evidence:** the Claude Code transcript (JSONL), `opencode export`,
   or Codex's exec JSONL. `verifier` and `checkpoint` in the row come from it.
   Wall time runs from the session's start to its last turn.
6. **Commit the workspace with the row,** as a git bundle in the kit's
   `demos/runs/` (make that folder first if your clone has none):
   - bash: `git -C <folder> bundle create ~/.claude-starter/demos/runs/<demo>-<tool>-<plan>-<date>-<n>.bundle --all`
   - PowerShell: `git -C <folder> bundle create "$HOME\.claude-starter\demos\runs\<demo>-<tool>-<plan>-<date>-<n>.bundle" --all`

   The row's `workspace` is that file's path under `demos/` (`runs/...`), and
   its `workspace_sha` is the commit the grade above ran on
   (`git -C <folder> rev-parse HEAD`). The bundle carries the workspace's
   commits, with their author's name and email.

## The answers card

Give these answers and no others. A brief never contains them (a test checks),
so the agent cannot find them in the workspace.

<!-- answers card -->
- When the agent asks whether to go ahead with its plan: "Go ahead."
- When it asks to commit: "Yes, commit it."
- When it asks about anything outward (a push, a deploy, publishing): "No, keep everything local."
- Anything else: "Use your judgement and carry on."
<!-- end answers card -->

## A row in costs.json

One object per run in `runs`. `demolib.check_row` checks each field; a row
counts only if `demolib.admit` admits it.

| Field | What it holds |
|---|---|
| `demo`, `tool`, `plan` | The cell. `plan` is the tool's plan id in `core/plans.json`. |
| `model`, `effort`, `tool_version` | What the session ran, as the tool reported it. |
| `kit_sha`, `accept_hash` | From the `RECORD:` line. |
| `workspace`, `workspace_sha` | The run's bundle, `runs/<file>.bundle` under `demos/`, and the commit in it that was graded. |
| `date` | The run's date, `YYYY-MM-DD`. Runs over 90 days old are not shown. |
| `mode` | `interactive`, or `exec` for `codex exec`. |
| `meter_delta` | The meter after minus before: `weekly_pct` (points of the weekly limit) on a plan with a usage limit, `usd` on an API key, nothing on a local model. Other reads, such as `session_pct`, may be added. |
| `tokens` | Total tokens, where the tool reports them, else `null`. |
| `wall_min`, `sessions` | Minutes from start to the last turn, and how many sessions it took. |
| `accept` | `PASS k/n` or `FAIL k/n`, from the `RECORD:` line. |
| `claimed_done` | Whether the agent said it was done. |
| `verifier`, `checkpoint` | `ran`, `not` or `unknown`, from the transcript. |
| `no_commit` | True when the run ended without a commit. |

A row counts only when its `accept_hash` is the tree of the files that grade
the demo at its `kit_sha`, so a check edited and committed in a clone cannot
count. CI also needs that `kit_sha` on `origin/main`, and it re-grades the run
before it admits it (`demolib.regrade`): it checks the bundle out at
`workspace_sha`, exports the kit at `kit_sha` with `git archive` into a fresh
folder, and runs that copy's `check.py` on the workspace with an empty home
folder. The verdict must be the row's `accept`. Nothing from the measuring
machine takes part but the committed workspace, so a local grade the agent
tampered with cannot become a row. On your machine, `demo pick` shows the rows
of the `costs.json` CI admitted, without re-grading them, and a row whose
`kit_sha` your clone's `HEAD` or `origin/main` reaches, so a run measured on a
branch shows there before it merges. `"synthetic": true` marks a made-up run
for the picker's tests, and `costs.json` refuses one.

## What this does not measure

A grade on your machine is feedback, not proof, and CI's re-grade proves only
that the committed workspace's code gives the right answers. Neither says who
wrote that code or how.

- Whether the agent read or copied the kit's `demos/` folder. The workspace's
  rules file forbids it, and the copy rule fails a workspace that shares more
  than ten long lines with the reference solution, but a paraphrase passes it
  (a comment in front of every line is enough). The reference is also public
  on GitHub, where the workspace's code could fetch it while it runs: Node's
  permission model, below, limits files, not the network. Only the transcript
  shows reading or copying: look for it.
- Code written to attack the grading. The checks run the workspace's code in
  processes of their own, so it cannot reach their asserts, on a copy of the
  workspace without links, under Node's permission model, which lets it read
  that copy and nothing of the kit's, and write nothing. Node documents that
  model as a seat belt for code you trust, not a sandbox against code that
  sets out to escape it. And the agent itself has a shell, as you: it can edit
  and commit the kit's clone, or fake a grade, so a local grade is feedback,
  not proof, and only CI's re-grade admits a run. CI runs the workspace's code
  too, under the same permission model. Look in the workspace and the
  transcript for code that touches other processes, the network or the kit.
- Every embedded asset. The no-binary-assets rule catches files, `data:` URLs
  and base64 over 1 KB, wrapped or not, but base64 cut into pieces under 32
  characters passes, as bytes written out as a number array do.
- Every franchise name. The denylist ignores case, accents, plurals and the
  hyphens or spaces put between a name's letters, but a word made from a name
  (an adjective, say) or a renamed lookalike passes.
- Anything about the drawing, sound or feel of a demo: the `NOT CHECKED:` line
  names it for each demo.
