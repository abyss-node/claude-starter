import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FIXTURE, MANY_SEEDS, close, collisions, entries, run, sum, tokens } from './helpers.mjs';

const TEMPS = [0, 1e-9, 1e-3, 0.1, 0.5, 0.7, 1, 1.5, 2, 10, 1000];
const KS = [0, 1, 2, 3, 5, 100];
const PS = [0.01, 0.2, 0.5, 0.75, 0.9, 0.999, 1];

// applySettings on each list under one setting each: [{ before, after, out }].
const apply = (jobs) => run('applied', jobs);
const kept = (list, settings) => apply([{ entries: list, settings }])[0].out;

test('sampling: kept distribution sums to 1 within 1e-9 for any settings', () => {
  const lists = [
    { entries: entries({ a: 0.5, b: 0.3, c: 0.2 }) },
    { entries: entries({ x: 1 }) },
    { entries: entries({ p: 0.25, q: 0.25, r: 0.25, s: 0.25 }) },
    { entries: entries({ big: 0.999999, tiny: 1e-6 }) },
    { entries: entries({ u: 3, v: 1, w: 0 }) }, // unnormalised, with a zero
    { entries: entries({ b: 0.2, a: 0.8 }) }, // not in sort order: an in-place sort changes it
    { entries: entries({ c: 0.1, a: 0.6, b: 0.3 }) },
    { entries: entries({ z: 0.25, y: 0.25, x: 0.25, w: 0.25 }) }, // all tied, reverse token order
    { corpusContext: 'the' },
    { corpusContext: 'zebra' },
  ];
  const grids = run('appliedGrid', lists.map((l) => ({ ...l, temperature: TEMPS, topK: KS, topP: PS })));
  grids.forEach((g, n) => {
    for (const { temperature, topK, topP, out } of g.cells) {
      const tag = `T=${temperature} k=${topK} p=${topP} on ${g.before.length} entries (list ${n})`;
      assert.ok(Array.isArray(out) && out.length >= 1, `${tag}: kept nothing`);
      for (const e of out) assert.ok(Number.isFinite(e.p) && e.p >= 0, `${tag}: bad p ${e.p}`);
      close(sum(out), 1, 1e-9, tag);
    }
    assert.deepEqual(g.after, g.before, 'applySettings must not change its input');
  });
  const emptySettings = [{}, { temperature: 0 }, { temperature: -1 }, { temperature: 2 }, { topK: 3 }, { topP: 0 }, { temperature: 0, topK: 1, topP: 0.5 }];
  const empties = apply(emptySettings.map((settings) => ({ entries: [], settings })));
  emptySettings.forEach((settings, i) => {
    assert.deepEqual(empties[i].out, [], `an empty list stays empty under ${JSON.stringify(settings)}`);
  });
});

test('sampling: applySettings returns a new list, never the caller\'s own array', () => {
  // Sorted, positive, summing to 1: the case where handing the input straight back would be tempting.
  const d = entries({ a: 0.5, b: 0.3, c: 0.2 });
  const settingsList = [undefined, {}, { temperature: 1, topK: 0, topP: 1 }, { topK: 3 }, { topK: 100 }, { topP: 1 }, { temperature: 1, topP: 1 }];
  const one = entries({ x: 1 });
  const got = apply([
    ...settingsList.map((settings) => ({ entries: d, settings, mutateResult: true })),
    { entries: one, noSettings: true, mutateResult: true },
  ]);
  settingsList.forEach((settings, i) => {
    assert.deepEqual(tokens(got[i].out), ['a', 'b', 'c']);
    assert.deepEqual(got[i].after, d, `${JSON.stringify(settings)}: changing the result must not change the input`);
  });
  assert.deepEqual(got[settingsList.length].after, one, 'one entry: changing the result must not change the input');
});

test('sampling: temperature 1 and defaults leave the distribution unchanged', () => {
  const d = entries({ a: 0.5, b: 0.3, c: 0.2 });
  const got = apply([{ entries: d, settings: { temperature: 1, topK: 0, topP: 1 } }, { entries: d, noSettings: true }]);
  for (const { out } of got) {
    assert.deepEqual(tokens(out), ['a', 'b', 'c']);
    out.forEach((e, i) => close(e.p, d[i].p, 1e-12, e.token));
  }
});

test('sampling: temperature reshapes as p^(1/T), normalised', () => {
  const d = entries({ a: 0.5, b: 0.3, c: 0.2 });
  // Low (0.05 to 0.2), high (10, 1000) and in-between temperatures all follow the same formula: none is
  // clamped, and none collapses to the first entry.
  const temps = [0.05, 0.1, 0.2, 0.3, 0.5, 0.9, 1.1, 2, 3, 10, 50, 1000];
  const got = apply(temps.map((temperature) => ({ entries: d, settings: { temperature } })));
  temps.forEach((T, n) => {
    const w = d.map((e) => e.p ** (1 / T));
    const z = w.reduce((s, x) => s + x, 0);
    const { out } = got[n];
    assert.deepEqual(tokens(out), ['a', 'b', 'c'], `T=${T} keeps all three`);
    out.forEach((e, i) => close(e.p, w[i] / z, 1e-12, `T=${T} ${e.token}`));
  });
});

test('sampling: temperature 0 picks the argmax (ties: first token)', () => {
  const got = apply([
    { entries: entries({ b: 0.3, a: 0.5, c: 0.2 }), settings: { temperature: 0 } },
    { entries: entries({ zed: 0.4, mid: 0.4, low: 0.2 }), settings: { temperature: 0 } },
    { entries: entries({ b: 0.3, a: 0.5, c: 0.2 }), settings: { temperature: 1e-6 } },
  ]);
  assert.deepEqual(got[0].out, [{ token: 'a', p: 1 }]);
  assert.deepEqual(got[1].out, [{ token: 'mid', p: 1 }]);
  const tiny = got[2].out;
  assert.equal(tiny[0].token, 'a');
  assert.ok(tiny[0].p >= 1 - 1e-9, `T=1e-6 should be all on the argmax, got ${tiny[0].p}`);
});

test('sampling: top-k keeps exactly k, ties at the cut broken by token', () => {
  const d = entries({ e: 0.1, a: 0.4, d: 0.2, b: 0.2, c: 0.1 });
  const punct = entries({ ':': 0.25, a: 0.25, '.': 0.25, '!': 0.25 });
  const ks = [1, 2, 4, 5, 50, 0];
  const got = apply([...ks.map((topK) => ({ entries: d, settings: { topK } })), { entries: punct, settings: { topK: 2 } }]);
  assert.deepEqual(tokens(got[0].out), ['a']);
  assert.deepEqual(tokens(got[1].out), ['a', 'b'], 'b and d tie; b sorts first');
  assert.deepEqual(tokens(got[2].out), ['a', 'b', 'd', 'c']);
  assert.equal(got[3].out.length, 5);
  assert.equal(got[4].out.length, 5, 'k above the vocabulary keeps all');
  assert.equal(got[5].out.length, 5, 'k = 0 means off');
  close(got[1].out[0].p, 2 / 3, 1e-12, 'renormalised p(a)');
  assert.deepEqual(tokens(got[6].out), ['!', '.'], 'ties by code unit: ! . : a');
});

test('sampling: top-p keeps the smallest set reaching p', () => {
  const d = entries({ c: 0.2, a: 0.5, b: 0.3 });
  const flat = entries({ d: 0.25, c: 0.25, b: 0.25, a: 0.25 });
  const ps = [0.5, 0.51, 0.8, 0.81, 0.01, 1];
  const got = apply([...ps.map((topP) => ({ entries: d, settings: { topP } })), { entries: flat, settings: { topP: 0.5 } }]);
  assert.deepEqual(tokens(got[0].out), ['a'], 'exactly reaching p is enough');
  assert.deepEqual(tokens(got[1].out), ['a', 'b']);
  assert.deepEqual(tokens(got[2].out), ['a', 'b']);
  assert.deepEqual(tokens(got[3].out), ['a', 'b', 'c']);
  assert.deepEqual(tokens(got[4].out), ['a'], 'always keeps at least one');
  assert.equal(got[5].out.length, 3);
  assert.deepEqual(tokens(got[6].out), ['a', 'b']);
  close(got[1].out[0].p, 0.625, 1e-12, 'renormalised p(a)');
});

test('sampling: order is temperature, top-k, then top-p on the renormalised result', () => {
  const d = entries({ a: 0.4, b: 0.3, c: 0.2, d: 0.1 });
  const got = apply([
    { entries: d, settings: { topK: 2, topP: 0.5 } },
    { entries: d, settings: { temperature: 2, topP: 0.6 } },
    { entries: d, settings: { temperature: 2, topP: 0.65 } },
  ]);
  // After top-k 2: a = 4/7 (0.571), which alone reaches p = 0.5.
  assert.deepEqual(tokens(got[0].out), ['a']);
  // T = 2 flattens to a ~0.3254 b ~0.2818 c ~0.2301 d ~0.1627 (sqrt weights).
  // Untempered, a + b = 0.7 reaches 0.65; tempered, a + b ~0.607 does not, so three are kept.
  assert.deepEqual(tokens(got[1].out), ['a', 'b']);
  assert.deepEqual(tokens(got[2].out), ['a', 'b', 'c']);
});

test('sampling: seeded generator is repeatable and in [0, 1)', () => {
  const seeds = [0, 1, 42, 2 ** 31 - 1];
  const got = run('rngs', [...seeds.map((seed) => ({ seed, draws: 1000, twin: true })), { seed: 1, draws: 3 }, { seed: 2, draws: 3 }]);
  seeds.forEach((seed, n) => {
    const { a, b } = got[n];
    assert.equal(a.length, 1000);
    a.forEach((x, i) => {
      assert.equal(x, b[i], `seed ${seed} draw ${i}`);
      assert.ok(typeof x === 'number' && x >= 0 && x < 1, `seed ${seed} draw ${i} out of range: ${x}`);
    });
  });
  assert.notDeepEqual(got[seeds.length].a, got[seeds.length + 1].a, 'different seeds should give different streams');
});

test('sampling: top-p counts a running total within 1e-12 of p as reaching it', () => {
  // In floating point 0.3 + 0.3 + 0.3 is 0.8999999999999999 and 0.7 + 0.1 + 0.1 is
  // 0.8999999999999999 too: three entries reach 0.9, and the fourth must not be kept.
  const d = entries({ a: 0.5, b: 0.3, c: 0.2 });
  const got = apply([
    { entries: entries({ a: 3, b: 3, c: 3, d: 1 }), settings: { topP: 0.9 } },
    { entries: entries({ a: 0.7, b: 0.1, c: 0.1, d: 0.1 }), settings: { topP: 0.9 } },
    { entries: entries({ d: 1, c: 3, b: 3, a: 3 }), settings: { topP: 0.9 } },
    { entries: d, settings: { topP: 0.500001 } },
    { entries: d, settings: { topP: 0.800001 } },
  ]);
  assert.deepEqual(tokens(got[0].out), ['a', 'b', 'c']);
  assert.deepEqual(tokens(got[1].out), ['a', 'b', 'c']);
  assert.deepEqual(tokens(got[2].out), ['a', 'b', 'c'], 'input order does not matter');
  // A total that is clearly short of p does not count.
  assert.deepEqual(tokens(got[3].out), ['a', 'b']);
  assert.deepEqual(tokens(got[4].out), ['a', 'b', 'c']);
});

test('sampling: entries with p of 0 or less are dropped first', () => {
  const d = entries({ u: 3, v: 1, w: 0, x: -2 });
  const settingsList = [{ temperature: 2 }, { temperature: 0.5 }, { topK: 3 }, { topK: 4 }, { topP: 0.99 }, { temperature: 1.5, topK: 3, topP: 0.999 }];
  const got = apply([
    { entries: d, noSettings: true },
    ...settingsList.map((settings) => ({ entries: d, settings })),
    { entries: entries({ z: 0, y: 0, m: 0.4, n: 0.6 }), settings: { topK: 3 } },
  ]);
  const plain = got[0].out;
  assert.deepEqual(tokens(plain), ['u', 'v']);
  close(plain[0].p, 0.75, 1e-12, 'p(u)');
  close(plain[1].p, 0.25, 1e-12, 'p(v)');
  settingsList.forEach((s, i) => {
    const { out } = got[1 + i];
    assert.deepEqual(tokens(out), ['u', 'v'], `${JSON.stringify(s)}: a zero or negative entry must never survive`);
    close(sum(out), 1, 1e-9, JSON.stringify(s));
  });
  assert.deepEqual(tokens(got[1 + settingsList.length].out), ['n', 'm']);
  assert.deepEqual(got[0].after, entries({ u: 3, v: 1, w: 0, x: -2 }), 'the input is untouched');
});

test('sampling: every seed is its own stream', () => {
  const got = run('rngs', MANY_SEEDS.map((seed) => ({ seed, draws: 20, twin: true })));
  const streamOf = (seed) => got[MANY_SEEDS.indexOf(seed)].a.slice(0, 4).join(',');
  const dup = collisions(MANY_SEEDS, streamOf);
  assert.deepEqual(dup, [], `these seeds start the same stream: ${dup.join(' ')}`);
  MANY_SEEDS.forEach((seed, n) => {
    got[n].a.forEach((x, i) => assert.equal(x, got[n].b[i], `seed ${seed} draw ${i} repeats`));
  });
});

test('sampling: sampleToken walks the cumulative sum in list order', () => {
  const d = entries({ a: 0.5, b: 0.3, c: 0.2 });
  const rs = [0, 0.49, 0.5, 0.79, 0.81, 0.9999999999];
  const got = run('sampled', [...rs.map((r) => ({ entries: d, r })), { entries: d, seed: 123, count: 20000 }]);
  assert.deepEqual(got.slice(0, rs.length).map((g) => g.tokens[0]), ['a', 'a', 'b', 'b', 'c', 'c']);
  const N = 20000;
  const { counts } = got[rs.length];
  close((counts.a ?? 0) / N, 0.5, 0.02, 'frequency of a');
  close((counts.b ?? 0) / N, 0.3, 0.02, 'frequency of b');
  close((counts.c ?? 0) / N, 0.2, 0.02, 'frequency of c');
});

test('sampling: sampleToken calls the generator exactly once per token', () => {
  const lists = [
    entries({ a: 0.5, b: 0.3, c: 0.2 }),
    entries({ only: 1 }), // a single entry still costs one draw
    entries({ a: 0.25, b: 0.25, c: 0.25, d: 0.25 }),
  ];
  const jobs = lists.flatMap((d) => [
    ...[0, 0.3, 0.999].map((r) => ({ entries: d, r })),
    { entries: d, r: 0.5, times: 10 },
  ]);
  const got = run('sampled', jobs);
  jobs.forEach((job, n) => {
    if (job.times) assert.equal(got[n].calls, 10, 'ten tokens should use ten draws');
    else assert.equal(got[n].calls, 1, `${job.entries.length} entries, r=${job.r}: rng called ${got[n].calls} times`);
  });
});

test('sampling: same seed and settings give the same sequence', () => {
  const settings = [
    { temperature: 1, topK: 0, topP: 1 },
    { temperature: 1.5, topK: 5, topP: 0.9 },
    { temperature: 0.7, topK: 0, topP: 0.6 },
  ];
  const calls = [];
  for (const s of settings) for (const seed of [1, 7, 99]) calls.push({ ...s, seed, length: 25 });
  const varied = Array.from({ length: 10 }, (_, i) => ({ temperature: 1.5, seed: i + 1, length: 15 }));
  const make = (opts) => ({ prompt: 'the', opts, kinds: ['gen'] });
  const [first, second, many] = run('generated', [
    { corpus: true, runs: calls.map(make) },
    { corpus: true, runs: calls.map(make) },
    { corpus: true, runs: varied.map(make) },
  ]);
  calls.forEach((opts, i) => {
    assert.deepEqual(first[i].gen, second[i].gen, `seed ${opts.seed} ${JSON.stringify(opts)}`);
    assert.equal(first[i].gen.length, 25);
  });
  const outs = new Set(many.map((r) => r.gen.join(' ')));
  assert.ok(outs.size >= 2, 'ten different seeds all produced the same text: is the seed used?');
});

test('sampling: temperature 0 generates the greedy chain', () => {
  const combos = [[FIXTURE, 'the', false], ['', 'the', true], ['', 'zebra', true]];
  const specs = combos.map(([text, prompt, corpus]) => ({
    ...(corpus ? { corpus: true } : { text }),
    runs: [
      { prompt, kinds: ['greedy'], greedyLength: 12 },
      ...[1, 2, 3].map((seed) => ({ prompt, opts: { temperature: 0, seed, length: 12 }, kinds: ['gen'] })),
    ],
  }));
  const got = run('generated', specs);
  combos.forEach(([, prompt], n) => {
    const [{ greedy }, ...gens] = got[n];
    gens.forEach((g, i) => assert.deepEqual(g.gen, greedy, `prompt "${prompt}" seed ${i + 1}`));
  });
});

test('sampling: unknown prompt still generates known words', () => {
  const [[withVocab], [empty]] = run('generated', [
    { corpus: true, runs: [{ prompt: 'qwzx vvvv ???', opts: { seed: 5, length: 20 }, kinds: ['gen', 'vocab'] }] },
    { text: '', runs: [{ prompt: 'anything', opts: { seed: 1, length: 5 }, kinds: ['gen'] }] },
  ]);
  const vocab = new Set(withVocab.vocab);
  assert.equal(withVocab.gen.length, 20);
  for (const t of withVocab.gen) assert.ok(vocab.has(t), `"${t}" is not in the corpus`);
  assert.deepEqual(empty.gen, [], 'empty model: no tokens, no error');
});

test('sampling: generate draws every token from one seeded generator', () => {
  const settings = [
    { temperature: 1, topK: 0, topP: 1 },
    { temperature: 1.5, topK: 0, topP: 1 },
    { temperature: 2, topK: 4, topP: 0.9 },
    { temperature: 0.8, topK: 0, topP: 0.7 },
  ];
  const calls = [];
  for (const s of settings) for (const seed of [1, 7, 99, 2024]) calls.push({ ...s, seed, length: 30 });
  const [runs] = run('generated', [{ corpus: true, runs: calls.map((opts) => ({ prompt: 'the', opts, kinds: ['gen', 'hand'] })) }]);
  calls.forEach((opts, i) => {
    assert.deepEqual(
      runs[i].gen,
      runs[i].hand,
      `seed ${opts.seed} ${JSON.stringify({ ...opts, seed: undefined, length: undefined })}: generate should step one createRng(seed) through sampleToken, one draw per token`,
    );
  });
});

test('sampling: generate applies top-k and top-p at every step', () => {
  const temps = [0.5, 1, 1.5, 3];
  const seeds = [1, 2, 3, 4, 5];
  const runs = [{ prompt: 'the', kinds: ['greedy'], greedyLength: 15 }];
  for (const temperature of temps) {
    for (const seed of seeds) {
      runs.push({ prompt: 'the', opts: { temperature, topK: 1, topP: 1, seed, length: 15 }, kinds: ['gen'] });
      runs.push({ prompt: 'the', opts: { temperature, topK: 0, topP: 0.01, seed, length: 15 }, kinds: ['gen'] });
    }
  }
  const top2Seeds = [1, 2, 3, 4, 5, 6, 7, 8];
  for (const seed of top2Seeds) runs.push({ prompt: 'the', opts: { temperature: 3, topK: 2, topP: 1, seed, length: 30 }, kinds: ['gen', 'top2'] });
  const [got] = run('generated', [{ corpus: true, runs }]);
  const greedy = got[0].greedy;
  let n = 1;
  for (const temperature of temps) {
    for (const seed of seeds) {
      assert.deepEqual(got[n++].gen, greedy, `top-k 1 at T=${temperature} seed ${seed} should be the greedy chain`);
      assert.deepEqual(got[n++].gen, greedy, `top-p 0.01 at T=${temperature} seed ${seed} should be the greedy chain`);
    }
  }
  for (const seed of top2Seeds) {
    const { gen, top2 } = got[n++];
    gen.forEach((t, i) => {
      assert.ok(top2[i].includes(t), `top-k 2 seed ${seed} step ${i}: "${t}" is not in the top 2 ${JSON.stringify(top2[i])}`);
    });
  }
});

test('sampling: a temperature below 0 keeps only the first entry, like 0', () => {
  const d = entries({ b: 0.3, a: 0.5, c: 0.2 });
  const temps = [-1, -0.5, -1e-9, -1000];
  const got = apply([
    ...temps.flatMap((temperature) => [
      { entries: d, settings: { temperature } },
      { entries: d, settings: { temperature, topK: 3, topP: 0.5 } },
    ]),
    { entries: entries({ zed: 0.4, mid: 0.4, low: 0.2 }), settings: { temperature: -2 } },
  ]);
  temps.forEach((temperature, i) => {
    assert.deepEqual(got[2 * i].out, [{ token: 'a', p: 1 }], `T=${temperature}`);
    assert.deepEqual(got[2 * i + 1].out, [{ token: 'a', p: 1 }], `T=${temperature} with top-k and top-p`);
  });
  assert.deepEqual(got[2 * temps.length].out, [{ token: 'mid', p: 1 }], 'on a tie the first in sort order');
});

test('sampling: top-p of 0 still keeps the first entry', () => {
  const d = entries({ c: 0.2, a: 0.5, b: 0.3 });
  const got = apply([
    { entries: d, settings: { topP: 0 } },
    { entries: d, settings: { topP: 0, topK: 2 } },
    { entries: d, settings: { topP: 0, temperature: 2 } },
    { entries: entries({ d: 0.25, c: 0.25, b: 0.25, a: 0.25 }), settings: { topP: 0 } },
  ]);
  assert.deepEqual(got[0].out, [{ token: 'a', p: 1 }]);
  assert.deepEqual(got[1].out, [{ token: 'a', p: 1 }]);
  assert.deepEqual(got[2].out, [{ token: 'a', p: 1 }]);
  assert.deepEqual(got[3].out, [{ token: 'a', p: 1 }], 'on a tie the first in sort order');
});

test('sampling: sampleToken returns the last token when rounding leaves none', () => {
  // Ten entries of 0.1 add up to 0.9999999999999999 in floating point, and a generator may
  // return 1 - 2**-53, the largest float below 1: no running total is above it.
  const tenths = Array.from({ length: 10 }, (_, i) => ({ token: `t${i}`, p: 0.1 }));
  const jobs = [
    { entries: tenths, r: 1 - 2 ** -53 },
    { entries: tenths, r: 0 },
    { entries: entries({ a: 0.3, b: 0.3 }), r: 0.9 },
    { entries: entries({ only: 0.5 }), r: 0.99 },
    // A list that sums to less than 1 is walked as it is: r is not scaled by the total.
    { entries: entries({ a: 0.3, b: 0.3 }), r: 0.4 },
    { entries: entries({ a: 0.3, b: 0.3 }), r: 0.2 },
    { entries: entries({ a: 0.25, b: 0.25 }), r: 0.3 },
    { entries: entries({ a: 0.25, b: 0.25 }), r: 0.24 },
    { entries: entries({ a: 0.25, b: 0.25, c: 0.25 }), r: 0.74 },
  ];
  const want = ['t9', 't0', 'b', 'only', 'b', 'a', 'b', 'a', 'c'];
  const got = run('sampled', jobs);
  jobs.forEach((job, i) => assert.equal(got[i].tokens[0], want[i], `r=${job.r} on ${job.entries.length} entries`));
});

test('sampling: sampleToken walks the list in the order it is given', () => {
  const ascending = [{ token: 'b', p: 0.2 }, { token: 'a', p: 0.8 }];
  const tied = [{ token: 'z', p: 0.5 }, { token: 'a', p: 0.5 }];
  const jobs = [
    { entries: ascending, r: 0.1 }, { entries: ascending, r: 0.19 }, { entries: ascending, r: 0.2 }, { entries: ascending, r: 0.9 },
    { entries: tied, r: 0.25 }, { entries: tied, r: 0.75 },
  ];
  const got = run('sampled', jobs).map((g) => g.tokens[0]);
  assert.equal(got[0], 'b', 'the first entry owns the first 0.2');
  assert.equal(got[1], 'b');
  assert.equal(got[2], 'a');
  assert.equal(got[3], 'a');
  assert.equal(got[4], 'z', 'no re-sorting by token either');
  assert.equal(got[5], 'a');
});

test('sampling: generate defaults to length 10, seed 1 and the applySettings defaults', () => {
  const explicit = { length: 10, seed: 1, temperature: 1, topK: 0, topP: 1 };
  const runs = [
    { opts: { seed: 3 } }, { opts: {} }, { opts: explicit }, { opts: {} }, // 0..3
    { opts: { length: 15 } }, { opts: { length: 15, seed: 1 } }, // 4, 5
  ];
  const seeds = [1, 2, 3, 4, 5, 6];
  for (const seed of seeds) {
    runs.push({ opts: { ...explicit, seed, length: 20 } });
    runs.push({ opts: { seed, length: 20 } });
    runs.push({ opts: { seed, length: 20, temperature: undefined, topK: undefined, topP: undefined } });
  }
  const tail = runs.length;
  runs.push({ opts: { seed: 1, length: 20 } }, { opts: { seed: 1, length: 20, temperature: 0 } });
  runs.push({ opts: { seed: 2, length: 20, temperature: -1 } }, { opts: { seed: 2, length: 20, temperature: 0 } });
  const [got] = run('generated', [{ corpus: true, runs: runs.map((r) => ({ prompt: 'the', kinds: ['gen'], ...r })) }]);
  const g = (i) => got[i].gen;
  assert.equal(g(0).length, 10, 'length defaults to 10');
  assert.equal(g(1).length, 10);
  assert.deepEqual(g(1), g(2), 'no options is length 10, seed 1, temperature 1, top-k 0, top-p 1');
  assert.deepEqual(g(1), g(3), 'the default seed is a fixed number, not a random one');
  assert.deepEqual(g(4), g(5), 'the default seed is 1');
  seeds.forEach((seed, n) => {
    const long = g(6 + 3 * n);
    assert.deepEqual(g(7 + 3 * n), long, `seed ${seed}: temperature, top-k and top-p default to 1, 0 and 1`);
    assert.deepEqual(g(8 + 3 * n), long, `seed ${seed}: undefined settings use the defaults`);
  });
  assert.notDeepEqual(g(tail), g(tail + 1), 'the default temperature is not 0');
  assert.deepEqual(g(tail + 2), g(tail + 3), 'a negative temperature generates the greedy chain too');
});

test('sampling: top-p of 1 keeps every entry, even ones too small to matter', () => {
  // The 1e-12 tolerance is for reaching a p below 1; p = 1 is "off", so a tail of 1e-13 stays.
  const d = entries({ a: 1, b: 1e-13, c: 1e-14 });
  const got = apply([
    { entries: d, settings: { topP: 1 } },
    { entries: d, noSettings: true },
    { entries: d, settings: { temperature: 1, topK: 0, topP: 1 } },
    { entries: entries({ a: 0.5, b: 0.5 }), settings: { topP: 1 } },
  ]);
  assert.deepEqual(tokens(got[0].out), ['a', 'b', 'c']);
  assert.deepEqual(tokens(got[1].out), ['a', 'b', 'c']);
  assert.deepEqual(tokens(got[2].out), ['a', 'b', 'c']);
  assert.deepEqual(tokens(got[3].out), ['a', 'b']);
});
