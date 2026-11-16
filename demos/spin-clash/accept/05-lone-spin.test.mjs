import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spinRose } from './helpers.mjs';
import { ask } from './ask.mjs';

// Fails on the first tick a spin in `series` (one per tick, from tick 0) rose.
function neverRises(series, what) {
  for (let t = 1; t < series.length; t++) {
    if (!(series[t] <= series[t - 1])) assert.fail(`${what}: spin rose from ${series[t - 1]} to ${series[t]} on tick ${t}`);
  }
}

test('Graded 5: spin only ever goes down: never up alone or in a clash, at least 0.5 rad/s lost each second with friction on, and a top spins down', () => {
  const seen = ask('spin');

  neverRises(seen.solo, 'friction on');
  assert.ok(seen.solo[seen.solo.length - 1] < seen.solo[0], `spin never fell in 3000 ticks with friction on (still ${seen.solo[seen.solo.length - 1]})`);

  // With friction off nothing drains spin, so any rise comes from somewhere else (steering, say).
  neverRises(seen.slick, 'friction off');

  assert.equal(seen.grippyStatus, 'spundown', 'a friction-1 top starting at spin 20 should spin down within 3600 ticks');

  // The floor under the loss: with friction on, every top in play loses at least 0.5 rad/s each second, even a
  // top whose own friction is 0, and a top with very little spin left is no exception. Only tops still in play
  // are held to it; a top that has spun down is done.
  for (const { label, spin, seconds } of seen.floors) {
    for (const { sec, ticks, tops } of seconds) {
      for (const top of tops) {
        if (top.status !== 'in') continue;
        assert.ok(top.spin <= Math.max(0, spin - 0.5 * sec * (1 - 1e-6)),
          `${label}: after ${sec} s (${ticks} ticks) top ${top.name} still spins at ${top.spin}; with friction on every top in play loses at least 0.5 rad/s each second, whatever its own friction`);
      }
    }
  }

  // No spin rises in a match with several tops either, tick by tick, collisions included.
  for (const { label, names, spins } of seen.matches) {
    for (let t = 1; t < spins.length; t++) {
      names.forEach((name, i) => {
        if (spinRose(spins[t - 1][i], spins[t][i])) {
          assert.fail(`${label}: tick ${t}, top ${name}'s spin rose from ${spins[t - 1][i]} to ${spins[t][i]}; nothing may raise a top's spin, a collision included`);
        }
      });
    }
  }
});
