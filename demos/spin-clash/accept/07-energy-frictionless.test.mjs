import { test } from 'node:test';
import assert from 'node:assert/strict';
import { energy } from './helpers.mjs';
import { ask } from './ask.mjs';

test('Graded 7: with friction off, total energy stays within 1e-6 through a collision', () => {
  const { ticks, start, frames } = ask('energyRun');
  const e0 = energy({ tops: start });
  assert.equal(frames.length, ticks);
  for (const { tick, tops } of frames) {
    const e = energy({ tops });
    if (!(Math.abs(e - e0) <= 1e-6 * e0)) assert.fail(`tick ${tick}: energy ${e0} became ${e}`);
  }
  const last = frames[frames.length - 1].tops;
  assert.ok(last[0].vx < 0, `the two tops never collided (Left is still moving right after ${ticks} ticks)`);
  for (const t of last) assert.equal(t.status, 'in', `${t.name} left play during a frictionless ${ticks}-tick run`);
});
