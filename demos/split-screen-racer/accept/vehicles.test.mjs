import { test } from 'node:test';
import assert from 'node:assert/strict';
import { scenario } from '../../probe.mjs';
import { arcRadius } from './helpers.mjs';

const S = new URL('./scenarios.mjs', import.meta.url);
const run = (name, ...args) => scenario(S, name, args);

test('vehicle data: car and bike are plain data with the required finite fields', () => {
  const d = run('vehicleData');
  for (const kind of ['car', 'bike']) {
    const s = d.kinds[kind];
    assert.ok(s, `VEHICLES.${kind} missing`);
    for (const f of ['topSpeed', 'accel', 'turnRate', 'mass', 'radius']) {
      assert.ok(Number.isFinite(s[f]) && s[f] > 0, `VEHICLES.${kind}.${f} must be a positive number, got ${s[f]}`);
    }
  }
  assert.ok(d.kinds.car.mass > d.kinds.bike.mass, 'the car must be heavier than the bike');
  // Plain data: every leaf is a finite number, a string, a boolean or null (no functions, no undefined), in plain objects and arrays.
  const bad = [];
  (function walkLeaves(node, path) {
    if (Array.isArray(node)) node.forEach((x, i) => walkLeaves(x, `${path}[${i}]`));
    else if (node && typeof node === 'object') for (const [k, v] of Object.entries(node)) walkLeaves(v, `${path}.${k}`);
    else if (!['number', 'string', 'boolean', 'null'].includes(node)) bad.push(`${path} is ${node}`);
  })(d.leaves, 'VEHICLES');
  assert.deepEqual(bad, [], 'VEHICLES must be plain data: a JSON round trip has to give it back unchanged (no functions, no undefined)');
  assert.equal(typeof d.json, 'string', 'VEHICLES must survive JSON.stringify');
});

test('heading 0 drives along +x and stepVehicle moves one tick of DT', () => {
  const d = run('headingAndDt');
  assert.ok(Math.abs(d.DT - 1 / 60) < 1e-12, `DT must be 1/60, got ${d.DT}`);
  const v = d.second;
  assert.ok(v.x > 10 && Math.abs(v.y) < 1e-6, `after 1 s of throttle at heading 0 expected +x travel, got (${v.x}, ${v.y})`);
  // One tick moves a vehicle by its speed over DT: at steady top speed, within 5%.
  for (const kind of ['car', 'bike']) {
    const w = d.steady[kind];
    const moved = Math.hypot(w.after.x - w.before.x, w.after.y);
    const expected = w.speed * d.DT;
    assert.ok(Math.abs(moved - expected) <= 0.05 * expected, `${kind}: one tick at ${w.speed.toFixed(1)} u/s moved ${moved.toFixed(3)}, expected about ${expected.toFixed(3)} (speed times DT)`);
  }
  assert.ok(d.up.y > 15 && Math.abs(d.up.x - 5) < 1e-6, `heading pi/2 must drive along +y, got (${d.up.x}, ${d.up.y})`);
});

test('top speed: each vehicle settles at its stated topSpeed and the car is faster', () => {
  const d = run('topSpeeds');
  const tops = {};
  for (const kind of ['car', 'bike']) {
    const { speed, stated } = d[kind];
    assert.ok(Math.abs(speed - stated) <= 0.05 * stated, `${kind}: measured top speed ${speed.toFixed(1)} is not within 5% of topSpeed ${stated}`);
    tops[kind] = speed;
  }
  assert.ok(tops.car >= 1.1 * tops.bike, `car top speed ${tops.car.toFixed(1)} must be at least 10% above the bike's ${tops.bike.toFixed(1)}`);
});

test('acceleration: the bike reaches 90% of its top speed sooner than the car', () => {
  const d = run('acceleration');
  const time = {};
  const at1s = {};
  for (const kind of ['car', 'bike']) {
    const { speeds, stated } = d[kind];
    const goal = 0.9 * stated;
    const idx = speeds.findIndex((s) => s >= goal);
    assert.ok(idx >= 0, `${kind} never reached 90% of its top speed`);
    time[kind] = (idx + 1) * d.DT;
    at1s[kind] = speeds[Math.round(1 / d.DT) - 1];
  }
  assert.ok(time.bike < 0.8 * time.car, `0-to-90% time: bike ${time.bike.toFixed(2)} s must be under 80% of the car's ${time.car.toFixed(2)} s`);
  assert.ok(at1s.bike > at1s.car, `after 1 s the bike (${at1s.bike.toFixed(1)}) must be faster than the car (${at1s.car.toFixed(1)})`);
});

test('turn radius: at the same speed the bike turns tighter than the car', () => {
  const d = run('turning');
  const got = {};
  for (const kind of ['car', 'bike']) {
    const t = d[kind];
    assert.ok(t.reached, `${kind} never reached ${d.target.toFixed(0)} u/s on a straight`);
    got[kind] = { radius: arcRadius(t.pts), meanSpeed: t.speedSum / t.pts.length };
  }
  for (const [k, r] of Object.entries(got)) {
    assert.ok(Number.isFinite(r.radius) && r.radius > 1, `${k} turn radius not measurable: ${r.radius}`);
    assert.ok(Math.abs(r.meanSpeed - d.target) < 0.15 * d.target, `${k} could not hold ${d.target.toFixed(0)} u/s while turning (mean ${r.meanSpeed.toFixed(0)})`);
  }
  assert.ok(got.bike.radius < 0.9 * got.car.radius, `bike radius ${got.bike.radius.toFixed(1)} must be under 90% of car radius ${got.car.radius.toFixed(1)} at ${d.target.toFixed(0)} u/s`);
});

test('off-track slows both vehicles and the bike loses more of its speed', () => {
  const d = run('offTrack');
  const ratio = {};
  for (const kind of ['car', 'bike']) {
    const { road, off, afterLeaving } = d[kind];
    ratio[kind] = off / road;
    assert.ok(ratio[kind] < 0.85, `${kind}: off-track top speed is ${(ratio[kind] * 100).toFixed(0)}% of road, must be under 85%`);
    // Entering the verge at full speed must bleed speed off within two seconds.
    assert.ok(afterLeaving < 0.9 * road, `${kind}: still at ${afterLeaving.toFixed(0)} u/s two seconds after leaving the road at ${road.toFixed(0)}`);
  }
  assert.ok(ratio.bike < ratio.car - 0.05, `off/road speed ratio: bike ${ratio.bike.toFixed(2)} must be at least 0.05 below car ${ratio.car.toFixed(2)}`);
});

test('handling follows the data: a spec with 1.5x topSpeed reaches 1.5x the speed', () => {
  const { topSpeed, speed } = run('handlingFollowsData');
  assert.ok(Math.abs(speed - topSpeed) <= 0.05 * topSpeed, `createVehicle(spec) ignored the data: expected about ${topSpeed}, got ${speed.toFixed(1)}`);
});

// Two vehicles with the same history, one fed input A and the other input B for 90 ticks, must end in the same state.
const PAIRS = [
  { label: 'throttle 7 and steer 9 act as 1', a: { throttle: 7, brake: 0, steer: 9 }, b: { throttle: 1, brake: 0, steer: 1 } },
  { label: 'steer -9 acts as -1', a: { throttle: 0.5, brake: 0, steer: -9 }, b: { throttle: 0.5, brake: 0, steer: -1 } },
  { label: 'throttle -4 acts as 0', a: { throttle: -4, brake: 0, steer: 0.4 }, b: { throttle: 0, brake: 0, steer: 0.4 } },
  { label: 'brake 6 acts as 1', a: { throttle: 0, brake: 6, steer: 0.4 }, b: { throttle: 0, brake: 1, steer: 0.4 } },
  { label: 'brake -6 acts as 0', a: { throttle: 0, brake: -6, steer: 0.4 }, b: { throttle: 0, brake: 0, steer: 0.4 } },
  { label: 'NaN fields act as 0', a: { throttle: NaN, brake: NaN, steer: NaN }, b: { throttle: 0, brake: 0, steer: 0 } },
  { label: 'missing fields act as 0', a: {}, b: { throttle: 0, brake: 0, steer: 0 } },
  { label: 'a throttle-only input is full throttle, no brake, no steer', a: { throttle: 1 }, b: { throttle: 1, brake: 0, steer: 0 } },
];

test('inputs: out-of-range values are clamped, and a missing or NaN field counts as 0', () => {
  for (const { kind, label, a, b } of run('inputPairs', ['car', 'bike'], PAIRS)) {
    for (const f of ['x', 'y', 'heading', 'speed']) {
      assert.ok(Math.abs(a[f] - b[f]) < 1e-9, `${kind}, ${label}: ${f} differs (${a[f]} against ${b[f]}); these two inputs must behave the same`);
    }
  }
});

test('brake: full brake slows a vehicle faster than coasting, and speed stays a magnitude of at least 0', () => {
  const d = run('braking');
  for (const kind of ['car', 'bike']) {
    const r = d[kind];
    assert.ok(r.braked < r.coasted - 5 && r.braked < r.start, `${kind}: after half a second braked speed ${r.braked.toFixed(1)} must be clearly under the coasting ${r.coasted.toFixed(1)}`);
    for (const s of r.speeds) {
      assert.ok(Number.isFinite(s) && s >= 0, `${kind}: speed is ${s} while braking; it must be a magnitude, never below 0`);
    }
    const end = r.speeds[r.speeds.length - 1];
    assert.ok(end < 1, `${kind}: still at ${end.toFixed(1)} u/s after braking for 20 s`);
  }
});
