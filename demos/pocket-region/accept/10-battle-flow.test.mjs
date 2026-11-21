import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 10: activeIndex, startBattle, knock-outs, the next creature, a finished battle, slots, running, and enemyChoose', () => {
  const o = ask('./sc-battle.mjs', 'flow');

  // activeIndex: the first creature with hp above 0, or -1
  assert.deepEqual(o.active, [0, 1, 2, -1, -1]);

  // startBattle: copies of both parties, turn 0, nothing decided, the rng from the seed
  const b = o.start.battle;
  assert.deepEqual(b.playerParty, [{ species: 'pup', name: 'A', type: 'plain', level: 5, hp: 500, maxHp: 500, atk: 30, def: 30, spd: 20, moves: ['jab'] }]);
  assert.deepEqual(b.enemyParty.map((m) => m.name), ['B']);
  assert.equal(o.start.sameParty, false);
  assert.equal(o.start.sameCreature, false, 'the party is copied, not shared');
  assert.equal(o.start.afterChange, 500, 'changing the given party afterwards changes nothing');
  assert.equal(b.turn, 0);
  assert.equal(b.over, false);
  assert.equal(b.winner, null);
  assert.equal(b.wild, false);
  assert.deepEqual(b.log, []);
  assert.equal(o.start.rng, o.start.expectedRng);
  assert.equal(o.start.wildTrue, true);
  assert.equal(o.start.wildFalse, false);

  // a knock-out ends it when the other side has nobody left
  const { won } = o.won;
  assert.equal(won.over, true);
  assert.equal(won.winner, 'player');
  assert.equal(won.enemyParty[0].hp, 0, 'hp does not go below 0');
  assert.equal(won.turn, 1);
  // a finished battle ignores further turns and comes back as a new, equal battle
  assert.equal(o.won.after, o.won.wonStable);
  assert.equal(o.won.sameObject, false, 'a finished battle comes back as a new, equal battle, not the same object');
  assert.equal(o.won.slot9, o.won.wonStable, 'even a move slot that does not exist');
  // the enemy wins when the player's whole party is down
  assert.equal(o.lost.over, true);
  assert.equal(o.lost.winner, 'enemy');
  assert.equal(o.lost.playerParty[0].hp, 0);

  // the next creature steps in: after the first falls the second is the target and the actor
  const { t1, t2 } = o;
  assert.equal(t1.over, false, 'the player still has a creature');
  assert.equal(t1.winner, null);
  assert.equal(t1.playerParty[0].hp, 0);
  assert.equal(t1.playerParty[1].hp, 500);
  assert.equal(t1.log.length, 1, 'the fallen first creature did not act');
  assert.equal(t2.log.length, 3);
  assert.equal(t2.log[1].actor, 'enemy', 'the enemy is faster');
  assert.equal(t2.log[2].actor, 'player');
  assert.equal(t2.log[2].move, 'vine', 'the second creature uses its own moves');
  assert.equal(t2.playerParty[1].hp < 500, true, 'the second creature took the hit');
  assert.equal(t2.playerParty[0].hp, 0);
  // enemy side with two creatures: the second comes in after the first falls
  const { e1, e2, e3 } = o;
  assert.equal(e1.over, false);
  assert.equal(e1.enemyParty[0].hp, 0);
  assert.equal(e1.enemyParty[1].hp, 500);
  assert.equal(e2.enemyParty[1].hp < 500, true);
  assert.equal(e2.over, false, 'the second creature is not down yet');
  assert.equal(e2.enemyParty[0].hp, 0);
  assert.equal(e3.over, true);
  assert.equal(e3.winner, 'player');

  // turn does not change what it was given
  assert.equal(o.frozen.turn, 0);
  assert.equal(o.frozen.newObject, true);

  // an unknown move slot is a RangeError
  for (const { slot, error } of o.slots) assert.equal(error, 'RangeError', `slot ${slot}`);
  // slots count the active creature's own list
  assert.equal(o.ownSlot, 'fast');

  // running: wild battles can be left, with no draw and no hit; others cannot
  const { ran } = o.ran;
  assert.equal(ran.over, true);
  assert.equal(ran.winner, 'fled');
  assert.equal(ran.turn, 1);
  assert.equal(o.ran.rng, o.ran.wildRng, 'no random draw for running');
  assert.equal(ran.playerParty[0].hp, 500);
  assert.equal(ran.enemyParty[0].hp, 500);
  assert.deepEqual(ran.log, [{ turn: 1, actor: 'player', action: 'run' }]);
  assert.equal(o.stuck.after, o.stuck.before, 'running from a trainer battle changes nothing');

  // enemyChoose: the slot whose move does the most damage to the player's active creature, accuracy and priority
  // ignored, ties to the lowest slot
  assert.deepEqual(o.picks, [
    1,  // rinse (50, brine) beats ember x2
    0,
    0,  // a tie goes to the lowest slot
    0,  // accuracy and priority do not count
    2,
    1,  // vine: moss beats brine, and same type
    0,  // vine into brine is x2 (104) against jab with the same-type bonus (63)
  ]);
  assert.equal(o.activePlayer, 1, 'it looks at the player creature that is active, not the first of the party');
  assert.equal(o.activeEnemy, 0, 'the enemy that is active is the second one');
});
