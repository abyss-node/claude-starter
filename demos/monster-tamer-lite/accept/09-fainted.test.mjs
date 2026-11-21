import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertUnchanged, assertThrew } from './helpers.mjs';
import { ofType, core } from './fixtures.mjs';
import { TIE_SEEDS } from './scenario-09.mjs';

test('Graded 9: A fainted creature cannot act', () => {
  const o = observe('./scenario-09.mjs');

  // The faster side fells the foe: the foe does not act at all, and the battle ends.
  {
    const { battle: b, legal, again, nulls } = o.fasterFells;
    const log = b.log;
    assert.equal(ofType(log, 'move').filter((e) => e.side === 1).length, 0, 'the fainted foe must not move');
    assert.equal(ofType(log, 'skip').length + ofType(log, 'miss').length, 0);
    assert.equal(b.sides[0].team[0].hp, 60, 'the fallen foe does no damage');
    assert.deepEqual(core(ofType(log, 'faint')), [{ type: 'faint', side: 1 }]);
    assert.equal(ofType(log, 'end').length, 1);
    assert.deepEqual(core(ofType(log, 'end'))[0], { type: 'end', winner: 0 });
    assert.equal(b.phase, 'over');
    assert.equal(b.winner, 0);
    assert.deepEqual(b.pending, [false, false]);
    assert.equal(b.history.length, 1);
    assert.deepEqual(legal, [[], []]);
    assertUnchanged(again, 'a finished battle');
    assertUnchanged(nulls, 'a finished battle, nulls');
  }
  // Same with the sides the other way round (the slower side is the one that falls).
  {
    const b = o.otherWay;
    assert.equal(ofType(b.log, 'move').length, 1);
    assert.equal(ofType(b.log, 'move')[0].side, 1);
    assert.equal(b.sides[1].team[0].hp, 60);
    assert.equal(b.winner, 1);
  }
  // A tie in speed: whoever goes first and fells the other wins; the other never acts (many seeds).
  counted(o.ties, TIE_SEEDS, 'tied battles').forEach(({ log, winner }, seed) => {
    assert.equal(ofType(log, 'move').length, 1, `seed ${seed}: only the first mover may act`);
    assert.equal(ofType(log, 'faint').length, 1);
    assert.equal(winner, ofType(log, 'move')[0].side);
  });

  // A draw: both last creatures fall on the same end of turn.
  {
    const b = o.draw;
    assert.equal(b.phase, 'over');
    assert.equal(b.winner, -1);
    assert.deepEqual(core(ofType(b.log, 'end')), [{ type: 'end', winner: -1 }]);
    assert.equal(ofType(b.log, 'faint').length, 2);
    assert.deepEqual(b.pending, [false, false]);
  }
  // Fainted benched creatures do not count: the last standing one falling ends it.
  assert.deepEqual(o.benchFainted, { phase: 'over', winner: 0 });

  // Replacement: the fainted side alone is asked, and only for creatures that can fight.
  {
    const { asked, bad, replaced, next } = o.replace;
    assert.equal(asked.battle.phase, 'replace');
    assert.deepEqual(asked.battle.pending, [false, true]);
    assert.equal(asked.battle.turn, 2);
    assert.equal(asked.battle.winner, null);
    assert.deepEqual(asked.legal, [[], [{ kind: 'switch', to: 2 }]]);
    const why = ['the side that is not pending moves', 'the fainted creature moves', 'switch to a fainted creature',
      'switch to the fainted active creature', 'the pending side gives nothing', 'the side that is not pending switches'];
    counted(bad, why.length, 'refused replacements').forEach((u, i) => assertUnchanged(u, why[i]));
    const b = replaced.battle;
    assert.equal(b.phase, 'choose');
    assert.deepEqual(b.pending, [false, false]);
    assert.equal(b.sides[1].active, 2);
    assert.equal(b.turn, 2, 'a replacement does not advance the turn');
    assert.deepEqual(core(replaced.newEntries), [{ type: 'switch', side: 1, to: 2 }], 'a replacement logs the switch and nothing else (no new turn entry)');
    assert.equal(replaced.rng, replaced.rngBefore, 'a replacement takes no draw');
    assert.equal(b.history.length, 2);
    assert.deepEqual(b.history[1], [null, { kind: 'switch', to: 2 }]);
    const dmg = ofType(next.log, 'damage').pop();
    assert.equal(dmg.side, 1);
    assert.equal(next.sides[1].team[2].hp < 60, true, 'the replacement takes the next hit');
    assert.equal(next.sides[1].team[0].hp, 0, 'the fallen creature stays down');
    assert.equal(next.sides[1].team[1].hp, 0);
  }
  // Both sides fall to scorch on the same turn with spares: both are asked, side 0 switches first in the log.
  {
    const { asked, newEntries, phase } = o.bothReplace;
    assert.equal(asked.battle.phase, 'replace');
    assert.deepEqual(asked.battle.pending, [true, true]);
    assert.deepEqual(asked.legal, [[{ kind: 'switch', to: 1 }], [{ kind: 'switch', to: 1 }]]);
    assertUnchanged(asked.oneOfTwo, 'only one of two pending sides chose');
    assert.deepEqual(core(newEntries), [{ type: 'switch', side: 0, to: 1 }, { type: 'switch', side: 1, to: 1 }]);
    assert.equal(phase, 'choose');
  }
  // A side that has nothing left loses even when the other side must replace.
  assert.deepEqual(o.nothingLeft, { phase: 'over', winner: 1 });

  // createBattle starts on the first creature that can fight, and refuses a side with none.
  assert.equal(o.start.active, 2);
  assert.equal(o.start.name, 'Third');
  assert.deepEqual(o.start.legal.filter((a) => a.kind === 'switch'), []);
  assertThrew(o.start.noneLeft, 'createBattle with no creature that can fight on side 0');
  assertThrew(o.start.noneRight, 'createBattle with no creature that can fight on side 1');
});
