import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FIXTURE, close, run, sum, tokenizeAll, tokens } from './helpers.mjs';

// FIXTURE tokens: the cat sat . the cat ran . the dog sat . a cat sat !  (16 tokens)

// One distribution: nextDistribution(train(text, order), context), asked beside the workspace.
const ask = (jobs) => run('dists', jobs).map((r) => r.dist);

test('model: tokenize follows the documented rule', () => {
  const [a, b, c, d] = tokenizeAll('The cat, sat.', "Don't STOP!  Now; 42 times?", 'a -- "b" (c)', '');
  assert.deepEqual(a, ['the', 'cat', ',', 'sat', '.']);
  assert.deepEqual(b, ["don't", 'stop', '!', 'now', ';', '42', 'times', '?']);
  assert.deepEqual(c, ['a', 'b', 'c']);
  assert.deepEqual(d, []);
});

test('model: underscores and non-ASCII letters separate tokens', () => {
  const got = tokenizeAll('snake_case naive-with-accent', '__a__b_', 'x_1 y_2', 'café au lait', 'naïve',
    'Über straße', 'a٣b 世界 c', 'it’s don\'t');
  assert.deepEqual(got[0], ['snake', 'case', 'naive', 'with', 'accent']);
  assert.deepEqual(got[1], ['a', 'b']);
  assert.deepEqual(got[2], ['x', '1', 'y', '2']);
  assert.deepEqual(got[3], ['caf', 'au', 'lait']);
  assert.deepEqual(got[4], ['na', 've']);
  assert.deepEqual(got[5], ['ber', 'stra', 'e']);
  assert.deepEqual(got[6], ['a', 'b', 'c'], 'non-ASCII digits and letters are dropped too');
  assert.deepEqual(got[7], ['it', 's', "don't"], 'a curly apostrophe is not an apostrophe');
});

test('model: one-word context gives counted probabilities', () => {
  const [d] = ask([{ text: FIXTURE, order: 3, context: ['the'] }]);
  assert.deepEqual(tokens(d.entries), ['cat', 'dog']);
  close(d.entries[0].p, 2 / 3, 1e-12, 'p(cat | the)');
  close(d.entries[1].p, 1 / 3, 1e-12, 'p(dog | the)');
  assert.deepEqual(d.usedContext, ['the']);
});

test('model: the longest seen context wins, ties sorted by token', () => {
  const [d, longer] = ask([
    { text: FIXTURE, order: 3, context: ['the', 'cat'] },
    { text: FIXTURE, order: 3, context: ['dog', 'a', 'cat'] },
  ]);
  assert.deepEqual(d.usedContext, ['the', 'cat']);
  assert.deepEqual(tokens(d.entries), ['ran', 'sat']);
  close(d.entries[0].p, 0.5, 1e-12, 'p(ran | the cat)');
  assert.deepEqual(longer.usedContext, ['a', 'cat'], 'only the last order-1 tokens are used');
  assert.deepEqual(tokens(longer.entries), ['sat']);
});

test('model: string context is tokenized (case-insensitive)', () => {
  const [d] = ask([{ text: FIXTURE, order: 3, context: 'THE  Cat' }]);
  assert.deepEqual(d.usedContext, ['the', 'cat']);
  assert.deepEqual(tokens(d.entries), ['ran', 'sat']);
});

test('model: unseen long context backs off to the shorter suffix', () => {
  const [d] = ask([{ text: FIXTURE, order: 3, context: ['dog', 'cat'] }]);
  assert.deepEqual(d.usedContext, ['cat']);
  assert.deepEqual(tokens(d.entries), ['sat', 'ran']);
  close(d.entries[0].p, 2 / 3, 1e-12, 'p(sat | cat)');
});

test('model: unknown word backs off to word frequency, ties by token', () => {
  const contexts = [['zebra'], ['the', 'zebra'], [], ''];
  const got = ask(contexts.map((context) => ({ text: FIXTURE, order: 3, context })));
  contexts.forEach((ctx, i) => {
    const d = got[i];
    assert.deepEqual(d.usedContext, [], `context ${JSON.stringify(ctx)}`);
    assert.deepEqual(tokens(d.entries), ['.', 'cat', 'sat', 'the', '!', 'a', 'dog', 'ran']);
    close(d.entries[0].p, 3 / 16, 1e-12, 'p(.)');
    close(d.entries[7].p, 1 / 16, 1e-12, 'p(ran)');
    close(sum(d.entries), 1, 1e-9, 'sum');
  });
});

test('model: a context never followed by anything backs off', () => {
  // "!" is the last token of the fixture: it was seen, but nothing followed it.
  const [d] = ask([{ text: FIXTURE, order: 3, context: ['sat', '!'] }]);
  assert.deepEqual(d.usedContext, []);
  assert.equal(d.entries.length, 8);
});

test('model: order sets how much context is used', () => {
  const [bigram, unigram, empty] = ask([
    { text: FIXTURE, order: 2, context: ['the', 'cat'] },
    { text: FIXTURE, order: 1, context: ['the', 'cat'] },
    { text: '', order: 3, context: ['anything'] },
  ]);
  assert.deepEqual(bigram.usedContext, ['cat']);
  assert.deepEqual(tokens(bigram.entries), ['sat', 'ran']);
  assert.deepEqual(unigram.usedContext, []);
  assert.equal(unigram.entries.length, 8);
  assert.deepEqual(empty.entries, [], 'an empty model gives an empty list, not an error');
});

test('model: embedded corpus is small, original-sized and trains', () => {
  const s = run('story');
  assert.equal(s.type, 'string');
  assert.ok(s.length <= 20000, `corpus is ${s.length} chars; keep it under 20000`);
  assert.ok(s.tokenCount >= 200, `corpus has ${s.tokenCount} tokens; need at least 200`);
  assert.ok(s.afterThe.entries.length >= 2, 'the default model should know more than one word after "the"');
  close(sum(s.afterThe.entries), 1, 1e-9, 'sum');
});

test('model: ties between punctuation and digits use code-unit order', () => {
  // After "b", each of these follows exactly once. Code-unit (`<`) order is
  // ! , . 0 : ; ? z; a locale-aware compare would put , ; : ! ? . first.
  const [d, three] = ask([
    { text: 'a b ! a b . a b : a b ? a b , a b ; a b 0 a b z', order: 3, context: ['b'] },
    { text: 'a b ! a b . a b :', order: 2, context: 'b' },
  ]);
  assert.deepEqual(d.usedContext, ['b']);
  assert.deepEqual(tokens(d.entries), ['!', ',', '.', '0', ':', ';', '?', 'z']);
  assert.deepEqual(tokens(three.entries), ['!', '.', ':']);
});

test('model: apostrophes stay in a token wherever they sit', () => {
  const got = tokenizeAll("'tis the dogs' bone", "rock 'n' roll", "don't 'em ''quoted''", "a ' b", "dogs'. it's");
  assert.deepEqual(got[0], ["'tis", 'the', "dogs'", 'bone']);
  assert.deepEqual(got[1], ['rock', "'n'", 'roll']);
  assert.deepEqual(got[2], ["don't", "'em", "''quoted''"]);
  assert.deepEqual(got[3], ['a', "'", 'b'], 'a lone apostrophe is a run of apostrophes, so a token');
  assert.deepEqual(got[4], ["dogs'", '.', "it's"]);
});

// The 5-token context below is followed by "six" every time it appears whole, but a
// shorter ending is also followed by "seven" once, so each context length gives its own answer.
const LONG = 'one two three four five six . one two three four five six . zero two three four five seven .';
const LONG_CTX = ['one', 'two', 'three', 'four', 'five'];

test('model: train with no order argument uses order 3', () => {
  const [viaDefault, explicit, cat] = ask([
    { text: LONG, context: LONG_CTX },
    { text: LONG, order: 3, context: LONG_CTX },
    { text: FIXTURE, context: ['the', 'cat'] },
  ]);
  assert.deepEqual(viaDefault.usedContext, ['four', 'five'], 'order 3 uses up to two previous tokens');
  assert.deepEqual(viaDefault, explicit, 'train(text) is train(text, 3)');
  assert.deepEqual(cat.usedContext, ['the', 'cat']);
  assert.deepEqual(tokens(cat.entries), ['ran', 'sat']);
});

test('model: order n uses up to n-1 previous tokens, for any n', () => {
  const orders = [1, 2, 3, 4, 5, 6, 7, 8];
  const got = ask(orders.map((order) => ({ text: LONG, order, context: LONG_CTX })));
  orders.forEach((order, i) => {
    const d = got[i];
    const want = order === 1 ? [] : LONG_CTX.slice(Math.max(0, LONG_CTX.length - (order - 1)));
    assert.deepEqual(d.usedContext, want, `order ${order} should use ${want.length} previous tokens`);
    if (order >= 2 && order <= 5) {
      assert.deepEqual(tokens(d.entries), ['six', 'seven'], `order ${order}`);
      close(d.entries[0].p, 2 / 3, 1e-12, `order ${order} p(six)`);
    }
    if (order >= 6) {
      assert.deepEqual(d.entries, [{ token: 'six', p: 1 }], `order ${order}: the whole five-token context was always followed by "six"`);
    }
  });
});

test('model: letters and digits in one run stay one token', () => {
  const got = tokenizeAll("b2b2 4th 90's", 'R2D2 x1y2z3 7UP', 'a1,b2');
  assert.deepEqual(got[0], ['b2b2', '4th', "90's"]);
  assert.deepEqual(got[1], ['r2d2', 'x1y2z3', '7up']);
  assert.deepEqual(got[2], ['a1', ',', 'b2'], 'a mark ends the run; the digits and letters either side stay whole');
});

test('model: each punctuation mark is a token of its own, even side by side', () => {
  const got = tokenizeAll('Wait... what?!', 'a,;:b', '!!', '..');
  assert.deepEqual(got[0], ['wait', '.', '.', '.', 'what', '?', '!']);
  assert.deepEqual(got[1], ['a', ',', ';', ':', 'b']);
  assert.deepEqual(got[2], ['!', '!']);
  assert.deepEqual(got[3], ['.', '.']);
});

test('model: counting runs straight across sentence ends', () => {
  // FIXTURE: "... sat . the cat ran . the dog sat . a cat sat !" -- the token after "." is "the" twice and "a" once.
  // A sentence end at the start, the middle and the end of a context, for . ! and ?,
  // at order 3 (two tokens of context) and order 4 (three).
  const text = 'a b . c d ! e f ? g h';
  const cases = [
    [3, ['.'], 'c'], [3, ['b', '.'], 'c'], [3, ['.', 'c'], 'd'],
    [3, ['!'], 'e'], [3, ['d', '!'], 'e'], [3, ['!', 'e'], 'f'],
    [3, ['?'], 'g'], [3, ['f', '?'], 'g'], [3, ['?', 'g'], 'h'],
    [4, ['b', '.', 'c'], 'd'], [4, ['.', 'c', 'd'], '!'], [4, ['d', '!', 'e'], 'f'],
    [4, ['!', 'e', 'f'], '?'], [4, ['e', 'f', '?'], 'g'],
  ];
  const got = ask([
    { text: FIXTURE, order: 3, context: ['.'] },
    { text: FIXTURE, order: 3, context: ['.', 'the'] },
    ...cases.map(([order, context]) => ({ text, order, context })),
  ]);
  const [dot, dotThe, ...rest] = got;
  assert.deepEqual(dot.usedContext, ['.']);
  assert.deepEqual(tokens(dot.entries), ['the', 'a']);
  close(dot.entries[0].p, 2 / 3, 1e-12, 'p(the | .)');
  close(dot.entries[1].p, 1 / 3, 1e-12, 'p(a | .)');
  assert.deepEqual(dotThe.usedContext, ['.', 'the'], 'a context may start with a sentence end');
  assert.deepEqual(tokens(dotThe.entries), ['cat', 'dog']);
  cases.forEach(([order, ctx, next], i) => {
    const d = rest[i];
    assert.deepEqual(d.usedContext, ctx, `order ${order}: context ${JSON.stringify(ctx)} was followed by "${next}" in the text and must be used whole`);
    assert.deepEqual(d.entries, [{ token: next, p: 1 }], `order ${order}: context ${JSON.stringify(ctx)}`);
  });
});

test('model: a string context is tokenized by the same rule as tokenize', () => {
  const texts = ['the "cat"', 'the--cat', 'THE\tCat\n', '(the) [cat]', 'the_cat', 'The cat sat. The', 'the cat’s', 'the cat ran...', '  ', 'sat !', 'cat;sat', 'the cat sat. the cat'];
  const got = run('dists', [
    { text: FIXTURE, order: 3, context: 'The dog sat.' },
    { text: FIXTURE, order: 3, context: 'cat,sat' },
    ...texts.map((context) => ({ text: FIXTURE, order: 3, context, alsoTokenized: true })),
    { text: FIXTURE, order: 3, context: '"the" -- CAT' },
    { text: FIXTURE, order: 3, context: 'the_cat' },
  ]);
  const [dog, comma] = got.map((r) => r.dist);
  // Punctuation, commas and other separators inside a string context are split off, not kept in the word.
  assert.deepEqual(dog.usedContext, ['sat', '.'], '"sat." is the two tokens sat and .');
  assert.deepEqual(dog.entries, [{ token: 'a', p: 0.5 }, { token: 'the', p: 0.5 }]);
  assert.deepEqual(comma.usedContext, ['sat'], '"cat,sat" is cat , sat; ", sat" was never seen, so it backs off to sat');
  assert.deepEqual(tokens(comma.entries), ['.', '!']);
  texts.forEach((text, i) => {
    const { dist, viaTokens } = got[2 + i];
    assert.deepEqual(dist, viaTokens, `string context ${JSON.stringify(text)} must give the same answer as tokenize(text)`);
  });
  assert.deepEqual(got[2 + texts.length].dist.usedContext, ['the', 'cat']);
  assert.deepEqual(got[3 + texts.length].dist.usedContext, ['the', 'cat'], 'an underscore separates tokens in a context too');
});
