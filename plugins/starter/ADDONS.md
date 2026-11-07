# Recommended add-ons

Pointers only; nothing here is bundled. Rule of thumb: add one when a task has
been done badly twice, not in anticipation. Every installed skill costs
attention on every session.

## gstack

A large skill pack (https://github.com/garrytan/gstack): `/review`, `/ship`,
`/qa`, `/investigate`, `/spec` and many more.

- Install when you ship web apps regularly and want a ready-made review/QA/ship routine.
- Do not install if you are new to Claude Code or write small scripts. It adds a long skill list to the listing budget of every session, which crowds out your own instructions.
- Install: follow the README in the repo.

## frontend-design (official plugin)

Guidance for distinctive UI instead of templated defaults.

- Install when you build or restyle user interfaces.
- Skip if you work on backend, data or CLI code.
- Install: `/plugin install frontend-design@anthropic-plugin-directory`
- If that fails, open `/plugin`, go to Discover, and search by name; `/plugin marketplace list` shows which marketplaces you have.

## Vercel plugin

Deploy, env var and log tooling for Vercel projects.

- Install only if you deploy on Vercel.
- Skip otherwise; it brings a lot of skills and tools.
- Install: `/plugin install vercel@anthropic-plugin-directory`
- If that fails, open `/plugin`, go to Discover, and search by name; `/plugin marketplace list` shows which marketplaces you have.

## Claude in Chrome

Lets Claude drive your real browser: click, fill forms, read console and pages.

- Install when you need to test a web app end to end or work behind a login.
- Skip if you never need Claude to see a rendered page.
- Install: add the Claude in Chrome extension from the Chrome Web Store, then run `/chrome`.
