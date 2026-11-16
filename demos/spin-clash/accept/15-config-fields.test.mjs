import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 15: every config field is honoured: top fields, minSpin, friction on and off, the bowl and steer', () => {
  const seen = ask('configFields');

  // A top's own settings are used as given when they are in range.
  const given = seen.given;
  assert.deepEqual(
    [given.name, given.mass, given.radius, given.friction, given.x, given.y, given.vx, given.vy, given.spin, given.status],
    ['Given', 1.7, 0.13, 0.35, 0.12, -0.34, 0.56, 0.78, 33, 'in'],
    'name, mass, radius, friction, x, y, vx, vy and spin in a top setting must be used as given',
  );

  // Zero is a value like any other: a given 0 is used as 0, not replaced by a default.
  for (const t of seen.zeros) {
    assert.deepEqual([t.x, t.vx, t.vy, t.spin, t.friction], [0, 0, 0, 0, 0], 'an x, vx, vy, spin or friction of 0 in a top setting must be used as 0, not replaced by a seeded or default value');
  }
  assert.deepEqual([seen.zeros[0].y, seen.zeros[1].y], [0, 0.3], 'a y of 0 or 0.3 in a top setting must be used as given');

  // minSpin: a top at or below it has spun down, one above it has not. Friction is off so the spin stays where
  // it was put.
  const s = seen.spinStatus;
  assert.equal(s['default 3.9'], 'spundown', 'with the default minSpin (4), spin 3.9 is spun down');
  assert.equal(s['default 4'], 'spundown', 'a spin exactly at minSpin (4 by default) is spun down: at or below');
  assert.equal(s['default 4.1'], 'in', 'with the default minSpin (4), spin 4.1 is still in play');
  assert.equal(s['min10 9.9'], 'spundown', 'minSpin 10: spin 9.9 is spun down');
  assert.equal(s['min10 10.1'], 'in', 'minSpin 10: spin 10.1 is still in play');
  assert.equal(s['min10 4.1'], 'spundown', 'minSpin 10: spin 4.1 is below it, so the default of 4 must not be used');

  // friction defaults to on: spin and speed fall. A flat floor, no input.
  const onTop = seen.onTop;
  assert.ok(onTop.spin < 50, `friction defaults to on, so spin must fall (still ${onTop.spin} after 100 ticks)`);
  assert.ok(Math.hypot(onTop.vx, onTop.vy) < 0.3, `friction on means drag: a top that coasts on a flat floor slows down (speed ${Math.hypot(onTop.vx, onTop.vy)} after 100 ticks, from 0.3)`);

  // friction false turns every kind of loss off: the spin and the velocity of a top coasting on a flat floor
  // stay exactly as they were, even with steering input.
  const offTop = seen.offTop;
  assert.ok(Math.abs(offTop.spin - 50) < 1e-9, `friction false: spin must not change (got ${offTop.spin}, from 50)`);
  assert.ok(Math.abs(offTop.vx - 0.3) < 1e-9, `friction false and a flat floor: nothing slows a top down (vx ${offTop.vx}, from 0.3)`);
  assert.ok(Math.abs(seen.steered.spin - 50) < 1e-9, `friction false: steering must not change the spin (got ${seen.steered.spin}, from 50)`);

  // slope: the bowl pulls towards the centre, harder the farther out, harder with a bigger slope; 0 is a flat
  // floor. A top at rest, one tick, friction off so nothing else acts on it.
  const p = seen.pull;
  assert.ok(p.default < 0, `the default slope must be above 0: a top at rest at x 0.5 should be pulled towards the centre (vx ${p.default})`);
  assert.ok(p.defaultNeg > 0, 'a top at x -0.5 should be pulled towards +x, the centre');
  assert.ok(p.flat === 0, `slope 0 is a flat floor: nothing pulls a top at rest (vx ${p.flat})`);
  assert.ok(Math.abs(p.far) > Math.abs(p.near), 'the pull must grow with the distance from the centre');
  assert.ok(Math.abs(p.s2) > Math.abs(p.s1), 'a bigger slope must pull harder');
  assert.ok(p.vy > 0, `the bowl pulls along y as well: a top at y -0.6 should gain +y speed (vy ${p.vy})`);

  // steer: how hard a full input pushes: more steer pushes more.
  const push = seen.push;
  assert.ok(push[3] > push[1] && push[1] > 0, `a bigger steer must push harder (steer 1: ${push[1]}, steer 3: ${push[3]})`);
  assert.ok(push[10] > push[5] && push[5] > push[3], `a bigger steer keeps pushing harder (steer 3: ${push[3]}, 5: ${push[5]}, 10: ${push[10]})`);
  // The default steer is above 0: a full input moves a top that is given no steer.
  assert.ok(push.default > 0, 'the default steer must be above 0');
});
