import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 9: replaying a recorded match gives the same winner on the same tick', () => {
  const seen = ask('replay');
  // Every slider in the config is out of range on purpose: a createWorld that clamps by writing the clamped value
  // back into the caller's config changes it. A sparse config is held to the same for the defaults it leaves out.
  assert.equal(seen.sparse[1], seen.sparse[0], 'createWorld or step wrote defaults back into the config it was given');
  for (const [before, after] of seen.bares) {
    assert.equal(after, before, `createWorld or step wrote defaults into the config ${before}, which now reads ${after}`);
  }
  assert.equal(seen.afterCreate[1], seen.afterCreate[0], 'createWorld wrote the clamped slider values back into the config it was given');
  assert.deepEqual(seen.firstTop, [0.5, 0.2, 0], 'sliders out of range were not clamped');
  assert.notEqual(seen.live.winner, null, 'no winner after 7200 ticks (two minutes of game time) with friction on');
  assert.equal(seen.afterLive[1], seen.afterLive[0], 'createWorld or step changed the config object it was given');

  assert.equal(seen.replay.winner, seen.live.winner, `replay winner ${seen.replay.winner}, live winner ${seen.live.winner}`);
  assert.equal(seen.replay.tick, seen.live.tick, 'the replay ended on a different tick');
  // The same winner can come out of a different match; the end state cannot.
  assert.equal(seen.replay.snap, seen.live.snap, 'the replay ended in a different state (positions, speeds or spins differ)');
});
