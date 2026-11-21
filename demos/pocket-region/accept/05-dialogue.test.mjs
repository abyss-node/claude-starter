import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

const ENDED = { node: null, text: '', choices: [], ended: true, battle: null };

test('Graded 5: dialogue trees follow choices and nexts, set flags, give items, loop, end, and refuse an invalid choice', () => {
  const o = ask('./sc-world.mjs', 'dialogue');

  // start: the first node is entered, its effects applied, the view shaped as documented
  const r = o.start.r;
  assert.deepEqual(r.view, { node: 'a', text: 'Welcome', choices: ['Ask', 'Leave', 'Skip'], ended: false, battle: null });
  assert.deepEqual(r.game.flags, { old: true, met: true });
  assert.deepEqual(r.game.inventory, { salve: 2, spark: 3 }, 'a missing count is 1, and items stack');
  assert.deepEqual(r.game.keep, { me: 1 }, 'other fields of the game are carried along');
  assert.equal(r.game.mode, 'dialogue');
  assert.equal(o.start.newObject, true);

  // a choice with next: the choice's own set, then the target node's text
  assert.deepEqual(o.a1.view, { node: 'ask', text: 'Question?', choices: [], ended: false, battle: null });
  assert.deepEqual(o.a1.game.flags, { old: true, met: true, asked: true });
  assert.deepEqual(o.a1.game.inventory, { salve: 2, spark: 3 });

  // a node with no choices follows next with no choice given; entering gives items
  assert.equal(o.a2.view.node, 'more');
  assert.deepEqual(o.a2.game.inventory, { salve: 4, spark: 3 });
  // a choice argument is ignored where there are no choices
  assert.equal(o.a2b.view.node, 'more');
  assert.deepEqual(o.a3.view, { node: 'ask2', text: 'Again?', choices: ['Back', 'Done'], ended: false, battle: null });

  // looping back re-enters a node, and its effects apply again
  assert.equal(o.back.view.node, 'a');
  assert.deepEqual(o.back.game.inventory, { salve: 5, spark: 6 });

  // a choice whose next is null ends the conversation; its set still applies
  assert.deepEqual(o.leave.view, ENDED);
  assert.deepEqual(o.leave.game.flags, { old: true, met: true, left: true });

  // a node with choices ignores its own next
  assert.equal(o.skip.view.node, 'end');
  assert.deepEqual(o.skip.game.flags, { old: true, met: true, bye: true });

  // a node with no next ends the conversation
  assert.deepEqual(o.fin.view, ENDED);
  assert.deepEqual(o.fin.game.flags, o.skip.game.flags);

  // an ended view stays ended
  assert.deepEqual(o.again.view, ENDED);
  assert.equal(o.againGameStable, o.finGameStable);

  // an invalid choice throws RangeError
  for (const { choice, threw } of o.bad) assert.equal(threw, 'RangeError', `choice ${choice} is not valid`);
});
