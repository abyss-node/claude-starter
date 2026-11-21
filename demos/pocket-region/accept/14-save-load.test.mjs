import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stable } from './helpers.mjs';
import { ask } from './ask.mjs';

test('Graded 14: save and load give the same game back, in any mode, and carry on the same; what cannot be read is refused', () => {
  const o = ask('./sc-data.mjs', 'saveLoad');
  assert.equal(o.atChiefMap, 'keep');
  assert.equal(o.chatMode, 'dialogue');
  assert.equal(o.fightingMode, 'battle', 'the chief is still standing after one hit');

  for (const s of o.games) {
    const { name, game: g } = s;
    assert.equal(s.textType, 'string');
    // the text is canonical JSON of { version: 1, game }
    assert.equal(s.text, s.canonical, `${name}: save text is canonical`);
    assert.equal(s.text, stable({ version: 1, game: g }), `${name}: and matches the tests' own canonical form`);
    assert.deepEqual(s.back, g, `${name}: load gives back the same game`);
    assert.equal(s.backCanonical, stable(g), `${name}: byte for byte`);
    assert.equal(s.again, s.text, `${name}: saving again gives the same text`);
    assert.equal(s.secondStable, s.gameStable, `${name}: loads are independent`);
  }
  // the pieces named in the brief
  const { b, hurt } = o.pieces;
  assert.deepEqual(b.player, hurt.player);
  assert.deepEqual(b.flags, { zeta: true, alpha: true });
  assert.deepEqual(b.inventory, { tag: 1, salve: 4, spark: 2 });
  assert.equal(b.party[0].hp, 3);
  assert.deepEqual(b.rng, hurt.rng);

  // keys are written in sorted order whatever order they were set in
  assert.equal(o.order[0], o.order[1]);
  assert.ok(o.order[0].includes('{"a":true,"b":true,"c":true}'));

  // a restored game carries on exactly as the original: same states, step by step, in every mode
  for (const { name, steps } of o.carry) {
    assert.ok(steps.length > 0);
    for (const { input, original, loaded } of steps) assert.equal(loaded, original, `${name}: after ${input} the loaded game differs`);
  }
  // saving in the middle of a long walk and loading changes nothing about where it ends
  assert.ok(o.cuts.resumed.length > 5);
  for (const { cut, stable: resumed } of o.cuts.resumed) assert.equal(resumed, o.cuts.straight, `saved after ${cut} inputs`);

  // loading refuses what it cannot read
  const expected = {
    'a different version': 'any', 'version 2': 'any', 'version as text': 'any', 'no version': 'any', 'not JSON': 'any', empty: 'any',
    nothing: 'any', 'an array': 'any', 'no game': 'any', 'a game that is not an object': 'any', null: 'any', 'a game with NaN': 'TypeError',
  };
  assert.deepEqual(o.refusals.map((r) => r.name), Object.keys(expected));
  for (const { name, error } of o.refusals) {
    assert.notEqual(error, null, `${name} must throw`);
    if (expected[name] !== 'any') assert.equal(error, expected[name], `${name}: the kind of error`);
  }
});
