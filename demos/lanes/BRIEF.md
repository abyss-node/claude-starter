# Ridgeline: two lanes, two small changes

**Tier:** S (teaching). **Expected sessions:** two, one per lane. **Runtimes:** Python 3.9 or later and
Node 22 or later, no packages to install.

## What this demo teaches

Ridgeline is a tiny trail board that is already built and already split into **lanes**, the way the
kit's `lanes` command splits a repo with two stacks:

- `backend/` is a Python standard-library HTTP server with a JSON API, tested with `unittest`.
- `frontend/` is a browser page built from ES modules, tested with `node --test`.

The rule a lane sets up: **editing is lane-bound, reading is not.** A session changes one lane. When it
needs to know something about the other lane, it asks the `consultant` agent, which can read but not
edit, instead of reading its own way across the tree. If a task needs the other lane to change, the
session says so and stops; that is a separate session.

`LANES.md` is the map. Each lane has its own brief: the rules file inside its folder, saying what it
owns, what it never edits, and what "done" means there. Read the brief for the lane you are working in before you edit it.

Run the app from the project root with `python backend/server.py` and open http://127.0.0.1:8000.

`npm test` is the project's test command. It runs held-out checks of the whole project and ends with `PASS k/n` or `FAIL k/n`; each lane also has tests of its own, named in its rules file.

## The two tasks

Do them in this order, **one per session**.

### Session 1, backend lane: add a difficulty to every trail

`GET /api/trails` returns `{"trails": [...]}`. Add a `difficulty` field to every trail in it.

- Work out an effort score: the trail's length in kilometres plus its climb in metres divided by 100.
- The difficulty is `"easy"` when the score is below 8, `"moderate"` from 8 up to but not including 15,
  and `"hard"` from 15 up. Exactly those three lower-case words.
- Keep every existing field and every trail as it is. The data file does not need to change.
- The error envelope stays as it is: an unknown `/api/...` path answers 404 with
  `{"error": {"code": "not_found", ...}}`.

Then commit (the kit's `checkpoint` command does this), and stop. Tell the user the frontend task is
next and needs a new session.

### Session 2, frontend lane: show the difficulty

Each trail row on the board shows its difficulty as a badge.

- The badge is an element whose class includes `difficulty` and `difficulty-<level>` (for example
  `difficulty-hard`), and whose text is the level.
- A trail with no difficulty (an older backend) shows no badge, and never the word `undefined`.
- The difficulty is escaped like every other value from the API.
- The rendering lives in `frontend/render.js`, which turns data into HTML strings without touching the
  page; keep it that way, so it stays testable without a browser.

You need the field's exact name and values from the backend. Ask the `consultant` agent for them
rather than opening `backend/` yourself. Then commit, and stop.

## Graded

Held-out checks you cannot see grade the finished workspace. Prose elsewhere in this brief describes the project and makes no extra promises: only the numbered contracts below are checked, and each is checked by at least one test.

1. **The backend starts.** `python backend/server.py --port <free port>`, run from the workspace root, starts and answers `GET /api/health` with 200 and `{"ok": true}`.
2. **The catalogue is kept.** `GET /api/trails` answers 200 with `{"trails": [...]}` holding all seven trails, each with its original `id`, `name`, `length_km` and `climb_m`, valued as in the shipped data (a changed name, a changed number or a dropped trail fails).
3. **Every trail has a difficulty.** Each served trail has a `difficulty` that is exactly `"easy"`, `"moderate"` or `"hard"`, lower case.
4. **The rule.** The score is `length_km + climb_m / 100`; below 8 is `"easy"`, 8 up to but not including 15 is `"moderate"`, 15 and over is `"hard"`. The seven shipped trails include one that scores exactly 8, one exactly 15 and one at 7.99. The rule is also run on a probe catalogue (scores from 0 to over 100, 14.99, 15.01, a climb that is not a multiple of 100) written over `backend/trails.json` in a throwaway copy of the workspace, if the backend reads that file as the shipped one does.
5. **The error envelope.** An unknown `/api/...` path answers 404 with `{"error": {"code": "not_found", "message": "<text>"}}`, where `message` is a string (its wording is not checked).
6. **The badge.** `renderTrailRow` in `frontend/render.js` gives a row with a difficulty exactly one element whose class list includes `difficulty` and `difficulty-<level>` (and no other level's class), and whose text, markup inside it ignored, is the level. Case of the text, the tag used and the quote style are free.
7. **No difficulty, no badge.** A trail without a `difficulty` (the key missing or `undefined`) renders no such element and never the word `undefined` or `null`.
8. **Escaping.** A difficulty, a name or an id holding `<`, `>`, `"`, `'` or `&` (`"><img src=x onerror=alert(1)>`, `x" onmouseover="alert(1)`, `a &amp; b`) puts no new tag and no event-handler attribute into the row. A name reads back from the row's text exactly as sent, and a difficulty that is shown reads back exactly as sent.
9. **The board and the module.** `renderBoard([])` still contains `No trails yet`; a row still shows its trail's name; with trails, every trail's name is on the board. `render.js` imports in Node and renders without a page: it touches no `document`.
10. **End to end.** The real backend's `/api/trails` body, through the real `renderBoard` and `renderTrailRow`, shows every trail with one badge of the right level and its text, and the board holds exactly one badge per trail.
11. **The workspace is its own repository.** Its git top level is the workspace folder itself, and it has at least one commit.
12. **One lane per commit.** Every commit after the initial one touches files in at most one lane (`frontend/` or `backend/`). Rules files (`AGENTS.md`, `CLAUDE.md`, any case) and root files (`README.md`, `LANES.md`, `package.json`) belong to no lane, so changing them never breaks the rule.
13. **Both changes committed, nothing left over.** After the initial commit there is a commit touching `backend/` and a commit touching `frontend/`, and nothing under either folder is untracked, modified or staged-only (`__pycache__` and `.pyc` do not count).

## Not graded

The brief describes these, or you might assume them, but the held-out checks do not test them. They are yours to judge.

- **Not checked, because no test can judge it:** whether the agent asked the `consultant` agent or read across the lane line itself; whether each change happened in its own session; how the page looks.
- The wording of the error `message` (it must be present as a string; the text is yours).
- The capitalisation of the badge text (`Easy` passes), and what is shown for a level outside the three, for `null` or for an empty string.
- Whether `frontend/app.js`, the stylesheet or `index.html` show the badge in a browser: only `render.js` and the served JSON are read.
- Serving the frontend files from the backend, the order of the trails, response headers, and query strings or sub-paths under `/api/trails`.
- The text of your commit messages, the `Verified:` and `Unverified:` trailers, and that the work happened in two sessions.
- The history of merge commits: a commit that only merges is skipped, so lane-crossing changes slipped into one are not seen.
- A backend that does not read `backend/trails.json` (the probe catalogue in item 4 is then skipped; the seven shipped trails are still graded).

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->
## What to watch for

The kit is doing its job when you see these:

- **The lane brief is read first.** At the start of each session the agent reads `LANES.md` and the
  brief for its lane, and names the "done" commands from it.
- **The consultant is asked, not bypassed.** In session 2 the agent should ask the `consultant` agent
  for the shape of the new field. If it opens `backend/trails.py` itself, it worked, but it skipped
  the habit this demo exists to show.
- **It stops at the lane line.** If you ask the frontend session to "also fix the backend", it should
  say that is a backend change for a separate session, not do it.
- **The verifier runs ground truth.** Before calling either task done, the agent should hand the work
  to the `verifier` agent, which runs the project's test command and reports PASS or FAIL from what it
  ran, not from the builder's claim.
- **Checkpoint makes one commit per lane**, each with `Verified:` and `Unverified:` trailers that say
  what was run and what was only reasoned about. The commit guard refuses a commit that carries
  neither.
- **Grade it yourself** with the `demo check` line in step 5, not with `npm test`, which the agent can change. That line is feedback, not proof: the agent has a shell on this machine, as you do, and could tamper with the kit or the grade, so a measured run counts only after CI re-grades the committed folder (the kit's `demos/MEASURING.md`). It reads the git history, so one commit that holds both lanes fails it.

## Suggested edits afterwards

Each is two lanes again, so each is two sessions.

1. **A filter.** Let `GET /api/trails?difficulty=hard` return only the hard trails (backend), then add
   a control on the page that uses it (frontend). An unknown value should get a machine-readable error
   code, not just a 400.
2. **Defend the contract.** Nothing fails today if the two lanes drift: rename `difficulty` in the
   backend and the page goes quiet. Add a small root-level `contract.json` naming the fields of a
   trail, with one test in each lane that checks its side against it. Which lane owns that file?
3. **Run the kit's `lanes` command** in the finished repo and compare its proposal with `LANES.md`. In
   tools that have project commands, it also writes a role command per lane.
