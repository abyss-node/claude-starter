# Writing a demo

A demo is a folder `demos/<name>/`. `<name>` is lower case words joined by
hyphens; it and `app` are what the workspace sees. This file is the one home of
what each part must hold. `demos/tests/test_runtimes.py` holds the framework to
it, and CI's `demo-mutants` job holds every demo to it.

```
demos/<name>/
  demo.json             what the picker and the scripts need to know
  BRIEF.md              the brief, the watch mark, then what the person watches for
  skeleton/             copied into the workspace as it starts
  accept/               the held-out checks: run from the kit, never copied
  accept/mutants/       the fixed mutant list that says the checks are done
  reference/            one solution (or the builder of one); never copied
```

## demo.json

| Key | Holds |
|---|---|
| `title` | The name the person picks it by. It may say what the demo tests, so it never reaches the workspace. |
| `app` | The app's name, which the workspace does see. |
| `tier` | `S`, `M`, `L` or `teaching`. |
| `stack` | `browser`, `node`, `python` or `browser-python` (a Node-side frontend and a Python backend). The rules file states it. |
| `runtime` | `node` for `browser` and `node`, `python` for `python`, `mixed` for `browser-python`. Anything else is refused. |
| `summary`, `not_checked` | One line each. `not_checked` is the `NOT CHECKED:` line, the brief's `## Not graded` in one line. |
| `kickoff` | The first message, or a list of one per session (lanes: two). start.py prints each. |
| `accept_count` | How many results the held-out checks report. More, fewer, or one twice is a FAIL. |
| `accept_runner` | `null`: `node --test` with the kit's reporter on `accept/*.test.mjs`. Or `accept/<file>.py` (required for `runtime: python`) or `accept/<file>.mjs` (node or mixed only). |
| `mutants_runner` | `demos/mutants.py`, the kit's engine. A runner of the demo's own (`demos/<name>/accept/...`) is allowed but must end with `MUTANTS OK` (below); prefer the kit's. |
| `timeout_s` | Seconds the whole held-out run may take, 30 to 7200. Past it the run is stopped and every unreported check fails. With `accept_runner: null` each test also gets `max(60, timeout_s / 10)` seconds. |
| `copy_git` (optional) | `true` when the grade reads the workspace's git history. The graded copy then keeps a cleaned `.git` (no hooks, no alternates, a config of format and line-ending keys only; reflog, index and its flags kept). |
| `fixture` (optional; required with `copy_git`) | `reference/<builder>.py` or `.mjs`: builds a finished workspace, history and all (below). |

## BRIEF.md

- The line `<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->`
  exactly once. Above it is the brief the agent reads; below it, what the
  person watches for.
- A `## Graded` section whose numbered list (`1. `, `2. `, ...) is every
  contract the checks hold, and a `## Not graded` section for what the brief
  describes but no check reads. Prose elsewhere promises nothing.
- Below the mark, the person is told to grade with the `demo check` line, not
  with what the agent ran, and that this grade is feedback, not proof, which
  counts only after CI re-grades the committed workspace. Keep the words
  "feedback, not proof" and "re-grade": `demos/tests/test_demos.py` looks for
  both, since the agent has a shell and can tamper with a local grade.
- No answer from the answers card in `demos/MEASURING.md`, and no franchise
  name from `demos/denylist.txt`.
- The test command: a node or mixed demo says `npm test`. A python demo has no
  package.json; the workspace's rules file names the launcher's
  `demo check <name>`, so the brief says "the test command in the rules file".

## skeleton/

What start.py copies before it writes BRIEF.md (the part above the mark), the
tool's rules file at the top, and package.json, then makes one commit of all of
it, with its final message (`Unverified:` trailer included), before the commit
guard's hooks go in. It never amends that commit, so a demo may grade the root.

- No `BRIEF.md` and no top-level rules file (`CLAUDE.md`, `AGENTS.md`): start.py writes them.
- A lane's rules file below the top ships as `AGENTS.md`; start.py renames it
  to the tool's name for it (`CLAUDE.md` for Claude Code). Call it "the rules
  file in `frontend/`" in prose, so the text is true either way. A check must
  not depend on the name.
- `package.json` (node and mixed only; a python demo ships none): start.py
  keeps every field but `name`, `private` and `description`, and sets
  `scripts.test` to the launcher. No other script whose name holds `test`.
- `.gitignore`: plain patterns only (no `!`, no `**`). What it ignores is the
  program's output (rendered frames, say), which the no-binary-assets rule
  leaves alone.
- It must FAIL the checks, and nothing in it may name the kit's files.

## accept/

check.py copies the workspace's plain files (no links, no `.git` unless
`copy_git`, no `node_modules` or `__pycache__`) into a new temporary folder
outside the workspace and the kit, and starts the runner by absolute path from
that copy's parent folder with:

| Variable | Holds |
|---|---|
| `DEMO_WORKSPACE` | The copy, absolute and native (`C:\...` on Windows). |
| `DEMO_PYTHON`, `DEMO_NODE`, `DEMO_GIT` | Absolute paths of the validated Python 3.9+, Node and git; `""` when absent. Never look a program up on PATH: on Windows that searches the current folder first. |
| `DEMO_RESULT_TOKEN` | This run's token. Only the runner's result lines carry it; never pass it to the workspace. |
| `DEMO_TIMEOUT_S` | `timeout_s`. |
| `DEMO_FAILFAST` | Set when only a FAIL matters (a mutant); a runner may stop at the first failure. |
| `GIT_CONFIG_NOSYSTEM`, `GIT_CONFIG_GLOBAL`, `GIT_CEILING_DIRECTORIES` | git reads no user config and finds no repo above the copy. |

Every `DEMO_*`, `PYTHON*`, `GIT_*`, `NPM_*` and `NODE_OPTIONS` variable from
outside is dropped first, as is every variable whose value names the kit's
clone and every PATH folder inside it. A runner writes nothing in the kit or
the copy; scratch goes in a new temporary folder.

**The checks never import the workspace's code into their own process.** It
could replace `assert` and pass everything. They run it in processes of their
own and assert on what comes back. Two static tests enforce it on every file in
`accept/` outside `accept/mutants/`.

### Node checks (`runtime: node` or `mixed`)

- One `accept/*.test.mjs` per area, `node:test` and `node:assert/strict` only.
  Imports: `node:` builtins, `../../probe.mjs` and `./` files of `accept/`.
  No dynamic `import()`, no `pathToFileURL(...)` import of the workspace.
- Reach workspace code only through `demos/probe.mjs`: `values(module, calls)`,
  `outcomes(...)`, `notRefused(...)` for calls with plain arguments (each a
  Node process under `--permission` that can read the copy and the probe
  files only), and `scenario(file, name, args)` for more (stepping a world
  10,000 times, freezing an argument, a callback): a function exported by an
  `accept/` module, run in such a process beside the workspace, given
  `{ load, withoutClocks }` (`await load('src/x.js')`; clocks below),
  returning plain data. It returns what it saw, never a verdict; the test
  compares. Each call takes `{ timeoutMs }` (default 30000), so an endless
  loop or a `process.exit` in the workspace fails that check instead of
  hanging the run. Batch calls: each probe is one process start.
- A scenario's process may also read the scenario's module and the `./*.mjs`
  modules of `accept/` it imports, followed through their static imports
  (`scenarioReads` in probe.mjs), and nothing else of the kit. The folder is
  never granted: a folder's grant covers everything below it, `accept/mutants/`
  included, whose `find` strings quote the reference. `scenario()` refuses,
  before any process starts, a scenario that imports anything but those and
  `../../probe.mjs` (a `node:` builtin, below, a JSON file, a module under
  `mutants/` or a file outside its folder). Whatever a scenario imports, the
  workspace's code in that process can read and import too, so nothing taken
  from `reference/` goes in a scenario's imports.
- **What a scenario's process freezes.** The workspace's code shares that
  process with the scenario, so before any workspace module loads,
  `probe-child.mjs` freezes what a scenario observes with. A verifier's
  workspace once changed `Number.prototype.toFixed`, `Object.getPrototypeOf`
  or `Math.random`, and another workspace a scenario's own table of seeds, in
  3 to 7 lines each, and hid a real bug every time. Frozen, with each global
  name for them made read-only:
  - the language's built-ins: every global constructor and namespace of the
    language (`Object`, `Function`, `Array`, `Number`, `String`, `Boolean`,
    `Symbol`, `BigInt`, `Math`, `JSON`, `Reflect`, `Proxy`, `Map`, `Set`,
    `WeakMap`, `WeakSet`, `Promise`, the `Error` types, `Date`, `RegExp`, the
    typed arrays, `ArrayBuffer`, `DataView`, `Intl`, `Iterator` and the rest
    this Node has), their prototypes, and the iterator, generator and
    async-function prototypes that no global names;
  - Node's `structuredClone`, `TextEncoder`, `TextDecoder`, `URL`,
    `URLSearchParams`, `Buffer`, `queueMicrotask`, `atob` and `btoa`, and
    `node:v8`, which writes the answer;
  - what each kit module in the process exports (the scenario's and those it
    imports), since the workspace's code can import them by URL and gets the
    very modules the scenario uses. A module there that exports something
    freezing cannot keep unchanged (a `Map`, a `Set`, a `Date`, a typed array)
    makes every scenario of it fail: export an array or a plain object.

  Assigning to any of it, or defining it anew, throws (at the workspace
  module's load, for a module that tries). Code that sets `name`, `message`,
  `constructor`, `toString`, `toLocaleString` or `valueOf` on objects of its
  own still works. Taken away, so that calling them throws, by every route to
  them (an import, `process.getBuiltinModule`, `require`): all of `node:v8`
  but its serializer and its statistics, and `node:async_hooks`' `createHook`
  and `executionAsyncResource`. A heap snapshot or `v8.queryObjects` reads
  every value in the process, the answer key below among them, and a promise
  hook is handed every promise made after it, with what it resolves to: a
  planted workspace read the key from `v8.getHeapSnapshot()` and had an answer
  line of its own believed, in 9 lines, and another rewrote the record a
  scenario's helper resolved with. The permission model allows both. Taken
  away too: `node:module`'s `syncBuiltinESMExports`, which re-points every
  named import of a builtin at what the builtin's module holds now. Not
  frozen: the global object (code may add globals), `process`, `console`, the
  timers, `performance` but for its `now`, and every `node:` module but
  `node:v8` and `node:async_hooks`. The probe itself uses three of those,
  `node:fs`, `node:module` and `node:util`, so it holds what it calls of them
  in constants of its own, taken from each module's object before any
  workspace module loads, never by a named import: a planted workspace set
  `node:fs`'s `writeSync` to a function of its own and called
  `syncBuiltinESMExports`, and the probe's named import of `writeSync` then
  handed that function the answer line, key and all, to rewrite. And a
  scenario imports no `node:` module (`scenario()` refuses one, above): their
  functions read what the workspace's code can set, `util.inspect`'s
  `defaultOptions` for one, which no freeze holds.
  The answer line also carries a key the process reads from stdin before any
  workspace module loads, so a line the workspace's code prints is not taken
  for it. And the answer holds copies: what a call or a scenario returns is
  copied (`structuredClone`) as it returns. The serializer asks a typed array
  for its length and its bytes by property reads, and a planted typed array of
  the workspace's own class answered 0 and then bytes that were read back as
  the rest of its scenario's record.
- **Clocks.** `withoutClocks(fn)` runs `fn` with `Math.random`, `Date.now` and
  `performance.now` throwing (until its promise settles, when it returns
  one), and throws, naming the clock, when the code read one and caught the
  throw. They are the probe's own functions from before the freeze, so the
  workspace's code can neither swap them back nor reach the switch. Never
  assign to `Math.random` in a scenario: it throws. `new Date()`,
  `process.hrtime` and `node:crypto` are not taken away.
- **What is left to the workspace's code: its own values.** A getter, a
  Proxy's traps, or a `toJSON` or `valueOf` of its own runs as a scenario reads
  the value, so a value can show one reader one thing and the next reader
  another. So a scenario returns the values themselves: numbers, arrays,
  copies taken when it looked (`structuredClone`, JSON text, or a digest of
  that text where two runs are only compared for equality), and leaves
  formatting and classifying (`toFixed`, `join`, a kind) to the test.
  monster-tamer-lite's scenarios do; spin-clash's and pocket-region's still
  work out kinds beside the workspace (their `helpers.mjs` `kinds`), which the
  freeze keeps safe from changed built-ins, not from the value's own code.
  The copy refuses a Proxy and a function; what it cannot carry, a scenario
  records beside it (a class instance arrives as a plain object, a getter as
  one value it gave: monster-tamer-lite's `fixtures.mjs` `uncopied`; a
  `Buffer` arrives as a `Uint8Array`). Past that, no other way is known for the
  workspace's code to change what a check sees than by changing the answers
  it gives, wrong on purpose or not. Wrong on purpose includes two-faced: the
  code can tell which scenario runs (from `process.argv`, a stack trace or the
  inputs) and lie only there. So a check whose expected value is worked out
  from a value the workspace reports cannot catch a bug that lie covers:
  monster-tamer-lite's Graded 11 derives the snare's outcome from the draw
  `nextFloat` reports, and a workspace that shifts two draws only in
  scenario 11 hides an off-by-one there. Where that matters, work the
  expected value out from inputs the scenario chose. That is a record of what
  has been tried, not a proof: the `writeSync` and typed-array routes above were found after
  this text said none was left. All of this holds within Node's permission
  model, which is a seat belt, not a sandbox (`demos/MEASURING.md`).
- Reading a workspace file as text (an `index.html`) from the test is fine.
- A mixed demo starts its backend from the test: `DEMO_PYTHON` by absolute
  path, `-B`, a free port, the copy as cwd, an environment without
  `DEMO_RESULT_TOKEN`, output piped (never inherited), killed after. It runs
  outside any permission model, as Python checks do (below).
- Results come from the kit's reporter: one per top-level test. Keep
  `accept_runner: null`. An `.mjs` runner of the demo's own runs as
  `node <runner>` and must print result lines (below) itself; a `run.mjs`
  that prints `PASS k/n` text is not a runner here.

### Python checks (`runtime: python`)

- `accept_runner` is `accept/<runner>.py`, run as
  `<DEMO_PYTHON> -I -S -B -X utf8 <kit>/demos/<name>/accept/<runner>.py`:
  isolated (no `PYTHON*`, no user site, not its own folder on `sys.path`),
  no site-packages, no bytecode in the kit, UTF-8 output. Standard library
  only, Python 3.9.
- Build it on `demos/acceptkit.py`:

  ```python
  import sys
  from pathlib import Path
  sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parent)]
  import acceptkit as ak
  import test_mine                      # the checks, next to the runner
  ak.main(test_mine.TESTS)              # [(name, function), ...] in order; exits 0, 1 or 2
  ```

  A check passes when it returns and fails on any exception (its first line
  is the reason). `ak.workspace()` is the copy; `ak.run(argv, timeout, cwd=,
  env=, input=)` runs a workspace process with its output captured, from a
  scratch cwd, with `ak.child_env(**extra)` (no `DEMO_*`, an empty HOME;
  `extra` sets, say, `PYTHONHASHSEED`); `ak.python_argv(*args,
  stdlib_only=True)` is the validated Python with `-s -B -S`;
  `ak.program('git')` is `DEMO_GIT`; `ak.scratch()` is an empty folder removed
  at exit.
- No `exec`, `eval`, `__import__`, `importlib` loading, `runpy` or
  `module_from_spec` anywhere in `accept/` outside `accept/mutants/`.
- **Python has no permission model like Node's.** A workspace process can read
  and run any file the person can, the kit's `reference/` included. The copy
  in a temporary folder, the empty HOME, no variable naming the kit and the
  rule "no code that names the kit's files" make that a step, not a wall:
  the workspace's own rules file names the launcher's path in the clone, and
  `demos/MEASURING.md` ("Where the kit is") lists every other way there. No
  check of a demo's own can close it, so none may claim to.

### Result lines (an own runner, `.py` or `.mjs`)

One line per check on stdout, then exit 0 when all passed, 1 when any failed,
2 when the checks could not run:

```
{"demo_event": "test", "token": "<DEMO_RESULT_TOKEN>", "ok": true, "name": "<distinct name>", "nesting": 0, "kind": "test", "file": null, "error": null}
```

`error` is the first line of the reason when `ok` is false. A line without the
token, a name reported twice, or an exit code that disagrees with the lines
fails the grade. No `PASS k/n`, `NOT CHECKED` or `RECORD` lines: check.py
prints those.

## reference/

A finished workspace that passes every check: check.py's copy rule compares a
workspace with its lines (those the skeleton and BRIEF.md also hold do not
count), and CI grades it. A demo graded on history (`copy_git`) cannot commit a
`.git`, so its `fixture` builds one:

```
<DEMO_PYTHON -I -S -B -X utf8 | DEMO_NODE> <copy of reference>/<fixture> --skeleton <kit>/demos/<name>/skeleton --out <empty folder>
```

from a temporary cwd, with the variables above (no workspace, no token), git
kept from user config, within `timeout_s`. It makes the finished repo in
`--out`, every commit's identity and date fixed, and exits 0. It runs on a
mutated copy of `reference/`, so it reads its own files next to it
(`Path(__file__).parent`), never the kit's `reference/`.

## accept/mutants/: what "done" means

```
python demos/mutants.py <name> [--only <text>...] [--jobs N] [--verbose]
```

It grades, exactly as a workspace is graded: `reference/` (or its fixture)
must PASS; the folder start.py makes from the skeleton, for Claude Code, must
FAIL; every mutant must FAIL; every legal variant must PASS; every `## Graded`
number must have a mutant. Prints `reference: PASS k/n`, `skeleton: FAIL k/n`,
`survivor:` lines, `KILLED k/n`, `LEGAL PASS k/m`, then `MUTANTS OK` (exit 0)
or `MUTANTS NOT OK` (1); exit 2 when a case cannot run.

- `accept/mutants/NNN-slug.json`:
  `{"id", "graded_item", "description", "file", "find", "replace", "also"?, "expect"?}`.
  `file` is relative to `reference/`; `find` occurs there exactly once (written
  with `\n`, it matches `\r\n` in a CRLF file). `graded_item` is a `## Graded`
  number, or `null` when the brief has no such list.
- `accept/mutants/legal/*.json`: the same without `expect` (`graded_item`
  optional): a change the brief allows, which must PASS.
- `also`: more edits, each `{"file"?, "find", "replace"}`, `{"file", "create", "encoding"?}`
  (a new file) or `{"file", "delete": true}`.
- `expect`: parts of check names that must be among the failures, so a mutant
  dies for its own reason.
- A mutated `.py`, `.js` or `.mjs` file must still parse.
- Ids are distinct across both lists.

CI's `demo-mutants` job runs this for every `demos/*/demo.json` on ubuntu at
Python 3.9 and Node 22.13.0 exactly, so nothing may need a newer runtime. An
own `mutants_runner` runs after the reference and skeleton cases, with
`DEMO_CHECK`, `DEMO_NAME`, `DEMO_DIR` and the program variables; it grades only
through `<DEMO_PYTHON> <DEMO_CHECK> <name> --accept-only --dir <folder>` and
must end its output with `MUTANTS OK`.

## What check.py adds to every grade

After the held-out checks, five rules on the copy, each one result: one test
entry point (node and mixed: package.json `test` exactly as start.py wrote it,
no other test script, no CI config, Makefile, justfile, taskfile, `tox.ini`,
`noxfile.py` or `.npmrc`; python: none of those and no package.json test
script); no binary assets; original names; not copied from `reference/` (more
than ten shared lines of 20 or more characters); no code that names the kit's
files (its path in any spelling, `.claude-starter`, `installs.json`,
`demos/<name>/reference`; documentation files are not read). Then `PASS k/n` or
`FAIL k/n`, the `NOT CHECKED` line, the LOCAL GRADE line and the `RECORD`.
