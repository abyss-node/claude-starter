import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted } from './helpers.mjs';
import { ofType } from './fixtures.mjs';
import { RUNS } from './scenario-07.mjs';

test('Graded 7: Accuracy and the draw order', () => {
  const o = observe('./scenario-07.mjs');
  const runs = (name) => counted(o[name], RUNS[name][0], `battles of the ${name} kind`);

  // Accuracy 100 and no status chance below 100: no draws, never a miss.
  for (const { states, log, rng } of runs('sure')) {
    assert.equal(rng, states[0], 'accuracy 100 and chance 100 take no draw');
    assert.equal(ofType(log, 'miss').length, 0);
    assert.equal(ofType(log, 'status').length, 2, 'chance 100 applies the status, one to each side');
  }

  // Accuracy 50 both sides: one draw each, in acting order; miss exactly when r*100 >= 50.
  runs('half').forEach(({ draws: [r1, r2], states, log, rng }, seed) => {
    const missed = ofType(log, 'miss').map((e) => e.side).sort();
    const want = [];
    if (r1 * 100 >= 50) want.push(0);
    if (r2 * 100 >= 50) want.push(1);
    assert.deepEqual(missed, want, `seed ${seed}: draws ${r1}, ${r2}`);
    const dmg = ofType(log, 'damage').map((e) => e.side).sort();
    const wantDmg = [];
    if (r1 * 100 < 50) wantDmg.push(1);
    if (r2 * 100 < 50) wantDmg.push(0);
    assert.deepEqual(dmg, wantDmg.sort(), `seed ${seed}: a hit does damage and a miss does none`);
    assert.equal(rng, states[2], `seed ${seed}: exactly two draws`);
  });

  // Accuracy then status chance: the status draw comes after the accuracy draw and only after a hit.
  runs('statusAfterHit').forEach(({ draws: [r1, r2], states, log, rng, foe }, seed) => {
    const hitIt = r1 * 100 < 70;
    const applied = hitIt && r2 * 100 < 40;
    assert.equal(ofType(log, 'status').length, applied ? 1 : 0, `seed ${seed}: draws ${r1}, ${hitIt ? r2 : null}`);
    assert.equal(ofType(log, 'skip').length, applied ? 1 : 0, `seed ${seed}: a dazed foe skips`);
    assert.equal(ofType(log, 'move').filter((e) => e.side === 1).length, applied ? 0 : 1);
    assert.equal(rng, states[hitIt ? 2 : 1], `seed ${seed}: ${hitIt ? 2 : 1} draws`);
    assert.equal(foe.status !== null, applied);
  });

  // No status draw when the foe faints (one draw only, for accuracy), and nothing is applied.
  runs('fells').forEach(({ draws: [r1], states, log, rng, foe }, seed) => {
    assert.equal(rng, states[1], `seed ${seed}: a foe that faints takes no status draw`);
    assert.equal(foe.status, null);
    if (r1 * 100 < 90) assert.equal(ofType(log, 'faint').length, 1, 'the hit should have felled the foe');
  });

  // A foe that already has a status takes no draw and keeps it.
  for (const { states, log, rng, foe } of runs('hasStatus')) {
    assert.equal(rng, states[0], 'a foe with a status takes no status draw');
    assert.equal(foe.status.kind, 'scorch');
    assert.equal(ofType(log, 'status').length, 0);
  }

  // A miss does no damage and applies nothing, even with status chance 100.
  const misses = runs('miss').filter(({ draws: [r] }) => r * 100 >= 1);
  for (const { log, foe } of misses) {
    assert.equal(foe.hp, foe.maxHp, 'a miss does no damage');
    assert.equal(foe.status, null, 'a miss applies no status');
    assert.equal(ofType(log, 'miss').length, 1);
  }
  assert.ok(misses.length > 30);

  // A status move with power 0 still has to hit.
  runs('statusMove').forEach(({ draws: [r1], states, log, rng, foe }, seed) => {
    assert.equal(foe.status !== null, r1 * 100 < 50, `seed ${seed}: a power-0 status move with accuracy 50, draw ${r1}`);
    assert.equal(ofType(log, 'miss').length, r1 * 100 < 50 ? 0 : 1);
    assert.equal(rng, states[1]);
  });

  // Snare first, then the foe's accuracy.
  const snareRuns = runs('snare').map((r, seed) => ({ ...r, seed })).filter(({ draws: [rs] }) => !(rs * 100 < 1));
  for (const { draws: [rs, ra], states, log, rng, seed } of snareRuns) {
    assert.equal(ofType(log, 'snare')[0].success, false);
    assert.equal(ofType(log, 'miss').length, ra * 100 >= 60 ? 1 : 0, `seed ${seed}: snare draw ${rs}, accuracy draw ${ra}`);
    assert.equal(rng, states[2]);
  }
  assert.ok(snareRuns.length > 50);

  // Tie draw, then each side's accuracy draw in acting order.
  runs('tie').forEach(({ draws: [rt, rFirst, rSecond], states, log, rng }, seed) => {
    const first = rt < 0.5 ? 0 : 1;
    const missed = ofType(log, 'miss').map((e) => e.side).sort();
    const want = [];
    if (rFirst * 100 >= 50) want.push(first);
    if (rSecond * 100 >= 50) want.push(1 - first);
    assert.deepEqual(missed, want.sort(), `seed ${seed}: tie ${rt}, then ${rFirst}, ${rSecond}`);
    assert.equal(rng, states[3]);
  });
});
