// Held-out checks for Fair Share. demos/check.py runs them from the kit on a copy of a workspace, which it names
// in DEMO_WORKSPACE; they are never copied there. The workspace's code runs in a process of its own
// (demos/probe.mjs), never in this one. Each check calls the module itself, so one that fails to load fails
// every check by name.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { inspect } from 'node:util';
import { notRefused, values } from '../../probe.mjs';

const share = (...calls) => values('src/share.js', calls);
const BILLS = [[1000, 4], [1001, 4], [1003, 4], [999, 7], [1, 3], [0, 5], [12345, 10], [7, 2], [100, 101]];
const sum = (xs) => xs.reduce((a, b) => a + b, 0);

function splits() {
  const got = share(...BILLS.map(([total, people]) => ['split', total, people]));
  return BILLS.map(([total, people], i) => {
    const shares = got[i];
    assert.ok(Array.isArray(shares) && shares.every((s) => typeof s === 'number'),
      `split(${total}, ${people}) returned ${inspect(shares)}, not an array of numbers`);
    return [total, people, shares];
  });
}

test('split: the shares add up to exactly the total', () => {
  for (const [total, people, shares] of splits()) {
    assert.equal(shares.length, people, `split(${total}, ${people}) has ${shares.length} shares`);
    assert.equal(sum(shares), total, `split(${total}, ${people}) = [${shares}] adds up to ${sum(shares)}`);
  }
});

test('split: one cent between three people is [1, 0, 0]', () => {
  const [shares] = share(['split', 1, 3]);
  assert.deepEqual(shares, [1, 0, 0], `split(1, 3) = [${shares}]`);
});

test('split: the shares differ by at most one cent', () => {
  for (const [total, people, shares] of splits()) {
    assert.ok(Math.max(...shares) - Math.min(...shares) <= 1, `split(${total}, ${people}) = [${shares}]`);
  }
});

test('split: the larger shares come first', () => {
  for (const [total, people, shares] of splits()) {
    assert.deepEqual(shares, [...shares].sort((a, b) => b - a), `split(${total}, ${people}) = [${shares}]`);
  }
});

test('split: one person pays the whole bill', () => {
  const [shares] = share(['split', 1234, 1]);
  assert.deepEqual(shares, [1234], `split(1234, 1) = [${shares}]`);
});

test('split: refuses a number of people that is not a whole number, one or more', () => {
  const bad = notRefused('src/share.js', [0, -2, 2.5, Number.NaN].map((people) => ['split', 1000, people]));
  assert.deepEqual(bad, [], bad.join('; '));
});

test('split and withTip: refuse a total that is not a whole number of cents, zero or more', () => {
  const calls = [-1, 10.5, Number.NaN].flatMap((total) => [['split', total, 2], ['withTip', total, 10]]);
  const bad = notRefused('src/share.js', calls);
  assert.deepEqual(bad, [], bad.join('; '));
});

test('withTip: adds the tip and rounds half up to a whole cent', () => {
  const cases = [[1999, 15, 2299], [10, 5, 11], [1000, 0, 1000], [333, 18, 393], [0, 20, 0]];
  const got = share(...cases.map(([total, tip]) => ['withTip', total, tip]));
  cases.forEach(([total, tip, want], i) => assert.equal(got[i], want, `withTip(${total}, ${tip}) returned ${inspect(got[i])}`));
});

test('withTip: refuses a negative tip', () => {
  const bad = notRefused('src/share.js', [['withTip', 1000, -5]]);
  assert.deepEqual(bad, [], bad.join('; '));
});
