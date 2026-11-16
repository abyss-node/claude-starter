import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 17: a top that is out stays exactly as it was and takes no part in clashes, and the winner is set once', () => {
  const seen = ask('outTops');

  // Top A stays in play and is thrown at top B, which is out from tick 1: B has spun down in one case, rung out
  // in the other. B has speed and gets steering input every tick, and the bowl pulls at it. Both orders: the top
  // that is out may come first or last in the list, since a clash is resolved pair by pair with the lower index
  // first. The control is top A alone in a world of one: if B takes no part, A moves exactly as it does there.
  assert.equal(seen.variants.length, 4, 'setup: a spun-down and a rung-out top, each listed first and second');
  for (const v of seen.variants) {
    assert.equal(v.statusB, v.want, `${v.label}: B (spin ${v.spinB}, at ${v.xB}, ${v.yB}) should be '${v.want}' after tick 1, got '${v.statusB}'`);
    assert.equal(v.statusA, 'in', `${v.label}: A should still be in play after tick 1`);
    for (const later of v.later) {
      assert.equal(later.b, v.frozen, `${v.label}: after tick ${later.tick} the top that is out has changed (position, velocity, spin or status); it must stay exactly as it was`);
      assert.equal(later.a, later.control, `${v.label}: after tick ${later.tick} top A moved differently from top A alone; a top that is out takes no part in clashes`);
    }
    assert.ok(v.nearest < v.reach, `setup: A should have been thrown through B (closest approach ${v.nearest}, contact at ${v.reach})`);
  }

  // The winner is set once. Gone rings out on tick 1, so Fading wins; later Fading spins down, and the result
  // must stay a win for Fading (not a draw).
  for (const { steps, tick, winner } of seen.fading) {
    assert.equal(tick, steps, 'tick goes up by one on every step, a decided match included');
    assert.equal(winner, 0, `tick ${tick}: Gone rang out on tick 1 and Fading was the last top in play, so the winner is top 0 and stays top 0 (got ${winner}); it is set once`);
  }
  assert.notEqual(seen.downAt, null, 'setup: Fading (spin 6, friction 1) should have spun down within 12 s of game time');

  // Until then it is null: two tops in play, no winner. A world of one top never has one.
  assert.equal(seen.pair.length, 30, 'setup: thirty ticks of two tops in play');
  for (const { tick, winner } of seen.pair) {
    assert.equal(winner, null, `tick ${tick}: both tops are still in play, so the winner is still null`);
  }
  assert.notEqual(seen.solo.status, 'in', 'setup: the lone top should have spun down');
  assert.equal(seen.solo.winner, null, 'a world with one top has no winner, even when that top spins down: a winner needs two or more tops');
});
