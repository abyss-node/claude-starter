import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PLAIN_KINDS } from './helpers.mjs';
import { ask } from './ask.mjs';

// The first value in a list of [path, kind] pairs that plain data does not allow, as text; null when all do.
const notPlain = (pairs) => {
  const bad = pairs.find(([, kind]) => !PLAIN_KINDS.has(kind));
  return bad ? `${bad[0]} is ${bad[1]}` : null;
};

test('Graded 3: the world is plain data: a JSON copy taken mid-match carries on identically, even on a fresh copy of the module', () => {
  const seen = ask('plainData');
  assert.equal(notPlain(seen.kindsStart), null, `a new world must hold only numbers, strings, booleans, null, arrays and plain objects: ${notPlain(seen.kindsStart)}`);
  assert.equal(notPlain(seen.kindsMid), null, `a world mid-match must hold only plain data: ${notPlain(seen.kindsMid)}`);
  assert.equal(seen.twinMid, seen.mid, 'the JSON copy lost state');
  // The second copy went to a freshly loaded copy of src/physics.js, which has never made a world: anything the
  // physics keeps in module variables (settings, a random generator, a counter) is missing there.
  assert.equal(seen.twinEnd, seen.end, 'the copy and the original diverged after 400 more ticks');
  assert.equal(seen.elsewhereEnd, seen.end, 'a JSON copy stepped on a fresh copy of src/physics.js (one that never made a world) diverged from the original: all state must live in the world, none in module variables');
  assert.equal(notPlain(seen.kindsEnd), null, `the world after 800 ticks must hold only plain data: ${notPlain(seen.kindsEnd)}`);
});
