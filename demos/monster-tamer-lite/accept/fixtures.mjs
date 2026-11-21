// Builders and arithmetic of the held-out checks. Nothing here touches the workspace: the scenarios
// (scenario-NN.mjs) import this to build inputs and to write down what the workspace's code returned, and the
// tests import it to build the same inputs and work out what a right answer is. A module the scenarios import may
// be read by the workspace's code in their process (demos/AUTHORING.md), so only the grader's own arithmetic
// belongs here.

export const clone = (v) => JSON.parse(JSON.stringify(v));
export const J = (v) => JSON.stringify(v);

// The workspace's engine modules, loaded with the scenario's `load` (a path of the workspace, query allowed).
export async function engineOf(load, query = '') {
  const names = ['rng', 'data', 'rules', 'battle', 'ai', 'duel', 'replay', 'game'];
  const mods = await Promise.all(names.map((n) => load(`src/${n}.js${query}`)));
  return Object.fromEntries(names.map((n, i) => [n, mods[i]]));
}

// A reader of the workspace's random state: starts from a seed (or a copy of a state) and draws with the
// workspace's own nextFloat.
export function probeOf(load) {
  return async function makeProbe(from) {
    const { rng } = await engineOf(load);
    const state = typeof from === 'number' ? rng.createRng(from) : clone(from);
    return {
      draw: () => rng.nextFloat(state),
      state: () => J(state),
    };
  };
}

// What a scenario reports about a value, a thrown error or two objects that should not be one. Each is a plain
// record of what happened; the tests decide what it should have been.

// What a copy of `value` cannot carry out of the scenario's process, as [path, what] for each place: an object whose
// prototype is not Object.prototype (nor null), or an array whose prototype is not Array.prototype ('prototype
// <its constructor's name>'), and a property that is a getter or a setter rather than a value ('accessor', never
// called). structuredClone and v8 serialization carry the rest of what a check reads (NaN, undefined, a Map), but a
// class instance arrives as a plain object and a getter as one value it gave. So a scenario returns a copy of the
// value and this list, and the test works out the kinds of value from both (helpers.mjs kindsOf). The built-ins used
// here are frozen before the workspace's code loads (demos/probe-child.mjs), so it cannot change what they say.
export function uncopied(value, path = 'value') {
  const out = [];
  const seen = new Set();
  const walk = (v, p) => {
    if (v === null || typeof v !== 'object' || seen.has(v)) return;
    seen.add(v);
    const isArray = Array.isArray(v);
    const proto = Object.getPrototypeOf(v);
    if (isArray ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) {
      let name = '?';
      try { name = String((proto && proto.constructor && proto.constructor.name) || '?'); } catch { /* a getter that throws */ }
      out.push([p, `prototype ${name}`]);
    }
    for (const k of Object.keys(v)) {
      const at = isArray && /^\d+$/.test(k) ? `${p}[${k}]` : `${p}.${k}`;
      const d = Object.getOwnPropertyDescriptor(v, k);
      if (!d) continue;
      if (!('value' in d)) out.push([at, 'accessor']);
      else walk(d.value, at);
    }
    seen.delete(v);
  };
  walk(value, path);
  return out;
}

// A copy of `value` to return, and what the copy cannot carry: { copy, uncopied }.
export const observed = (value, path = 'value') => ({ copy: structuredClone(value), uncopied: uncopied(value, path) });

const protoNames = (e) => {
  if (e === null || (typeof e !== 'object' && typeof e !== 'function')) return [e === null ? 'null' : typeof e];
  const names = [];
  for (let p = Object.getPrototypeOf(e); p && names.length < 10; p = Object.getPrototypeOf(p)) {
    let name = '?';
    try { name = String(p.constructor && p.constructor.name); } catch { /* a getter that throws */ }
    names.push(name);
  }
  return names;
};

// What calling fn did: { threw, chain (the class names of what it threw, nearest first), tag, message }.
export function thrown(fn) {
  try {
    fn();
  } catch (e) {
    let tag = '';
    let message = '';
    try { tag = Object.prototype.toString.call(e); } catch { /* left empty */ }
    try { message = String(e && e.message); } catch { /* left empty */ }
    return { threw: true, chain: protoNames(e), tag, message };
  }
  return { threw: false, chain: [], tag: '', message: '' };
}

// Labels for objects by identity: the same object always gets the same label ('object 1', 'object 2', ...) and a
// value that is not an object says what it is. A scenario reports the labels of a copy and its source, and the test
// judges whether they are two objects, since a copy that leaves the process has no identity to compare.
export function objectIds() {
  const seen = new Map();
  return (v) => {
    if (v === null || (typeof v !== 'object' && typeof v !== 'function')) return `not an object (${v === null ? 'null' : typeof v})`;
    if (!seen.has(v)) seen.set(v, `object ${seen.size + 1}`);
    return seen.get(v);
  };
}

// ---- fixtures: literal creature and move records, written from the brief's record shape ----

export function mv(o = {}) {
  return { id: 'fx-move', name: 'Fx Move', type: 'stone', power: 40, accuracy: 100, status: null, ...o };
}

export function mon(o = {}) {
  const maxHp = o.maxHp ?? 60;
  return {
    species: o.species ?? 'fixture',
    name: o.name ?? 'Fixture',
    type: o.type ?? 'stone',
    level: o.level ?? 10,
    xp: o.xp ?? 0,
    hp: o.hp ?? maxHp,
    maxHp,
    base: { hp: 50, atk: 50, def: 50, spd: 50, ...(o.base || {}) },
    stats: { atk: 30, def: 30, spd: 30, ...(o.stats || {}) },
    baseXp: o.baseXp ?? 50,
    catchRate: o.catchRate ?? 40,
    moves: o.moves ?? [mv()],
    status: o.status ?? null,
  };
}

// A move that does nothing at all (no damage, never misses, no status).
export const idle = (o = {}) => mv({ id: 'idle', name: 'Idle', power: 0, accuracy: 100, status: null, ...o });

export function config(a, b, extra = {}) {
  const team = (x) => (Array.isArray(x) ? x : [x]);
  return { seed: 1, sides: [{ name: 'Left', team: team(a) }, { name: 'Right', team: team(b) }], ...extra };
}

export const MV = (slot = 0) => ({ kind: 'move', slot });
export const SW = (to) => ({ kind: 'switch', to });
export const SNARE = { kind: 'snare' };

export const types = (log) => log.map((e) => e.type);

// Log entries reduced to the fields the brief names, so that extra fields are allowed.
const CORE = { turn: ['type', 'n'], move: ['type', 'side', 'move'], miss: ['type', 'side', 'move'], damage: ['type', 'side', 'amount', 'hp', 'cause'], status: ['type', 'side', 'kind'], cured: ['type', 'side', 'kind'], skip: ['type', 'side', 'reason'], faint: ['type', 'side'], switch: ['type', 'side', 'to'], snare: ['type', 'side', 'success'], end: ['type', 'winner'] };
export const core = (log) => log.map((e) => Object.fromEntries((CORE[e.type] || ['type']).filter((k) => k in e).map((k) => [k, e[k]])));
export const ofType = (log, t) => log.filter((e) => e.type === t);

// A tiny seeded generator of our own, for building random test inputs (not the workspace's).
export function testRng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function fnv1a(text) {
  let h = 0x811c9dc5;
  for (const b of new TextEncoder().encode(text)) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

// Exact floor of an integer fraction, no floating point.
export function floorDiv(num, den) {
  return Number(BigInt(num) / BigInt(den));
}

export function deepFreeze(v) {
  if (v && typeof v === 'object' && !Object.isFrozen(v)) {
    Object.freeze(v);
    for (const k of Object.keys(v)) deepFreeze(v[k]);
  }
  return v;
}

// Play a battle to the end with a picker; returns the battle. pick(battle, side) returns an action or null.
export function playOut(battle, resolveTurn, legalActions, pick, maxTurns = 400) {
  for (let i = 0; i < maxTurns && battle.phase !== 'over'; i++) {
    resolveTurn(battle, [0, 1].map((side) => (legalActions(battle, side).length ? pick(battle, side) : null)));
  }
  return battle;
}

// ---- random fixtures for the battle-level checks ----
// The brief's five types, in its order.
export const TYPE_NAMES = ['cinder', 'tide', 'moss', 'spark', 'stone'];
const TYPE_LIST = TYPE_NAMES;
// The brief's type chart: CHART[attacking][i] against TYPE_NAMES[i].
export const CHART = {
  cinder: [0.5, 0.5, 2, 1, 1],
  tide: [2, 0.5, 0.5, 1, 2],
  moss: [0.5, 2, 0.5, 1, 2],
  spark: [1, 2, 0.5, 0.5, 0],
  stone: [2, 1, 1, 2, 0.5],
};
const KINDS = ['scorch', 'daze', 'chill'];

// Every creature has at least two damaging moves of different types, so a battle always ends.
export function randTeam(rnd, n, tag = 'T') {
  const pick = (k) => Math.floor(rnd() * k);
  return Array.from({ length: n }, (_, i) => {
    const ta = pick(5);
    const moves = [
      mv({ id: `${tag}${i}-a`, name: 'A', type: TYPE_LIST[ta], power: 40 + pick(40), accuracy: 80 + pick(21) }),
      mv({ id: `${tag}${i}-b`, name: 'B', type: TYPE_LIST[(ta + 1 + pick(4)) % 5], power: 30 + pick(50), accuracy: 70 + pick(31), status: rnd() < 0.5 ? { kind: KINDS[pick(3)], chance: 20 + pick(81) } : null }),
    ];
    if (rnd() < 0.5) moves.push(mv({ id: `${tag}${i}-c`, name: 'C', type: TYPE_LIST[pick(5)], power: pick(2) * 50, accuracy: 60 + pick(41), status: { kind: KINDS[pick(3)], chance: 30 + pick(71) } }));
    const maxHp = 30 + pick(60);
    return mon({
      name: `${tag}${i}`, type: TYPE_LIST[pick(5)], level: 5 + pick(10), maxHp, hp: maxHp,
      stats: { atk: 15 + pick(40), def: 15 + pick(40), spd: 10 + pick(40) },
      baseXp: 40 + pick(60), catchRate: 20 + pick(70), moves,
    });
  });
}
