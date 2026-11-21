import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertPlain, clone, kindsOf } from './helpers.mjs';
import { SEEDS, N } from './scenario-02.mjs';

test('Graded 2: Seeded random numbers', () => {
  const o = observe('./scenario-02.mjs');

  assert.deepEqual(clone(o.state), o.state, 'a random state must be plain data');
  assert.deepEqual(JSON.parse(o.stateJson), o.state, 'a random state must be plain data');
  assertPlain(kindsOf(o.stateSeen.copy, o.stateSeen.uncopied, 'the random state'), 'the random state');
  const bins = new Array(10).fill(0);
  let sum = 0;
  counted(o.draws, N, 'draws from seed 42').forEach((x, i) => {
    assert.ok(typeof x === 'number' && x >= 0 && x < 1, `draw ${i} is ${x}, outside [0, 1)`);
    sum += x;
    bins[Math.floor(x * 10)]++;
  });
  assert.ok(Math.abs(sum / N - 0.5) < 0.02, `mean ${sum / N} is not near 0.5`);
  bins.forEach((n, i) => assert.ok(n > 800 && n < 1200, `tenth ${i} holds ${n} of ${N} draws`));

  for (const [x, y] of counted(o.sameSeed, 50, 'two streams from seed 7')) assert.equal(x, y, 'the same seed must give the same stream');
  for (const [x, y] of counted(o.copied, 25, 'a stream and its JSON copy')) assert.equal(x, y, 'a JSON copy of a state must continue the same stream');

  const adv = counted(o.advancing, 6, 'states after each draw');
  for (let i = 1; i < adv.length; i++) assert.notEqual(adv[i], adv[i - 1], 'nextFloat must advance the state it is given');
  const [x1, x2] = counted(o.twoInARow, 2, 'two draws from seed 5');
  assert.notEqual(x1, x2, 'two draws in a row came out equal');

  const streams = new Map();
  counted(o.streams, SEEDS.length, 'streams per seed').forEach((draws, i) => {
    counted(draws, 6, `draws from seed ${SEEDS[i]}`).forEach((x) => assert.equal(typeof x, 'number'));
    const key = draws.map((x) => x.toFixed(12)).join(',');
    assert.ok(!streams.has(key), `seed ${SEEDS[i]} gives the same stream as seed ${streams.get(key)}`);
    streams.set(key, SEEDS[i]);
  });
  assert.equal(streams.size, SEEDS.length);
});
