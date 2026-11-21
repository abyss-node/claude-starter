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
tampered with cannot become a row; a workspace whose own code attacks the
grade is another matter (What this does not measure, below). On your machine, `demo pick` shows the rows
of the `costs.json` CI admitted, without re-grading them, and a row whose
`kit_sha` your clone's `HEAD` or `origin/main` reaches, so a run measured on a
branch shows there before it merges. `"synthetic": true` marks a made-up run
for the picker's tests, and `costs.json` refuses one.

## What this does not measure

A grade on your machine is feedback, not proof, and CI's re-grade proves only
that the committed workspace, run beside a clean copy of the kit, gives the
right answers. Neither says who wrote that code or how, nor, for Python code,
that the answers are its own (below).

- Whether the agent read or copied the kit's `demos/` folder. The workspace's
  rules file forbids it, and the copy rule fails a workspace that shares more
  than ten long lines with the reference solution, but a paraphrase passes it
  (a comment in front of every line is enough). The reference is also public
  on GitHub, where the workspace's code could fetch it while it runs: Node's
  permission model, below, limits files, not the network. Only the transcript
  shows reading or copying: look for it.
- Code written to attack the grading. The checks run the workspace's code in
  processes of their own, so it cannot reach their asserts, on a copy of the
  workspace without links. Its Node code runs under Node's permission model,
  which lets it read that copy and, of the kit's files, only the two probe
  files and, in a scenario's process, the scenario's module and the `accept/`
  modules it imports (`demos/AUTHORING.md`): never `reference/` or
  `accept/mutants/`, whose mutants quote the reference. It can write nothing
  and start no process. The model limits files and processes, not the network,
  and it hides no path: the code can learn where the kit is (below), though
  not read it. Node documents the model as a seat belt for code you trust, not
  a sandbox against code that sets out to escape it. Where a scenario runs
  beside that code, the probe first freezes the JavaScript built-ins, the few
  Node globals the kit uses there and what the kit's modules there export,
  takes away Node's heap snapshots, promise hooks and
  `syncBuiltinESMExports`, holds the clocks and the functions it writes the
  answer with itself, and writes the answer from copies (`demos/AUTHORING.md`,
  "What a scenario's process freezes"). Workspaces once hid real bugs by
  changing `Number.prototype.toFixed`, `Object.getPrototypeOf` or
  `Math.random`, or a scenario's own table of seeds, in 3 to 7 lines each.
  Planted ones read the probe's answer key from a heap snapshot, rewrote the
  probe's answer line through `node:fs`'s `writeSync`, and rewrote a
  scenario's record through a typed array of their own class, and each had
  the checks believe an answer the code had not given. Each of those is closed
  now, and a test in `demos/tests` holds it closed. What the code still
  controls there is its own values, whose getters or Proxy traps run as the
  scenario reads them. No other way is known for it to change what a check
  sees, but the last two were found after this text said none was left: read
  it as what has been tried, not as proof. The freeze leaves `process`,
  `console` and the timers alone, and holds only within the permission model
  above. And the agent itself has
  a shell, as you: it can edit and commit the kit's clone, or fake a grade, so
  a local grade is feedback, not proof, and only CI's re-grade admits a run.
  CI runs the workspace's code too, under the same permission model. Look in
  the workspace and the transcript for code that touches other processes, the
  network or the kit.
- Where the kit is. The workspace's code can always learn the path of the
  kit's clone; the grade does not hide it, and only what the code can then read
  differs between Node and Python. It is in:
  - the workspace's own files. A python demo's rules file names the launcher
    by its path in the clone, because that is the test command the agent runs,
    and a node or mixed demo's `package.json` `test` names the clone's
    `npm-test.mjs` and `starter.py`. The graded copy holds both, as does the
    history of a demo graded on it. The rule against code that names the kit's
    files does not read them: they are the kit's text, not the workspace's code.
  - the processes. A Node probe process's own command line names the kit's
    probe files, and the process list shows the grade's command lines (check.py,
    the accept runner, `node --test` on the kit's test files), each naming the
    clone.
  - the home folder. A python demo's checks give the workspace's processes an
    empty folder as their home, but the real one is in reach: Node probe
    processes keep it in their environment, as does a mixed demo's backend
    unless its checks clear it (lanes' do not), on Windows the temporary
    folder is inside it and `%LOCALAPPDATA%` names it, and anywhere the user
    database does. Its install record names the clone, and the clone's default
    place, `~/.claude-starter`, is in the kit's own instructions.
- Python code that finds the kit. Python has no permission model like Node's,
  so in a Python demo, and in a mixed demo's Python backend, the workspace's
  code can read and run any file you can, the kit's `reference/` included. The
  grade makes that a step, not a wall: the code runs on a copy in a temporary
  folder with no variable naming the kit's clone (and in a python demo with an
  empty folder for a home), and a workspace whose code names the kit's files
  fails a rule. But every route above leads to the clone, and the shortest is
  one read of a file in the workspace: its rules file, or its `package.json`.
  A workspace that did no work, read the clone's path from its rules file or
  from the process list and ran the kit's reference got a recordable PASS.
  CI's re-grade does not stop it either: a path learnt from the workspace's
  files or on your machine leads nowhere there, but CI's clean copy of the kit
  shows in its own process list. So before a Python or mixed run becomes a
  row, read the workspace's Python for code that reads its rules file or
  `package.json`, other processes, the home folder, the install record or any
  file outside the workspace.
- Every embedded asset. The no-binary-assets rule catches files, `data:` URLs
  and base64 over 1 KB, wrapped or not, but base64 cut into pieces under 32
  characters passes, as bytes written out as a number array do.
- Every franchise name. The denylist ignores case, accents, plurals and the
  hyphens or spaces put between a name's letters, but a word made from a name
  (an adjective, say) or a renamed lookalike passes.
- Anything about the drawing, sound or feel of a demo: the `NOT CHECKED:` line
  names it for each demo.
