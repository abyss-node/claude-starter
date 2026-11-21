import { test } from 'node:test';
import assert from 'node:assert/strict';
import { notPlain } from './helpers.mjs';
import { ask } from './ask.mjs';

const SEEDS = [0, 1, 2, 3, 7, 8, 9, 255, 256, 257, 65535, 65536, 65537, 65538, 999999, 1000000, 16777216, 2147483647, 2147483648, 4294967294, 4294967295, 123456789, 305419896, 3735928559, 1048577, 33554433, 536870913];

test('Graded 12: the generator is seeded, draws in [0, 1), is plain data, advances in place and shares nothing', () => {
  const o = ask('./sc-data.mjs', 'rng', SEEDS);

  // the same seed, the same stream; every draw in [0, 1)
  assert.deepEqual(o.same[0], o.same[1]);
  assert.equal(o.same[0].length, 200);
  for (const v of o.range) assert.ok(typeof v === 'number' && v >= 0 && v < 1, `${v} is in [0, 1)`);
  // seeds at both ends of the range work
  for (const [seed, draws] of Object.entries(o.ends)) {
    assert.equal(draws.length, 50, `seed ${seed}`);
    for (const v of draws) assert.ok(typeof v === 'number' && v >= 0 && v < 1, `seed ${seed}: ${v} is in [0, 1)`);
  }
  // different seeds give different streams, for the whole range of whole numbers
  const streams = new Map();
  SEEDS.forEach((s, i) => {
    const key = o.streams[i].join(',');
    assert.ok(!streams.has(key), `seeds ${s} and ${streams.get(key)} give the same stream`);
    streams.set(key, s);
  });
  // the stream is not stuck or lopsided
  const many = o.many;
  assert.equal(many.length, 10000);
  assert.ok(new Set(many).size > 9900, 'almost no repeated values in 10,000 draws');
  const mean = many.reduce((a, b) => a + b, 0) / many.length;
  assert.ok(mean > 0.47 && mean < 0.53, `the mean is about 0.5 (got ${mean})`);
  const lo = many.filter((v) => v < 0.1).length;
  assert.ok(lo > 800 && lo < 1200, `about a tenth of draws are below 0.1 (got ${lo})`);

  // the state is plain data: it survives a JSON copy and the copy carries on the same
  assert.equal(notPlain(o.kinds), null);
  assert.equal(o.copySame, true);
  assert.equal(o.carryOn[0].length, 30);
  assert.deepEqual(o.carryOn[0], o.carryOn[1]);
  // and a draw changes the state in place
  assert.equal(o.advancedInPlace, true);
  assert.equal(o.seed5[0], o.seed5[1]);

  // two generators do not share anything: interleaved draws match solo draws
  assert.deepEqual(o.interleaved.xs, o.interleaved.soloX);
  assert.deepEqual(o.interleaved.ys, o.interleaved.soloY);
  // making a new generator does not disturb a running one
  assert.deepEqual(o.undisturbed.got, o.undisturbed.want);
});
