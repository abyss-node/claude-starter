import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertThrew } from './helpers.mjs';
import { NAMES, BAD_PAIRS } from './scenario-03.mjs';
import { CHART as TABLE } from './fixtures.mjs';


test('Graded 3: The type chart', () => {
  const o = observe('./scenario-03.mjs');
  assert.deepEqual(o.TYPES, NAMES);
  for (const att of NAMES) {
    const chart = counted(o.chart && o.chart[att], 5, `TYPE_CHART[${att}]`);
    const mult = counted(o.multiplier && o.multiplier[att], 5, `typeMultiplier(${att}, ...)`);
    NAMES.forEach((def, j) => {
      assert.equal(chart[j], TABLE[att][j], `TYPE_CHART[${att}][${def}]`);
      assert.equal(mult[j], TABLE[att][j], `typeMultiplier(${att}, ${def})`);
    });
  }
  const m = (a, d) => o.multiplier[a][NAMES.indexOf(d)];
  assert.equal(m('spark', 'stone'), 0);
  assert.equal(m('stone', 'spark'), 2);
  assert.equal(m('tide', 'cinder'), 2);
  assert.equal(m('cinder', 'tide'), 0.5);
  counted(o.bad, BAD_PAIRS.length, 'unknown types').forEach((t, i) => assertThrew(t, `typeMultiplier(${BAD_PAIRS[i].map(String).join(', ')})`));
});
