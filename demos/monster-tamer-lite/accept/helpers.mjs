// The asserting side of the held-out checks. The workspace's code never runs in this process: a scenario
// (scenario-NN.mjs) runs it beside the workspace through demos/probe.mjs and returns what it saw, as plain data
// (values, states, logs, what was thrown). The NN-*.test.mjs files work out what a right answer is from their own
// inputs (fixtures.mjs builds them) and compare here, with node:assert, so no verdict is reached beside the
// workspace's code.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { readFile, readdir } from 'node:fs/promises';
import { isAbsolute, join, relative, resolve, sep } from 'node:path';
import { scenario } from '../../probe.mjs';

export function workspace() {
  const ws = process.env.DEMO_WORKSPACE;
  if (!ws) throw new Error('DEMO_WORKSPACE is not set');
  return isAbsolute(ws) ? ws : resolve(ws);
}

export function readWorkspaceFile(rel) {
  return readFile(join(workspace(), rel), 'utf8');
}

export const clone = (v) => JSON.parse(JSON.stringify(v));

// Runs the scenario `file` (a module of this folder) beside the workspace and returns what it saw: an object of
// plain data. A scenario that hands back nothing, or an empty object, has seen nothing, and that is a failure: every
// scenario here has something to report.
export function observe(file, args = [], { timeoutMs = 80000, name = 'run' } = {}) {
  const seen = scenario(new URL(file, import.meta.url), name, args, { timeoutMs });
  if (seen === null || typeof seen !== 'object' || Array.isArray(seen) || Object.keys(seen).length === 0) {
    throw new Error(`${file} returned no observations (${seen === null ? 'null' : Array.isArray(seen) ? 'a list' : typeof seen})`);
  }
  return seen;
}

// `list` holds exactly `n` entries.
export function counted(list, n, what) {
  assert.ok(Array.isArray(list), `${what}: the scenario returned no list`);
  assert.equal(list.length, n, `${what}: the scenario reported ${list.length} of ${n}`);
  return list;
}

// The kinds of value a scenario saw, as {kind: the first path holding one}: 'null', 'number' (a finite one;
// 'number:NaN' and 'number:Infinity' otherwise), 'string', 'boolean', 'array', 'object' (a plain one;
// 'object:<class>' otherwise), 'accessor', and the typeof of anything else. Worked out here, from the scenario's copy
// of the value and the places fixtures.mjs uncopied says the copy could not carry (a class instance, a getter).
export function kindsOf(copy, uncopied, path = 'value') {
  assert.ok(Array.isArray(uncopied), `${path}: the scenario did not say what its copy could not carry`);
  const out = {};
  const seen = new Set();
  const note = (kind, p) => { if (!(kind in out)) out[kind] = p; };
  const walk = (v, p) => {
    if (v === null) note('null', p);
    else if (typeof v === 'number') note(Number.isFinite(v) ? 'number' : `number:${v}`, p);
    else if (typeof v === 'string' || typeof v === 'boolean') note(typeof v, p);
    else if (Array.isArray(v)) note('array', p);
    else if (typeof v === 'object') {
      const proto = Object.getPrototypeOf(v);
      note(proto === Object.prototype || proto === null ? 'object' : `object:${(proto && proto.constructor && proto.constructor.name) || '?'}`, p);
    } else note(typeof v, p);
    if (v === null || typeof v !== 'object' || seen.has(v)) return;
    seen.add(v);
    if (Array.isArray(v)) v.forEach((x, i) => walk(x, `${p}[${i}]`));
    else for (const k of Object.keys(v)) walk(v[k], `${p}.${k}`);
    seen.delete(v);
  };
  walk(copy, path);
  for (const [p, what] of uncopied) {
    assert.ok(typeof p === 'string' && typeof what === 'string', `${path}: a malformed record of what its copy lost`);
    note(what === 'accessor' ? 'accessor' : `object:${what.replace(/^prototype /, '')}`, p);
  }
  return out;
}

// The kinds a value may hold to be plain data.
const PLAIN = new Set(['null', 'number', 'string', 'boolean', 'array', 'object']);
export function assertPlain(kinds, what) {
  assert.ok(kinds && typeof kinds === 'object' && Object.keys(kinds).length > 0, `${what}: no kinds were reported`);
  const bad = Object.entries(kinds).filter(([k]) => !PLAIN.has(k)).map(([k, at]) => `${at} is ${k}`);
  assert.deepEqual(bad, [], `${what} is plain data`);
}

// A fixtures.mjs thrown() record: it threw an Error.
export function assertThrew(t, what) {
  assert.ok(t && typeof t === 'object', `${what}: nothing was reported`);
  assert.ok(t.threw === true, `${what}: it did not throw`);
  assert.ok(Array.isArray(t.chain) && t.chain.includes('Error'),
    `${what}: it threw something that is not an Error (${J(t.chain)})`);
}

export function assertNoThrow(t, what) {
  assert.ok(t && typeof t === 'object', `${what}: nothing was reported`);
  assert.ok(t.threw === false, `${what}: it threw: ${t.message}`);
}

// Two fixtures.mjs objectIds() labels: two different objects.
export function assertDistinct(labels, what) {
  assert.ok(Array.isArray(labels) && labels.length === 2, `${what}: nothing was reported`);
  const [a, b] = labels;
  assert.ok(/^object \d+$/.test(a) && /^object \d+$/.test(b), `${what}: ${a} and ${b}`);
  assert.notEqual(a, b, `${what}: they are the very same object`);
}

// A throwing call that must change nothing: { before, call: thrown(), after }.
export function assertUnchanged(u, what) {
  assert.ok(u && typeof u === 'object', `${what}: nothing was reported`);
  assertThrew(u.call, what);
  assert.equal(u.after, u.before, `${what}: a throwing call must change nothing`);
}

const J = (v) => JSON.stringify(v);

// ---- originality ----
// The terms of the kit's own list (demos/denylist.txt), matched as check.py and demolib.py match them: ignoring
// case and accents, with spaces, hyphens, underscores, dots and apostrophes allowed between the letters of a term,
// a plural allowed, and a term never inside a longer word. The list has one home.
const SEP = String.raw`[\s\-_.'’]*`;
const fold = (s) => s.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
const DENYLIST = readFileSync(new URL('../../denylist.txt', import.meta.url), 'utf8').split('\n').flatMap((line) => {
  const term = line.split('#')[0].trim();
  if (!term) return [];
  const letters = fold(term).match(/[a-z0-9]+/g).join('');
  return [{ term, rx: new RegExp(`(?<![a-z0-9])${[...letters].join(SEP)}(?:e?s)?(?![a-z0-9])`) }];
});

// The terms of the list that `text` names.
export function namesIn(text) {
  const lines = fold(text).split('\n');
  return DENYLIST.filter(({ rx }) => lines.some((l) => rx.test(l))).map(({ term }) => term);
}

// All text files under the workspace (not node_modules, .git or tests/), as {rel, text}.
export async function textFiles({ includeTests = false } = {}) {
  const root = workspace();
  const out = [];
  async function walk(dir) {
    for (const e of await readdir(dir, { withFileTypes: true })) {
      const full = join(dir, e.name);
      const rel = relative(root, full).split(sep).join('/');
      if (e.isDirectory()) {
        if (e.name === 'node_modules' || e.name === '.git') continue;
        if (!includeTests && rel === 'tests') continue;
        await walk(full);
      } else {
        out.push({ rel, full });
      }
    }
  }
  await walk(root);
  return out;
}

// ---- a small, forgiving HTML tag reader (comments and script bodies are not searched) ----
export function htmlTags(html) {
  const bare = html
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/(<script\b(?:[^>"']|"[^"]*"|'[^']*')*>)[\s\S]*?<\/script\s*>/gi, '$1')
    .replace(/(<style\b(?:[^>"']|"[^"]*"|'[^']*')*>)[\s\S]*?<\/style\s*>/gi, '$1');
  const tags = [];
  const tagRe = /<([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
  let m;
  while ((m = tagRe.exec(bare))) {
    const attrs = {};
    const attrRe = /([^\s=/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
    let a;
    while ((a = attrRe.exec(m[2]))) attrs[a[1].toLowerCase()] = a[2] ?? a[3] ?? a[4] ?? '';
    tags.push({ name: m[1].toLowerCase(), attrs });
  }
  return tags;
}
