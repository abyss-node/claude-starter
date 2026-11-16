import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 8: ring-out and spin-down are judged on tick 1 by the centre, ring-out first, and the last top in play wins', () => {
  const seen = ask('ringout');

  for (const c of seen.cases) {
    assert.equal(c.tick, 1, `${c.label}: tick should be 1`);
    assert.equal(c.statuses[1], 'ringout', `${c.label}: the outside top should be 'ringout' after one step`);
    assert.equal(c.statuses[0], 'in', `${c.label}: the centred top should still be in`);
    assert.equal(c.winner, 0, `${c.label}: winner should be top 0`);
  }

  // The default rim is 1: a config that leaves arenaRadius out.
  assert.equal(seen.dflt.statuses[0], 'ringout', 'with the default rim, a top 1.05 from the centre should ring out');
  assert.equal(seen.dflt.statuses[1], 'in', 'with the default rim, a top 0.95 from the centre is still in');
  assert.equal(seen.dflt.winner, 1, 'the top inside the default rim should win');

  // The rim is the config's arenaRadius, not a built-in 1: a wider rim keeps a top that a rim of 1 would throw
  // out, and a narrower rim throws out a top that a rim of 1 would keep.
  assert.deepEqual(seen.wider.statuses, ['in', 'in'], 'with arenaRadius 2, tops 1.5 and 1.2 from the centre are inside the rim');
  assert.equal(seen.wider.winner, null, 'with arenaRadius 2 nobody has won yet');
  assert.deepEqual(seen.narrower.statuses, ['ringout', 'in'], 'with arenaRadius 0.5, a top 0.7 from the centre has rung out and one 0.1 from it has not');
  assert.equal(seen.narrower.winner, 1, 'with arenaRadius 0.5 the top near the middle wins');

  // The rim is judged on the top's centre: a wide top whose edge overhangs the rim but whose centre is inside
  // it is still in play.
  assert.equal(seen.wide.statuses[0], 'in', 'a top whose centre is inside the rim (0.95 of 1) is in play even if its edge (radius 0.2) is past the rim');
  assert.equal(seen.wide.winner, null, 'both tops are still in play, so there is no winner yet');

  // Ring-out is checked before spin-down: a top past the rim with almost no spin left has rung out, it has not
  // spun down.
  assert.equal(seen.both.statuses[0], 'ringout', 'a top past the rim whose spin is also below minSpin (4 by default) must be ringout, not spundown');
  assert.equal(seen.both.winner, 1, 'the other top should win');

  // A top whose spin is at or below minSpin inside the rim has spun down.
  assert.equal(seen.spent.statuses[0], 'spundown', 'a top inside the rim with spin 2 (minSpin 4 by default) should be spundown after one step');
  assert.equal(seen.spent.winner, 1, 'the top still spinning should win');

  // At or below minSpin, whichever side of it the spin sits; and a given minSpin moves the line.
  const want = new Map([['null 4', 'spundown'], ['null 3', 'spundown'], ['null 0.5', 'spundown'], ['null 4.5', 'in'], ['9 9', 'spundown'], ['9 8', 'spundown'], ['9 9.5', 'in'], ['1 3', 'in'], ['1 1', 'spundown']]);
  assert.equal(seen.edges.length, want.size);
  for (const e of seen.edges) {
    const w = want.get(`${e.minSpin} ${e.spin}`);
    const rim = e.minSpin === null ? '4 (default)' : e.minSpin;
    assert.equal(e.statuses[0], w, `spin ${e.spin} with minSpin ${rim} should be '${w}' after one step`);
    assert.equal(e.winner, w === 'in' ? null : 1, `spin ${e.spin} with minSpin ${rim}: winner`);
  }

  // Nobody left in play on the same tick is a draw: winner -1.
  assert.equal(seen.draw.tick, 1);
  assert.equal(seen.draw.winner, -1, 'both tops rung out on one tick: the winner is -1');
});
