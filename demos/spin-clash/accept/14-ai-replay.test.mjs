import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 14: replaying the recorded inputs of both players reproduces the winner of a solo match', () => {
  const seen = ask('soloReplay');
  assert.equal(seen.matches.length, 6, 'setup: idle and dodger, seeds 2, 5 and 11');
  let decided = 0;
  for (const { label, seed, live, replay } of seen.matches) {
    if (live.winner !== null) decided++;
    assert.equal(replay.winner, live.winner, `${label}, seed ${seed}: replay winner ${replay.winner}, live winner ${live.winner}`);
    assert.equal(replay.tick, live.tick, `${label}, seed ${seed}: the replay ended on a different tick`);
    assert.equal(replay.snap, live.snap, `${label}, seed ${seed}: the replay ended in a different state (the AI must only read the world, and its input must be what step receives)`);
  }
  assert.ok(decided >= 4, `only ${decided} of 6 solo matches were decided within 2400 ticks`);
  assert.equal(seen.topsAfter, seen.topsBefore, 'createWorld or step changed the config object it was given');
});
