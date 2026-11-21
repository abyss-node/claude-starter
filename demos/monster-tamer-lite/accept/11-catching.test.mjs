import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted } from './helpers.mjs';
import { types, core, ofType } from './fixtures.mjs';
import { CHANCES, ATTEMPTS, attemptDraws, N, STATUS_SEEDS } from './scenario-11.mjs';

test('Graded 11: Catching', () => {
  const o = observe('./scenario-11.mjs');
  counted(o.chances, CHANCES.length, 'catchChance calls').forEach((got, i) => {
    const [creature, want, why] = CHANCES[i];
    assert.equal(got, want, why ?? `catchChance of catchRate ${creature.catchRate}, hp ${creature.hp}/${creature.maxHp}, status ${JSON.stringify(creature.status)}`);
  });

  // attemptCatch: exactly one draw; succeeds when r * 100 < chance.
  counted(o.attempts, ATTEMPTS.length, 'attemptCatch creatures').forEach((tries, i) => {
    const chance = ATTEMPTS[i][1];
    const draws = attemptDraws(chance);
    counted(tries, draws.length, `attemptCatch at chance ${chance}`).forEach(({ got, calls }, j) => {
      assert.equal(got, draws[j][1], `chance ${chance}, draw ${draws[j][0]}`);
      assert.equal(calls, 1, 'attemptCatch must call rand exactly once');
    });
  });

  // In a battle: one snare, one draw, the first of the turn; success when that draw succeeds.
  let wins = 0;
  counted(o.battles, N, 'snare battles').forEach(({ chance, r, after, rng, battle: b }, seed) => {
    assert.equal(chance, 33);
    const success = r * 100 < chance;
    assert.equal(b.snares, 2, 'a snare is spent whether or not it holds');
    assert.deepEqual(core(ofType(b.log, 'snare')), [{ type: 'snare', side: 0, success }], `seed ${seed}, draw ${r}`);
    assert.equal(rng, after, 'a snare takes exactly one draw');
    if (success) {
      wins++;
      assert.equal(b.caught, true);
      assert.equal(b.phase, 'over');
      assert.equal(b.winner, 0);
      assert.equal(ofType(b.log, 'move').length, 0, 'the foe does not move after it is caught');
      assert.deepEqual(core(ofType(b.log, 'end')), [{ type: 'end', winner: 0 }]);
      assert.equal(b.turn, 1, 'a catch does not advance the turn');
      assert.equal(b.sides[1].team[0].hp, 30);
      assert.equal(b.history.length, 1);
    } else {
      assert.equal(b.caught, false);
      assert.equal(b.phase, 'choose');
      assert.equal(ofType(b.log, 'move').length, 1, 'after a failed snare the foe still moves');
      assert.equal(ofType(b.log, 'move')[0].side, 1);
      assert.equal(b.turn, 2);
      assert.equal(b.winner, null);
    }
  });
  assert.ok(wins > 70 && wins < 130, `${wins} of ${N} snares held at 33%`);

  // A status on the foe raises the chance the battle uses; the same seed always gives the same result.
  let withStatus = 0;
  counted(o.withStatus, STATUS_SEEDS, 'snares at a dazed foe').forEach(({ r, caught, log, again }, seed) => {
    assert.equal(caught, r * 100 < 43, `seed ${seed}: chance with a status is 43`);
    assert.equal(typeof log, 'string');
    assert.equal(again, log);
    if (caught) withStatus++;
  });
  assert.ok(withStatus > 60 && withStatus < 115, `${withStatus} caught of 200 at 43%`);

  // The snare costs a snare each time, and runs out.
  {
    const { r, first, snares, log } = o.runsOut;
    assert.ok(r * 100 >= 1);
    assert.equal(first.snares, 1);
    assert.equal(first.caught, false);
    assert.equal(snares, 1, 'a move does not spend a snare');
    assert.equal(types(log).filter((t) => t === 'snare').length, 1);
  }
});
