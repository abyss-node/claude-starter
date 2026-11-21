import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted } from './helpers.mjs';
import { CURVE, LEVEL_FOR, REWARDS, SMALL, BAD_AMOUNTS } from './scenario-12.mjs';

test('Graded 12: XP and levelling', () => {
  const o = observe('./scenario-12.mjs');
  const levels = Object.keys(CURVE);
  counted(o.curve, levels.length, 'xpForLevel calls').forEach((got, i) => assert.equal(got, CURVE[levels[i]], `xpForLevel(${levels[i]})`));
  counted(o.levelFor, LEVEL_FOR.length, 'levelForXp calls').forEach((got, i) => assert.equal(got, LEVEL_FOR[i][1], `levelForXp(${LEVEL_FOR[i][0]})${LEVEL_FOR[i][0] === 99999 ? ': level 30 is the top' : ''}`));
  counted(o.roundTrip, 30, 'levels 1 to 30').forEach(([at, short], i) => {
    const level = i + 1;
    assert.equal(at, level, `levelForXp at the start of level ${level}`);
    if (level > 1) assert.equal(short, level - 1, `one XP short of level ${level}`);
  });
  counted(o.rewards, REWARDS.length, 'xpReward calls').forEach((got, i) => assert.equal(got, REWARDS[i][1], `xpReward(${JSON.stringify(REWARDS[i][0])})${REWARDS[i][1] === 1 ? ': a reward is at least 1' : ''}`));

  // no gain
  counted(o.small, SMALL.length, 'small gains').forEach(({ gained, before, after }, i) => {
    const amount = SMALL[i];
    assert.equal(gained, 0);
    assert.equal(after.xp, 120 + amount);
    assert.equal(after.level, 5);
    assert.deepEqual({ ...after, xp: before.xp }, before);
  });
  counted(o.bad, BAD_AMOUNTS.length, 'bad amounts').forEach(({ gained, before, after }, i) => {
    const bad = String(BAD_AMOUNTS[i]);
    assert.equal(gained, 0, `gainXp(${bad}) gains nothing`);
    assert.deepEqual(after, before, `gainXp(${bad}) changes nothing`);
  });

  // one level
  {
    const { gained, at175, after: c } = o.oneLevel;
    assert.equal(gained[0], 0, '120 + 55 = 175: not yet level 6 (180)');
    assert.equal(at175.level, 5);
    assert.equal(gained[1], 1);
    assert.equal(c.level, 6);
    assert.equal(c.xp, 180);
    assert.equal(c.maxHp, 36);
    assert.equal(c.hp, 36, 'a full-health creature stays full');
    assert.deepEqual(c.stats, { atk: 14, def: 12, spd: 9 });
  }
  // hp rises by the rise in maxHp, not to full
  assert.equal(o.hurt.gained, 1);
  assert.equal(o.hurt.after.maxHp, 36);
  assert.equal(o.hurt.after.hp, 15, '10 + (36 - 31)');
  // several levels at once
  {
    const { gained, after: c, hurtHp, made } = o.several;
    assert.equal(gained, 9, '1120 XP is level 14');
    assert.equal(c.level, 14);
    assert.equal(c.xp, 1120);
    assert.equal(c.maxHp, 70);
    assert.equal(c.hp, 70);
    assert.deepEqual(c.stats, { atk: 27, def: 21, spd: 16 });
    assert.equal(hurtHp, 1 + (70 - 31));
    // same result as making it at that level
    assert.deepEqual(made.stats, c.stats);
    assert.equal(made.maxHp, c.maxHp);
  }
  // fainted: levels up but stays at 0
  assert.equal(o.fainted.gained, 9);
  assert.equal(o.fainted.after.hp, 0, 'a fainted creature stays at 0');
  assert.equal(o.fainted.after.maxHp, 70);
  assert.equal(o.fainted.after.level, 14);
  // the cap
  {
    const { gained, capped, after, from29 } = o.cap;
    assert.equal(gained[0], 25);
    assert.equal(capped.level, 30);
    assert.equal(capped.xp, 5220, 'xp is capped at xpForLevel(30)');
    assert.equal(capped.maxHp, 140);
    assert.equal(capped.hp, 140);
    assert.equal(gained[1], 0);
    assert.equal(after.level, 30);
    assert.equal(after.xp, 5220);
    assert.equal(gained[2], 1);
    assert.equal(from29.level, 30);
    assert.equal(from29.xp, 5220);
    assert.equal(o.MAX_LEVEL, 30);
  }
  // stats come from base, not from the old stats
  assert.deepEqual(o.fromBase.stats, { atk: 29, def: 29, spd: 29 }, 'level 6 stats from base 100: floor(600 / 25) + 5');
  assert.equal(o.fromBase.maxHp, 36);
});
