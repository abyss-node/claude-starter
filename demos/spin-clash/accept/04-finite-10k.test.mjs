import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 4: no NaN or Infinity in 10,000 ticks, including stacked tops and extreme sliders', () => {
  const worlds = ask('finite');
  assert.equal(worlds.length, 4);
  for (const { label, tick, notFinite } of worlds) {
    const [bad] = notFinite;
    if (bad) assert.fail(`${label}: tick ${bad.tick}, top ${bad.top}.${bad.field} = ${bad.value}`);
    assert.equal(tick, 10000, `${label}: world.tick should be 10000`);
  }
});
