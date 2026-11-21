import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertPlain, assertDistinct, assertNoThrow, kindsOf } from './helpers.mjs';
import { MAP } from './scenario-19.mjs';

test('Graded 19: Plain data and determinism', () => {
  const o = observe('./scenario-19.mjs');

  // Plain data at every stage of a battle, a duel and a game.
  assert.ok(Array.isArray(o.stages), 'no stages were reported');
  const labels = o.stages.map(([label]) => label);
  for (const label of ['battle at the start', 'finished battle', 'duel at the start', 'duel view', 'new game', 'game after walking']) {
    assert.ok(labels.includes(label), `no kinds were reported for the ${label}`);
  }
  assert.ok(labels.some((l) => l.startsWith('duel stage ')), 'no duel stage was reported');
  for (const [label, seen] of o.stages) assertPlain(kindsOf(seen.copy, seen.uncopied, label), label);

  // A JSON copy taken midway carries on exactly like the original.
  for (const what of ['battle', 'duel', 'view', 'game']) {
    const [a, b] = counted(o.copies[what], 2, `${what} and its copy`);
    assert.equal(typeof a, 'string');
    assert.equal(b, a, `${what} copy`);
  }

  // Two battles stepped turn about end exactly as each does alone; so with a fresh copy of the modules.
  {
    const { x, y, turnAbout, games } = o.alone;
    assert.notEqual(x, y);
    for (const [tx, ty] of counted(turnAbout, 2, 'battles stepped turn about')) {
      assert.equal(tx, x, 'battle X stepped turn about differs from X alone');
      assert.equal(ty, y, 'battle Y stepped turn about differs from Y alone');
    }
    const [g, fresh, again] = counted(games, 3, 'games played');
    assert.equal(typeof g, 'string');
    assert.equal(fresh, g, 'a fresh copy of game.js plays the same');
    assert.equal(again, g);
  }

  // Clocks and Math.random taken away.
  assertNoThrow(o.clockless.call, 'with the clocks and Math.random taken away');
  assert.equal(o.clockless.finished, 'all of it ran');
  const [replayed, live] = counted(o.clockless.replayed, 2, 'a replay without clocks');
  assert.equal(replayed, live);

  // Inputs are left alone and nothing is shared with them.
  {
    const i = o.inputs;
    counted(i.held, 2, 'the battle and the duel battle').forEach(({ creatures, team }) => {
      counted(creatures, 2, 'sides');
      creatures.forEach((side, s) => counted(side, i.cfgSizes[s], `side ${s}'s creatures`).forEach((pairs) => {
        const [creature, moves, move, stats, base] = counted(pairs, 5, 'objects of a creature');
        assertDistinct(creature, 'a battle must hold copies of the creatures');
        assertDistinct(moves, 'a battle must hold copies of the moves');
        assertDistinct(move, 'a battle must hold copies of each move');
        assertDistinct(stats, 'a battle must hold copies of the stats');
        assertDistinct(base, 'a battle must hold copies of the base stats');
      }));
      assertDistinct(team, 'a battle must hold a copy of the team');
    });
    assert.notEqual(i.cfgAfter.hp, 1);
    assert.notEqual(i.cfgAfter.power, 999);
    assertNoThrow(i.again, 'a second battle from the same frozen config');
    assertDistinct(i.mapIds, 'the game map is a copy of the options map');
    assert.deepEqual(i.map, MAP);
    assert.notEqual(i.optionsRow, 'zzz');
    assertDistinct(i.moveIds, 'a game creature holds copies of its moves');
    assert.notEqual(i.powerAfter, 999, 'editing a game creature must not edit MOVES');
    assert.equal(i.powerAfter, i.powerBefore, 'editing a game creature must not edit MOVES');
    assertNoThrow(i.frozenSpecies, 'makeCreature of a frozen species');
  }
});
