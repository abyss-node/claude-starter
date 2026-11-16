// Held-out checks for Roulette Loom. demos/check.py runs them from the kit on a copy of a workspace, which it
// names in DEMO_WORKSPACE; they are never copied there. The workspace's code runs in a process of its own
// (demos/probe.mjs), never in this one, and the expected values are worked out here, not asked of the module.
// Each check calls the module itself, so one that fails to load fails every check by name.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { inspect } from 'node:util';
import { notRefused, values } from '../../probe.mjs';

const loom = (...calls) => values('src/loom.js', calls);
const TAU = 2 * Math.PI;
const gcd = (a, b) => (b === 0 ? a : gcd(b, a % b));
const lapsOf = (R, r) => r / gcd(R, r);

function near(a, b, tol, what) {
  assert.ok(typeof a === 'number' && Math.abs(a - b) <= tol, `${what}: ${a} is not within ${tol} of ${b}`);
}

function points(got, what) {
  for (const p of Array.isArray(got) ? got : [got]) {
    assert.ok(p && typeof p.x === 'number' && typeof p.y === 'number', `${what}: ${inspect(p)} is not { x, y }`);
  }
  return got;
}

// laps(R, r) = r / gcd(R, r): coprime radii, r dividing R, and shared factors.
for (const [R, r, want] of [[5, 3, 3], [8, 2, 1], [10, 4, 2], [12, 8, 2], [96, 35, 35]]) {
  test(`laps(${R}, ${r}) is r / gcd(R, r) = ${want}`, () => {
    const [got] = loom(['laps', R, r]);
    assert.equal(got, want, `laps(${R}, ${r}) returned ${inspect(got)}`);
  });
}

const SHAPES = [[5, 3, 5], [7, 2, 0.5], [12, 5, 9], [10, 4, 0], [96, 35, 20]];
// Where every curve starts: t = 0 puts the rolling circle's centre at (R - r, 0) and the pen d beyond it.
const startOf = (R, r, d) => ({ x: R - r + d, y: 0 });

test('point comes back to its start after laps(R, r) turns, within 1e-9', () => {
  // Per shape: the start, after laps turns, and one turn short of that.
  const turns = SHAPES.map(([R, r]) => [0, lapsOf(R, r), lapsOf(R, r) - 1]);
  const got = points(loom(...SHAPES.flatMap(([R, r, d], i) => turns[i].map((n) => ['point', R, r, d, TAU * n]))),
    'point');
  SHAPES.forEach(([R, r, d], i) => {
    const [a, b, c] = got.slice(3 * i, 3 * i + 3);
    const want = startOf(R, r, d);
    near(a.x, want.x, 1e-9, `start x for R=${R} r=${r} d=${d}`);
    near(a.y, want.y, 1e-9, `start y for R=${R} r=${r} d=${d}`);
    near(b.x, a.x, 1e-9, `x for R=${R} r=${r} d=${d}`);
    near(b.y, a.y, 1e-9, `y for R=${R} r=${r} d=${d}`);
    if (lapsOf(R, r) > 1) {  // and not before: one turn short of closing, the pen is somewhere else
      assert.ok(d === 0 || Math.hypot(c.x - a.x, c.y - a.y) > 1e-6, `R=${R} r=${r} d=${d} closed early`);
    }
  });
});

test('trace gives steps + 1 points, from the start of the curve back to it', () => {
  const got = loom(...SHAPES.map(([R, r, d]) => ['trace', R, r, d, 400]));
  SHAPES.forEach(([R, r, d], i) => {
    const pts = got[i];
    assert.ok(Array.isArray(pts), `trace(${R}, ${r}, ${d}, 400) returned ${typeof pts}, not an array`);
    assert.equal(pts.length, 401, `R=${R} r=${r} d=${d}: number of points`);
    points(pts, `R=${R} r=${r} d=${d}`);
    const start = startOf(R, r, d);
    near(pts[0].x, start.x, 1e-9, 'first x');
    near(pts[0].y, start.y, 1e-9, 'first y');
    near(pts[400].x, start.x, 1e-9, `R=${R} r=${r} d=${d}: last x`);
    near(pts[400].y, start.y, 1e-9, `R=${R} r=${r} d=${d}: last y`);
  });
});

test('R = 2r with d = r draws a straight line across the ring', () => {
  const rs = [1, 3, 10];
  const got = loom(...rs.map((r) => ['trace', 2 * r, r, r, 200]));
  rs.forEach((r, i) => {
    const pts = points(got[i], `r=${r}`);
    assert.ok(Array.isArray(pts) && pts.length > 0, `trace(${2 * r}, ${r}, ${r}, 200) gave no points`);
    for (const p of pts) near(p.y, 0, 1e-9, `y at x=${p.x}, r=${r}`);
    near(Math.max(...pts.map((p) => p.x)), 2 * r, 1e-9, `rightmost x, r=${r}`);
    near(Math.min(...pts.map((p) => p.x)), -2 * r, 1e-9, `leftmost x, r=${r}`);
  });
});

test('every point lies within R - r + d of the centre, and the start is that far out', () => {
  const got = loom(...SHAPES.map(([R, r, d]) => ['trace', R, r, d, 2000]));
  SHAPES.forEach(([R, r, d], i) => {
    const pts = points(got[i], `R=${R} r=${r} d=${d}`);
    assert.ok(Array.isArray(pts) && pts.length > 0, `trace(${R}, ${r}, ${d}, 2000) gave no points`);
    const far = R - r + d;
    for (const p of pts) assert.ok(Math.hypot(p.x, p.y) <= far + 1e-9, `R=${R} r=${r} d=${d}: (${p.x}, ${p.y})`);
    near(Math.hypot(pts[0].x, pts[0].y), far, 1e-9, `R=${R} r=${r} d=${d}: distance of the start`);
  });
});

test('laps, point and trace refuse a shape that is not a curve', () => {
  const calls = [];
  for (const [R, r] of [[5, 5], [3, 5], [5, 0], [5, -2], [5, 2.5], [5.5, 2]]) {
    calls.push(['laps', R, r], ['point', R, r, 1, 0]);
  }
  calls.push(['point', 5, 3, -1, 0], ['trace', 5, 3, -1, 10]);
  for (const steps of [0, -1, 2.5]) calls.push(['trace', 5, 3, 1, steps]);
  const bad = notRefused('src/loom.js', calls);
  assert.deepEqual(bad, [], bad.join('; '));
});
