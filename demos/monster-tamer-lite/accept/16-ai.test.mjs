import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted } from './helpers.mjs';
import { MV, SW } from './fixtures.mjs';
import { EQUAL_SEEDS, AI_SEEDS } from './scenario-16.mjs';

const J = (v) => JSON.stringify(v);

test('Graded 16: The computer opponent', () => {
  const o = observe('./scenario-16.mjs');

  // Legal, pure and repeatable at every state of many random battles.
  let checked = 0;
  let replaceSeen = 0;
  let nullSeen = 0;
  assert.ok(Array.isArray(o.positions), 'no positions were reported');
  for (const p of o.positions) {
    assert.equal(p.after, p.before, 'chooseAction changed the battle (its random state included)');
    if (p.legal.length === 0) { assert.equal(p.a, null, `no legal action: chooseAction must return null (phase ${p.phase})`); nullSeen++; continue; }
    assert.ok(p.a && p.legal.some((x) => J(x) === J(p.a)), `seed ${p.seed}: ${J(p.a)} is not among ${J(p.legal)}`);
    assert.notEqual(p.a.kind, 'snare', 'the computer never snares');
    if (p.phase === 'replace') { assert.equal(p.a.kind, 'switch'); replaceSeen++; }
    assert.equal(p.again, J(p.a), 'the same battle must give the same answer');
    assert.equal(p.ofCopy, J(p.a), 'a JSON copy of the battle must give the same answer');
    assert.equal(p.ofFresh, J(p.a));
    checked++;
  }
  for (const [a0, a1] of o.overAnswers) {
    assert.equal(a0, null);
    assert.equal(a1, null);
  }
  assert.ok(checked > 500, `only ${checked} positions were tried`);
  assert.ok(replaceSeen > 5, 'the tests should have reached replacement phases');
  assert.ok(nullSeen > 5);

  // Forced choices.
  assert.deepEqual(o.forced.only, MV(0));
  assert.equal(o.forced.phase, 'replace');
  assert.deepEqual(o.forced.notAsked, null, 'the side that does not have to replace has nothing to choose');
  assert.deepEqual(o.forced.replace, SW(1));

  // Equally good moves: the answer depends on the seed, but only on the seed.
  const answers = new Set();
  for (const { a, again, other } of counted(o.equal, EQUAL_SEEDS, 'battles of equal moves')) {
    assert.equal(again, a);
    assert.equal(other, a, 'two battles from the same config must get the same answer');
    answers.add(a);
  }
  assert.ok(answers.size >= 2, `across 80 seeds the computer always chose ${[...answers]}`);

  // Two battles asked in turn answer as each does alone (no memory between calls).
  const { solo, soloY, mixed } = o.turnAbout;
  counted(mixed, 4, 'answers asked in turn');
  assert.deepEqual([mixed[0], mixed[2]], solo);
  assert.deepEqual([mixed[1], mixed[3]], soloY);

  // A whole computer-against-computer battle finishes with legal choices, the same every time.
  const logs = new Set();
  counted(o.whole, AI_SEEDS, 'computer battles').forEach(([a, b], seed) => {
    for (const run of [a, b]) {
      assert.equal(run.phase, 'over', `seed ${seed}: the battle did not finish in 600 turns`);
      assert.ok(run.winner === 0 || run.winner === 1 || run.winner === -1);
    }
    assert.equal(b.log, a.log, `seed ${seed}: the same seed must give the same battle`);
    logs.add(a.log);
  });
  assert.ok(logs.size > 10);
});
