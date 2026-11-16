// Shared by the held-out tests. The workspace's code is never imported here: it runs in processes of its
// own (demos/probe.mjs: values(), scenario() over scenarios.mjs), and these helpers only build the inputs
// and compare what came back.

import { readFile } from 'node:fs/promises';
import { isAbsolute, join, resolve } from 'node:path';
import { scenario, values } from '../../probe.mjs';

const SCENARIOS = new URL('./scenarios.mjs', import.meta.url);

// Runs the scenario `name` of scenarios.mjs beside the workspace and returns its answer.
export function run(name, ...args) {
  return scenario(SCENARIOS, name, args, { timeoutMs: 25000 });
}

// tokenize(text) for each text, in one process.
export function tokenizeAll(...texts) {
  return values('src/lm.js', texts.map((text) => ['tokenize', text]));
}

// parseSeed(text) for each text, in one process.
export function parseAll(...texts) {
  return values('src/seed.js', texts.map((text) => ['parseSeed', text]));
}

export function workspace() {
  const ws = process.env.DEMO_WORKSPACE;
  if (!ws) throw new Error('DEMO_WORKSPACE is not set');
  return isAbsolute(ws) ? ws : resolve(ws);
}

export function readWorkspaceFile(rel) {
  return readFile(join(workspace(), rel), 'utf8');
}

export function sum(entries) {
  return entries.reduce((s, e) => s + e.p, 0);
}

export function tokens(entries) {
  return entries.map((e) => e.token);
}

export function entries(obj) {
  return Object.entries(obj).map(([token, p]) => ({ token, p }));
}

export function close(actual, expected, tol, msg) {
  if (!(Math.abs(actual - expected) <= tol)) {
    throw new Error(`${msg ?? 'value'}: expected ${expected} within ${tol}, got ${actual}`);
  }
}

// Fixed fixture text, independent of whatever corpus the workspace embeds.
export const FIXTURE = 'The cat sat. The cat ran. The dog sat. A cat sat!';

// A fixed text with many choices at every step, built here and never read from the
// workspace: ten words in a pseudo-random order, so after any word about ten different
// words follow. Two different seeds that really give different streams then write the
// same twenty-odd words with a chance too small to matter.
const BRANCHY_WORDS = ['amber', 'birch', 'cedar', 'dune', 'ember', 'fern', 'glade', 'heath', 'iris', 'jade'];
export function branchyText(count = 600) {
  let x = 12345;
  const out = [];
  for (let i = 0; i < count; i++) {
    x = (Math.imul(x, 1103515245) + 12345) >>> 0;
    out.push(BRANCHY_WORDS[(x >>> 16) % BRANCHY_WORDS.length]);
  }
  return out.join(' ');
}

// Seeds the tests treat as "every one is its own": neighbours, multiples of 7, powers of two
// and one more than a power of two, the newSeed ceiling, and the top of parseSeed's range.
export const MANY_SEEDS = [
  0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 22, 29, 64, 65, 256, 257, 65536, 65537,
  999999, 1000000, 2147483648, 4294967294, 4294967295,
];

// Groups items by key and returns the groups with more than one member, as readable text.
export function collisions(items, keyOf) {
  const groups = new Map();
  for (const item of items) {
    const k = keyOf(item);
    groups.set(k, (groups.get(k) ?? []).concat([item]));
  }
  return [...groups.values()].filter((g) => g.length > 1).map((g) => `{${g.join(', ')}}`);
}
