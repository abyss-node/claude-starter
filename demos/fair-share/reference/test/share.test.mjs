import { test } from 'node:test';
import assert from 'node:assert/strict';
import { split, withTip } from '../src/share.js';

test('an even bill splits evenly', () => {
  assert.deepEqual(split(1000, 4), [250, 250, 250, 250]);
});

test('every person gets a share', () => {
  assert.equal(split(900, 3).length, 3);
});

test('a ten percent tip', () => {
  assert.equal(withTip(1000, 10), 1100);
});

test('nobody to pay is refused', () => {
  assert.throws(() => split(1000, 0), RangeError);
});
