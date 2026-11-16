// Turning a next-token distribution into a choice: temperature, top-k, top-p, seeded sampling.

import { compareEntries, nextDistribution, tokenize } from './lm.js';

function normalize(entries) {
  let total = 0;
  for (const e of entries) total += e.p;
  return entries.map((e) => ({ token: e.token, p: e.p / total }));
}

// Order: temperature, then top-k, then top-p on the renormalised top-k result.
// Returns only the kept entries, sorted by compareEntries, summing to 1.
export function applySettings(entries, { temperature = 1, topK = 0, topP = 1 } = {}) {
  let list = entries.filter((e) => e.p > 0).map((e) => ({ token: e.token, p: e.p }));
  if (list.length === 0) return [];
  list.sort(compareEntries);
  list = normalize(list);

  if (temperature <= 0) return [{ token: list[0].token, p: 1 }];
  if (temperature !== 1) {
    const logMax = Math.log(list[0].p);
    list = normalize(
      list.map((e) => ({ token: e.token, p: Math.exp((Math.log(e.p) - logMax) / temperature) })),
    );
  }

  if (Number.isInteger(topK) && topK >= 1 && topK < list.length) {
    list = normalize(list.slice(0, topK));
  }

  if (topP < 1) {
    let cum = 0;
    let keep = list.length;
    for (let i = 0; i < list.length; i++) {
      cum += list[i].p;
      if (cum >= topP - 1e-12) {
        keep = i + 1;
        break;
      }
    }
    list = normalize(list.slice(0, Math.max(1, keep)));
  }
  return list;
}

// mulberry32: a small seeded generator returning floats in [0, 1).
export function createRng(seed) {
  let a = Number(seed) >>> 0;
  return function rng() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Inverse CDF in list order: the first entry whose running sum exceeds r.
export function sampleToken(entries, rng) {
  if (entries.length === 0) return null;
  const r = rng();
  let cum = 0;
  for (const e of entries) {
    cum += e.p;
    if (r < cum) return e.token;
  }
  return entries[entries.length - 1].token;
}

export function generate(model, prompt, { length = 10, seed = 1, temperature = 1, topK = 0, topP = 1 } = {}) {
  const rng = createRng(seed);
  const context = Array.isArray(prompt) ? prompt.slice() : tokenize(prompt);
  const out = [];
  for (let i = 0; i < length; i++) {
    const { entries } = nextDistribution(model, context);
    const kept = applySettings(entries, { temperature, topK, topP });
    if (kept.length === 0) break;
    const token = sampleToken(kept, rng);
    out.push(token);
    context.push(token);
  }
  return out;
}
