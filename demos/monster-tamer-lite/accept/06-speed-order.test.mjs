import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted } from './helpers.mjs';
import { SPEED_PAIRS, TIE_SEEDS, SNARE_SEEDS } from './scenario-06.mjs';

test('Graded 6: Speed order and the tie rule', () => {
  const o = observe('./scenario-06.mjs');

  // Faster acts first, whichever side, whatever the seed; and no draw is taken.
  const fixed = counted(o.fixed, 20 * SPEED_PAIRS.length, 'battles of different speeds');
  let k = 0;
  for (let seed = 1; seed <= 20; seed++) {
    for (const [s0, s1, first] of SPEED_PAIRS) {
      const f = fixed[k++];
      assert.deepEqual(f.order, first === 0 ? [0, 1] : [1, 0], `speeds ${s0} v ${s1}, seed ${seed}`);
      assert.equal(f.rng, f.start, `no draw may be taken when speeds differ (speeds ${s0} v ${s1})`);
    }
  }

  // A tie takes exactly one draw: side 0 first when it is below 0.5.
  let zeroFirst = 0;
  counted(o.ties, TIE_SEEDS, 'ties').forEach((t, seed) => {
    assert.deepEqual(t.order, t.r < 0.5 ? [0, 1] : [1, 0], `tie, seed ${seed}, draw ${t.r}`);
    assert.equal(t.rng, t.after, `a tie takes exactly one draw (seed ${seed})`);
    if (t.r < 0.5) zeroFirst++;
  });
  assert.ok(zeroFirst > 60 && zeroFirst < 140, `side 0 went first in ${zeroFirst} of 200 ties`);
  const [x, y] = counted(o.sameSeed, 2, 'two battles from seed 77');
  assert.equal(typeof x, 'string');
  assert.equal(x, y);

  // Only one side moving: no tie, no draw.
  counted(o.lone.rng, 2, 'lone movers');
  assert.equal(o.lone.rng[0], o.lone.start, 'a lone mover takes no tie draw');
  assert.equal(o.lone.rng[1], o.lone.start);

  // Chill halves the speed, rounded down.
  assert.deepEqual(o.speeds, [40, 20, 20, 3, 40, 40], 'effectiveSpeed: only chill slows a creature, by half rounded down');
  assert.deepEqual(o.chill.chilledOrder, [1, 0], 'a chilled 40 (20) is slower than a 30');
  // 41 chilled is 20, a tie with 20: one draw is taken; unfloored 20.5 would not tie.
  assert.notEqual(o.chill.tieRng, o.chill.tieStart, 'a chilled 41 ties a 20, so a draw is taken');
  assert.deepEqual(o.chill.scorchOrder, [0, 1]);

  // Switches come before moves, whoever is faster.
  counted(o.switches, 2, 'switching battles').forEach(([t, tc], i) => {
    const [s0, s1] = [[10, 99], [99, 10]][i];
    assert.ok(t.indexOf('switch') !== -1 && t.indexOf('switch') < t.indexOf('move'), `switch must come before the move (speeds ${s0} v ${s1}): ${t}`);
    assert.ok(tc.indexOf('switch') < tc.indexOf('move'), `switch must come before the move (speeds ${s0} v ${s1}), side 1 switching: ${tc}`);
  });

  // The snare comes before the foe's move, even when the foe is much faster (the first four seeds where it fails).
  const failed = counted(o.snares, SNARE_SEEDS, 'snare battles').filter((s) => !(s.r * 100 < 1)).slice(0, 4);
  assert.equal(failed.length, 4);
  for (const { types: t } of failed) assert.ok(t.indexOf('snare') !== -1 && t.indexOf('snare') < t.indexOf('move'), `snare must come before the move: ${t}`);
});
