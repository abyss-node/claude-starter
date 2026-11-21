import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

const INPUT = /^(up|down|left|right|action|run|choose:\d+|move:\d+|use:[^:]+:\d+)$/;

test('Graded 18: the shipped walkthrough reaches the ending, passes a gate tile, the same way every time and across a save', () => {
  const o = ask('./sc-game.mjs', 'walkthrough');
  const w = o.given;
  assert.ok(w, 'CONTENT.walkthrough is { seed, inputs }');
  assert.ok(Number.isInteger(w.seed) && w.seed >= 0 && w.seed <= 4294967295, 'seed is a whole number in 0..4294967295');
  assert.ok(Array.isArray(w.inputs) && w.inputs.length >= 20 && w.inputs.length <= 20000, 'between 20 and 20,000 inputs');
  for (const i of w.inputs) assert.ok(typeof i === 'string' && INPUT.test(i), `${JSON.stringify(i)} is not an input the game takes`);
  assert.equal(o.ran, true, 'the walkthrough could be played');

  assert.equal(o.startEnded, false, 'the game does not start finished');
  const a = o.first;
  assert.equal(a.ended, true, `after ${w.inputs.length} inputs the ending flag ${o.endFlagName} is set`);
  assert.equal(a.endFlag, true);
  assert.equal(a.mode, 'world', 'the game is back in the world at the end');
  assert.ok(a.modes.includes('dialogue'), 'the walkthrough talks to someone');
  assert.ok(a.modes.includes('battle'), 'the walkthrough fights a battle');
  assert.ok(a.maps.length >= 3, `the walkthrough visits at least three maps (visited ${a.maps.join(', ')})`);
  assert.ok(a.gates.length >= 1, 'the walkthrough walks through a gated door');
  assert.ok(a.partyLength >= 1);

  // deterministic: a second run ends in exactly the same state
  assert.equal(o.second.stable, a.stable);
  assert.equal(o.second.endedAt, a.endedAt);

  // saved partway and loaded, it ends in exactly the same state
  for (const { cut, stable } of o.resumed) assert.equal(stable, a.stable, `saved after ${cut} inputs`);
});
