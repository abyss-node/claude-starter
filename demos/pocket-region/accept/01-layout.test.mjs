import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

const EXPECTED = {
  'src/rng.js': ['makeRng', 'rngNext'],
  'src/map.js': ['tileAt', 'blockedReason', 'canEnter'],
  'src/movement.js': ['movePlayer'],
  'src/dialogue.js': ['startDialogue', 'advanceDialogue'],
  'src/battle.js': ['makeCreature', 'damage', 'activeIndex', 'startBattle', 'enemyChoose', 'takeTurn'],
  'src/inventory.js': ['countOf', 'addItem', 'removeItem', 'useItem'],
  'src/save.js': ['canonicalJson', 'saveGame', 'loadGame'],
  'src/game.js': ['newGame', 'step', 'isEnded'],
  'src/content.js': ['CONTENT'],
};
const CONTENT_KEYS = ['start', 'endFlag', 'maps', 'trees', 'species', 'moves', 'items', 'walkthrough'];

test('Graded 1: every module exists, imports in Node with no browser, and exports its names; CONTENT has its keys', () => {
  const seen = ask('./sc-world.mjs', 'layout', EXPECTED, CONTENT_KEYS);
  assert.equal(seen.documentType, 'undefined', 'the checks run without a DOM');
  for (const [file, names] of Object.entries(EXPECTED)) {
    const f = seen.files[file];
    assert.ok(f && f.loaded, `${file} did not load in Node: ${f && f.error}`);
    for (const name of names) {
      assert.notEqual(f.types[name], null, `${file} does not export ${name}`);
      if (name !== 'CONTENT') assert.equal(f.types[name], 'function', `${file}: ${name} must be a function`);
    }
  }
  assert.equal(seen.content.type, 'object', 'CONTENT must be an object');
  for (const key of CONTENT_KEYS) assert.ok(seen.content.has[key], `CONTENT has no ${key}`);
});
