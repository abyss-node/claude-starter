import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertThrew, assertDistinct, kindsOf } from './helpers.mjs';
import { CASES, BAD } from './scenario-18.mjs';

test('Graded 18: Save and load', () => {
  const o = observe('./scenario-18.mjs');

  counted(o.roundTrips, CASES.length, 'games saved and loaded').forEach((r, i) => {
    const label = CASES[i];
    const { game: g, back } = r;
    assert.equal(r.textType, 'string', label);
    assert.deepEqual(back, g, `${label}: loadGame(saveGame(game)) must equal the game`);
    counted(r.ids, 3, `${label}: identities`);
    assertDistinct(r.ids[0], `${label}: a fresh object`);
    assertDistinct(r.ids[1], `${label}: a fresh party`);
    assertDistinct(r.ids[2], `${label}: a fresh creature`);
    counted(r.uncopied, 2, `${label}: what the copies of the game and the loaded game could not carry`);
    const kinds = [kindsOf(g, r.uncopied[0], 'game'), kindsOf(back, r.uncopied[1], 'game')];
    assert.deepEqual(Object.keys(kinds[1]).sort(), Object.keys(kinds[0]).sort(), `${label}: the loaded game holds the same kinds of value as the game`);
    assert.equal(r.resaved, r.text, `${label}: saving what was loaded gives the same text`);
    if (g.battle) {
      assert.ok(back.battle && back.battle.log.length === g.battle.log.length, 'the battle in progress, log included, comes back');
      assert.deepEqual(back.battle.rng, g.battle.rng);
    }
    assert.deepEqual(back.rng, g.rng, `${label}: the random state comes back`);
    assert.deepEqual(back.box, g.box);
    assert.equal(back.snares, g.snares);
    assert.equal(back.steps, g.steps);
    assert.notEqual(r.originalHpAfterEdit, -999, 'a loaded game shares nothing with the original');
    assert.equal(r.originalHpAfterEdit, g.party[0].hp, 'a loaded game shares nothing with the original');
  });
  const byLabel = Object.fromEntries(CASES.map((c, i) => [c, o.roundTrips[i].game]));
  assert.ok(byLabel['mid battle'].battle, 'the mid-battle case really is mid battle');
  assert.ok(byLabel['after a catch'].party.length > 1 || byLabel['after a catch'].box.length > 0);
  assert.equal(byLabel['a full party and a box'].party.length, 6);

  // The loaded game carries on exactly like the original.
  counted(o.playOn, CASES.length, 'games played on').forEach(({ a, b, c, savedA, savedC }, i) => {
    assert.equal(typeof a, 'string');
    assert.equal(a, b);
    assert.equal(a, c, `${CASES[i]}: a loaded game must play on exactly as the original`);
    assert.equal(savedA, savedC);
  });

  // Bad saves throw.
  counted(o.bad, BAD.length, 'bad saves').forEach((t, i) => assertThrew(t, `loadGame must throw for: ${BAD[i]}`));

  // Edges that are valid.
  counted(o.edges, 2, 'valid edge saves').forEach(({ game, back }) => assert.deepEqual(back, game));
});
