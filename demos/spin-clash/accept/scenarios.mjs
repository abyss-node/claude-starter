// What the held-out Spin Clash checks ask of the workspace, as scenarios (demos/probe.mjs, scenario()). Each
// function here is run in a process of its own, beside the workspace's code, which it reaches through the `load`
// it is given: it plays the match or makes the calls and returns what it saw, as plain data. It never judges:
// the numbered test files hold every assert, and compare what came back with what the brief says.
//
// A scenario shares its process with the workspace, so what it returns is a record of what the code did, and a
// right record is the work itself. The inputs are made here (helpers.mjs) so nothing large crosses on the
// command line.
import {
  snapshot, kinds, inputScript, rng, clone, withoutClocksOrRandom, idleInput, dodgerInput, SOLO_TOPS, playSolo,
} from './helpers.mjs';

async function physicsOf(load, label) {
  const mod = await load(label ? `src/physics.js?fresh=${encodeURIComponent(label)}` : 'src/physics.js');
  for (const name of ['DT', 'createWorld', 'step', 'collide']) {
    if (!(name in mod)) throw new Error(`src/physics.js does not export ${name}`);
  }
  return mod;
}

async function aiOf(load, label) {
  const mod = await load(label ? `src/ai.js?fresh=${encodeURIComponent(label)}` : 'src/ai.js');
  if (typeof mod.aiInput !== 'function') throw new Error('src/ai.js does not export a function aiInput');
  return mod;
}

const copy = (v) => structuredClone(v);

// ---- 1: the world's shape ------------------------------------------------------------------------------------
export async function shape({ load }) {
  const { DT, createWorld } = await physicsOf(load);
  const world = createWorld({
    seed: 11,
    tops: [
      { name: 'Heavy', mass: 10, radius: 0.01, friction: -1 },
      { name: 'Light', mass: 0.1, radius: 9, friction: 7 },
    ],
  });
  const zeros = createWorld({ seed: 2, tops: [{ mass: 0, radius: 0, friction: 0 }, { mass: -4, radius: -1, friction: 0 }] });
  const named = createWorld({ seed: 3, tops: [{ name: 'Old Ballast' }, { name: 'Copperhull Nettle Quill of the Long Name' }] });
  const plain = createWorld({});
  const asked = createWorld({ seed: 5, tops: [{ spin: -5 }, { spin: -1e9 }] });
  return {
    DT, world, zeros, names: named.tops.map((t) => t.name), plainTops: plain.tops.length,
    plainSnap: snapshot(plain), seedOneSnap: snapshot(createWorld({ seed: 1 })), asked,
  };
}

// ---- 2: determinism ------------------------------------------------------------------------------------------
export async function determinism({ load }) {
  const { createWorld, step, collide } = await physicsOf(load);
  const out = {};
  const config = {
    seed: 1234,
    tops: [
      { name: 'Kestrel', mass: 1.2, radius: 0.1, friction: 0.4 },
      { name: 'Ballast', mass: 0.9, radius: 0.12, friction: 0.6 },
    ],
  };
  const script = inputScript(77, 600, 2);
  await withoutClocksOrRandom(() => {
    const a = createWorld(clone(config));
    const b = createWorld(clone(config));
    out.start = snapshot(a);
    for (let t = 0; t < 600; t++) {
      step(a, clone(script[t]));
      step(b, clone(script[t]));
    }
    out.tick = a.tick;
    out.a = snapshot(a);
    out.b = snapshot(b);
    out.other = snapshot(createWorld({ ...clone(config), seed: 99 }));
  });

  await withoutClocksOrRandom(() => {
    const long = createWorld({ seed: 31, friction: false, tops: [{}, {}, {}] });
    const rows = inputScript(31, 3000, 3);
    for (let t = 0; t < 3000; t++) step(long, clone(rows[t]));
    out.longTick = long.tick;
  });

  const corners = {
    'three tops on one spot': { seed: 4, tops: [{ x: 0, y: 0, vx: 0, vy: 0 }, { x: 0, y: 0, vx: 0, vy: 0 }, { x: 0, y: 0, vx: 0, vy: 0 }] },
    'four tops, friction off, flat floor': { seed: 6, friction: false, slope: 0, tops: [{}, {}, {}, {}] },
    'one top outside the rim': { seed: 8, tops: [{ x: 1.4, y: 0 }, {}] },
    'two tops on one spot, moving the same way': { seed: 10, tops: [{ x: 0.2, y: 0.1, vx: 0.5, vy: 0 }, { x: 0.2, y: 0.1, vx: 0.5, vy: 0 }] },
  };
  out.corners = [];
  await withoutClocksOrRandom(() => {
    for (const [label, cfg] of Object.entries(corners)) {
      const x = createWorld(clone(cfg));
      const y = createWorld(clone(cfg));
      const rows = inputScript(label.length, 800, x.tops.length);
      for (let t = 0; t < 800; t++) {
        // No input for the first ticks, so stacked tops are still stacked when they first touch.
        const row = t < 10 ? undefined : rows[t];
        step(x, row && clone(row));
        step(y, row && clone(row));
      }
      out.corners.push({ label, x: snapshot(x), y: snapshot(y) });
    }
    const pair = {
      seed: 2, slope: 0,
      tops: [{ mass: 1, radius: 0.1, x: 0.1, y: 0.1, vx: 0.4, vy: 0, spin: 40 }, { mass: 2, radius: 0.1, x: 0.1, y: 0.1, vx: -0.2, vy: 0.1, spin: 30 }],
    };
    const p = createWorld(clone(pair));
    const q = createWorld(clone(pair));
    collide(p, 0, 1);
    collide(q, 0, 1);
    out.pair = [snapshot(p), snapshot(q)];
  });

  const xConfig = {
    seed: 21, friction: false, slope: 0, steer: 4, arenaRadius: 3, minSpin: 1,
    tops: [{ name: 'X1', x: -0.5, y: 0.1, vx: 0.4, vy: 0, spin: 30 }, { name: 'X2', x: 0.5, y: 0, vx: -0.3, vy: 0.05, spin: 25 }],
  };
  const yConfig = {
    seed: 22, friction: true, slope: 2.5, steer: 1, arenaRadius: 0.8, minSpin: 9,
    tops: [{ name: 'Y1', x: -0.3, y: 0.1, vx: 0.4, vy: 0, spin: 30 }, { name: 'Y2', x: 0.3, y: 0, vx: -0.3, vy: 0.05, spin: 25 }],
  };
  const turn = inputScript(5, 400, 2);
  await withoutClocksOrRandom(() => {
    const x = createWorld(clone(xConfig));
    const y = createWorld(clone(yConfig));
    for (let t = 0; t < 400; t++) {
      step(x, clone(turn[t]));
      step(y, clone(turn[t]));
    }
    const xAlone = createWorld(clone(xConfig));
    for (let t = 0; t < 400; t++) step(xAlone, clone(turn[t]));
    const yAlone = createWorld(clone(yConfig));
    for (let t = 0; t < 400; t++) step(yAlone, clone(turn[t]));
    out.settings = { x: snapshot(x), xAlone: snapshot(xAlone), y: snapshot(y), yAlone: snapshot(yAlone) };
  });
  return out;
}

// ---- 3: the world is plain data ------------------------------------------------------------------------------
export async function plainData({ load }) {
  const { createWorld, step } = await physicsOf(load);
  const script = inputScript(5, 800, 3);
  const live = createWorld({ seed: 42, tops: [{ friction: 0.2 }, { friction: 0.5 }, { friction: 0.8 }] });
  const out = { kindsStart: kinds(live) };
  for (let t = 0; t < 400; t++) step(live, clone(script[t]));
  out.kindsMid = kinds(live);
  const twin = JSON.parse(JSON.stringify(live));
  out.mid = snapshot(live);
  out.twinMid = snapshot(twin);
  // A second copy goes to a freshly loaded copy of src/physics.js, which has never made a world.
  const elsewhere = JSON.parse(JSON.stringify(live));
  const fresh = await physicsOf(load, 'json-copy');
  for (let t = 400; t < 800; t++) {
    step(live, clone(script[t]));
    step(twin, clone(script[t]));
    fresh.step(elsewhere, clone(script[t]));
  }
  out.end = snapshot(live);
  out.twinEnd = snapshot(twin);
  out.elsewhereEnd = snapshot(elsewhere);
  out.kindsEnd = kinds(live);
  return out;
}

// ---- 4: nothing blows up -------------------------------------------------------------------------------------
const FIELDS = ['mass', 'radius', 'friction', 'x', 'y', 'vx', 'vy', 'spin'];

export async function finite({ load }) {
  const { createWorld, step } = await physicsOf(load);
  const worlds = {
    'seeded pair': { seed: 3 },
    'three tops on one spot': { seed: 4, tops: [{ x: 0, y: 0, vx: 0, vy: 0 }, { x: 0, y: 0, vx: 0, vy: 0 }, { x: 0, y: 0, vx: 0, vy: 0 }] },
    'extreme sliders': { seed: 5, tops: [{ mass: 0, radius: 0, friction: 0, spin: 1e6 }, { mass: 1e9, radius: 1e9, friction: 1e9 }] },
    'friction off': { seed: 6, friction: false, tops: [{}, {}, {}, {}] },
  };
  const wild = [[{ x: 1e9, y: -1e9 }, { x: NaN, y: Infinity }], [{ x: 'left' }, undefined], [null, {}]];
  const out = [];
  for (const [label, config] of Object.entries(worlds)) {
    const w = createWorld(config);
    const script = inputScript(label.length, 10000, w.tops.length);
    const found = [];
    for (let t = 0; t < 10000 && found.length === 0; t++) {
      step(w, t < 10 ? undefined : t % 97 < 3 ? wild[t % 3] : script[t]);
      for (const top of w.tops) {
        for (const k of FIELDS) {
          if (!Number.isFinite(top[k])) found.push({ tick: w.tick, top: top.name, field: k, value: String(top[k]) });
        }
      }
    }
    out.push({ label, tick: w.tick, notFinite: found.slice(0, 3) });
  }
  return out;
}

// ---- 5: spin only goes down ----------------------------------------------------------------------------------
export async function spin({ load }) {
  const { DT, createWorld, step } = await physicsOf(load);
  const out = { DT };

  const w = createWorld({ seed: 8, tops: [{ name: 'Solo', friction: 0.5, spin: 50, x: 0, y: 0, vx: 0.3, vy: 0 }] });
  const script = inputScript(9, 3000, 1);
  out.solo = [w.tops[0].spin];
  for (let t = 0; t < 3000; t++) { step(w, script[t]); out.solo.push(w.tops[0].spin); }

  const slick = createWorld({ seed: 8, friction: false, tops: [{ name: 'Slick', spin: 30, x: 0, y: 0, vx: 0, vy: 0 }] });
  out.slick = [slick.tops[0].spin];
  for (let t = 0; t < 3000; t++) { step(slick, script[t]); out.slick.push(slick.tops[0].spin); }

  const grippy = createWorld({ seed: 8, tops: [{ name: 'Grippy', friction: 1, spin: 20, x: 0, y: 0, vx: 0, vy: 0 }] });
  for (let t = 0; t < 3600 && grippy.tops[0].status === 'in'; t++) step(grippy);
  out.grippyStatus = grippy.tops[0].status;

  const floors = [
    { label: 'spin 40', config: { minSpin: 4 }, spin: 40 },
    { label: 'spin 6, minSpin 1', config: { minSpin: 1 }, spin: 6 },
    { label: 'spin 1.2, minSpin 0.1', config: { minSpin: 0.1 }, spin: 1.2 },
  ];
  out.floors = [];
  for (const { label, config, spin: start } of floors) {
    const idle = createWorld({
      seed: 8, slope: 0, ...config,
      tops: [
        { name: 'Slippery', friction: 0, spin: start, x: -0.5, y: 0, vx: 0, vy: 0 },
        { name: 'Middling', friction: 0.5, spin: start, x: 0.5, y: 0, vx: 0, vy: 0 },
        { name: 'Grippy', friction: 1, spin: start, x: 0, y: 0.5, vx: 0, vy: 0 },
      ],
    });
    const centre = createWorld({ seed: 8, slope: 0, ...config, tops: [{ name: 'Centre', friction: 0, spin: start, x: 0, y: 0, vx: 0, vy: 0 }] });
    const seconds = [];
    let ticks = 0;
    for (let sec = 1; sec <= 3; sec++) {
      const upTo = Math.ceil(sec / DT - 1e-9);
      while (ticks < upTo) { step(idle); step(centre); ticks++; }
      seconds.push({ sec, ticks, tops: idle.tops.concat(centre.tops).map((t) => ({ name: t.name, status: t.status, spin: t.spin })) });
    }
    out.floors.push({ label, spin: start, seconds });
  }

  const matches = [
    { label: 'two seeded tops, seed 3', config: { seed: 3 }, ticks: 1500 },
    { label: 'two seeded tops, seed 12', config: { seed: 12 }, ticks: 1500 },
    { label: 'light, heavy and mid tops with little friction', config: { seed: 6, tops: [{ mass: 0.6, friction: 0, spin: 60 }, { mass: 2.8, friction: 0.1, spin: 55 }, { mass: 1.5, friction: 0.4, spin: 58 }] }, ticks: 2500 },
    { label: 'four tops, no friction of their own', config: { seed: 21, tops: [{ mass: 0.5, friction: 0 }, { mass: 3, friction: 0 }, { mass: 1, friction: 0 }, { mass: 2, friction: 0 }] }, ticks: 2500 },
    { label: 'three tops, friction off', config: { seed: 7, friction: false, tops: [{ mass: 0.7 }, { mass: 2.6 }, { mass: 1.4 }] }, ticks: 1500 },
  ];
  out.matches = [];
  for (const { label, config, ticks: n } of matches) {
    const world = createWorld(config);
    const inputs = inputScript(100 + config.seed, n, world.tops.length);
    const names = world.tops.map((t) => t.name);
    const spins = [world.tops.map((t) => t.spin)];
    for (let t = 0; t < n; t++) {
      step(world, inputs[t]);
      spins.push(world.tops.map((t2) => t2.spin));
    }
    out.matches.push({ label, names, spins });
  }
  return out;
}

// ---- 6: one clash --------------------------------------------------------------------------------------------
// The cases (fixed ones, then forty seeded ones) are made here; each record holds the tops before the call, after
// it and after a second call, so the test works out momentum, energy and the rest itself.
function clashRecord(physics, label, friction, tops) {
  const w = physics.createWorld({ seed: 2, slope: 0, friction, tops });
  const before = copy(w.tops);
  const hit = physics.collide(w, 0, 1);
  const after = copy(w.tops);
  const again = physics.collide(w, 0, 1);
  return { label, friction, before, hit, after, again, afterAgain: copy(w.tops) };
}

function contactRecord(physics, label, friction, gap) {
  const w = physics.createWorld({
    seed: 2, slope: 0, friction,
    tops: [
      { name: 'Left', mass: 1, radius: 0.1, friction: 0.4, x: -gap / 2 - 0.1, y: 0, vx: 1, vy: 0.1, spin: 40 },
      { name: 'Right', mass: 2, radius: 0.1, friction: 0.4, x: gap / 2 + 0.1, y: 0, vx: -1, vy: 0, spin: 30 },
    ],
  });
  const before = copy(w.tops);
  const hit = physics.collide(w, 0, 1);
  return { label, before, hit, after: copy(w.tops) };
}

export async function clashes({ load }) {
  const physics = await physicsOf(load);
  const contacts = [];
  for (const friction of [true, false]) {
    for (const gap of [0.004, 0.02, 0.1, 0.25, 0.8]) contacts.push(contactRecord(physics, `friction ${friction}, gap ${gap}`, friction, gap));
  }

  const records = [];
  for (const topFriction of [0.9, 0.1, 0]) {
    for (const friction of [true, false]) {
      records.push(clashRecord(physics, `friction ${friction}, top friction ${topFriction}`, friction, [
        { name: 'Small', mass: 0.7, radius: 0.1, friction: topFriction, x: -0.08, y: 0.02, vx: 0.9, vy: 0.1, spin: 50 },
        { name: 'Big', mass: 2.4, radius: 0.15, friction: topFriction, x: 0.1, y: -0.03, vx: -0.4, vy: 0.2, spin: 30 },
      ]));
    }
  }

  for (const [flip, wideSpin] of [[false, 1], [true, 1], [false, 0.3], [true, 0.3], [false, 0.02], [true, 0.02]]) {
    const tiny = { name: 'Tiny', mass: 0.5, radius: 0.05, friction: 1, x: -0.04, y: 0.01, vx: 1, vy: 0, spin: 60 };
    const wide = { name: 'Wide', mass: 3, radius: 0.2, friction: 0.1, x: 0.17, y: -0.01, vx: -1, vy: 0, spin: wideSpin };
    records.push(clashRecord(physics, `a tiny top and a wide top with spin ${wideSpin} (${flip ? 'wide' : 'tiny'} first), friction on`, true, flip ? [{ ...wide }, { ...tiny }] : [{ ...tiny }, { ...wide }]));
  }

  const r = rng(606);
  const pick = (lo, hi) => lo + (hi - lo) * r();
  const frictions = [0, 0, 0.1, 0.4, 1];
  for (let k = 0; k < 40; k++) {
    const ra = pick(0.05, 0.2);
    const rb = pick(0.05, 0.2);
    const gap = (ra + rb) * pick(0.5, 0.95);
    const angle = pick(0, 2 * Math.PI);
    const nx = Math.cos(angle);
    const ny = Math.sin(angle);
    const a = { name: 'A', mass: pick(0.5, 3), radius: ra, friction: frictions[Math.floor(r() * frictions.length)], x: -0.1, y: 0.05, vx: pick(-1.5, 1.5), vy: pick(-1.5, 1.5), spin: pick(1, 60) };
    const b = { name: 'B', mass: pick(0.5, 3), radius: rb, friction: frictions[Math.floor(r() * frictions.length)], x: -0.1 + nx * gap, y: 0.05 + ny * gap, vx: pick(-1.5, 1.5), vy: pick(-1.5, 1.5), spin: pick(1, 60) };
    const vn = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
    if (vn > -0.2) {
      const fix = -0.2 - vn - pick(0, 1);
      b.vx += fix * nx;
      b.vy += fix * ny;
    }
    for (const friction of [true, false]) {
      records.push(clashRecord(physics, `seeded clash ${k + 1} (friction ${friction}, masses ${a.mass.toFixed(2)} and ${b.mass.toFixed(2)}, top frictions ${a.friction} and ${b.friction})`, friction, [{ ...a }, { ...b }]));
    }
  }
  return { contacts, clashes: records };
}

// ---- 7: energy with friction off -----------------------------------------------------------------------------
export async function energyRun({ load }) {
  const { DT, createWorld, step } = await physicsOf(load);
  const w = createWorld({
    seed: 3, friction: false, slope: 0,
    tops: [
      { name: 'Left', mass: 1, radius: 0.1, friction: 0.8, x: -0.4, y: 0.03, vx: 0.6, vy: 0, spin: 30 },
      { name: 'Right', mass: 2.5, radius: 0.15, friction: 0.8, x: 0.4, y: -0.02, vx: -0.5, vy: 0.05, spin: 45 },
    ],
  });
  const start = copy(w.tops);
  // 1.25 s of game time, so a different DT sees the same stretch of play.
  const ticks = Math.ceil(1.25 / DT - 1e-9);
  const frames = [];
  for (let t = 0; t < ticks; t++) {
    step(w);
    frames.push({ tick: w.tick, tops: copy(w.tops) });
  }
  return { ticks, start, frames };
}

// ---- 8: ring-out and spin-down on tick 1 ---------------------------------------------------------------------
function afterOneStep(physics, config) {
  const w = physics.createWorld(config);
  physics.step(w);
  return { tick: w.tick, statuses: w.tops.map((t) => t.status), winner: w.winner };
}

export async function ringout({ load }) {
  const physics = await physicsOf(load);
  const out = {};
  const cases = [
    { label: 'past the rim on +x', arenaRadius: 1, out: { x: 1.5, y: 0 } },
    { label: 'past the rim on -y, arena radius 2', arenaRadius: 2, out: { x: 0, y: -2.3 } },
    { label: 'past the rim on a diagonal', arenaRadius: 1, out: { x: -0.8, y: 0.8 } },
  ];
  out.cases = cases.map((c) => ({
    label: c.label,
    ...afterOneStep(physics, {
      seed: 7, arenaRadius: c.arenaRadius,
      tops: [{ name: 'Inside', x: 0, y: 0, vx: 0, vy: 0, spin: 50 }, { name: 'Outside', ...c.out, vx: 0, vy: 0, spin: 50 }],
    }),
  }));
  out.dflt = afterOneStep(physics, { seed: 7, tops: [{ name: 'Over', x: 1.05, y: 0, vx: 0, vy: 0, spin: 50 }, { name: 'Under', x: -0.95, y: 0, vx: 0, vy: 0, spin: 50 }] });
  out.wider = afterOneStep(physics, { seed: 7, arenaRadius: 2, tops: [{ name: 'Far', x: 1.5, y: 0, vx: 0, vy: 0, spin: 50 }, { name: 'Mid', x: 0, y: -1.2, vx: 0, vy: 0, spin: 50 }] });
  out.narrower = afterOneStep(physics, { seed: 7, arenaRadius: 0.5, tops: [{ name: 'Near', x: 0.7, y: 0, vx: 0, vy: 0, spin: 50 }, { name: 'Core', x: 0.1, y: 0, vx: 0, vy: 0, spin: 50 }] });
  out.wide = afterOneStep(physics, { seed: 7, arenaRadius: 1, tops: [{ name: 'Overhang', radius: 0.2, x: 0.95, y: 0, vx: 0, vy: 0, spin: 50 }, { name: 'Centre', x: -0.3, y: 0, vx: 0, vy: 0, spin: 50 }] });
  out.both = afterOneStep(physics, { seed: 7, tops: [{ name: 'Over and spent', x: 1.5, y: 0, vx: 0, vy: 0, spin: 2 }, { name: 'Steady', x: 0, y: 0, vx: 0, vy: 0, spin: 50 }] });
  out.spent = afterOneStep(physics, { seed: 7, tops: [{ name: 'Spent', x: 0, y: 0, vx: 0, vy: 0, spin: 2 }, { name: 'Steady', x: 0.5, y: 0, vx: 0, vy: 0, spin: 50 }] });
  out.edges = [[undefined, 4], [undefined, 3], [undefined, 0.5], [undefined, 4.5], [9, 9], [9, 8], [9, 9.5], [1, 3], [1, 1]].map(([minSpin, spinValue]) => {
    const cfg = { seed: 7, friction: false, tops: [{ name: 'Edge', x: 0, y: 0, vx: 0, vy: 0, spin: spinValue }, { name: 'Steady', x: 0.5, y: 0, vx: 0, vy: 0, spin: 80 }] };
    if (minSpin !== undefined) cfg.minSpin = minSpin;
    return { minSpin: minSpin === undefined ? null : minSpin, spin: spinValue, ...afterOneStep(physics, cfg) };
  });
  out.draw = afterOneStep(physics, { seed: 7, tops: [{ name: 'Over', x: 1.4, y: 0, vx: 0, vy: 0, spin: 50 }, { name: 'Under', x: -1.4, y: 0, vx: 0, vy: 0, spin: 50 }] });
  return out;
}

// ---- 9: replay -----------------------------------------------------------------------------------------------
export async function replay({ load }) {
  const { createWorld, step } = await physicsOf(load);
  const out = {};
  const config = {
    seed: 2026,
    tops: [
      { name: 'Wren', mass: 0.1, radius: 0.4, friction: -2, spin: 50 },
      { name: 'Copperhull', mass: 9, radius: 0.001, friction: 5, spin: 45 },
    ],
  };
  const frozen = JSON.stringify(config);
  const sparse = { tops: [{}, { name: 'Plain' }] };
  const sparseFrozen = JSON.stringify(sparse);
  step(createWorld(sparse), [{ x: 1, y: 0 }, null]);
  out.sparse = [sparseFrozen, JSON.stringify(sparse)];

  out.bares = [];
  for (const bare of [{}, { seed: 3 }, { friction: false }, { tops: [] }, { seed: 4, tops: [{ x: 0.1 }, {}] }]) {
    const bareFrozen = JSON.stringify(bare);
    const bareWorld = createWorld(bare);
    step(bareWorld);
    step(bareWorld, [{ x: 1, y: 1 }, null]);
    out.bares.push([bareFrozen, JSON.stringify(bare)]);
  }

  const first = createWorld(config);
  out.afterCreate = [frozen, JSON.stringify(config)];
  out.firstTop = [first.tops[0].mass, first.tops[0].radius, first.tops[0].friction];
  const script = inputScript(31, 7200, 2);
  const log = [];
  const live = createWorld(config);
  while (live.winner === null && live.tick < 7200) {
    const row = clone(script[live.tick]);
    log.push(clone(row));
    step(live, row);
  }
  out.afterLive = [frozen, JSON.stringify(config)];
  out.live = { winner: live.winner, tick: live.tick, snap: snapshot(live) };
  const again = createWorld(config);
  for (const row of log) step(again, row);
  out.replay = { winner: again.winner, tick: again.tick, snap: snapshot(again) };
  return out;
}

// ---- 10: the computer's answer is valid ----------------------------------------------------------------------
export async function aiShape({ load }) {
  const physics = await physicsOf(load);
  const { aiInput } = await aiOf(load);
  const out = {};
  const world = physics.createWorld({ seed: 3, tops: SOLO_TOPS });
  out.ticks = [];
  for (let t = 0; t < 600 && world.winner === null; t++) {
    const before = JSON.stringify(world);
    const answer = aiInput(world, 1);
    out.ticks.push({ t, before, after: JSON.stringify(world), answer });
    physics.step(world, [dodgerInput(world, 0), answer]);
  }

  const awkward = [
    ['the foe at the centre', { x: 0, y: 0 }, { x: 0.4, y: 0.1 }],
    ['the computer at the centre', { x: 0.3, y: -0.2 }, { x: 0, y: 0 }],
    ['both on one spot', { x: 0.2, y: 0.2 }, { x: 0.2, y: 0.2 }],
    ['both at the centre', { x: 0, y: 0 }, { x: 0, y: 0 }],
    ['the foe at the centre and the computer beside it', { x: 0, y: 0 }, { x: 0.05, y: 0 }],
  ];
  out.awkward = awkward.map(([label, a, b]) => {
    const w = physics.createWorld({ seed: 5, tops: [{ ...a, vx: 0, vy: 0, spin: 50 }, { ...b, vx: 0, vy: 0, spin: 50 }] });
    const before = JSON.stringify(w);
    const answers = [0, 1].map((idx) => aiInput(w, idx));
    return { label, before, after: JSON.stringify(w), answers };
  });

  const done = physics.createWorld({ seed: 3, tops: [{ x: 5 }, { name: 'Other' }] });
  physics.step(done, null);
  out.doneWinner = done.winner;
  const alone = physics.createWorld({ seed: 3, tops: [{}] });
  out.nothing = [[done, 1, 'the winner of a finished match'], [done, 0, 'a top that is out'], [alone, 0, 'a world with one top']]
    .map(([w, who, label]) => ({ label, answer: aiInput(w, who) }));
  return out;
}

// ---- 11: the computer is deterministic -----------------------------------------------------------------------
const MATCH_TICKS = 500;
const MATCH_SEEDS = [4, 9];

const matchKey = (m) => `${snapshot(m.world)}|${JSON.stringify(m.rows)}`;

export async function aiDeterminism({ load }) {
  const physics = await physicsOf(load);
  const ai = await aiOf(load);
  const newMatch = (seed) => ({ world: physics.createWorld({ seed, tops: SOLO_TOPS }), rows: [] });
  const playTick = (aiInput, opponent, m) => {
    const row = [opponent(m.world, 0), aiInput(m.world, 1)];
    m.rows.push(clone(row));
    physics.step(m.world, row);
  };
  // Fresh copies of src/ai.js, loaded before the clocks come off: each has seen no other match.
  const fresh = {};
  for (const name of ['idle', 'dodger']) {
    for (const seed of MATCH_SEEDS) fresh[`${name}-${seed}`] = await aiOf(load, `${name}-${seed}`);
  }
  const out = { matches: [] };
  await withoutClocksOrRandom(() => {
    for (const [name, opponent] of [['idle', idleInput], ['dodger', dodgerInput]]) {
      const a = newMatch(MATCH_SEEDS[0]);
      const b = newMatch(MATCH_SEEDS[0]);
      const c = newMatch(MATCH_SEEDS[1]);
      for (let t = 0; t < MATCH_TICKS; t++) {
        for (const m of [a, c, b]) playTick(ai.aiInput, opponent, m);
      }
      const record = { name, a: matchKey(a), b: matchKey(b), c: matchKey(c), alone: [] };
      for (const [m, seed] of [[a, MATCH_SEEDS[0]], [c, MATCH_SEEDS[1]]]) {
        const alone = newMatch(seed);
        for (let t = 0; t < MATCH_TICKS; t++) playTick(fresh[`${name}-${seed}`].aiInput, opponent, alone);
        record.alone.push({ seed, turnAbout: matchKey(m), alone: matchKey(alone) });
      }
      out.matches.push(record);
    }
  });
  await withoutClocksOrRandom(() => {
    const w = physics.createWorld({ seed: 4, tops: SOLO_TOPS });
    for (let t = 0; t < 200; t++) physics.step(w, [idleInput(), ai.aiInput(w, 1)]);
    const twin = JSON.parse(JSON.stringify(w));
    out.twin = { original: ai.aiInput(w, 1), copy: ai.aiInput(twin, 1) };
  });
  return out;
}

// ---- 12, 13: the computer against the two scripted opponents -------------------------------------------------
const OPPONENTS = { idle: idleInput, dodger: dodgerInput };

export async function soloWinners({ load }, opponent, seeds, ticks) {
  const physics = await physicsOf(load);
  const ai = await aiOf(load);
  const out = [];
  for (let seed = 1; seed <= seeds; seed++) {
    const { world } = playSolo(physics, ai, seed, OPPONENTS[opponent], ticks);
    out.push({ seed, winner: world.winner, tick: world.tick });
  }
  return out;
}

// ---- 14: solo matches replay ---------------------------------------------------------------------------------
export async function soloReplay({ load }) {
  const physics = await physicsOf(load);
  const ai = await aiOf(load);
  const frozen = JSON.stringify(SOLO_TOPS);
  const matches = [];
  for (const label of ['idle', 'dodger']) {
    for (const seed of [2, 5, 11]) {
      const { world: live, rows } = playSolo(physics, ai, seed, OPPONENTS[label], 2400);
      // The replay never calls the AI: it feeds back what was recorded for both tops.
      const again = physics.createWorld({ seed, tops: SOLO_TOPS });
      for (const row of rows) physics.step(again, clone(row));
      matches.push({
        label, seed,
        live: { winner: live.winner, tick: live.tick, snap: snapshot(live) },
        replay: { winner: again.winner, tick: again.tick, snap: snapshot(again) },
      });
    }
  }
  return { matches, topsBefore: frozen, topsAfter: JSON.stringify(SOLO_TOPS) };
}

// ---- 15: the config fields -----------------------------------------------------------------------------------
export async function configFields({ load }) {
  const physics = await physicsOf(load);
  const { createWorld, step } = physics;
  const out = {};
  // One lone top placed where the test says, stepped for `ticks` with the same input every tick (or none).
  const lone = (config, top, ticks, input) => {
    const w = createWorld({ seed: 1, tops: [{ vx: 0, vy: 0, spin: 50, ...top }], ...config });
    for (let t = 0; t < ticks; t++) step(w, input ? [input] : undefined);
    return w.tops[0];
  };

  out.given = createWorld({ seed: 3, tops: [{ name: 'Given', mass: 1.7, radius: 0.13, friction: 0.35, x: 0.12, y: -0.34, vx: 0.56, vy: 0.78, spin: 33 }] }).tops[0];
  out.zeros = createWorld({ seed: 3, tops: [{ x: 0, y: 0, vx: 0, vy: 0, spin: 0, friction: 0 }, { x: 0, y: 0.3, vx: 0, vy: 0, spin: 0, friction: 0 }] }).tops;

  const spinStatus = (config, spinValue) => {
    const w = createWorld({ seed: 1, friction: false, ...config, tops: [{ x: 0, y: 0, vx: 0, vy: 0, spin: spinValue }, { x: 0.6, y: 0, vx: 0, vy: 0, spin: 80 }] });
    step(w);
    return w.tops[0].status;
  };
  out.spinStatus = {
    'default 3.9': spinStatus({}, 3.9), 'default 4': spinStatus({}, 4), 'default 4.1': spinStatus({}, 4.1),
    'min10 9.9': spinStatus({ minSpin: 10 }, 9.9), 'min10 10.1': spinStatus({ minSpin: 10 }, 10.1), 'min10 4.1': spinStatus({ minSpin: 10 }, 4.1),
  };

  out.onTop = lone({ slope: 0 }, { x: -0.4, y: 0, vx: 0.3, friction: 1 }, 100);
  out.offTop = lone({ friction: false, slope: 0 }, { x: -0.4, y: 0, vx: 0.3, friction: 1 }, 100);
  out.steered = lone({ friction: false, slope: 0 }, { x: 0, y: 0 }, 200, { x: 1, y: 0.5 });

  const pull = (config, x) => lone({ friction: false, ...config }, { x, y: 0 }, 1).vx;
  out.pull = {
    default: pull({}, 0.5), defaultNeg: pull({}, -0.5), flat: pull({ slope: 0 }, 0.5),
    far: pull({ slope: 1 }, 0.8), near: pull({ slope: 1 }, 0.4), s2: pull({ slope: 2 }, 0.5), s1: pull({ slope: 1 }, 0.5),
    vy: lone({ friction: false, slope: 1 }, { x: 0, y: -0.6 }, 1).vy,
  };

  const push = (steer) => lone({ friction: false, slope: 0, steer }, { x: 0, y: 0 }, 5, { x: 1, y: 0 }).vx;
  out.push = { 1: push(1), 3: push(3), 5: push(5), 10: push(10), default: lone({ friction: false, slope: 0 }, { x: 0, y: 0 }, 5, { x: 1, y: 0 }).vx };
  return out;
}

// ---- 16: steering and step's return --------------------------------------------------------------------------
const steerMake = (createWorld) => createWorld({
  seed: 1, friction: false, slope: 0, steer: 2,
  tops: [
    { name: 'A', radius: 0.05, x: -0.3, y: 0, vx: 0, vy: 0, spin: 50 },
    { name: 'B', radius: 0.05, x: 0.3, y: 0, vx: 0, vy: 0, spin: 50 },
  ],
});

// Top A's x, y, vx and vy after 20 ticks of each row of inputs (a row is `inputs`, which may be undefined).
export async function steerRuns({ load }, rows) {
  const { createWorld, step } = await physicsOf(load);
  return rows.map((row) => {
    const w = steerMake(createWorld);
    for (let t = 0; t < 20; t++) step(w, structuredClone(row));
    const a = w.tops[0];
    return [a.x, a.y, a.vx, a.vy];
  });
}

export async function steerWorld({ load }) {
  const { createWorld, step } = await physicsOf(load);
  const out = {};
  const w = steerMake(createWorld);
  const first = step(w, [{ x: 1, y: 0 }, null]);
  out.sameAfterInputs = first === w;
  out.tick1 = w.tick;
  out.sameWithoutInputs = step(w) === w;
  out.tick2 = w.tick;

  const pair = steerMake(createWorld);
  for (let t = 0; t < 20; t++) step(pair, [null, { x: 1, y: 0 }]);
  out.pair = pair.tops.map((t) => ({ x: t.x, vx: t.vx }));

  const short = steerMake(createWorld);
  for (let t = 0; t < 20; t++) step(short, [{ x: 1, y: 1 }]);
  out.short = short.tops.map((t) => ({ x: t.x, y: t.y, vx: t.vx, vy: t.vy }));
  const lonely = steerMake(createWorld);
  for (let t = 0; t < 20; t++) step(lonely, [{ x: 1, y: 0 }, null]);
  out.lonely = lonely.tops.map((t) => ({ x: t.x, y: t.y, vx: t.vx, vy: t.vy }));
  const holey = steerMake(createWorld);
  for (let t = 0; t < 20; t++) step(holey, [undefined, { x: -1, y: 1 }]);
  out.holey = holey.tops.map((t) => ({ x: t.x, vx: t.vx }));

  const far = () => createWorld({
    seed: 1, friction: false, slope: 0, steer: 2, arenaRadius: 1000,
    tops: [{ radius: 0.05, x: -300, y: 0, vx: 0, vy: 0, spin: 50 }, { radius: 0.05, x: 300, y: 0, vx: 0, vy: 0, spin: 50 }],
  });
  const aged = far();
  for (let t = 0; t < 1500; t++) step(aged);
  for (let t = 0; t < 20; t++) step(aged, [{ x: 1, y: 1 }, { x: -1, y: -1 }]);
  const young = far();
  for (let t = 0; t < 20; t++) step(young, [{ x: 1, y: 1 }, { x: -1, y: -1 }]);
  out.aged = aged.tops.map((t) => ({ vx: t.vx, vy: t.vy }));
  out.young = young.tops.map((t) => ({ vx: t.vx, vy: t.vy }));
  return out;
}

// ---- 17: a top that is out, and the winner -------------------------------------------------------------------
const mark = (t) => JSON.stringify([t.x, t.y, t.vx, t.vy, t.spin, t.status]);

export async function outTops({ load }) {
  const { DT, createWorld, step } = await physicsOf(load);
  const out = { variants: [] };
  const variants = [
    {
      label: 'a spun-down top',
      a: { name: 'A', mass: 1, radius: 0.1, friction: 0.2, x: -0.3, y: 0, vx: 1.6, vy: 0, spin: 60 },
      b: { name: 'B', mass: 1, radius: 0.1, friction: 0.5, x: 0.25, y: 0.02, vx: 0.3, vy: -0.1, spin: 4 + 1e-9 },
      want: 'spundown',
    },
    {
      label: 'a rung-out top',
      a: { name: 'A', mass: 1, radius: 0.1, friction: 0.2, x: 0.2, y: 0, vx: 2.5, vy: 0, spin: 60 },
      b: { name: 'B', mass: 1, radius: 0.2, friction: 0.5, x: 1.15, y: 0.02, vx: 0.2, vy: 0.1, spin: 3 },
      want: 'ringout',
    },
  ];
  for (const v of variants) for (const outFirst of [false, true]) {
    const ai = outFirst ? 1 : 0;
    const bi = outFirst ? 0 : 1;
    const tops = outFirst ? [v.b, v.a] : [v.a, v.b];
    const world = createWorld({ seed: 3, slope: 1, steer: 2, tops });
    // The control: top A alone in a world of one, same everything else.
    const control = createWorld({ seed: 3, slope: 1, steer: 2, tops: [v.a] });
    const rows = (t) => {
      const row = [null, null];
      row[bi] = t % 2 ? { x: 1, y: 1 } : { x: -1, y: 0.5 };
      return row;
    };
    step(world, clone(rows(0)));
    step(control, [null]);
    const record = {
      label: `${v.label}, listed ${outFirst ? 'first' : 'second'}`, want: v.want, reach: v.a.radius + v.b.radius,
      statusB: world.tops[bi].status, statusA: world.tops[ai].status, spinB: v.b.spin, xB: v.b.x, yB: v.b.y,
      frozen: mark(world.tops[bi]), later: [], nearest: Infinity,
    };
    for (let t = 1; t < 60; t++) {
      step(world, clone(rows(t)));
      step(control, [null]);
      record.later.push({ tick: world.tick, b: mark(world.tops[bi]), a: mark(world.tops[ai]), control: mark(control.tops[0]) });
      record.nearest = Math.min(record.nearest, Math.hypot(world.tops[ai].x - world.tops[bi].x, world.tops[ai].y - world.tops[bi].y));
    }
    out.variants.push(record);
  }

  const w = createWorld({
    seed: 3,
    tops: [{ name: 'Fading', x: 0, y: 0, vx: 0, vy: 0, spin: 6, friction: 1 }, { name: 'Gone', x: 1.4, y: 0, vx: 0, vy: 0, spin: 50 }],
  });
  const limit = Math.ceil(12 / DT);
  let steps = 0;
  let downAt = null;
  out.fading = [];
  while (steps < limit && (downAt === null || steps < downAt + 120)) {
    step(w);
    steps++;
    out.fading.push({ steps, tick: w.tick, winner: w.winner });
    if (downAt === null && w.tops[0].status === 'spundown') downAt = steps;
  }
  out.downAt = downAt;

  const pair = createWorld({ seed: 3, slope: 0, friction: false, tops: [{ x: -0.4, y: 0, vx: 0, vy: 0, spin: 50 }, { x: 0.4, y: 0, vx: 0, vy: 0, spin: 50 }] });
  out.pair = [];
  for (let t = 0; t < 30; t++) {
    step(pair);
    out.pair.push({ tick: pair.tick, winner: pair.winner });
  }
  const solo = createWorld({ seed: 3, tops: [{ x: 0, y: 0, vx: 0, vy: 0, spin: 6, friction: 1 }] });
  for (let t = 0; t < limit && solo.tops[0].status === 'in'; t++) step(solo);
  for (let t = 0; t < 10; t++) step(solo);
  out.solo = { status: solo.tops[0].status, winner: solo.winner };
  return out;
}

// ---- 18: every pair clashes ----------------------------------------------------------------------------------
export async function allPairs({ load }) {
  const { DT, createWorld, step } = await physicsOf(load);
  const ticks = Math.ceil(1.2 / DT);
  const radius = 0.1;
  const out = { radius, pairs: [] };
  for (let i = 0; i < 4; i++) {
    for (let j = i + 1; j < 4; j++) {
      const parked = [{ x: 0, y: 0.8 }, { x: 0, y: -0.8 }];
      const tops = [];
      for (let k = 0; k < 4; k++) {
        if (k === i) tops.push({ name: `T${k}`, mass: 1, radius, x: -0.35, y: 0, vx: 0.6, vy: 0, spin: 50 });
        else if (k === j) tops.push({ name: `T${k}`, mass: 1, radius, x: 0.35, y: 0, vx: -0.6, vy: 0, spin: 50 });
        else tops.push({ name: `T${k}`, mass: 1, radius, ...parked.shift(), vx: 0, vy: 0, spin: 50 });
      }
      const w = createWorld({ seed: 2, friction: false, slope: 0, tops });
      let closest = Infinity;
      for (let t = 0; t < ticks; t++) {
        step(w);
        closest = Math.min(closest, Math.hypot(w.tops[i].x - w.tops[j].x, w.tops[i].y - w.tops[j].y));
      }
      out.pairs.push({ i, j, vxI: w.tops[i].vx, vxJ: w.tops[j].vx, closest });
    }
  }
  return out;
}

// ---- 19: the computer steers against the nearest top ---------------------------------------------------------
export async function aiNearest({ load }) {
  const physics = await physicsOf(load);
  const { aiInput } = await aiOf(load);
  const fields = (t) => ({ name: t.name, mass: t.mass, radius: t.radius, friction: t.friction, x: t.x, y: t.y, vx: t.vx, vy: t.vy, spin: t.spin });
  const r = rng(1919);
  const pick = (lo, hi) => lo + (hi - lo) * r();
  const out = { layouts: [], tooClose: 0 };
  for (let n = 0; n < 60; n++) {
    const count = 3 + (n % 2);
    const me = Math.floor(r() * count);
    const tops = [];
    for (let k = 0; k < count; k++) {
      // Everyone is the same size and weight, so "nearest" means the same thing by centre or by edge.
      const rim = k === me ? 0.95 : 0.8;
      const angle = pick(0, 2 * Math.PI);
      const dist = pick(0.1, rim);
      tops.push({ name: `T${k}`, mass: 1.4, radius: 0.12, friction: 0.4, x: Math.cos(angle) * dist, y: Math.sin(angle) * dist, vx: pick(-0.4, 0.4), vy: pick(-0.4, 0.4), spin: pick(30, 60) });
    }
    const dists = tops.map((t, k) => (k === me ? Infinity : Math.hypot(t.x - tops[me].x, t.y - tops[me].y)));
    const sorted = [...dists].sort((a, b) => a - b);
    if (sorted[1] < sorted[0] * 1.05) { out.tooClose++; continue; } // too close to call which is nearest
    const nearest = dists.indexOf(sorted[0]);
    const full = physics.createWorld({ seed: 5, tops });
    const alone = physics.createWorld({ seed: 5, tops: [fields(tops[me]), fields(tops[nearest])] });
    out.layouts.push({ n, count, me, nearest, d0: sorted[0], d1: sorted[1], got: aiInput(full, me), want: aiInput(alone, 0) });
  }

  const lineup = (withNear) => {
    const tops = [
      { name: 'Far', mass: 1.4, radius: 0.12, friction: 0.4, x: 0.45, y: -0.35, vx: 0, vy: 0, spin: 50 },
      { name: 'Me', mass: 1.4, radius: 0.12, friction: 0.4, x: 0.05, y: 0.05, vx: 0, vy: 0, spin: 50 },
    ];
    if (withNear) tops.push({ name: 'Near', mass: 1.4, radius: 0.12, friction: 0.4, x: -0.3, y: 0.2, vx: 0, vy: 0, spin: 4 + 1e-9 });
    const w = physics.createWorld({ seed: 5, tops });
    physics.step(w);
    return w;
  };
  const crowded = lineup(true);
  out.crowdedStatuses = crowded.tops.map((t) => t.status);
  out.crowded = aiInput(crowded, 1);
  out.without = aiInput(lineup(false), 1);
  return out;
}
