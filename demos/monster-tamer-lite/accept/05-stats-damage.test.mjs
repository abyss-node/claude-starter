import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertDistinct } from './helpers.mjs';
import { floorDiv, CHART, TYPE_NAMES } from './fixtures.mjs';
import { STAT_CALLS, HP_CALLS, ODD_LEVELS, FIXED, randomCases } from './scenario-05.mjs';

const STAT_WANT = [25, 22, 59, 5, 185];
const HP_WANT = [53, 46, 240, 11];
const LEVEL_WANT = [1, 1, 30, 7];
// What each FIXED case must do, and why.
const FIXED_WANT = [
  [26, '40*30*20/900 = 26.67 floors to 26 (moss v spark is 1; a cinder move has no matching-type bonus)'],
  [40, 'bonus 1.5 on 26.67 is exactly 40'],
  [53, 'super effective x2 (tide v cinder), no bonus: 53.33'],
  [13, 'resisted 0.5 (cinder v tide): 13.33'],
  [80, 'super effective and matching type: 26.67 * 3 = exactly 80'],
  [20, 'resisted and matching: 26.67 * 0.75 = 20'],
  [0, 'immune: spark to stone'],
  [0, 'immune: spark to stone, no matching type'],
  [0, 'power 0 does no damage, even super effective'],
  [1, 'never less than 1 otherwise'],
  [1, 'never less than 1 otherwise, resisted'],
  [14, 'level matters: (level + 10), level 1'],
  [53, 'level matters: (level + 10), level 30'],
  [60, 'attack and defence are not interchangeable (60 v 20)'],
  [6, 'attack and defence are not interchangeable (20 v 60)'],
  [26, "the defender's own attack stat and the attacker's defence play no part"],
];

test('Graded 5: Stats and damage', () => {
  const o = observe('./scenario-05.mjs');
  assert.equal(o.MAX_LEVEL, 30);
  counted(o.stat, STAT_CALLS.length, 'calcStat calls').forEach((got, i) => assert.equal(got, STAT_WANT[i], `calcStat(${STAT_CALLS[i]})`));
  counted(o.maxHp, HP_CALLS.length, 'calcMaxHp calls').forEach((got, i) => assert.equal(got, HP_WANT[i], `calcMaxHp(${HP_CALLS[i]})`));

  const c = o.creature;
  assert.ok(c && typeof c === 'object', 'makeCreature returned nothing');
  assert.equal(c.species, 'fx-species');
  assert.equal(c.name, 'Fx Species');
  assert.equal(c.type, 'moss');
  assert.equal(c.level, 5);
  assert.equal(c.xp, 120);
  assert.equal(c.maxHp, 31);
  assert.equal(c.hp, 31);
  assert.deepEqual(c.base, { hp: 50, atk: 40, def: 30, spd: 20 });
  assert.deepEqual(c.stats, { atk: 13, def: 11, spd: 9 });
  assert.equal(c.baseXp, 60);
  assert.equal(c.catchRate, 33);
  assert.equal(c.status, null);
  counted(o.moves, 2, 'the first two moves of MOVES');
  assert.deepEqual(c.moves, o.moves);
  assertDistinct(o.moveIds2, 'creature moves must be copies');
  assert.notEqual(o.afterEdit.movePower, 999, 'editing a creature must not edit MOVES');
  assert.equal(o.afterEdit.movePower, o.moves[0].power, 'editing a creature must not edit MOVES');
  assert.equal(o.afterEdit.speciesHp, 50, 'editing a creature must not edit its species');
  counted(o.oddLevels, ODD_LEVELS.length, 'odd levels').forEach((got, i) => assert.equal(got, LEVEL_WANT[i], `makeCreature(species, ${ODD_LEVELS[i]}).level`));
  assert.equal(o.xpAt30, 5220);
  assert.equal(o.xpAt1, 0);
  assert.equal(o.l30.maxHp, 140);
  assert.deepEqual(o.l30.stats, { atk: 53, def: 41, spd: 29 });

  const fixed = FIXED();
  counted(o.fixed, fixed.length, 'fixed damage cases').forEach((got, i) => assert.equal(got, FIXED_WANT[i][0], FIXED_WANT[i][1]));

  // Exact oracle over many random cases, in whole-number maths.
  const cases = randomCases();
  counted(o.random, cases.length, 'random damage cases').forEach(([got, after], i) => {
    const [a, d, m] = cases[i];
    const typePct = Math.round(CHART[m.type][TYPE_NAMES.indexOf(d.type)] * 100);
    const stabPct = m.type === a.type ? 150 : 100;
    let want = floorDiv(m.power * a.stats.atk * (a.level + 10) * typePct * stabPct, d.stats.def * 30 * 100 * 100);
    if (m.power > 0 && typePct > 0) want = Math.max(1, want);
    assert.equal(got, want, `case ${i}: ${JSON.stringify([a.level, a.stats.atk, a.type, d.stats.def, d.type, m.type, m.power])}`);
    assert.deepEqual(after, [a, d, m], 'calcDamage changed its arguments');
  });
});
