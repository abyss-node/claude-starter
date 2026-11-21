import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stable } from './helpers.mjs';
import { ask } from './ask.mjs';

// Talk to the sage and ask to open the way; walk east through the gate, across the wild map
// on its floor row, into the keep; fight the chief with two jabs; talk to the chief again.
const INPUTS = [
  'action', 'choose:0', 'action',
  'right', 'right', 'right', 'right',
  'right', 'right', 'right', 'right', 'right', 'right',
  'right', 'right', 'right',
  'action', 'action', 'move:0', 'move:0', 'action', 'action',
];
const SEEDS = [0, 1, 2, 1234, 4294967295];

test('Graded 19: a fixed list of inputs reaches the ending flag on the check\'s own world, whatever the seed', () => {
  const o = ask('./sc-game.mjs', 'playthrough', INPUTS, SEEDS);
  assert.deepEqual(o.runs.map((r) => r.seed), SEEDS);
  const finals = [];
  for (const { seed, states, endedAfter20, endedAtEnd } of o.runs) {
    assert.equal(states.length, INPUTS.length);
    const at = (n) => states[n - 1];
    assert.equal(at(1).mode, 'dialogue', `seed ${seed}: the sage speaks`);
    assert.equal(at(2).flags.pass, true, `seed ${seed}: the choice sets the flag`);
    assert.deepEqual(at(3).inventory, { tag: 1, salve: 2 });
    assert.equal(at(3).mode, 'world');
    assert.deepEqual(at(3).player, { map: 'town', x: 4, y: 3, facing: 'up' });
    assert.deepEqual(at(7).player, { map: 'wild', x: 1, y: 2, facing: 'right' }, 'through the gate and the warp');
    assert.deepEqual(at(13).player, { map: 'keep', x: 1, y: 2, facing: 'right' }, 'across the wild map and into the keep');
    assert.deepEqual(at(16).player, { map: 'keep', x: 3, y: 2, facing: 'right' }, 'up to the chief');
    assert.equal(at(17).mode, 'dialogue');
    assert.equal(at(18).mode, 'battle', 'the chief fights');
    assert.equal(at(19).mode, 'battle');
    assert.equal(at(19).battle.enemyParty[0].hp, 21, 'the chief took one jab');
    assert.equal(at(19).battle.playerParty[0].hp, 14);
    assert.equal(at(20).mode, 'world', 'the second jab wins');
    assert.equal(at(20).flags.chief_beaten, true);
    assert.equal(at(20).party[0].hp, 14);
    assert.equal(endedAfter20, false, 'not over until the chief has spoken again');
    assert.equal(at(21).flags.the_end, true);
    const g = at(22);
    assert.equal(endedAtEnd, true, `seed ${seed}: the ending flag is set`);
    assert.equal(g.mode, 'world');
    assert.equal(g.battle, null);
    assert.equal(g.dialogue, null);
    assert.deepEqual(g.flags, { pass: true, asked: true, chief_beaten: true, the_end: true });
    assert.deepEqual(g.inventory, { tag: 1, salve: 2 });
    assert.deepEqual(g.player, { map: 'keep', x: 3, y: 2, facing: 'right' });
    assert.deepEqual([g.party[0].hp, g.party[0].maxHp, g.party.length], [14, 35, 1]);
    const { rng, ...rest } = g;
    finals.push(stable(rest));
  }
  assert.equal(new Set(finals).size, 1, 'the end state does not depend on the seed (nothing in this walk is random)');

  // the same seed again, and through a save and a load at every step, gives the same game
  assert.equal(o.seed77.direct, o.seed77.again);
  assert.equal(o.seed77.reloaded, o.seed77.direct);
});
