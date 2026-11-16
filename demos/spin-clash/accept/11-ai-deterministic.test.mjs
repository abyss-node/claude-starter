import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clone } from './helpers.mjs';
import { ask } from './ask.mjs';

test('Graded 11: the computer opponent is deterministic: the same seed gives the same match', () => {
  // The scenario takes Math.random, Date.now and performance.now away (they throw) around every match, so a call
  // from the computer fails this check with the message it throws.
  const seen = ask('aiDeterminism');
  assert.equal(seen.matches.length, 2, 'setup: one record each for the idle and the dodger opponent');
  for (const { name, a, b, c, alone } of seen.matches) {
    assert.equal(a, b, `${name}: seed 4 gave two different matches`);
    assert.notEqual(a, c, `${name}: seeds 4 and 9 gave the same match`);

    // Each seed's match must also equal the same match played alone, start to end, on its own fresh copy of the
    // module. This catches an AI whose answers leak from one match into another (a cache keyed on the tick, say)
    // even when the two matches that share a seed leak the same way.
    assert.equal(alone.length, 2, 'setup: two matches replayed alone');
    for (const { seed, turnAbout, alone: solo } of alone) {
      assert.equal(turnAbout, solo,
        `${name}: the seed ${seed} match played turn about with other matches differs from the same match played alone on a fresh copy of src/ai.js; the AI must keep no state in module variables`);
    }
  }

  // The AI keeps no state of its own: a JSON copy of the world gets the same answer.
  assert.deepEqual(clone(seen.twin.copy), clone(seen.twin.original), 'a JSON copy of the world got a different answer from the original');
});
