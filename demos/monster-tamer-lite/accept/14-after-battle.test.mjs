import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertThrew } from './helpers.mjs';
import { PARTY_SIZES, CATCH_SEEDS } from './scenario-14.mjs';

test('Graded 14: After the battle', () => {
  const o = observe('./scenario-14.mjs');

  // No battle, or an unfinished one: throws, changes nothing.
  {
    const n = o.notOver;
    assertThrew(n.none, 'endBattle with no battle');
    assert.equal(n.afterNone, n.before, 'endBattle with no battle must change nothing');
    assertThrew(n.unfinished, 'a battle in phase choose is not finished');
    assert.equal(n.afterUnfinished, n.mid);
    assert.notEqual(n.before, n.mid);
  }

  // A win: XP for every party creature that is standing, none for the fainted.
  {
    const { over, expected, result, game: g, again } = o.win;
    assert.equal(over.phase, 'over');
    assert.equal(over.winner, 0);
    assert.deepEqual(result, { result: 'won', xp: 160 });
    assert.equal(g.battle, null);
    assert.equal(g.party.length, 3);
    assert.deepEqual(g.party.map((c) => c.name), ['A', 'Down', 'Bench'], 'same order');
    assert.equal(g.snares, 2, 'the snares left carry back');
    assert.deepEqual(g.party, expected);
    assert.equal(g.party[0].level, 7, '120 + 160 = 280 XP is level 7');
    assert.equal(g.party[0].xp, 280);
    assert.equal(g.party[1].xp, 120, 'the fainted creature gets no XP');
    assert.equal(g.party[1].level, 5);
    assert.equal(g.party[1].hp, 0);
    assert.equal(g.party[2].level, 7, 'a standing creature on the bench shares the XP');
    assert.equal(g.party[2].status, null);
    assert.deepEqual(g.box, []);
    assertThrew(again, 'there is no battle left to end');
  }

  // A catch: the foe joins with its hp and no status; no XP; snares carry.
  {
    const { chance, draws, seed } = o.catchSeed;
    assert.equal(chance, 95);
    counted(draws, CATCH_SEEDS, 'first draws per seed');
    let want = 0;
    while (want < CATCH_SEEDS && !(draws[want] * 100 < chance)) want++;
    assert.equal(seed, want, 'the catching battles use the first seed whose first draw catches');
    counted(o.catches, PARTY_SIZES.length, 'catching battles').forEach(({ caught, xps, result, game: g }, i) => {
      const partySize = PARTY_SIZES[i];
      assert.equal(caught, true);
      assert.deepEqual(result, { result: 'caught', xp: 0 });
      assert.equal(g.battle, null);
      assert.equal(g.snares, 3, 'one snare was spent');
      assert.deepEqual(g.party.map((c) => c.xp).slice(0, partySize), xps, 'a catch gives no XP');
      const joined = partySize < 6 ? g.party[g.party.length - 1] : g.box[0];
      assert.equal(joined.name, 'Catchee');
      assert.equal(joined.hp, 5, 'it joins with the hp it had');
      assert.equal(joined.status, null, 'and no status');
      assert.equal(g.party.length, Math.min(6, partySize + 1), `party of ${partySize}`);
      assert.equal(g.box.length, partySize < 6 ? 0 : 1, `box for a party of ${partySize}`);
    });
  }

  // A loss (or a draw): everyone healed, back to the start, no XP.
  counted(o.lost, 2, 'lost battles').forEach(({ over, xps, result, game: g }, i) => {
    const draw = i === 1;
    assert.equal(over.phase, 'over');
    assert.equal(over.winner, draw ? -1 : 1);
    assert.deepEqual(result, { result: 'lost', xp: 0 });
    assert.deepEqual([g.x, g.y], [1, 1], 'back at the start');
    assert.equal(g.steps, 9, 'steps are history, not reset');
    for (const c of g.party) { assert.equal(c.hp, c.maxHp); assert.equal(c.status, null); }
    assert.deepEqual(g.party.map((c) => c.xp), xps);
    assert.equal(g.party.length, 2);
    assert.equal(g.battle, null);
    assert.equal(over.ends, 1);
  });
});
