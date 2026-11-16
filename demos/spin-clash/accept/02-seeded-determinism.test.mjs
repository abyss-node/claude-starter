import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 2: same seed and same inputs give the same state after 600 ticks, with no Math.random or clock, even with worlds of different settings stepped turn about', () => {
  // The scenario takes Math.random, Date.now and performance.now away (they throw) around every run it makes, so
  // a call from the physics, from any of the corners below included, fails this check with the message it throws.
  const seen = ask('determinism');

  assert.equal(seen.tick, 600, 'world.tick counts steps');
  assert.equal(seen.a, seen.b, 'two runs with one seed and one input script diverged');
  assert.notEqual(seen.a, seen.start, 'nothing changed in 600 ticks');
  assert.notEqual(seen.other, seen.start, 'seed 99 and seed 1234 start identically: the seed must place the tops');

  // Matches run for thousands of ticks, so the clocks and Math.random must stay untouched far past tick 1000.
  assert.equal(seen.longTick, 3000, 'step must keep counting ticks');

  // The awkward corners of the physics: tops that share a centre (no direction to push apart along), no
  // friction, four tops, a top that rings out at once. Two runs of one seed must still end in one state.
  assert.equal(seen.corners.length, 4);
  for (const { label, x, y } of seen.corners) {
    assert.equal(x, y, `${label}: two runs with one seed and one input script diverged`);
  }
  assert.equal(seen.pair[0], seen.pair[1], 'collide on tops that share a centre gave two different results for one world');

  // Worlds with different settings stepped turn about must each end exactly as the same world stepped on its
  // own: settings live in the world, not in a variable shared by every world.
  const { x, xAlone, y, yAlone } = seen.settings;
  assert.notEqual(xAlone, yAlone, 'setup: the two settings should play differently');
  assert.equal(x, xAlone, 'the world made first, stepped turn about with a world of other settings, differs from the same world stepped alone: settings must live in the world');
  assert.equal(y, yAlone, 'the world made second, stepped turn about with a world of other settings, differs from the same world stepped alone: settings must live in the world');
});
