// Shared helpers for the held-out Spin Clash checks: kit code only, Node builtins only. The test files import it
// to work out what a right answer is; scenarios.mjs imports it to play matches in the process that holds the
// workspace's code (demos/probe.mjs), where it is a source of inputs and a way of writing down what happened.
// Nothing here imports the workspace: a module of it reaches a scenario only through the `load` it is given.

// The state two worlds are compared by: everything the brief says a top and a world carry.
export function snapshot(world) {
  return JSON.stringify({
    tick: world.tick,
    winner: world.winner,
    tops: world.tops.map((t) => [t.x, t.y, t.vx, t.vy, t.spin, t.status]),
  });
}

// The tests' own seeded stream (mulberry32), independent of the workspace's.
export function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), s | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// A reproducible list of per-tick inputs: one {x, y} (or null) per top.
export function inputScript(seed, ticks, tops) {
  const r = rng(seed);
  const out = [];
  for (let t = 0; t < ticks; t++) {
    const row = [];
    for (let i = 0; i < tops; i++) {
      row.push(r() < 0.25 ? null : { x: r() * 2 - 1, y: r() * 2 - 1 });
    }
    out.push(row);
  }
  return out;
}

export const clone = (v) => JSON.parse(JSON.stringify(v));

// What every value in `value` is, as [path, kind] pairs: 'null', 'number' (a finite one; 'number:NaN' and
// 'number:Infinity' otherwise), 'string', 'boolean', 'array', 'object' (a plain one; 'object:<class>' otherwise)
// and the typeof of anything else (undefined, function, bigint, symbol). A scenario returns this for a world and
// the test decides what plain data allows (PLAIN_KINDS), since a class instance or a Map does not survive the trip
// out of the scenario's process as what it was.
export function kinds(value, path = 'world', out = []) {
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

export const PLAIN_KINDS = new Set(['null', 'number', 'string', 'boolean', 'array', 'object']);

// True when a spin went up by more than float noise (a part in a billion). A
// solver that rebuilds a spin from an impulse of zero may land one ulp higher; a
// real gain is far bigger than that.
export const spinRose = (before, after) => after > before + 1e-9 * Math.max(1, before);

export function momentum(world) {
  let px = 0;
  let py = 0;
  for (const t of world.tops) {
    px += t.mass * t.vx;
    py += t.mass * t.vy;
  }
  return [px, py];
}

// Kinetic energy: translation plus spin, with a top as a solid disc (I = m r^2 / 2).
export function energy(world) {
  let e = 0;
  for (const t of world.tops) {
    e += 0.5 * t.mass * (t.vx * t.vx + t.vy * t.vy);
    e += 0.5 * (0.5 * t.mass * t.radius * t.radius) * t.spin * t.spin;
  }
  return e;
}

// Replace the global sources of nondeterminism with ones that throw, run fn, restore.
export async function withoutClocksOrRandom(fn) {
  const saved = { random: Math.random, now: Date.now, perf: globalThis.performance };
  const boom = (what) => () => { throw new Error(`physics called ${what}; use the seed and the tick instead`); };
  Math.random = boom('Math.random');
  Date.now = boom('Date.now');
  Object.defineProperty(globalThis, 'performance', {
    value: { now: boom('performance.now') }, configurable: true, writable: true,
  });
  try {
    return await fn();
  } finally {
    Math.random = saved.random;
    Date.now = saved.now;
    Object.defineProperty(globalThis, 'performance', { value: saved.perf, configurable: true, writable: true });
  }
}

// The scripted opponents the solo-mode checks use. Both are functions of the
// world alone, so they play the same on every machine.
//
// idleInput: the idle opponent. It never touches the keyboard: input null.
export function idleInput() {
  return null;
}

// The rim of every solo match: the brief's default, since the solo scenarios
// leave `arenaRadius` out. It is a constant here, not read from the world,
// because the brief fixes only `tick`, `winner` and `tops` on a world and does
// not say where a workspace keeps its settings.
export const SOLO_ARENA_RADIUS = 1;

// dodgerInput: the fleeing opponent, for the top at `index`. If it is farther
// than 0.6 of the rim from the centre it steers straight for the centre;
// otherwise it steers straight away from the nearest other top that is still in
// play. A top that is out, or has nothing to flee from, gets input null.
export function dodgerInput(world, index, arenaRadius = SOLO_ARENA_RADIUS) {
  const me = world.tops[index];
  if (!me || me.status !== 'in') return null;
  const home = Math.hypot(me.x, me.y);
  if (home > 0.6 * arenaRadius) return { x: -me.x / home, y: -me.y / home };
  let foe = null;
  let best = Infinity;
  world.tops.forEach((t, i) => {
    if (i === index || t.status !== 'in') return;
    const d = Math.hypot(t.x - me.x, t.y - me.y);
    if (d < best) { best = d; foe = t; }
  });
  if (!foe) return null;
  const d = best || 1;
  return { x: (me.x - foe.x) / d, y: (me.y - foe.y) / d };
}

// The two tops every solo-mode check uses: the same build for both sides, so
// the match is decided by the inputs, not by the sliders. Top A (index 0) is the
// scripted one, Top B (index 1) is the computer.
export const SOLO_TOPS = [
  { name: 'Foil', mass: 1.4, radius: 0.12, friction: 0.4 },
  { name: 'Seeker', mass: 1.4, radius: 0.12, friction: 0.4 },
];

// Play Top A from `opponent(world, 0)` and Top B from aiInput(world, 1) until
// there is a winner or `maxTicks`. Returns the world, and the rows fed to step.
export function playSolo(physics, ai, seed, opponent, maxTicks) {
  const world = physics.createWorld({ seed, tops: SOLO_TOPS });
  const rows = [];
  while (world.winner === null && world.tick < maxTicks) {
    const row = [opponent(world, 0), ai.aiInput(world, 1)];
    rows.push(clone(row));
    physics.step(world, row);
  }
  return { world, rows };
}
