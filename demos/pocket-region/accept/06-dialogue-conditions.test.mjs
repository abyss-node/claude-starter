import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 6: start lists, if and ifNot, own-key flags, hidden choices, and the battle hand-off', () => {
  const o = ask('./sc-world.mjs', 'conditions');

  // start lists: the first entry whose conditions hold
  assert.deepEqual(o.t1, ['ab', 'a', 'notc', 'rest', 'notc']);
  // no entry matches: the conversation is over before it starts, the game unchanged
  assert.deepEqual(o.none.view, { node: null, text: '', choices: [], ended: true, battle: null });
  assert.equal(o.none.game, o.none.given);

  // a flag is set only when the game has it as an own key with the value true
  assert.deepEqual(o.t3, ['plain', 'plain', 'inherited'], 'toString is not a flag until it is set; false is not set');
  assert.deepEqual(o.t3b, ['free', 'blocked']);

  // choices: if / ifNot hide them; the index counts visible choices only
  assert.deepEqual(o.t4texts[0], ['one', 'not-seen', 'last']);
  assert.deepEqual(o.t4texts[1], ['one', 'needs-key', 'not-seen', 'both', 'last']);
  assert.deepEqual(o.t4texts[2], ['one', 'needs-key', 'last']);
  assert.deepEqual(o.t4texts[3], ['one', 'last']);
  assert.equal(o.t4index1, 'nl', 'index 1 of the visible list is "last"');
  assert.equal(o.t4index2, 'RangeError', 'only two choices are visible');
  assert.equal(o.t4index3, 'nb');

  // flags set on entering a node count straight away for that node's own choices
  assert.deepEqual(o.t5, ['shown']);

  // every choice hidden: the node behaves as one with no choices
  assert.deepEqual(o.t6.choices, []);
  assert.equal(o.t6.next, 'y');
  assert.equal(o.t6bEnded, true);

  // a battle on a node without choices: leaving it ends the conversation with the battle named
  const spec = { party: [{ species: 'rockling', level: 6 }], win: 'beaten' };
  assert.deepEqual(o.t7.b.view, { node: 'fight', text: 'Fight!', choices: [], ended: false, battle: null });
  assert.deepEqual(o.t7.b.game.flags, { dared: true });
  assert.deepEqual(o.t7.done.view, { node: null, text: '', choices: [], ended: true, battle: spec });
  assert.deepEqual(o.t7.done.game.flags, { dared: true });
  // a battle on a node that has choices is ignored
  assert.equal(o.t8.node, 'y');
  assert.equal(o.t8.battle, null);
  // an ordinary ending has no battle
  assert.equal(o.t9, null);
});
