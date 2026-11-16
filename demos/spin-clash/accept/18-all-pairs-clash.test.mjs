import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 18: every pair of tops in play clashes through step, not only neighbours in the list', () => {
  // Four tops on a flat floor with no friction. For each of the six pairs (i, j), those two are thrown head-on
  // along the x axis and the other two are parked, at rest, well out of the way. A pair that is not resolved
  // passes through itself.
  const { radius, pairs } = ask('allPairs');
  assert.equal(pairs.length, 6, 'setup: six pairs');
  for (const { i, j, vxI, vxJ, closest } of pairs) {
    assert.ok(vxI < 0 && vxJ > 0,
      `tops ${i} and ${j} met head-on in a world of four tops but did not bounce (vx ${vxI} and ${vxJ}); every pair of tops in play must be resolved with collide, not only neighbours in the list`);
    assert.ok(closest > radius,
      `tops ${i} and ${j} passed through each other (closest centres ${closest.toFixed(3)}, radii ${radius} each, so they touch at ${2 * radius})`);
  }
});
