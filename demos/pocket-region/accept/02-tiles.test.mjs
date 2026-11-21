import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stable, tilesMap, TILE_FLAGS } from './helpers.mjs';
import { ask } from './ask.mjs';

// The brief's rules for the map in tilesMap(), written out again here as the check's own model.
const MAP = tilesMap();
const isFlag = (flags, name) => Object.hasOwn(flags, name) && flags[name] === true;
function tileOf(x, y) {
  if (!Number.isInteger(x) || !Number.isInteger(y) || x < 0 || y < 0 || y >= MAP.height || x >= MAP.width) return null;
  return MAP.rows[y][x];
}
function reasonOf(x, y, flags) {
  const t = tileOf(x, y);
  if (t === null) return 'edge';
  if (t !== '.' && t !== ',') return 'tile';
  if (MAP.npcs.some((n) => n.x === x && n.y === y)) return 'npc';
  if (MAP.gates.some((g) => g.x === x && g.y === y && !isFlag(flags, g.flag))) return 'gate';
  return null;
}

test('Graded 2: tileAt reads the grid; blockedReason and canEnter name why a tile cannot be entered, in the stated order', () => {
  const seen = ask('./sc-world.mjs', 'tiles');
  // the model itself says what the brief's examples say
  assert.equal(reasonOf(3, 0, {}), 'tile');
  assert.equal(reasonOf(1, 2, {}), 'npc');
  assert.equal(reasonOf(0, 0, {}), 'tile');
  assert.equal(reasonOf(2, 2, {}), 'gate');

  for (const [key, got] of Object.entries(seen.tile)) {
    const [x, y] = key.split(',').map(Number);
    assert.equal(got, tileOf(x, y), `tileAt(m, ${x}, ${y})`);
  }
  assert.equal(seen.odd.halfX, null, 'a coordinate that is not a whole number is outside the map');
  assert.equal(seen.odd.halfY, null);
  assert.equal(seen.odd.far, null);

  // walkable tiles are floor and tall grass; every other character blocks; the edge, a person (a wall under a
  // person is still a wall), a closed gate; only the own key `true` is a set flag
  for (const [key, got] of Object.entries(seen.reason)) {
    const [x, y, ...rest] = key.split(',');
    const flags = TILE_FLAGS.find((f) => stable(f) === rest.join(','));
    assert.equal(got, reasonOf(Number(x), Number(y), flags), `blockedReason(m, ${x}, ${y}, ${rest.join(',')})`);
    assert.equal(seen.can[key], got === null, `canEnter(m, ${x}, ${y}, ${rest.join(',')}) is blockedReason === null`);
  }
  assert.equal(seen.bare, null, 'a map with no npcs or gates lists works');
});
