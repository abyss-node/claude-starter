import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clone } from './helpers.mjs';
import { ask } from './ask.mjs';

// The brief says the computer steers against the nearest other top still in play. So its answer in a world of
// three or four tops must be the answer it gives in a world that holds only itself and that nearest top, however
// the others lie. The test never says what the answer is, only what it may depend on.
test('Graded 19: the computer opponent steers against the nearest other top in play and nothing else', () => {
  const seen = ask('aiNearest');

  for (const { n, count, me, nearest, d0, d1, got, want } of seen.layouts) {
    assert.deepEqual(clone(got), clone(want),
      `layout ${n}: with ${count} tops the computer (index ${me}) answered ${JSON.stringify(got)}, but with only itself and its nearest other top (index ${nearest}, ${d0.toFixed(3)} away; the next is ${d1.toFixed(3)} away) it answers ${JSON.stringify(want)}; it must steer against the nearest other top in play and ignore the rest`);
  }
  assert.ok(seen.layouts.length >= 40, `setup: only ${seen.layouts.length} of 60 layouts had a clear nearest top`);

  // A nearer top that is out of play does not count. Near spins down on tick 1, so it is out but still sits
  // closest; Far is the nearest top still in play.
  assert.equal(seen.crowdedStatuses[2], 'spundown', 'setup: Near should be out after one tick');
  assert.equal(seen.crowdedStatuses[0], 'in');
  assert.deepEqual(clone(seen.crowded), clone(seen.without),
    'a top that is out of play must not be chosen as the nearest other top: with Near out, the answer must equal the answer in the world that has no Near');
});
