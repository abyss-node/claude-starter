# Frontend lane

Read this before editing anything under `frontend/`. It holds what is true of this stack only; the
root rules file holds what is true of every lane.

## What this lane owns, and what it never edits

- **Owns:** everything under `frontend/`: `index.html`, `style.css`, `app.js` (the browser entry, the
  only file that touches the DOM or calls `fetch`) and `render.js` (pure functions from API data to HTML
  strings, so they can be tested without a browser).
- **Never edits:** `backend/`. The backend lane owns it. If a frontend task needs the API to change,
  say so and stop: that is a separate backend session.
- **To learn something about the backend** (a field's name, type or meaning), ask the `consultant`
  agent rather than reading `backend/` yourself. Reading another lane's code drags its idiom into this
  one.

## Done means

- `node --test frontend/render.test.js` passes, run from the project root.
- Any new rendering behaviour has a test in `frontend/render.test.js`.
- The change is committed on its own: a commit that touches `frontend/` touches nothing in `backend/`.

End with which of those you ran and which you only reasoned about.

## What this lane must know

- **The contract.** The backend owns the shape of `GET /api/trails`: `{"trails": [ ... ]}`, one object per
  trail. Nothing defends it: no schema, no codegen and no type-check fails when the two sides drift. A
  renamed field breaks the page silently. Treat every field as possibly missing, and render nothing
  rather than the word `undefined`.
- **The error envelope.** API errors are `{"error": {"code": "...", "message": "..."}}`. Branch on
  `code`; `message` is prose for people and may change.
- **Migrations:** none in this lane.
- **The canary test:** `names are escaped` in `render.test.js`. Every value from the API goes through
  `escapeHtml` before it reaches HTML, because `app.js` assigns the result to `innerHTML`. Never weaken
  that test or skip escaping for a field that "can only be a known word".
- **Modern here means:** ES modules with `import`/`export`, `const` and `let`, template literals, no
  build step and no npm dependencies. Nothing refuses a dated construct mechanically in this lane
  (there is no linter); that is a known gap.
