import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted } from './helpers.mjs';
import { ofType, types, core } from './fixtures.mjs';
import { SCORCH_AMOUNTS, DAZE_SEEDS } from './scenario-08.mjs';

const scorchHits = (log) => log.filter((e) => e.type === 'damage' && e.cause === 'scorch');
const movesBy = (log, side) => ofType(log, 'move').filter((e) => e.side === side).length;

test('Graded 8: Status effects and their durations', () => {
  const o = observe('./scenario-08.mjs');
  assert.deepEqual(o.STATUS_TURNS, { scorch: 3, daze: 2, chill: 3 });

  // scorch from a preset status: max(1, floor(maxHp / 8)) per end of turn, exactly 3 turns, then cured.
  {
    const p = o.preset;
    assert.deepEqual(p.hps, [70, 60, 50, 50, 50]);
    const curedAt = [];
    counted(p.cured, 5, 'cured counts per turn').forEach((n, i) => { if (n > curedAt.length) curedAt.push(i + 1); });
    assert.deepEqual(curedAt, [3], 'cured is logged on the third turn, once');
    assert.equal(p.status, null);
    const scorch = scorchHits(p.log);
    assert.equal(scorch.length, 3);
    scorch.forEach((e) => { assert.equal(e.side, 1); assert.equal(e.amount, 10); });
    assert.deepEqual(scorch.map((e) => e.hp), [70, 60, 50]);
    assert.equal(ofType(p.log, 'cured')[0].kind, 'scorch');
    assert.equal(ofType(p.log, 'cured')[0].side, 1);
    assert.equal(p.ownHp, 80, 'the unburnt side loses nothing');
  }
  // the amount: floor(maxHp / 8) with a floor of 1
  counted(o.amounts, SCORCH_AMOUNTS.length, 'scorch amounts').forEach(({ log, hp }, i) => {
    const [maxHp, amount] = SCORCH_AMOUNTS[i];
    assert.equal(ofType(log, 'damage')[0].amount, amount, `maxHp ${maxHp}`);
    assert.equal(hp, Math.max(0, maxHp - amount));
  });
  // both sides burn, side 0 first in the log; the status turns count down
  assert.deepEqual(o.bothBurn.log.filter((e) => e.type === 'damage').map((e) => e.side), [0, 1]);
  assert.deepEqual(o.bothBurn.statuses, [{ kind: 'scorch', turns: 1 }, { kind: 'scorch', turns: 2 }]);
  // scorch can fell a creature: faint after the damage, no cured, status cleared
  {
    const f = o.felled;
    assert.equal(f.foe.hp, 0);
    assert.equal(f.foe.status, null, 'fainting clears the status');
    const t = types(f.log);
    assert.ok(t.indexOf('faint') > t.indexOf('damage'));
    assert.equal(ofType(f.log, 'cured').length, 0);
    assert.equal(f.phase, 'replace');
  }

  // scorch applied by a move ticks that same turn: applied on turn 1, ticks on turns 1, 2 and 3.
  counted(o.applied, 2, 'scorch by a move').forEach(({ first, third, fourth, log }, i) => {
    const foeSpd = [20, 40][i];
    assert.equal(first.hp, 70, `ticks on the turn it was applied (foe speed ${foeSpd})`);
    assert.deepEqual(first.status, { kind: 'scorch', turns: 2 });
    assert.equal(ofType(first.log, 'status').length, 1);
    assert.deepEqual(core(ofType(first.log, 'status'))[0], { type: 'status', side: 1, kind: 'scorch' });
    assert.equal(third.hp, 50);
    assert.equal(third.status, null);
    assert.equal(fourth.hp, 50);
    assert.equal(scorchHits(log).length, 3);
  });

  // daze: the foe is slower and gets dazed before it acts: it skips this turn and the next, then is cured.
  for (const { t1, t2, t3 } of counted(o.dazeSlow, DAZE_SEEDS, 'daze on a slower foe')) {
    assert.equal(ofType(t1.log, 'skip').length, 1);
    assert.deepEqual(core(ofType(t1.log, 'skip'))[0], { type: 'skip', side: 1, reason: 'daze' });
    assert.equal(movesBy(t1.log, 1), 0, 'a dazed creature does not use its move');
    assert.equal(t1.status.turns, 1);
    assert.equal(ofType(t2.log, 'skip').length, 2);
    assert.equal(ofType(t2.log, 'cured').length, 1);
    assert.equal(t2.status, null);
    assert.equal(t2.rng, t2.start, 'a dazed creature takes no accuracy draw');
    assert.equal(t2.ownHp, 80, 'a dazed creature does no damage');
    assert.equal(ofType(t3.log, 'skip').length, 2, 'the third turn is free again');
    assert.equal(movesBy(t3.log, 1), 1);
  }
  // daze: the foe is faster and has already acted when it is dazed: it skips only the next turn.
  {
    const { t1, t2, t3 } = o.dazeFast;
    assert.equal(movesBy(t1.log, 1), 1, 'the faster foe acts before it is dazed');
    assert.equal(ofType(t1.log, 'skip').length, 0);
    assert.equal(t1.status.turns, 1);
    assert.equal(ofType(t2.log, 'skip').length, 1);
    assert.equal(ofType(t2.log, 'cured').length, 1);
    assert.equal(t2.status, null);
    assert.equal(ofType(t3.log, 'skip').length, 1);
    assert.equal(movesBy(t3.log, 1), 2);
  }

  // chill: speed halved for 3 turns counting the turn it lands in.
  assert.deepEqual(o.chill.moves, [[1, 0], [0, 1], [0, 1], [1, 0]], 'chilled on turns 1 (after the order was set), 2 and 3 only');
  assert.equal(o.chill.status, null);
  assert.equal(ofType(o.chill.log, 'cured').length, 1);

  // At most one status; the first is kept.
  assert.equal(ofType(o.oneStatus.log, 'status').length, 0);
  assert.equal(o.oneStatus.foe.status.kind, 'daze');
  assert.equal(o.oneStatus.foe.hp, 80, 'no scorch damage: the scorch never landed');

  // A benched creature's status neither ticks nor hurts.
  assert.equal(o.bench.originalHp, 50, 'the original object is untouched anyway');
  assert.equal(o.bench.bench.hp, 50);
  assert.deepEqual(o.bench.bench.status, { kind: 'scorch', turns: 3 });
  assert.equal(o.bench.inPlay.hp, 40, 'once it is in, scorch resumes');
  assert.deepEqual(o.bench.inPlay.status, { kind: 'scorch', turns: 2 });

  // Fainting by a move clears the status.
  assert.equal(o.faintByMove.hp, 0);
  assert.equal(o.faintByMove.status, null);
});
