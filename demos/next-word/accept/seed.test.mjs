import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MANY_SEEDS, branchyText, collisions, parseAll, run } from './helpers.mjs';

const inSeedRange = (s) => Number.isInteger(s) && s >= 1 && s <= 999999;

test('seed: parseSeed reads a typed whole number', () => {
  const got = parseAll('42', '  7 ', '007', '0', '4294967295', '123456', '7', '8', '1', '2');
  assert.equal(got[0], 42);
  assert.equal(got[1], 7, 'surrounding spaces are ignored');
  assert.equal(got[2], 7);
  assert.equal(got[3], 0);
  assert.equal(got[4], 4294967295);
  assert.equal(got[5], 123456);
  assert.notEqual(got[6], got[7], 'different typed seeds must stay different');
  assert.notEqual(got[8], got[9]);
});

test('seed: parseSeed returns null for anything that is not a whole number', () => {
  const bad = ['', '   ', 'abc', '12abc', 'abc12', '-5', '+5', '1.5', '1e3', '0x10', '4 2', '4294967296', '99999999999999999999', '1.0', '7.', '.5', '42.000', '0.0', '1,000', '1_000'];
  const got = parseAll(...bad);
  bad.forEach((text, i) => assert.equal(got[i], null, `parseSeed(${JSON.stringify(text)}) should be null`));
});

test('seed: newSeed returns an integer from 1 to 999999 and draws once', () => {
  const draws = [0, 0.9999999999, 0, 0.000001, 0.25, 0.5, 0.75, 0.999999, 0.9999999999, 0.25, 0.75];
  const got = run('newSeedsFrom', draws);
  assert.equal(got[0].value, 1, 'lowest draw gives the lowest seed, 1');
  assert.equal(got[1].value, 999999, 'highest draw gives the highest seed, 999999');
  draws.slice(2, 9).forEach((r, i) => {
    const { value, calls } = got[2 + i];
    assert.equal(calls, 1, `r=${r}: rng called ${calls} times`);
    assert.ok(inSeedRange(value), `r=${r}: ${value} is not an integer in 1..999999`);
  });
  assert.ok(got[9].value < got[10].value, 'a larger draw gives a larger seed');
});

test('seed: newSeed with no argument gives a valid, varying seed', () => {
  const { seeds, parsed } = run('randomSeeds', 200);
  assert.equal(seeds.length, 200);
  seeds.forEach((s, i) => {
    assert.ok(inSeedRange(s), `${s} is not an integer in 1..999999`);
    assert.equal(parsed[i], s, 'the seed shown in the box must parse back to itself');
  });
  assert.ok(new Set(seeds).size >= 100, `200 random seeds gave only ${new Set(seeds).size} distinct values`);
});

test('seed: a typed seed drives sampling (same seed same text, different seed different text)', () => {
  const settings = { temperature: 1.5, topK: 0, topP: 1, length: 20 };
  const typed = ['1', '42', ' 42 ', '0042', '999999', ...Array.from({ length: 12 }, (_, i) => String(i + 1))];
  const [runs] = run('generated', [{ corpus: true, runs: typed.map((t) => ({ prompt: 'the', opts: settings, typedSeed: t, kinds: ['gen'] })) }]);
  const text = (i) => runs[i].gen.join(' ');
  // Each seed was drawn once above; ask again for the repeat of the first five.
  const [again] = run('generated', [{ corpus: true, runs: typed.slice(0, 5).map((t) => ({ prompt: 'the', opts: settings, typedSeed: t, kinds: ['gen'] })) }]);
  typed.slice(0, 5).forEach((t, i) => assert.equal(text(i), again[i].gen.join(' '), `seed "${t}" twice`));
  assert.equal(text(1), text(2), 'the same number typed with spaces is the same seed');
  assert.equal(text(1), text(3));
  const texts = new Set(runs.slice(5).map((r) => r.gen.join(' ')));
  assert.ok(texts.size >= 6, `twelve different typed seeds gave only ${texts.size} different texts`);
});

test('seed: every typed seed gives its own text', () => {
  // The text has about ten choices after every word, so a different stream that is a
  // real one writes different words; only a seed that is ignored in part writes the same.
  const typed = MANY_SEEDS.map(String);
  const extra = ['0', '1', '8', ' 65537 ', '65537'];
  const kinds = ['gen'];
  const opts = { temperature: 1, topK: 0, topP: 1, length: 24 };
  const [runs] = run('generated', [{
    text: branchyText(), order: 2,
    runs: [...typed, ...typed.slice(0, 8), ...extra].map((t) => ({ prompt: 'amber', opts, typedSeed: t, kinds })),
  }]);
  const textOf = (i) => runs[i].gen.join(' ');
  typed.slice(0, 8).forEach((t, i) => assert.equal(textOf(i), textOf(typed.length + i), `seed "${t}" twice`));
  const dup = collisions(typed, (t) => textOf(typed.indexOf(t)));
  assert.deepEqual(dup, [], `these typed seeds wrote the same text: ${dup.join(' ')}`);
  const base = typed.length + 8;
  assert.notEqual(textOf(base), textOf(base + 1), 'seed 0 is not seed 1');
  assert.notEqual(textOf(base + 1), textOf(base + 2), 'seed 1 is not seed 8');
  assert.equal(textOf(base + 3), textOf(base + 4));
});

test('seed: a seed from newSeed works with the generator', () => {
  const got = run('newSeedsDrive', { rngSeed: 2024, count: 8, prompt: 'the', opts: { temperature: 1.5, length: 20 } });
  assert.equal(got.length, 8);
  for (const { seed, parsed, a, b } of got) {
    assert.equal(parsed, seed, `seed ${seed} is read back as ${parsed}`);
    assert.deepEqual(a, b, `seed ${seed} twice`);
    assert.equal(a.length, 20);
  }
  const texts = new Set(got.map((g) => g.a.join(' ')));
  assert.ok(texts.size >= 4, `eight new seeds gave only ${texts.size} different texts`);
});

test('seed: parseSeed accepts zero-padded digits of any length', () => {
  const got = parseAll('00000000007', `${'0'.repeat(40)}42`, '0'.repeat(30), ' 000000000000123  ', '0004294967295', '0004294967296');
  assert.equal(got[0], 7, 'eleven characters, value 7');
  assert.equal(got[1], 42);
  assert.equal(got[2], 0);
  assert.equal(got[3], 123);
  assert.equal(got[4], 4294967295, 'the value is what is capped, not the number of characters');
  assert.equal(got[5], null);
});
