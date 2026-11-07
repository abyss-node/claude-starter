---
name: llm-app-guardrails
description: >-
  Use when writing or changing code that calls an LLM API (Anthropic, OpenAI,
  etc.) or acts on its output: prompts in code, RAG, embeddings/vector search,
  tool use/agents, MCP servers or tools exposed to a model, structured output.
  Not for editing Claude Code config, CLAUDE.md, or skills.
---

# LLM App Guardrails

Checks to run *while* building LLM features. The failure mode this exists to
catch: a feature that demos beautifully on three hand-picked prompts, then in
production hallucinates, gets hijacked by pasted text, or quietly runs up a
bill — shipped on vibes, with no eval.

## Prime directive: treat model output as untrusted, and never ship on vibes

First, **model output is untrusted input** — wrong, malformed, or
attacker-influenced — so validate it and bound its authority like user input.
Second, you **cannot evaluate an LLM feature by eyeballing a few cases** — you
need a repeatable eval set, or every prompt change or model swap is blind.

## Checks by activity

### Keys, spend & secrets
- Never call the model API from a browser or app with your key; anyone can
  extract it. Proxy through a server.
- Set a hard limit (not just an alert) in the provider console before anything
  goes live.
- Assume the system prompt leaks. No secrets or internal-only data in prompts.

### Acting on model output
- Never pass model output directly into `exec`, SQL, a shell, a filesystem path,
  or `innerHTML` without validation and sandboxing. "The model usually returns
  safe text" is not a security model.
- Prefer native structured outputs / strict tool schemas (constrained decoding)
  over asking for JSON. What still fails: refusals, truncation at max tokens
  (check `stop_reason` / `finish_reason` / `status: incomplete`), and values that parse but are wrong —
  validate those.
- Define the behavior when validation fails (retry, fallback, surface an
  error) — not an unhandled exception.

### Prompt injection & tool authority ★
- User input and retrieved documents can contain instructions that override
  yours. Keep trusted instructions structurally separate from untrusted content,
  and don't assume the model will ignore "ignore previous instructions."
- Grant tools the least authority of the least-trusted input in the context. If
  untrusted text is in the prompt, the model must not be able to trigger
  destructive or high-privilege actions unchecked.
- Private data + untrusted input + an outbound channel = exfiltration. Rendered
  markdown images and links in model output can send context to an attacker's
  URL; don't auto-render them, or allowlist domains.
- Gate irreversible tool actions behind validation or human confirmation.

### Evaluation — build it before you iterate ★
- Create a golden eval set (real inputs + expected properties) before tuning
  prompts. Without it, every prompt change is an unmeasured guess.
- Keep it as a regression suite: run it when you change the prompt, the model, or
  the retrieval, so you catch the fix that broke three other cases.
- Measure the properties that matter (accuracy, groundedness, format validity).
  LLM-as-judge is useful but needs its own spot-checks — don't trust it blindly.

### RAG
- If the corpus fits in context, put it all in context first, and use prompt
  caching so you don't pay for it every call.
- Retrieval quality caps output quality. Measure retrieval (did the right chunk
  come back?) separately from generation, or you'll tune the wrong half.
- Chunk with intent; return and cite sources. Try hybrid keyword (BM25) + vector
  search first. Add a reranker if your retrieval eval shows it helps.
- Handle "no relevant context found" explicitly — forcing an answer from nothing
  is how you manufacture confident hallucinations.

### Cost & latency
- Cost and latency scale with tokens in context. Cap context size.
- Provider prompt caching is usually the biggest cost lever for repeated long
  prompts: put stable content (tools, system prompt, documents) first and varying
  content last. Cache reads are heavily discounted, but on Anthropic you must opt
  in (`cache_control`), writes cost more than normal input, and prompts under the
  model's minimum length aren't cached. Check the usage fields to confirm hits.
- Scope any response cache per user/tenant. Semantic caching answers near-miss
  queries with someone else's answer — avoid unless the domain tolerates it.
- Stream responses for perceived latency; set per-request budgets.
- Match model to task; a small model often suffices for classification.

### Reliability
- Official SDKs already retry with backoff by default — set their timeout and
  retry count; don't stack another retry loop. Raw HTTP: back off, honor
  `Retry-After`.
- A fallback model must pass the same evals before it serves traffic.
- Degrade gracefully when the model is unavailable; handle mid-stream failures.

### Determinism, logging & privacy
- Pin an exact model ID (not a `-latest` alias) and track deprecations; old
  models get retired.
- Temperature 0 was never deterministic on hosted APIs, and current Claude models
  and OpenAI reasoning models don't accept sampling parameters at all. Get
  consistency from structured outputs and evals, not sampling settings.
- Version prompts like code.
- Log tokens and latency per call. Logging full prompts and responses creates
  a PII store: redact, set retention, restrict access.

### Agents / multi-step loops
- Bound the loop: max steps and a clear termination condition.
- Validate every tool call's arguments before executing.
- Cap total cost/tokens per task.

## Before you call it done
- **Eval set passes** and is wired to run on prompt/model changes.
- **Injection test**: paste adversarial instructions into every user-controlled
  and retrieved field; confirm tools/authority hold.
- **Structured outputs** are validated with a defined failure path.
- **Cost per request** is measured and a spend limit is set.
- Run against a dev key or small sample; ask before spending real money.
- Anything you could not actually run goes under Unverified in your report —
  never claim a check you didn't perform.
