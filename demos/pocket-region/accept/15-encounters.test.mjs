import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stable } from './helpers.mjs';
import { ask } from './ask.mjs';

test('Graded 15: stepping onto tall grass draws a, then b, c and d only on a hit; the pick, level and seed follow; nothing else draws', () => {
  const o = ask('./sc-data.mjs', 'encounters');

  // rate 100, one species, a fixed level: a battle starts, and the draws are used in order
  {
    const { g, out, draws, enemy, battleRng, after4 } = o.hundred;
    assert.ok(draws[0] * 100 < 100);
    assert.deepEqual(out.player, { map: 'wild', x: 1, y: 1, facing: 'up' });
    assert.equal(out.mode, 'battle');
    assert.equal(out.dialogue, null);
    assert.equal(out.battle.wild, true);
    assert.equal(out.battle.over, false);
    assert.deepEqual(out.battle.enemyParty, [enemy]);
    assert.deepEqual(out.battle.playerParty, g.party);
    assert.equal(stable(out.battle.rng), battleRng, 'the battle is seeded from the fourth draw');
    assert.equal(stable(out.rng), after4, 'four draws were used');
    assert.equal(out.battle.winFlag, null);
  }
  // rate 0: one draw, no battle
  assert.equal(o.zero.out.mode, 'world');
  assert.equal(o.zero.out.battle, null);
  assert.equal(stable(o.zero.out.rng), o.zero.after1, 'one draw even though nothing happens');

  // a rate in between: the draw decides, over many seeds, and the pick and the level follow the next draws
  const picks = new Set();
  const levels = new Set();
  let started = 0;
  let quiet = 0;
  for (const { seed, out, draws, after1, after4, creatures, battleRng } of o.mixed) {
    const [a, b, lv] = draws;
    if (a * 100 < 35) {
      const species = b * 4 < 3 ? 'pool' : 'sprig';
      const level = species === 'pool' ? 2 + Math.floor(lv * 4) : 7;
      assert.equal(out.mode, 'battle', `seed ${seed}: draw ${a} is under the rate`);
      assert.deepEqual(out.battle.enemyParty, [creatures[`${species},${level}`]], `seed ${seed}`);
      assert.equal(stable(out.battle.rng), battleRng);
      picks.add(species);
      levels.add(level);
      started++;
      assert.equal(stable(out.rng), after4, `seed ${seed}: the right number of draws`);
    } else {
      assert.equal(out.mode, 'world', `seed ${seed}: draw ${a} is not under the rate`);
      quiet++;
      assert.equal(stable(out.rng), after1, `seed ${seed}: the right number of draws`);
    }
  }
  assert.ok(started >= 10 && quiet >= 10, `both outcomes happen (${started} battles, ${quiet} quiet)`);
  assert.deepEqual([...picks].sort(), ['pool', 'sprig']);
  assert.ok(levels.has(2) && levels.has(5) && levels.has(7), 'levels run over the whole range, both ends included');
  assert.ok([...levels].every((l) => (l >= 2 && l <= 5) || l === 7));

  // weights: three entries, the walk goes through the running totals
  for (const { seed, draws, mode, species } of o.weights) {
    const t = draws[1] * 6;
    const want = t < 1 ? 'pool' : t < 3 ? 'sprig' : 'rockling';
    assert.equal(mode, 'battle', `seed ${seed}`);
    assert.equal(species, want, `seed ${seed}`);
  }

  // a map with no encounter list: the draw is made, and that is all
  assert.equal(o.noList.mode, 'world');
  assert.equal(o.noList.rng, o.noList.after1);
  assert.equal(o.noList.mode2, 'world', 'no rate, no list');
  assert.equal(o.noList.rng2, o.noList.after1, 'still one draw');

  // grass to grass counts again
  assert.deepEqual(o.grassToGrass.player, { map: 'wild', x: 2, y: 1, facing: 'right' });
  assert.equal(o.grassToGrass.rng, o.grassToGrass.twoDraws, 'two steps on grass, two draws');

  // no draw anywhere else: floor, blocked moves, turning, a warp that lands on grass, other inputs
  assert.equal(o.noDraw.length, 6);
  for (const { why, before, after } of o.noDraw) assert.equal(after, before, why);
  assert.deepEqual(o.warpOntoGrass.player, { map: 'wild', x: 2, y: 1, facing: 'right' });
  assert.equal(o.warpOntoGrass.mode, 'world');
  assert.equal(o.warpOntoGrass.after, o.warpOntoGrass.before, 'landing on grass by a warp draws nothing');
});
