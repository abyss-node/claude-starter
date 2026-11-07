---
name: frontend-build-guardrails
description: >-
  Use when building or changing an interactive UI component, form, client-side
  data fetching, browser-side auth/token handling, accessibility fixes, Core Web
  Vitals/performance, or Next.js Server Actions or env vars (React/Next.js and
  similar). Not for purely visual styling or copy changes (contrast and
  accessibility fixes do count).
---

# Frontend Build Guardrails

Checks to run *while* building UI. The failure mode this exists to catch:
generated UI that looks right in the demo, then breaks the moment data is empty,
slow, or hostile — and quietly excludes anyone not using a mouse. Examples are
React/Next.js; the checks apply to any framework.

## Prime directive: build for real data and real users, not the demo

The happy-path render is the easy 80%. The value is in the states you didn't
screenshot: empty, loading, error, too-long, too-many, none-selected, offline,
and the user navigating by keyboard or screen reader. Assume every list can be
empty, every fetch can fail, and every string can be longer than your mockup.

Default to the simplest design that works (see the Complexity budget section in AGENTS.md, if you have one): a component
with `useState` and a fetch is the correct default, not a thing to apologize for.

## Checks by activity

### Rendering dynamic data / lists
- Handle all four states explicitly: loading, error, empty, and populated. A
  component that only renders the array is unfinished.
- Use stable, identity-based keys — never the array index for lists that can
  reorder, insert, or delete.
- Virtualize lists that can grow large.

### Fetching data
- Plain `fetch` in a component is fine. Hand-rolled, guard against stale
  responses (search-as-you-type lets an older response land last) with an
  `AbortController` or request id, and dedupe identical in-flight requests.
- A server-state library (TanStack Query, SWR) is an option when caching and
  refetch needs grow, not the default.
- Optimistic updates need a rollback path for when the mutation fails.
- Avoid request waterfalls: fetch independent data in parallel and start it
  early (route loaders, prefetch), not in nested effects.

### Forms & user input
- Validate on the client for fast feedback, but **re-validate on the server** —
  client validation is UX, never a security boundary.
- Every input needs an accessible name: a visible `<label>` preferred,
  `aria-labelledby` is valid, a placeholder alone is not enough (it disappears on
  input and is announced inconsistently). Link errors with `aria-describedby`
  and set `aria-invalid`; on submit, move focus to the first error or use a live
  region so the error is announced.
- Controlled inputs need both `value` and `onChange`.
- Debounce expensive change handlers (search, autosave).

### Accessibility (not optional, not a phase-2)
- Reach for semantic HTML first: a `<button>`, not a `<div onClick>`. You get
  keyboard operability, focus, and roles for free.
- Everything interactive must be keyboard-operable with a visible focus
  indicator.
- Images need meaningful `alt`; decorative images need empty `alt=""`.
- Never rely on color alone to convey state. Contrast: 4.5:1 for normal-size text;
  3:1 for large text, UI components, and focus indicators.
- Use ARIA to fill gaps in native semantics, not to replace them — a wrong ARIA
  role is worse than none.

### Client-side security
- **Never** inject unsanitized input as HTML (`dangerouslySetInnerHTML`,
  `innerHTML`) — this is the XSS front door. Sanitize or render as text.
- Don't hand-roll auth-token storage in `localStorage`/`sessionStorage`: any XSS
  can read it. Prefer httpOnly, Secure, SameSite cookies plus CSRF protection
  (httpOnly stops token theft, not XSS acting as the user). If
  your auth provider's SDK stores tokens client-side, don't rip it out; keep XSS
  defences and CSP tight instead.
- Treat everything from the client as forgeable. The server authorizes.
- Add a Content-Security-Policy. Prefer a strict nonce- or hash-based one
  (host-allowlist CSPs are routinely bypassed), but in Next.js nonces force every
  page to dynamic rendering (no static/ISR/CDN caching), so decide that
  trade-off deliberately.

### Next.js / React Server Components
- Server Actions are public POST endpoints: authenticate, authorize, and
  validate input inside each one. Hiding the button protects nothing.
- Anything `NEXT_PUBLIC_*` ships to the browser. No secrets there.
- Never trust `params`/`searchParams`; validate them like any request input.
- Secrets and DB access stay in server components, route handlers, and actions.
  Put DB and secret access in modules marked `import 'server-only'`, which makes
  the build fail if a client component imports them. Props passed to a client component are
  sent to the browser — pass what the UI needs, not the whole record.

### State management
- Escalate deliberately: local state → lifted state → server-state library →
  global store. Reaching for Redux/global state by default is the common
  over-engineering tell.
- Derive state, don't duplicate it. Storing a value you could compute from
  existing state creates sync bugs; compute during render, not in an effect.

### Performance
- Don't optimize on a guess: get Core Web Vitals (LCP, INP, CLS) from a
  Lighthouse run or field data, or ask the user for them.
- Images are usually the biggest LCP lever: right-size, use modern formats
  (webp/avif), set explicit dimensions; reserve space for async content (CLS).
- Lazy-load routes and heavy below-the-fold components; watch bundle size.
- Memoize only measured hotspots. The React Compiler auto-memoizes where it's
  enabled; profile before hand-writing `useMemo`/`memo`.

## Before you call it done
- **Keyboard-only pass** through the main flow: reach and operate everything,
  focus visible and sensible. Use a browser tool if you have one; otherwise ask
  the user.
- **Real-data pass** — empty, slow, failed, and overflowing content. Nothing
  should crash or overflow silently.
- Run an automated a11y check (axe / Lighthouse) and fix the criticals.
- No secrets, tokens, or API keys in the client bundle.
- Wrap risky subtrees in an error boundary so one component can't blank the page.
- Anything you could not actually run goes under Unverified in your report —
  never claim a check you didn't perform.
