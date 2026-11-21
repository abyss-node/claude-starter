import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 9: priority, then speed, then the player; one draw per attack in order; accuracy; the log; a knocked-out creature does not act', () => {
  const o = ask('./sc-battle.mjs', 'turnOrder');

  // speed decides; a tie goes to the player; priority beats speed; equal priority falls back to speed
  assert.deepEqual(o.order, [
    'player,enemy', 'enemy,player', 'player,enemy', // faster first; a tie goes to the player
    'enemy,player', 'player,enemy', 'enemy,player', // the slower side's priority move first; the faster side's; speed again
  ]);

  // the log: turn number, actor, move id, hit, damage, and the target's hp afterwards
  const b = o.logged;
  assert.equal(b.turn, 1);
  assert.deepEqual(b.log, [
    { turn: 1, actor: 'player', move: 'jab', hit: true, damage: 63, targetHp: 37 },
    { turn: 1, actor: 'enemy', move: 'jab', hit: true, damage: 82, targetHp: 18 },
  ]);
  // (floor(40*30/30)+2 = 42, x1.5 = 63; floor(40*40/30)+2 = 55, x1.5 = 82)
  assert.equal(b.enemyParty[0].hp, 100 - b.log[0].damage, 'hp of both sides moved by exactly the logged damage');
  assert.equal(b.playerParty[0].hp, 100 - b.log[1].damage);

  // a side that is knocked out before it acts does not act: no log line, no draw
  const k = o.playerKnocksOut;
  assert.equal(k.log.length, 1);
  assert.equal(k.playerHp, 30, 'the knocked-out enemy never struck back');
  assert.equal(k.enemyHp, 0);
  assert.equal(k.rng, k.oneDraw, 'exactly one draw was used');
  const q = o.enemyKnocksOut;
  assert.deepEqual(q.actors, ['enemy']);
  assert.equal(q.playerHp, 0);
  assert.equal(q.enemyHp, 30);
  assert.equal(q.rng, q.oneDraw, 'exactly one draw was used, the enemy being the quick one');

  // one draw per attack, in the order the attacks happen, even for a move that cannot miss
  for (const { seed, rng, twoDraws } of o.draws) assert.equal(rng, twoDraws, `seed ${seed}: two attacks, two draws`);

  // accuracy: a draw r hits when r * 100 < accuracy. wobbly has accuracy 50.
  const mixes = new Set();
  for (const { seed, first, second, log, enemyHp } of o.wobbly) {
    const hit1 = first * 100 < 50;
    const hit2 = second * 100 < 50;
    assert.equal(log[0].hit, hit1, `seed ${seed}: the first attack uses the first draw`);
    assert.equal(log[1].hit, hit2, `seed ${seed}: the second attack uses the second draw`);
    for (const l of log) {
      if (l.hit) assert.equal(l.damage, 63);
      else assert.deepEqual([l.damage], [0], 'a miss does no damage');
    }
    assert.equal(enemyHp, 200 - log[0].damage);
    assert.equal(log[0].targetHp, enemyHp, 'a miss leaves the target hp as it was');
    mixes.add(`${hit1}${hit2}`);
  }
  assert.equal(mixes.size, 4, 'forty seeds include every mix of hit and miss');
  // accuracy 100 always hits
  for (const { seed, hits } of o.sure) assert.ok(hits.length === 2 && hits.every(Boolean), `seed ${seed}: accuracy 100 never misses`);
  // a power-0 move hits and does 0
  assert.equal(o.dud.first.hit, true);
  assert.equal(o.dud.first.damage, 0);
  assert.equal(o.dud.enemyHp, 500);

  // the input battle was frozen and unchanged; every turn adds one to the turn count
  for (const { i, turn, logTurns, logLength } of o.turns) {
    assert.equal(turn, i);
    assert.deepEqual(logTurns, [i, i]);
    assert.equal(logLength, 2 * i);
  }
  assert.equal(o.startTurn, 0);
  assert.equal(o.startLogLength, 0);
});
