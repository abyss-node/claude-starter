import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

const REASONS = {
  wall: 'tile', water: 'tile', tree: 'tile',
  'left edge': 'edge', 'top edge': 'edge', 'right edge': 'edge', 'bottom edge': 'edge',
  npc: 'npc', gate: 'gate',
};

test('Graded 3: movePlayer moves one tile, turns the player even when blocked, names the reason, opens a gate with its flag', () => {
  const seen = ask('./sc-world.mjs', 'movement');
  // each direction moves exactly one tile and turns the player
  const dirs = { up: [1, 0], down: [1, 2], left: [0, 1], right: [2, 1] };
  for (const [dir, [x, y]] of Object.entries(dirs)) {
    const { r, newObject } = seen.dirs[dir];
    assert.equal(r.moved, true, `${dir} from (1,1) moves`);
    assert.equal(r.blocked, null);
    assert.equal(r.warped, false);
    assert.deepEqual(r.player, { map: 'm', x, y, facing: dir }, `${dir} lands on (${x},${y})`);
    assert.equal(newObject, true, 'the result is a new object');
  }
  // blocked: position stays, facing still turns, the reason is named
  assert.deepEqual(seen.blocked.map((b) => b.name), Object.keys(REASONS));
  for (const { name, p, dir, r } of seen.blocked) {
    assert.equal(r.moved, false, `${name}: not moved`);
    assert.equal(r.blocked, REASONS[name], `${name}: reason`);
    assert.equal(r.warped, false);
    assert.deepEqual(r.player, { ...p, facing: dir }, `${name}: stays put and turns to ${dir}`);
  }
  // the gate opens with its flag, and the player walks onto its tile
  assert.equal(seen.open.moved, true);
  assert.deepEqual(seen.open.player, { map: 'm', x: 1, y: 4, facing: 'right' });
  // one move never covers two tiles, and moves chain from the result
  assert.deepEqual(seen.chain, { map: 'm', x: 2, y: 3, facing: 'right' });
  // (the inputs were frozen in the scenario: a function that changed one would have thrown there)
});
