import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 4: stepping onto a warp tile lands on the stated tile of the stated map; a landing, a closed gate and standing still do not warp', () => {
  const o = ask('./sc-world.mjs', 'warps');

  // a plain warp: lands on (tx, ty) of the other map, turned as the warp says
  assert.equal(o.plain.moved, true);
  assert.equal(o.plain.warped, true);
  assert.equal(o.plain.blocked, null);
  assert.deepEqual(o.plain.player, { map: 'b', x: 2, y: 0, facing: 'up' });
  assert.notEqual(o.plain.player.map, 'a', 'the tile the player stepped onto is not where they end up');

  // the warp's own facing wins over the direction moved
  assert.deepEqual(o.ownFacing.player, { map: 'b', x: 1, y: 1, facing: 'left' });

  // no facing in the warp: the direction of the move is kept, whichever it is
  for (const { dir, r } of o.keepsDirection) {
    assert.equal(r.warped, true, `${dir} onto (2,2) warps once the gate is open`);
    assert.deepEqual(r.player, { map: 'b', x: 0, y: 1, facing: dir });
  }

  // landing on a warp tile does not warp again
  assert.deepEqual(o.landsOnWarp1.player, { map: 'b', x: 2, y: 0, facing: 'up' });
  assert.equal(o.landsOnWarp2.warped, true);
  assert.deepEqual(o.landsOnWarp2.player, { map: 'b', x: 1, y: 1, facing: 'left' }, 'lands on a warp tile of b and stays there');

  // a warp tile behind a closed gate is just blocked
  assert.equal(o.behindGate.moved, false);
  assert.equal(o.behindGate.warped, false);
  assert.equal(o.behindGate.blocked, 'gate');
  assert.deepEqual(o.behindGate.player, { map: 'a', x: 2, y: 1, facing: 'down' });

  // standing on a warp tile, or leaving one, does not warp
  assert.deepEqual(o.leaving.player, { map: 'b', x: 0, y: 1, facing: 'left' });
  assert.equal(o.leaving.warped, false);

  // a tile that shares only a column or a row with a warp tile is not a warp
  assert.equal(o.sharesColumnOrRow.warped, false);
  assert.deepEqual(o.sharesColumnOrRow.player, { map: 'b', x: 1, y: 0, facing: 'right' });

  // there and back: the return warp lands on its own stated tile
  assert.equal(o.there.warped, true);
  assert.deepEqual(o.there.player, { map: 'a', x: 3, y: 1, facing: 'left' });
  assert.deepEqual(o.andBack.player, { map: 'b', x: 2, y: 0, facing: 'up' });

  // a warp is chosen by its coordinates, and only on the player's own map
  assert.equal(o.byCoordinates.warped, true);
  assert.deepEqual(o.byCoordinates.player, { map: 'c', x: 0, y: 0, facing: 'down' });
  assert.equal(o.ownMapOnly.moved, true);
  assert.equal(o.ownMapOnly.warped, false);
  assert.deepEqual(o.ownMapOnly.player, { map: 'c', x: 1, y: 0, facing: 'right' });
});
