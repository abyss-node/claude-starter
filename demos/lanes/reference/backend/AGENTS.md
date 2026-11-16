# Backend lane

Read this before editing anything under `backend/`. It holds what is true of this stack only; the
root rules file holds what is true of every lane.

## What this lane owns, and what it never edits

- **Owns:** everything under `backend/`: `server.py` (the HTTP server, routes and the error envelope),
  `trails.py` (the catalogue and `trail_view`, which shapes each trail for the API), `trails.json`
  (the data) and `tests/`.
- **Never edits:** `frontend/`. The frontend lane owns it. If a backend change needs the page to show
  something, say so and stop: that is a separate frontend session.
- **To learn something about the frontend**, ask the `consultant` agent rather than reading
  `frontend/` yourself.

## Done means

- `python -m unittest discover -s backend` passes, run from the project root.
- Any new field or rule has a test in `backend/tests/`.
- The server still starts: `python backend/server.py --port 8123`, then `/api/trails` answers.
- The change is committed on its own: a commit that touches `backend/` touches nothing in `frontend/`.

End with which of those you ran and which you only reasoned about.

## What this lane must know

- **The contract.** This lane owns the shape of `GET /api/trails`, and `trail_view` in `trails.py` is its
  single source of truth. Nothing defends it: no schema, no codegen and no type-check fails when the
  frontend and this function drift. Adding a field is safe; renaming or removing one breaks the page
  silently, so do neither without a frontend session to match.
- **The error envelope.** Every error is `{"error": {"code": "...", "message": "..."}}` through
  `send_error_json`. The code is a machine-readable word (`not_found`), not a restated HTTP status.
- **Migrations:** none; the data is a JSON file. Adding a field computed from the stored ones needs no
  change to `trails.json`.
- **The canary test:** `test_every_trail_has_the_contract_fields`. It stands between a refactor and a
  blank page, so never weaken it; extend it when the contract grows.
- **Modern here means:** Python 3.9 or later, standard library only, `pathlib` rather than `os.path`,
  f-strings, type hints with `from __future__ import annotations`. No linter refuses the dated
  construct in this lane; that is a known gap.
