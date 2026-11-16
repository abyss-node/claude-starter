import { test } from 'node:test';
import assert from 'node:assert/strict';
import { scenario, values } from '../../probe.mjs';
import { assertValidLoop, cumulative, distToLoop, tangent } from './helpers.mjs';

const S = new URL('./scenarios.mjs', import.meta.url);
const run = (name, ...args) => scenario(S, name, args);
const trk = (calls) => values('src/track.js', calls);

const SEEDS = Array.from({ length: 25 }, (_, i) => i * 7919 + 1);
// Integers that a 32-bit truncation (seed >>> 0) would fold together: 5, -5 and 2^32 + 5 are three seeds.
const WIDE_SEEDS = [0, -1, 5, -5, 2 ** 32 + 5, 9, 2 ** 40 + 9, 2 ** 31, -(2 ** 31)];
const shape = (track) => JSON.stringify(track.centerline);

function checkGates(track, expected, label) {
  const pts = track.centerline;
  const gates = track.checkpoints;
  assert.ok(Array.isArray(gates), `${label}: checkpoints must be an array`);
  assert.equal(gates.length, expected, `${label}: expected ${expected} checkpoints, got ${gates.length}`);
  const { cum, total } = cumulative(pts);
  const pos = [];
  gates.forEach((g, k) => {
    const len = Math.hypot(g.b.x - g.a.x, g.b.y - g.a.y);
    assert.ok(len >= 0.9 * track.width && len <= track.width + 2 * track.verge + 1, `${label}: gate ${k} is ${len.toFixed(1)} long; it must span the road and at most road plus both verges`);
    const mx = (g.a.x + g.b.x) / 2;
    const my = (g.a.y + g.b.y) / 2;
    const near = distToLoop(pts, mx, my);
    assert.ok(near.dist <= 0.1 * track.width, `${label}: gate ${k} is centred ${near.dist.toFixed(1)} off the centreline`);
    const t = tangent(pts, near.index);
    const cos = Math.abs(((g.b.x - g.a.x) * t.x + (g.b.y - g.a.y) * t.y) / len);
    assert.ok(cos < 0.5, `${label}: gate ${k} is not across the road (|cos| ${cos.toFixed(2)})`);
    pos.push(cum[near.index]);
  });
  const rel = pos.map((s) => (s - pos[0] + total) % total);
  for (let k = 1; k < rel.length; k++) {
    assert.ok(rel[k] > rel[k - 1] + track.width, `${label}: gate ${k} is not after gate ${k - 1} in driving (centreline) order`);
  }
}

test('seeded track is deterministic for a seed and differs across seeds', () => {
  const [a, b, c] = trk([['generateTrack', 1234], ['generateTrack', 1234], ['generateTrack', 1235]]);
  assert.deepEqual(a.centerline, b.centerline, 'same seed gave different centrelines');
  assert.deepEqual(a.checkpoints, b.checkpoints, 'same seed gave different checkpoints');
  assert.notDeepEqual(a.centerline, c.centerline, 'seeds 1234 and 1235 gave the same track');
});

test('every integer seed is its own track: zero, negative and past 2^32 included', () => {
  const got = trk(WIDE_SEEDS.flatMap((seed) => [['generateTrack', seed], ['generateTrack', seed]]));
  const seen = new Map();
  WIDE_SEEDS.forEach((seed, k) => {
    const t = got[2 * k];
    assert.equal(shape(got[2 * k + 1]), shape(t), `seed ${seed}: the same seed gave two different tracks`);
    const key = shape(t);
    assert.ok(!seen.has(key), `seeds ${seen.get(key)} and ${seed} gave the same track; different integer seeds must give different tracks`);
    seen.set(key, seed);
    assertValidLoop(t, `seed ${seed}`);
  });
});

test('seeded tracks are valid closed loops without self-intersection (25 seeds)', () => {
  const got = trk(SEEDS.map((seed) => ['generateTrack', seed]));
  const shapes = new Set();
  SEEDS.forEach((seed, k) => {
    const t = got[k];
    assertValidLoop(t, `seed ${seed}`);
    shapes.add(`${t.centerline.length}:${Math.round(t.centerline[0].x)}:${Math.round(t.centerline[5].y)}`);
  });
  assert.ok(shapes.size >= 20, `only ${shapes.size} distinct tracks from 25 seeds`);
});

test('fixed track is a valid closed loop with a name', () => {
  const d = run('fixedStability');
  assert.ok(typeof d.name === 'string' && d.name.length > 0, 'fixedTrack() needs a name');
  assertValidLoop(JSON.parse(d.before), 'fixed track');
  // The whole track, not only the centreline, and a call that asks for something else leaves later calls and earlier results alone.
  assert.equal(d.again, d.before, 'fixedTrack() must return the same track on every call: name, gates and grid included');
  assert.equal(d.twelveGates, 12, 'fixedTrack({ checkpoints: 12 }) must give 12 gates');
  assert.equal(d.afterTwelve, d.before, 'after fixedTrack({ checkpoints: 12 }) a plain fixedTrack() must still be the same 8-gate track');
  assert.equal(d.earlierGates, 8, 'a track returned earlier must not change when fixedTrack is called again');
  assert.equal(d.earlier, d.before, 'a track returned earlier must not change when fixedTrack is called again');
});

test('checkpoint count matches the request and gates span the road in driving order', () => {
  const seeds = SEEDS.slice(0, 6);
  const got = trk([
    ['fixedTrack'],
    ['fixedTrack', { checkpoints: 12 }],
    ...seeds.flatMap((seed) => [['generateTrack', seed], ['generateTrack', seed, { checkpoints: 5 }]]),
  ]);
  checkGates(got[0], 8, 'fixed track default');
  checkGates(got[1], 12, 'fixed track, 12 requested');
  seeds.forEach((seed, k) => {
    checkGates(got[2 + 2 * k], 8, `seed ${seed} default`);
    checkGates(got[3 + 2 * k], 5, `seed ${seed}, 5 requested`);
  });
});

test('surfaceAt matches distance from the centreline: road, off, wall', () => {
  for (const seed of [null, 99]) {
    const { track: t, samples } = run('surfaceSamples', seed);
    const seen = { road: 0, off: 0, wall: 0 };
    for (const { x, y, got } of samples) {
      const d = distToLoop(t.centerline, x, y).dist;
      const edges = [t.width / 2, t.width / 2 + t.verge];
      if (edges.some((e) => Math.abs(d - e) < 0.5)) continue;
      const want = d < edges[0] ? 'road' : d < edges[1] ? 'off' : 'wall';
      assert.equal(got, want, `${t.name}: point at ${d.toFixed(1)} from the centreline should be '${want}', got '${got}'`);
      seen[want]++;
    }
    assert.ok(seen.road > 20 && seen.off > 20 && seen.wall > 20, `sampling did not cover every band: ${JSON.stringify(seen)}`);
  }
});

// Distance is to the nearest point of the loop, not the nearest vertex: sample the middle of every segment, just inside
// and just outside both edges, keeping only points whose true distance (grader geometry) is the intended one.
test('surfaceAt measures distance to the nearest point of the centreline, not to its nearest vertex', () => {
  for (const seed of [null, 99, 5]) {
    const { track: t, samples } = run('edgeSamples', seed);
    const pts = t.centerline;
    const n = pts.length;
    const road = t.width / 2;
    const bands = [
      [road - 0.8, 'road'],
      [road + 0.8, 'off'],
      [road + t.verge - 0.8, 'off'],
      [road + t.verge + 0.8, 'wall'],
    ];
    let checked = 0;
    for (const { i, band, x, y, got } of samples) {
      const [off, want] = bands[band];
      if (Math.abs(distToLoop(pts, x, y).dist - off) > 0.05) continue;
      checked++;
      assert.equal(got, want, `${t.name}: point ${off.toFixed(1)} from the middle of segment ${i} is ${off.toFixed(1)} from the centreline and should be '${want}', got '${got}'`);
    }
    assert.ok(checked > n, `${t.name}: only ${checked} edge samples were usable`);
  }
});

test('start grid: two poses on the road, apart, facing the driving direction', () => {
  const { radii, tracks } = run('gridData');
  const gap = 2 * Math.max(radii.car, radii.bike);
  for (const t of tracks) {
    assert.ok(Array.isArray(t.grid) && t.grid.length >= 2, `${t.name}: grid needs at least 2 poses`);
    for (const g of t.grid.slice(0, 2)) {
      const near = distToLoop(t.centerline, g.x, g.y);
      assert.ok(near.dist <= t.width / 2, `${t.name}: grid pose is off the road`);
      const tan = tangent(t.centerline, near.index);
      assert.ok(Math.cos(g.heading) * tan.x + Math.sin(g.heading) * tan.y > 0.7, `${t.name}: grid pose does not face the driving direction`);
    }
    const d = Math.hypot(t.grid[0].x - t.grid[1].x, t.grid[0].y - t.grid[1].y);
    assert.ok(d >= gap, `${t.name}: grid poses are ${d.toFixed(1)} apart, need ${gap}`);
  }
});
