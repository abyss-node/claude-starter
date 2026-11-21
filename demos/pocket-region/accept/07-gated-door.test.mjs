import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 7: the gated door opens only after its flag, which a conversation sets, and the flag survives a warp', () => {
  const o = ask('./sc-world.mjs', 'gatedDoor');

  // before the flag: the gate at (7,3) stops the player at (6,3), however often they try
  assert.deepEqual(o.blocked.player, { map: 'town', x: 6, y: 3, facing: 'right' });
  assert.equal(o.blocked.flags.pass, undefined);
  // a flag that is not the gate's does nothing
  assert.deepEqual(o.wrongFlag.player, { map: 'town', x: 6, y: 3, facing: 'right' });
  assert.equal(o.falseFlag.player.x, 6, 'only true opens it');

  // talk to the sage: a conversation starts, and the flag is not set until the choice is made
  assert.equal(o.talk.mode, 'dialogue');
  assert.equal(o.talk.flags.pass, undefined, 'the flag is not set until the choice is made');
  assert.equal(o.otherChoice.mode, 'dialogue', 'the other choice ends nowhere near the flag');
  assert.equal(o.otherChoice.flags.pass, undefined);
  assert.equal(o.justPassing.mode, 'world');
  assert.equal(o.justPassing.flags.pass, undefined, '"Just passing" does not open the door');
  assert.equal(o.justPassingWalk.player.x, 6);

  // "Open the way" sets the flag; the same walk now passes the gate and warps
  assert.equal(o.openedAtChoice.flags.pass, true, 'set on entering the node');
  assert.equal(o.opened.mode, 'world');
  assert.equal(o.opened.flags.pass, true);
  assert.equal(o.opened.flags.asked, true);
  assert.deepEqual(o.opened.inventory, { tag: 1, salve: 2 });
  assert.deepEqual(o.through.player, { map: 'town', x: 7, y: 3, facing: 'right' }, 'standing on the gate tile');
  assert.deepEqual(o.out.player, { map: 'wild', x: 1, y: 2, facing: 'right' }, 'and on through the warp');

  // the flag, not the conversation, is what opens it
  assert.equal(o.direct.player.x, 7);

  // walking back through the warp and forward again: the flag stays set
  assert.deepEqual(o.home.player, { map: 'town', x: 6, y: 3, facing: 'left' });
  assert.equal(o.homeAgain.player.x, 7);

  // a closed gate changes nothing but facing
  assert.equal(o.closedGateStable.after, o.closedGateStable.before);
});
