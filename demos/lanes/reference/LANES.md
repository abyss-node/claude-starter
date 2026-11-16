# Lanes in this repo

This repo is split into lanes, the way the kit's `lanes` command sets one up. **Editing is
lane-bound; reading is not.** A session works in one lane at a time. To learn something about the
other lane it asks the `consultant` agent, which can read but not edit. If the answer means the other
lane has to change, the session says so and stops; that is a separate session.

| Lane | Owns | Evidence it is a lane | Its brief |
|---|---|---|---|
| frontend | `frontend/` | Browser ES modules, tested with `node --test` | the rules file in `frontend/` |
| backend | `backend/` | Python standard library `http.server`, tested with `unittest` | the rules file in `backend/` |

The tooling, the test runner and the idiom all change at the `frontend/` / `backend/` line, which is
what makes it a seam rather than just two directories.

**No ops lane.** The root holds `package.json`, `README.md`, `.gitignore` and this file: small enough
to read in one pass, so it gets no lane of its own. Any session may edit root files.

## What each entry is for

- **The rules file in `frontend/` and in `backend/`** (named as your tool names its rules file): each
  lane's invariants, loaded when a file in that folder is read. They exist because a session told to hold two
  specialisms behaves as a generalist across both.
- **This file:** the map. It exists so a session can tell which lane a file is in without reading
  either lane's code.

No per-lane consultant: the global one covers a repo this small. Add one only when a lane gains an
artefact worth hardcoding into it, such as a generated schema.
