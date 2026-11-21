import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

const OK = [
  [{ b: 1, a: { d: [3, { z: 1, y: 2 }], c: null } }, '{"a":{"c":null,"d":[3,{"y":2,"z":1}]},"b":1}'],
  [{ a: 1, b: 2 }, '{"a":1,"b":2}'],
  [{ b: 2, a: 1 }, '{"a":1,"b":2}'],
  // keys are sorted by code unit, not by locale: upper case before lower case, digits as text
  [{ a: 1, B: 2, _: 3, 9: 4, 10: 5, 'é': 6, Z: 7, z: 8 }, '{"10":5,"9":4,"B":2,"Z":7,"_":3,"a":1,"z":8,"é":6}'],
  [{ ab: 1, a: 2, aB: 3, '': 4 }, '{"":4,"a":2,"aB":3,"ab":1}'],
  // arrays keep their order, at any depth
  [[3, 1, [2, { b: 1, a: 2 }], 'x'], '[3,1,[2,{"a":2,"b":1}],"x"]'],
  // scalars
  [null, 'null'], [true, 'true'], [false, 'false'], [0, '0'],
  [-0, '0'], [{ x: -0 }, '{"x":0}'], [[-0], '[0]'],
  [0.1, '0.1'], [-12.5, '-12.5'], [1e21, '1e+21'], [123456789012, '123456789012'],
  ['a"b\\c\nd\u0001', '"a\\"b\\\\c\\nd\\u0001"'],
  ['café 世', '"café 世"'],
  [{ 'k"ey': 1 }, '{"k\\"ey":1}'],
  [{}, '{}'], [[], '[]'], [{ a: {}, b: [] }, '{"a":{},"b":[]}'],
];
const BAD = [
  ['NaN', NaN], ['Infinity', Infinity], ['-Infinity', -Infinity], ['undefined', undefined], ['a bigint', 10n],
  ['undefined in an object', { a: undefined }], ['undefined in an array', [1, undefined]],
  ['NaN deep down', { a: [{ b: { c: NaN } }] }], ['Infinity deep down', [[Infinity]]],
];

test('Graded 13: canonical JSON sorts keys by code unit, writes no whitespace, and refuses what is not plain saved data', () => {
  const o = ask('./sc-data.mjs', 'canonical', OK.map(([v]) => v), BAD.map(([, v]) => v));
  OK.forEach(([, want], i) => assert.equal(o.ok[i], want, `value ${i}`));
  // no whitespace anywhere outside strings
  assert.equal(o.big.replace(/"(?:[^"\\]|\\.)*"/g, '""').includes(' '), false);
  // it reads back to the same value, and the input is untouched
  assert.equal(o.frozen.parsed, o.frozen.given);
  // an own property called __proto__ is a key like any other
  assert.equal(o.proto, '{"__proto__":2,"a":3,"b":1}');
  // values that are not plain saved data are an error, at any depth
  BAD.forEach(([name], i) => assert.equal(o.bad[i], 'TypeError', `${name} must throw a TypeError`));
  for (const { name, error } of o.badBuilt) assert.equal(error, 'TypeError', `${name} must throw a TypeError`);
});
