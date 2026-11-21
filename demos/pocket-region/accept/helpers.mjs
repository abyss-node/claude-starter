// Shared helpers for the held-out Pocket Region checks: kit code only, Node builtins only. The test files import it
// to work out what a right answer is; the scenario modules import it to build inputs and write down what happened
// in the process that holds the workspace's code (demos/probe.mjs). Nothing here imports the workspace: a module of
// it reaches a scenario only through the `load` it is given.

// The tests' own canonical text: keys sorted, no whitespace. Independent of the workspace.
export function stable(v) {
  if (v === undefined) return 'undefined';
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(stable).join(',')}]`;
  return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${stable(v[k])}`).join(',')}}`;
}

export const clone = (v) => JSON.parse(JSON.stringify(v));

// Freezes a value and everything inside it. A function that tries to change its input then throws, because
// ES modules run in strict mode.
export function deepFreeze(v) {
  if (v !== null && typeof v === 'object' && !Object.isFrozen(v)) {
    Object.freeze(v);
    for (const k of Object.keys(v)) deepFreeze(v[k]);
  }
  return v;
}

// What every value in `value` is, as [path, kind] pairs: 'null', 'number' (a finite one; 'number:NaN' and
// 'number:Infinity' otherwise), 'string', 'boolean', 'array', 'object' (a plain one; 'object:<class>' otherwise)
// and the typeof of anything else. A scenario returns this and the test decides what plain data allows, since a
// class instance or a Map does not survive the trip out of the scenario's process as what it was.
export function kinds(value, path = 'value', out = []) {
  if (value === null) out.push([path, 'null']);
  else if (typeof value === 'number') out.push([path, Number.isFinite(value) ? 'number' : `number:${value}`]);
  else if (typeof value === 'string' || typeof value === 'boolean') out.push([path, typeof value]);
  else if (Array.isArray(value)) {
    out.push([path, 'array']);
    value.forEach((v, i) => kinds(v, `${path}[${i}]`, out));
  } else if (typeof value === 'object') {
    const proto = Object.getPrototypeOf(value);
    const plain = proto === Object.prototype || proto === null;
    out.push([path, plain ? 'object' : `object:${(proto && proto.constructor && proto.constructor.name) || '?'}`]);
    for (const k of Object.keys(value)) kinds(value[k], `${path}.${k}`, out);
  } else out.push([path, typeof value]);
  return out;
}

export const PLAIN_KINDS = ['null', 'number', 'string', 'boolean', 'array', 'object'];

// The first path in a `kinds` list that is not plain data, as text; null when all of it is plain.
export function notPlain(list) {
  const bad = list.find(([, kind]) => !PLAIN_KINDS.includes(kind));
  return bad ? `${bad[0]} is not plain data (${bad[1]})` : null;
}

// What a call did: { ok: true, value } or { ok: false, error: 'RangeError' | 'TypeError' | 'other' }.
export function attempt(fn) {
  try {
    return { ok: true, value: fn() };
  } catch (e) {
    return { ok: false, error: e instanceof RangeError ? 'RangeError' : e instanceof TypeError ? 'TypeError' : 'other' };
  }
}

// Plays a list of inputs, returning the final game.
export function play(content, step, game, inputs) {
  let g = game;
  for (const i of inputs) g = step(content, g, i);
  return g;
}

// A bare map for the movement and map tests.
export function mapOf(rows, extra = {}) {
  return { id: 'm', name: 'M', width: rows[0].length, height: rows.length, rows, warps: [], gates: [], npcs: [], ...extra };
}
export function contentOf(maps) {
  const byId = {};
  for (const m of maps) byId[m.id] = m;
  return { maps: byId };
}

// The map the tile checks read, and the flag sets they try.
export const TILE_FLAGS = [{}, { other: true }, { open: true }, { open: false }, { constructor: true }];
export const tilesMap = () => mapOf(['#.,~', 'T.ZN', '....'], {
  npcs: [{ id: 'n', x: 1, y: 2, tree: 't' }, { id: 'w', x: 0, y: 0, tree: 't' }],
  gates: [{ x: 2, y: 2, flag: 'open' }, { x: 3, y: 2, flag: 'constructor' }],
});
