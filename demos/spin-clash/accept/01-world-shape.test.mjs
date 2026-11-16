import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 1: createWorld builds the documented world and clamps the sliders', () => {
  const seen = ask('shape');
  const { DT, world: w, zeros, names, plainTops, plainSnap, seedOneSnap, asked } = seen;
  assert.equal(typeof DT, 'number', 'DT must be a number');
  assert.ok(Number.isFinite(DT) && DT > 0 && DT <= 0.05, `DT must be a fixed step in seconds (got ${DT})`);

  assert.equal(w.tick, 0, 'a new world starts at tick 0');
  assert.equal(w.winner, null, 'a new world has no winner');
  assert.ok(Array.isArray(w.tops) && w.tops.length === 2, 'world.tops holds one entry per configured top');
  for (const t of w.tops) {
    for (const k of ['mass', 'radius', 'friction', 'x', 'y', 'vx', 'vy', 'spin']) {
      assert.ok(Number.isFinite(t[k]), `top ${t.name}: ${k} must be a finite number (got ${t[k]})`);
    }
    assert.equal(t.status, 'in', `top ${t.name} starts in play`);
    assert.ok(t.spin > 0, `top ${t.name} starts spinning`);
  }
  const [h, l] = w.tops;
  assert.equal(h.name, 'Heavy');
  assert.deepEqual([h.mass, h.radius, h.friction], [3, 0.05, 0], 'values below/above range clamp to mass 3, radius 0.05, friction 0');
  assert.deepEqual([l.mass, l.radius, l.friction], [0.5, 0.2, 1], 'values clamp to mass 0.5, radius 0.2, friction 1');

  // Zero is a number too: a slider at 0 is below its range and clamps up (mass 0.5,
  // radius 0.05), it does not fall back to the default; a friction of 0 is in range.
  for (const t of zeros.tops) {
    assert.deepEqual([t.mass, t.radius, t.friction], [0.5, 0.05, 0], `a mass of 0 clamps to 0.5, a radius of 0 to 0.05, and a friction of 0 stays 0 (got ${t.mass}, ${t.radius}, ${t.friction})`);
  }

  // The names you give are kept whole, long ones included.
  assert.deepEqual(names, ['Old Ballast', 'Copperhull Nettle Quill of the Long Name'], 'the names you give must be kept exactly, not cut or changed');

  // The defaults the config table gives: two tops, seed 1.
  assert.equal(plainTops, 2, 'a config without tops gives two tops');
  assert.equal(plainSnap, seedOneSnap, 'a config without a seed must start exactly like seed 1');

  // A spin is never negative, even when the config asks for one.
  for (const t of asked.tops) assert.ok(t.spin >= 0, `top ${t.name}: a configured negative spin must not stay negative (got ${t.spin})`);
});
