// A tiny n-gram language model: counts which token follows which context.

const TOKEN_RE = /[a-z0-9']+|[.!?,;:]/g;

// Lower-case the text; a token is a run of a-z, 0-9 and apostrophes, or one
// of . ! ? , ; : on its own. Everything else separates tokens and is dropped.
export function tokenize(text) {
  return String(text ?? '').toLowerCase().match(TOKEN_RE) ?? [];
}

// Highest probability first; equal probabilities in code-unit order of the token.
export function compareEntries(a, b) {
  if (b.p !== a.p) return b.p - a.p;
  return a.token < b.token ? -1 : a.token > b.token ? 1 : 0;
}

function bump(map, key) {
  map.set(key, (map.get(key) ?? 0) + 1);
}

function toEntries(counts) {
  let total = 0;
  for (const c of counts.values()) total += c;
  const entries = [];
  for (const [token, c] of counts) entries.push({ token, p: c / total });
  return entries.sort(compareEntries);
}

// order n uses up to n-1 previous tokens as context. order 1 is word frequency only.
export function train(text, order = 3) {
  if (!Number.isInteger(order) || order < 1) {
    throw new RangeError(`order must be an integer >= 1, got ${order}`);
  }
  const tokens = tokenize(text);
  const unigram = new Map();
  for (const t of tokens) bump(unigram, t);
  const contexts = new Map(); // "w1 w2" -> Map(next -> count)
  for (let i = 1; i < tokens.length; i++) {
    for (let len = 1; len <= order - 1 && len <= i; len++) {
      const key = tokens.slice(i - len, i).join(' ');
      let next = contexts.get(key);
      if (!next) contexts.set(key, (next = new Map()));
      bump(next, tokens[i]);
    }
  }
  return { order, unigram, contexts, tokenCount: tokens.length };
}

// Backoff rule: use the longest suffix of the context (at most order-1 tokens)
// that was followed by at least one token in training. If no suffix was, fall
// back to the frequency of every token in the training text (usedContext []).
export function nextDistribution(model, context) {
  const tokens = Array.isArray(context) ? context.slice() : tokenize(context);
  const maxLen = Math.min(model.order - 1, tokens.length);
  for (let len = maxLen; len >= 1; len--) {
    const used = tokens.slice(tokens.length - len);
    const counts = model.contexts.get(used.join(' '));
    if (counts) return { entries: toEntries(counts), usedContext: used };
  }
  return { entries: toEntries(model.unigram), usedContext: [] };
}
