---
name: backend-build-guardrails
description: >-
  Server-side correctness and security checks. Use when adding or changing an
  HTTP endpoint or Next.js Server Action, SQL query or migration,
  auth/permission check, background job, cache, or outbound API call; when
  handling money, dates/timezones, passwords or user input, or fetching
  user-supplied URLs; or before adding queues, microservices or other
  infrastructure. Not for frontend styling, one-off scripts, ad-hoc analysis
  queries, or docs.
---

# Backend Build Guardrails

A short set of checks to run *while* building, not after. Default to the simplest design that works (see the Complexity budget section in AGENTS.md, if you have one).
Before adding a queue, a second datastore or another service, name the constraint
that needs it.

## Checks by activity

Run the block that matches what you're touching. These catch the silent bugs
that "looks right" code hides.

### Touching a database query or data access
- Never build SQL by string concatenation with user input. Use parameterized
  queries / prepared statements — this is both a correctness and an injection
  concern.
- Identifiers (table/column names, `ORDER BY` column and direction) can't be
  parameterized. Map them through an allowlist; never interpolate them raw.
- Watch for **N+1**: a query inside a loop over rows. Fetch in a set (join or
  `WHERE id IN (...)`) instead.
- Check the query plan (`EXPLAIN`) for the hot queries. A full scan is fine at
  100 rows and a fire at 1M.
- Wrap multi-statement writes that must succeed together in a transaction. Know
  the isolation level you're relying on.
- Make schema changes backward-compatible (expand → migrate → contract) so a
  deploy doesn't break the running old version.

### Handling money, dates, or user input
- Money: integer minor units or fixed-precision decimal. **Never floats.**
- Time: UTC for instants that already happened. For future or recurring
  local-time events (a 9am meeting, a monthly bill) store local time + IANA zone
  ID (`Europe/Berlin`); offset rules change. Do calendar math (add a day,
  business days) in the local zone.
- Text: assume UTF-8; don't assume ASCII length == byte length == display width.
- Validate and normalize input at the boundary — type, range, length, format —
  before it reaches business logic. Reject early; don't sanitize silently in ten
  places downstream.

### Adding a call to an external service or network
- Set an explicit timeout. A call with no timeout is a hang waiting to happen.
- Decide the failure behavior *before* the happy path: retry, fall back, or fail
  fast? Only retry idempotent operations.
- If you retry, use exponential backoff **with jitter**, and cap attempts.
- For retried writes, ensure idempotency (an idempotency key or a naturally
  idempotent operation) so a retry can't double-charge / double-create.
- Consider what happens when this dependency is down, not just slow.

### Writing an API endpoint
- Validate the request body against a schema; return clear 4xx on bad input,
  5xx only for genuine server faults.
- Paginate any list endpoint that can grow. Prefer cursor-based over offset for
  large or changing sets.
- Make it idempotent where the semantics allow (especially POST that creates).
- Version the contract if external clients depend on it; don't silently change
  response shapes.

### Auth & security
- Authentication (who you are) and **authorization** (what you may do) are
  different — check both. A logged-in user is not automatically an allowed user.
- **Object-level authorization on every handler that takes an ID.** For
  `GET /invoices/123`, scope the query by owner/tenant, not just by ID. Missing
  this (IDOR/BOLA) is #1 on the OWASP API Top 10 and extremely common.
- Passwords: a vetted library's Argon2id (scrypt if unavailable; bcrypt only for
  legacy systems, and cap input at 72 bytes). The library generates and embeds the salt — never hand-roll
  salting. Never store or log plaintext credentials or tokens.
- Fetching a user-supplied URL (webhooks, link previews, imports) invites SSRF:
  allowlist hosts, resolve the hostname yourself, reject private/loopback/
  link-local IPs (incl. cloud metadata 169.254.169.254 and IPv6 equivalents),
  then connect to that validated IP. Disable automatic redirects, or
  re-validate each hop the same way.
- Cookie-based auth needs CSRF protection on every state-changing request:
  your framework's CSRF token, or a `Sec-Fetch-Site` check with an Origin-header
  fallback. SameSite alone is not enough. (Next.js Server Actions check Origin
  for you; your own route handlers do not.)
- Keep secrets out of source and logs; read them from a secret store / env.
- Enforce least privilege on every credential and role.

### Background jobs / async / queues
- Jobs must be idempotent — they will be retried.
- Handle poison messages: a dead-letter path so one bad item doesn't wedge the
  queue.
- Make consumers handle at-least-once delivery (dedupe on a key); exactly-once
  is mostly a myth at the transport layer.

### Caching
- Decide the invalidation strategy at the same time you add the cache — a stale
  cache with no invalidation plan is a bug generator.
- Set a TTL. Guard against stampede/thundering-herd on expiry for hot keys.
- Never cache per-user/authorized data under a shared key.

## Before you call it done
- **Tests exist for the logic you wrote** — at minimum the core happy path and
  the failure/edge cases you just reasoned about. Untested generated code is how
  "it looked right" ships broken.
- Errors are handled, logged with enough context (include a correlation/request
  id), and surfaced — not swallowed.
- No secrets committed; no plaintext sensitive data in logs.
- Migrations are reversible or forward-safe; there's a way to roll back the
  deploy.
- Basic observability: the new path emits at least a log line and, where it
  matters, a metric, so a failure is visible without a debugger.
- Run against a local/dev target; ask before touching a shared database or
  spending money.
- Anything you could not actually run goes under Unverified in your report —
  never claim a check you didn't perform.
