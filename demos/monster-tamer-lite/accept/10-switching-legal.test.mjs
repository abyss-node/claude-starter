import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertUnchanged, assertThrew } from './helpers.mjs';
import { MV, SW, SNARE, types, core, ofType } from './fixtures.mjs';
import { ASKED, BAD } from './scenario-10.mjs';

const ASKED_WANT = [
  [false, 'slot 3 does not exist'], [false, 'slot -1 does not exist'], [false, 'cannot switch to the active creature'],
  [false, 'cannot switch to a fainted creature'], [false, 'there is no creature 4'], [false, 'there is no action "dance"'],
  [false, 'null is no action'], [false, 'only side 0 may snare'], [false, 'no snare outside a wild battle'],
  [false, 'no snare with none left'], [false, 'a slot must be the number'], [true, 'a switch to a standing creature'],
];

test('Graded 10: Switching and legal actions', () => {
  const o = observe('./scenario-10.mjs');
  const all = [MV(0), MV(1), MV(2), SW(1), SW(3)];
  assert.deepEqual(o.legal.wild[0], [...all, SNARE]);
  assert.deepEqual(o.legal.wild[1], all, 'only side 0 may snare');
  assert.deepEqual(o.legal.tame[0], all, 'no snare outside a wild battle');
  assert.deepEqual(o.legal.dry[0], all, 'no snare with none left');
  assert.deepEqual(o.legal.lone[0], [MV(0), SNARE]);
  assert.deepEqual(o.legal.lone[1], [MV(0)]);

  for (const k of ['wild', 'tame', 'dry']) {
    counted(o.listedAsked[k], 2, `${k}: both sides`).forEach(({ each, junk }, side) => {
      counted(each, o.legal[k][side].length, `${k}: side ${side}'s actions asked back`).forEach((ok, i) => assert.ok(ok, `${JSON.stringify(o.legal[k][side][i])} is listed, so it is legal`));
      assert.ok(junk, 'extra properties are ignored');
    });
  }
  counted(o.asked, ASKED.length, 'isLegalAction calls').forEach((got, i) => assert.equal(got, ASKED_WANT[i][0], `${ASKED_WANT[i][1]} (${JSON.stringify(ASKED[i])})`));

  // Throwing calls change nothing.
  counted(o.bad, BAD.length, 'illegal choices').forEach((u, i) => assertUnchanged(u, `choices ${JSON.stringify(BAD[i])} are not legal`));
  counted(o.badSnare, 2, 'snares that may not be used');
  assertUnchanged(o.badSnare[0], 'snare in a tame battle');
  assertUnchanged(o.badSnare[1], 'snare with none left');

  // A switch is logged, and the creature that comes in takes the foe's move that turn.
  {
    const { first: b, second } = o.switchIn;
    assert.equal(b.sides[0].active, 1);
    assert.equal(b.sides[0].team[0].hp, 60, 'the creature that left is untouched');
    assert.ok(b.sides[0].team[1].hp < 60, 'the creature that came in takes the hit');
    assert.deepEqual(types(b.log), ['turn', 'switch', 'move', 'damage']);
    assert.deepEqual(core(b.log)[1], { type: 'switch', side: 0, to: 1 });
    assert.equal(ofType(b.log, 'damage')[0].side, 0);
    assert.deepEqual(b.history, [[{ kind: 'switch', to: 1 }, { kind: 'move', slot: 0 }]], 'history keeps copies of what was chosen');
    assert.equal(b.turn, 2);
    // next turn the new creature uses its own move
    assert.equal(ofType(second.log, 'move').filter((e) => e.side === 0).pop().move, 'y');
    assert.equal(second.history.length, 2);
  }
  // Both switch: side 0 then side 1; neither moves.
  {
    const b = o.bothSwitch;
    assert.deepEqual(types(b.log), ['turn', 'switch', 'switch']);
    assert.deepEqual(ofType(b.log, 'switch').map((e) => e.side), [0, 1]);
    assert.deepEqual([b.sides[0].active, b.sides[1].active], [1, 1]);
  }
  // legalActions follows the active creature after a switch.
  assert.deepEqual(o.afterSwitch, [MV(0), MV(1), MV(2), MV(3), SW(0)]);
  // history of a longer run holds every successful call, none of the failed ones
  counted(o.failed, 4, 'illegal calls in a longer run').forEach((t) => assertThrew(t, 'resolveTurn with slot 7'));
  assert.equal(o.longRun.historyLength, 4);
  assert.deepEqual(o.longRun.history, Array.from({ length: 4 }, () => [MV(0), MV(0)]));
  assert.equal(o.longRun.turn, 5);
});
