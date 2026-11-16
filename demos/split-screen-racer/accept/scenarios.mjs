// Scenarios for the held-out checks: each runs in a process of its own beside the workspace (../../probe.mjs),
// steps the workspace's simulation as a check needs, and returns what it saw as plain data. None of them judges
// anything: the tests next to this file compare the observations with the grader's own geometry and numbers.
// A scenario gets { load }, which imports a module of the workspace by its path there.
import { distToLoop, inputsAt, rng, tangent, totalLength, wrapAngle } from './helpers.mjs';

const FULL = { throttle: 1, brake: 0, steer: 0 };
const snap = (x) => JSON.parse(JSON.stringify(x));

async function sim(load) {
  const [vehicles, track, race, ai, camera] = await Promise.all([
    load('src/vehicles.js'),
    load('src/track.js'),
    load('src/race.js'),
    load('src/ai.js'),
    load('src/camera.js'),
  ]);
  return { vehicles, track, race, ai, camera };
}

const trackOf = (m, seed) => (seed === null ? m.track.fixedTrack() : m.track.generateTrack(seed));
const radiiOf = (m) => ({ car: m.vehicles.VEHICLES.car.radius, bike: m.vehicles.VEHICLES.bike.radius });

// ---- vehicles ------------------------------------------------------------------------------------------------

function straight(m, kindOrSpec, surface, ticks) {
  const v = m.vehicles.createVehicle(kindOrSpec, { x: 0, y: 0, heading: 0 });
  const speeds = [];
  for (let i = 0; i < ticks; i++) {
    m.vehicles.stepVehicle(v, FULL, surface);
    speeds.push(v.speed);
  }
  return { v, speeds };
}

// What kind of value each leaf of `v` is: a plain-data tree holds only numbers, strings, booleans and null.
function leaves(v) {
  if (v === null) return 'null';
  if (Array.isArray(v)) return v.map(leaves);
  const t = typeof v;
  if (t === 'number') return Number.isFinite(v) ? 'number' : 'non-finite number';
  if (t !== 'object') return t;
  const proto = Object.getPrototypeOf(v);
  if (proto !== Object.prototype && proto !== null) return 'not a plain object';
  const out = {};
  for (const k of Object.keys(v)) out[k] = leaves(v[k]);
  return out;
}

export async function vehicleData({ load }) {
  const { VEHICLES } = await load('src/vehicles.js');
  const out = { kinds: {}, leaves: leaves(VEHICLES), json: JSON.stringify(VEHICLES) ?? null };
  for (const kind of ['car', 'bike']) {
    const s = VEHICLES && VEHICLES[kind];
    out.kinds[kind] = s && typeof s === 'object' ? Object.fromEntries(['topSpeed', 'accel', 'turnRate', 'mass', 'radius'].map((f) => [f, s[f]])) : null;
  }
  return out;
}

export async function headingAndDt({ load }) {
  const m = await sim(load);
  const out = { DT: m.race.DT, second: null, steady: {}, up: null };
  const one = straight(m, 'car', 'road', 60).v;
  out.second = { x: one.x, y: one.y };
  for (const kind of ['car', 'bike']) {
    const w = straight(m, kind, 'road', 3000).v;
    const before = { x: w.x, y: w.y };
    m.vehicles.stepVehicle(w, FULL, 'road');
    out.steady[kind] = { before, after: { x: w.x, y: w.y }, speed: w.speed };
  }
  const v2 = m.vehicles.createVehicle('bike', { x: 5, y: 5, heading: Math.PI / 2 });
  for (let i = 0; i < 60; i++) m.vehicles.stepVehicle(v2, { throttle: 1 }, 'road');
  out.up = { x: v2.x, y: v2.y };
  return out;
}

export async function topSpeeds({ load }) {
  const m = await sim(load);
  const out = {};
  for (const kind of ['car', 'bike']) {
    out[kind] = { speed: straight(m, kind, 'road', 3000).v.speed, stated: m.vehicles.VEHICLES[kind].topSpeed };
  }
  return out;
}

export async function acceleration({ load }) {
  const m = await sim(load);
  const out = { DT: m.race.DT };
  for (const kind of ['car', 'bike']) {
    out[kind] = { speeds: straight(m, kind, 'road', 3000).speeds, stated: m.vehicles.VEHICLES[kind].topSpeed };
  }
  return out;
}

// Full steer at a steady speed: the path from tick 60 on, one point a tick, and the speed summed over it.
export async function turning({ load }) {
  const m = await sim(load);
  const { VEHICLES } = m.vehicles;
  const target = 0.6 * Math.min(VEHICLES.car.topSpeed, VEHICLES.bike.topSpeed);
  const out = { target };
  for (const kind of ['car', 'bike']) {
    const v = m.vehicles.createVehicle(kind, { x: 0, y: 0, heading: 0 });
    let t = 0;
    while (v.speed < target && t < 3000) {
      m.vehicles.stepVehicle(v, FULL, 'road');
      t++;
    }
    const run = { reached: v.speed >= target, speed: v.speed, pts: [], speedSum: 0 };
    if (run.reached) {
      for (let i = 0; i < 240; i++) {
        m.vehicles.stepVehicle(v, { throttle: v.speed < target ? 1 : 0, brake: 0, steer: 1 }, 'road');
        if (i >= 60) {
          run.pts.push({ x: v.x, y: v.y });
          run.speedSum += v.speed;
        }
      }
    }
    out[kind] = run;
  }
  return out;
}

export async function offTrack({ load }) {
  const m = await sim(load);
  const out = {};
  for (const kind of ['car', 'bike']) {
    const road = straight(m, kind, 'road', 3000).v.speed;
    const off = straight(m, kind, 'off', 3000).v.speed;
    const v = straight(m, kind, 'road', 3000).v;
    for (let i = 0; i < 120; i++) m.vehicles.stepVehicle(v, { throttle: 1 }, 'off');
    out[kind] = { road, off, afterLeaving: v.speed };
  }
  return out;
}

export async function handlingFollowsData({ load }) {
  const m = await sim(load);
  const spec = { ...m.vehicles.VEHICLES.car, topSpeed: m.vehicles.VEHICLES.car.topSpeed * 1.5 };
  return { topSpeed: spec.topSpeed, speed: straight(m, spec, 'road', 4000).v.speed };
}

// Each pair of inputs is run from the same history for 90 ticks; the end states come back side by side.
export async function inputPairs({ load }, kinds, pairs) {
  const m = await sim(load);
  const out = [];
  for (const kind of kinds) {
    for (const { label, a: inA, b: inB } of pairs) {
      const make = () => {
        const v = m.vehicles.createVehicle(kind, { x: 10, y: -20, heading: 0.3 });
        for (let i = 0; i < 90; i++) m.vehicles.stepVehicle(v, { throttle: 1, brake: 0, steer: 0.2 }, 'road');
        return v;
      };
      const a = make();
      const b = make();
      for (let i = 0; i < 90; i++) {
        m.vehicles.stepVehicle(a, { ...inA }, 'road');
        m.vehicles.stepVehicle(b, { ...inB }, 'road');
      }
      const state = (v) => ({ x: v.x, y: v.y, heading: v.heading, speed: v.speed });
      out.push({ kind, label, a: state(a), b: state(b) });
    }
  }
  return out;
}

export async function braking({ load }) {
  const m = await sim(load);
  const out = {};
  for (const kind of ['car', 'bike']) {
    const braked = straight(m, kind, 'road', 3000).v;
    const coasted = straight(m, kind, 'road', 3000).v;
    const start = braked.speed;
    for (let i = 0; i < 30; i++) {
      m.vehicles.stepVehicle(braked, { throttle: 0, brake: 1, steer: 0 }, 'road');
      m.vehicles.stepVehicle(coasted, { throttle: 0, brake: 0, steer: 0 }, 'road');
    }
    const run = { start, braked: braked.speed, coasted: coasted.speed, speeds: [] };
    for (let i = 0; i < 1200; i++) {
      m.vehicles.stepVehicle(braked, { throttle: 0, brake: 1, steer: i % 7 === 0 ? 1 : -1 }, 'road');
      run.speeds.push(braked.speed);
    }
    out[kind] = run;
  }
  return out;
}

// ---- tracks ----------------------------------------------------------------------------------------------------

// What fixedTrack() gives over several calls, as JSON taken at each moment.
export async function fixedStability({ load }) {
  const { fixedTrack } = await load('src/track.js');
  const t = fixedTrack();
  const before = JSON.stringify(t);
  const again = JSON.stringify(fixedTrack());
  const twelve = fixedTrack({ checkpoints: 12 });
  const twelveGates = twelve.checkpoints.length;
  const afterTwelve = JSON.stringify(fixedTrack());
  return { name: t.name, before, again, twelveGates, afterTwelve, earlierGates: t.checkpoints.length, earlier: JSON.stringify(t) };
}

// surfaceAt on about 900 points, half of them near the road, answered for the track of `seed` (null: the fixed one).
export async function surfaceSamples({ load }, seed) {
  const m = await sim(load);
  const t = trackOf(m, seed);
  const track = snap(t);
  const xs = t.centerline.map((p) => p.x);
  const ys = t.centerline.map((p) => p.y);
  const pad = t.width + t.verge + 150;
  const r = rng(77);
  const lo = { x: Math.min(...xs) - pad, y: Math.min(...ys) - pad };
  const span = { x: Math.max(...xs) + pad - lo.x, y: Math.max(...ys) + pad - lo.y };
  const samples = [];
  for (let i = 0; i < 900; i++) {
    let x;
    let y;
    if (i % 2) {
      const p = t.centerline[Math.floor(r() * t.centerline.length)];
      x = p.x + (r() * 2 - 1) * (t.width / 2 + t.verge + 40);
      y = p.y + (r() * 2 - 1) * (t.width / 2 + t.verge + 40);
    } else {
      x = lo.x + r() * span.x;
      y = lo.y + r() * span.y;
    }
    samples.push({ x, y, got: m.track.surfaceAt(t, x, y) });
  }
  return { track, samples };
}

// surfaceAt at the middle of every segment, 0.8 inside and outside each edge, on both sides: band 0 is 0.8 inside
// the road edge, 1 is 0.8 outside it, 2 is 0.8 inside the verge edge and 3 is 0.8 outside it.
export async function edgeSamples({ load }, seed) {
  const m = await sim(load);
  const t = trackOf(m, seed);
  const track = snap(t);
  const pts = track.centerline;
  const n = pts.length;
  const road = track.width / 2;
  const offsets = [road - 0.8, road + 0.8, road + track.verge - 0.8, road + track.verge + 0.8];
  const samples = [];
  for (let i = 0; i < n; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % n];
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    const nx = -(b.y - a.y) / len;
    const ny = (b.x - a.x) / len;
    offsets.forEach((off, band) => {
      for (const side of [1, -1]) {
        const x = (a.x + b.x) / 2 + nx * off * side;
        const y = (a.y + b.y) / 2 + ny * off * side;
        samples.push({ i, band, x, y, got: m.track.surfaceAt(t, x, y) });
      }
    });
  }
  return { track, samples };
}

export async function gridData({ load }) {
  const m = await sim(load);
  const out = { radii: radiiOf(m), tracks: [] };
  for (const seed of [null, 5, 31]) out.tracks.push(snap(trackOf(m, seed)));
  return out;
}

// ---- lap progress ------------------------------------------------------------------------------------------------

// A point 37% of the way along centreline segment i, so no sample sits exactly on a gate.
function q(track, i) {
  const pts = track.centerline;
  const n = pts.length;
  const a = pts[((i % n) + n) % n];
  const b = pts[(((i + 1) % n) + n) % n];
  return { x: a.x + (b.x - a.x) * 0.37, y: a.y + (b.y - a.y) * 0.37 };
}

function gateIndex(track, k) {
  const g = track.checkpoints[k];
  return distToLoop(track.centerline, (g.a.x + g.b.x) / 2, (g.a.y + g.b.y) / 2).index;
}

function forward(track, from, steps) {
  const out = [];
  for (let s = 0; s <= steps; s++) out.push(q(track, from + s));
  return out;
}

// Walks `path` one segment per call. Every call gets its own frozen copies of the progress and both points,
// including the calls that cross a gate, so an advanceProgress that changes what it was given throws on the call
// that does it; that comes back as `frozen`, the message, with lap and next null.
function walk(advance, track, path) {
  let prog = { lap: 0, next: 1 };
  for (let i = 1; i < path.length; i++) {
    const given = Object.freeze({ lap: prog.lap, next: prog.next });
    const from = Object.freeze({ x: path[i - 1].x, y: path[i - 1].y });
    const to = Object.freeze({ x: path[i].x, y: path[i].y });
    try {
      prog = advance(track, given, from, to);
    } catch (err) {
      if (err instanceof TypeError && /read.only|frozen|not extensible|immutable/i.test(err.message)) {
        return { lap: null, next: null, frozen: `call ${i}, progress lap ${given.lap} next ${given.next}: ${err.message}` };
      }
      throw err;
    }
  }
  return { lap: prog.lap, next: prog.next, frozen: null };
}

async function progressSetup(load, seed) {
  const m = await sim(load);
  return { track: trackOf(m, seed), advance: m.race.advanceProgress };
}

export async function progressLaps({ load }, seed) {
  const { track, advance } = await progressSetup(load, seed);
  const n = track.centerline.length;
  const s = gateIndex(track, 0) + 2;
  return {
    one: walk(advance, track, forward(track, s, n)),
    two: walk(advance, track, forward(track, s, 2 * n)),
    part: walk(advance, track, forward(track, s, gateIndex(track, 2) - s + 3)),
  };
}

// Past gates 1 and 2, then straight across to just before the line, and over it.
export async function progressShortcut({ load }, seed) {
  const { track, advance } = await progressSetup(load, seed);
  const n = track.centerline.length;
  const s = gateIndex(track, 0) + 2;
  const g2 = gateIndex(track, 2);
  const g0 = gateIndex(track, 0);
  return walk(advance, track, [...forward(track, s, ((g2 - s + n) % n) + 3), ...forward(track, g0 - 3, 6)]);
}

// A lap that goes round the outside of the bend at gate k, wider than the gate's end, for each gate in turn.
export async function progressOutside({ load }, seed) {
  const { track, advance } = await progressSetup(load, seed);
  const n = track.centerline.length;
  const s = gateIndex(track, 0) + 2;
  const out = [];
  for (let k = 1; k < track.checkpoints.length; k++) {
    const gk = gateIndex(track, k);
    const gate = track.checkpoints[k];
    const half = Math.hypot(gate.b.x - gate.a.x, gate.b.y - gate.a.y) / 2;
    const ta = tangent(track.centerline, gk - 3);
    const tb = tangent(track.centerline, gk + 3);
    const side = ta.x * tb.y - ta.y * tb.x > 0 ? -1 : 1; // turning left: the outside is on the right
    const path = forward(track, s, n).map((p, i) => {
      const idx = (s + i) % n;
      const off = Math.abs(((idx - gk + n + n / 2) % n) - n / 2);
      if (off > 6) return p;
      const t = tangent(track.centerline, idx);
      return { x: p.x - t.y * (half + 40) * side, y: p.y + t.x * (half + 40) * side };
    });
    out.push({ k, gates: track.checkpoints.length, ...walk(advance, track, path) });
  }
  return out;
}

export async function progressBackwards({ load }, seed) {
  const { track, advance } = await progressSetup(load, seed);
  const n = track.centerline.length;
  const s = gateIndex(track, 0) + 2;
  const path = [];
  for (let k = 0; k <= n + 8; k++) path.push(q(track, s - k));
  return walk(advance, track, path);
}

// ---- races -------------------------------------------------------------------------------------------------------

// Per-tick numbers of every player, and each numeric field that was not finite when a tick ended (finishTick,
// which is null until a finish, is left out).
function recorder(race) {
  const rec = { players: race.players.map(() => ({ x: [], y: [], heading: [], speed: [] })), nonFinite: [] };
  rec.add = (tick) => {
    race.players.forEach((p, i) => {
      for (const f of ['x', 'y', 'heading', 'speed']) rec.players[i][f].push(p[f]);
      for (const [k, v] of Object.entries(p)) {
        if (typeof v === 'number' && k !== 'finishTick' && !Number.isFinite(v)) rec.nonFinite.push({ tick, player: i, field: k, value: v });
      }
    });
  };
  return rec;
}

export async function raceBasics({ load }) {
  const m = await sim(load);
  const race = m.race.createRace({ track: m.track.fixedTrack(), vehicles: ['car', 'bike'] });
  const out = {
    TICK_HZ: m.race.TICK_HZ,
    DT: m.race.DT,
    tick: race.tick,
    laps: race.laps,
    finishOrder: [...race.finishOrder],
    kinds: race.players.map((p) => p.kind),
    players: race.players.map((p) => ({ lap: p.lap, next: p.next, finished: p.finished })),
  };
  m.race.stepRace(race, [{ throttle: 1 }, { throttle: 1 }]);
  out.tickAfter = race.tick;
  return out;
}

export async function raceCreated({ load }) {
  const m = await sim(load);
  const track = m.track.generateTrack(31);
  const race = m.race.createRace({ track, vehicles: ['bike', 'car'], laps: 2 });
  const out = {
    laps: race.laps,
    raceCenterline: snap(race.track.centerline),
    givenCenterline: snap(track.centerline),
    grid: snap(track.grid),
    kinds: race.players.map((p) => p.kind),
    players: race.players.map((p) => ({
      x: p.x, y: p.y, heading: p.heading, speed: p.speed, lap: p.lap, next: p.next, finished: p.finished, finishTick: p.finishTick,
      plainObject: Object.getPrototypeOf(p) === Object.prototype,
    })),
  };
  const solo = m.race.createRace({ track, vehicles: ['car'] });
  const players = solo.players.length;
  m.race.stepRace(solo, [{ throttle: 1 }]);
  out.solo = { players, tickAfter: solo.tick };
  return out;
}

function recordAi(m, track, laps, cap) {
  const race = m.race.createRace({ track, vehicles: ['car', 'bike'], laps });
  const log = [];
  const hashes = [];
  while (race.finishOrder.length < 2 && race.tick < cap) {
    const inputs = [{ ...m.ai.aiInput(race, 0) }, { ...m.ai.aiInput(race, 1) }];
    log.push(inputs);
    m.race.stepRace(race, inputs);
    if (race.tick % 50 === 0) hashes.push(m.race.hashRace(race));
  }
  return { race, log, hashes };
}

function replay(m, track, laps, log) {
  const race = m.race.createRace({ track, vehicles: ['car', 'bike'], laps });
  const hashes = [];
  for (const inputs of log) {
    m.race.stepRace(race, inputs.map((x) => ({ ...x })));
    if (race.tick % 50 === 0) hashes.push(m.race.hashRace(race));
  }
  return { race, hashes };
}

// The AI's recorded inputs, replayed into a fresh race.
export async function replayAi({ load }, seed, laps, cap) {
  const m = await sim(load);
  const a = recordAi(m, m.track.generateTrack(seed), laps, cap);
  const b = replay(m, m.track.generateTrack(seed), laps, a.log);
  return {
    recorded: {
      finishOrder: [...a.race.finishOrder],
      finishTicks: a.race.finishOrder.map((i) => a.race.players[i].finishTick),
      hashes: a.hashes,
      finalHash: m.race.hashRace(a.race),
    },
    replayed: {
      finishOrder: [...b.race.finishOrder],
      hashes: b.hashes,
      finalHash: m.race.hashRace(b.race),
      hashType: typeof m.race.hashRace(b.race),
    },
  };
}

// Random inputs for both players on the fixed track, replayed twice.
export async function replayRandom({ load }, seed, ticks) {
  const m = await sim(load);
  const r = rng(seed);
  const log = [];
  let cur = [inputsAt(r, false), inputsAt(r, false)];
  for (let t = 0; t < ticks; t++) {
    if (t % 15 === 0) cur = [inputsAt(r, false), inputsAt(r, false)];
    log.push(cur.map((x) => ({ ...x })));
  }
  const x = replay(m, m.track.fixedTrack(), 3, log);
  const y = replay(m, m.track.fixedTrack(), 3, log);
  return { first: x.hashes, second: y.hashes };
}

// Final hashes after 400 ticks: a base run, the same with one input changed at tick 100, and another track.
export async function hashAfterInputs({ load }) {
  const m = await sim(load);
  const log = [];
  for (let t = 0; t < 400; t++) log.push([{ throttle: 1, steer: 0.1 }, { throttle: 1, steer: -0.1 }]);
  const base = replay(m, m.track.fixedTrack(), 3, log);
  const changed = log.map((x) => x.map((i) => ({ ...i })));
  changed[100][1] = { throttle: 1, steer: 1 };
  const other = replay(m, m.track.fixedTrack(), 3, changed);
  const seeded = replay(m, m.track.generateTrack(77), 3, log);
  return { base: m.race.hashRace(base.race), other: m.race.hashRace(other.race), seeded: m.race.hashRace(seeded.race) };
}

// The hash of a race after 120 ticks, then with each piece of its state changed on its own and put back.
export async function hashPerState({ load }) {
  const m = await sim(load);
  const race = m.race.createRace({ track: m.track.fixedTrack(), vehicles: ['car', 'bike'], laps: 3 });
  for (let t = 0; t < 120; t++) m.race.stepRace(race, [{ throttle: 1, steer: 0.05 }, { throttle: 1, steer: -0.05 }]);
  const base = m.race.hashRace(race);
  const again = m.race.hashRace(race);
  const edits = [
    ['tick', () => ((race.tick += 1), () => (race.tick -= 1))],
    ['finishOrder', () => (race.finishOrder.push(1), () => race.finishOrder.pop())],
  ];
  race.players.forEach((p, i) => {
    for (const [f, d] of [['x', 0.001], ['y', 0.001], ['heading', 0.001], ['lap', 1], ['next', 1]]) {
      edits.push([`player ${i} ${f}`, () => ((p[f] += d), () => (p[f] -= d))]);
    }
    edits.push([`player ${i} finished`, () => ((p.finished = !p.finished), () => (p.finished = !p.finished))]);
    edits.push([`player ${i} finishTick`, () => ((p.finishTick = 7), () => (p.finishTick = null))]);
  });
  const changes = [];
  for (const [what, apply] of edits) {
    const undo = apply();
    const changed = m.race.hashRace(race);
    undo();
    changes.push({ what, changed, restored: m.race.hashRace(race) });
  }
  return { base, again, changes };
}

// 20,000 ticks of random inputs, odd values included, for a car and a bike on `seed`.
export async function abuse({ load }, seed, ticks) {
  const m = await sim(load);
  const track = m.track.generateTrack(seed);
  const race = m.race.createRace({ track, vehicles: ['car', 'bike'], laps: 99 });
  const rec = recorder(race);
  const r = rng(20000);
  let cur = [inputsAt(r, true), inputsAt(r, true)];
  for (let t = 0; t < ticks; t++) {
    if (t % 20 === 0) cur = [inputsAt(r, true), inputsAt(r, true)];
    m.race.stepRace(race, cur);
    rec.add(t);
  }
  return { track: snap(track), radii: radiiOf(m), kinds: race.players.map((p) => p.kind), tick: race.tick, players: rec.players, nonFinite: rec.nonFinite };
}

// Overlapping vehicles, each placed `gap` apart (or `share` of the combined radii) at `angle`, after one tick.
export async function collisions({ load }, kindsList, cases) {
  const m = await sim(load);
  const radii = radiiOf(m);
  const sum = radii.car + radii.bike;
  const runs = [];
  for (const kinds of kindsList) {
    for (const c of cases) {
      const race = m.race.createRace({ track: m.track.fixedTrack(), vehicles: kinds });
      const [first, second] = race.players;
      const d = c.gap ?? c.share * sum;
      second.x = first.x + d * Math.cos(c.angle);
      second.y = first.y + d * Math.sin(c.angle);
      const before = race.players.map((p) => ({ x: p.x, y: p.y }));
      const gap = Math.hypot(second.x - first.x, second.y - first.y);
      m.race.stepRace(race, [{}, {}]);
      runs.push({ kinds, angle: c.angle, gap, before, after: race.players.map((p) => ({ x: p.x, y: p.y })) });
    }
  }
  return { sum, runs };
}

// Both vehicles steer at each other at full throttle for `ticks` ticks, for each pair of kinds.
export async function ramming({ load }, seed, kindsList, ticks) {
  const m = await sim(load);
  const track = trackOf(m, seed);
  const out = { track: snap(track), runs: [] };
  for (const kinds of kindsList) {
    const race = m.race.createRace({ track, vehicles: kinds, laps: 99 });
    const rec = recorder(race);
    for (let t = 0; t < ticks; t++) {
      const inputs = race.players.map((p, i) => {
        const o = race.players[1 - i];
        const turn = wrapAngle(Math.atan2(o.y - p.y, o.x - p.x) - p.heading);
        return { throttle: 1, brake: 0, steer: Math.max(-1, Math.min(1, turn * 3)) };
      });
      m.race.stepRace(race, inputs);
      rec.add(t);
    }
    out.runs.push({ kinds, sum: m.vehicles.VEHICLES[kinds[0]].radius + m.vehicles.VEHICLES[kinds[1]].radius, players: rec.players, nonFinite: rec.nonFinite });
  }
  return out;
}

// Drives one player with the AI until it finishes; the other gets no input. lapTick is the first tick after which
// that player's lap count had reached race.laps.
function driveToFinish(m, race, driver, cap) {
  let lapTick = null;
  while (!race.players[driver].finished && race.tick < cap) {
    const inputs = [{}, {}];
    inputs[driver] = m.ai.aiInput(race, driver);
    m.race.stepRace(race, inputs);
    if (lapTick === null && race.players[driver].lap >= race.laps) lapTick = race.tick;
  }
  return { finished: race.players[driver].finished, lapTick };
}

const finishSnap = (race, who, drive) => ({
  finished: drive.finished,
  lapTick: drive.lapTick,
  lap: race.players[who].lap,
  laps: race.laps,
  tick: race.tick,
  finishTick: race.players[who].finishTick,
  finishOrder: [...race.finishOrder],
});

// Player order[0] is driven home first, then order[1], over `laps` laps.
export async function finishOrderRun({ load }, order, laps) {
  const m = await sim(load);
  const race = m.race.createRace({ track: m.track.fixedTrack(), vehicles: ['car', 'bike'], laps });
  const [first, second] = order;
  const a = finishSnap(race, first, driveToFinish(m, race, first, 12000));
  a.idleFinished = race.players[second].finished;
  const b = finishSnap(race, second, driveToFinish(m, race, second, race.tick + 12000));
  return { first: a, second: b, firstFinishTick: race.players[first].finishTick, secondFinishTick: race.players[second].finishTick, finishOrder: [...race.finishOrder] };
}

// Players held at spots on the track, each carrying its full road speed along the tangent, one run per entry of
// `runs` ({ kinds, placements: 'road' | 'verge' per player, ticks }). Every tick each player is put back at its
// spot before the step, so only the surface there can change its speed.
function spotAt(track, off) {
  const pts = track.centerline;
  const n = pts.length;
  for (let k = 0; k < n; k++) {
    const i = (Math.floor(n / 4) + k * 7) % n;
    const { x: tx, y: ty } = tangent(pts, i);
    for (const side of [1, -1]) {
      const x = pts[i].x - ty * off * side;
      const y = pts[i].y + tx * off * side;
      if (Math.abs(distToLoop(pts, x, y).dist - off) < 1) return { x, y, tx, ty };
    }
  }
  return null;
}

export async function holdRuns({ load }, seed, runs) {
  const m = await sim(load);
  const track = trackOf(m, seed);
  const out = { name: track.name, runs: [] };
  for (const { kinds, placements, ticks } of runs) {
    const offs = placements.map((place, i) => {
      if (place === 'road') return 0;
      const r = m.vehicles.VEHICLES[kinds[i]].radius;
      return track.width / 2 + Math.max(0.5, Math.min(track.verge / 2, track.verge - r - 1));
    });
    const spots = offs.map((off) => spotAt(track, off));
    if (spots.some((s) => s === null)) {
      out.runs.push({ kinds, placements, offs, noSpot: true, players: [] });
      continue;
    }
    const race = m.race.createRace({ track, vehicles: kinds, laps: 99 });
    const entry = [];
    race.players.forEach((p, i) => {
      const heading = Math.atan2(spots[i].ty, spots[i].tx);
      const v = m.vehicles.createVehicle(kinds[i], { x: 0, y: 0, heading });
      for (let t = 0; t < 1200; t++) m.vehicles.stepVehicle(v, FULL, 'road');
      entry.push(v.speed);
      const keep = { lap: p.lap, next: p.next, finished: p.finished, finishTick: p.finishTick };
      Object.assign(p, v, keep, { x: spots[i].x, y: spots[i].y });
    });
    const speeds = kinds.map(() => []);
    for (let t = 0; t < ticks; t++) {
      race.players.forEach((p, i) => {
        p.x = spots[i].x;
        p.y = spots[i].y;
      });
      m.race.stepRace(race, kinds.map(() => FULL));
      race.players.forEach((p, i) => speeds[i].push(p.speed));
    }
    out.runs.push({ kinds, placements, offs, noSpot: false, players: kinds.map((_, i) => ({ entry: entry[i], speeds: speeds[i] })) });
  }
  return out;
}

// A car and a bike, each alone, driven one lap by the AI.
export async function soloLaps({ load }, seed) {
  const m = await sim(load);
  const track = trackOf(m, seed);
  const length = totalLength(track.centerline);
  const out = { name: track.name, runs: [] };
  for (const kind of ['car', 'bike']) {
    const race = m.race.createRace({ track, vehicles: [kind], laps: 1 });
    const bound = Math.ceil((3 * length) / m.vehicles.VEHICLES[kind].topSpeed / m.race.DT) + 600;
    let lapTick = null;
    while (!race.players[0].finished && race.tick < bound) {
      m.race.stepRace(race, [m.ai.aiInput(race, 0)]);
      if (lapTick === null && race.players[0].lap >= 1) lapTick = race.tick;
    }
    out.runs.push({ kind, bound, ...finishSnap(race, 0, { finished: race.players[0].finished, lapTick }), next: race.players[0].next });
  }
  return out;
}
