import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask, checkVisibleOnlyOnFlash, close, flashTimes, fourWithinASecond, hueDistance, runs, statesOf, values } from './helpers.mjs';

const strobe = { t: 'strobe', seconds: 10, fftSize: 512, hop: 256 };
const strobeStates = (opts) => statesOf(runs(opts === undefined ? { frames: strobe } : { frames: strobe, opts })[0]);

test('item 15: the limiter is on by default, and the state says so', () => {
  const optsList = [undefined, {}, { seed: 5, preset: 'ember' }, { limiter: undefined }];
  const got = runs(...optsList.map((opts) => ({ opts, steps: [{ read: 'start' }] })));
  got.forEach((r, i) => {
    assert.equal(r.reads[0].limiter, true, `createSynth(${JSON.stringify(optsList[i])}).limiter`);
    assert.equal(r.reads[0].state.limiter, true, `createSynth(${JSON.stringify(optsList[i])}).state.limiter`);
  });
});

test('item 15: a strobe of 20 Hz never gets more than three flashes in any second over 10 s, but is not blocked either', () => {
  const states = strobeStates();
  const times = flashTimes(states);
  assert.equal(fourWithinASecond(times), false, 'four flashes inside one second');
  assert.ok(times.length >= 20, `only ${times.length} flashes in 10 s: the limiter lets about three a second through`);
  assert.ok(times.length <= 31, `${times.length} flashes in 10 s`);
  assert.ok(states.at(-1).onsets > states.at(-1).flashes, 'the strobe was heard (onsets) and the limiter held flashes back');
  assert.equal(states.at(-1).limiter, true);
});

test('item 15: on the strobe a refused onset shows nothing: pulse and pattern change only on frames where a flash was counted', () => {
  checkVisibleOnlyOnFlash(strobeStates(), assert);
});

test('item 15: a sudden loud burst train at 5 per second is also held to three flashes a second', () => {
  const states = statesOf(runs({ frames: { t: 'bursts' } })[0]);
  const times = flashTimes(states);
  assert.ok(times.length >= 10, `only ${times.length} flashes`);
  assert.equal(fourWithinASecond(times), false);
  checkVisibleOnlyOnFlash(states, assert);
});

test('item 15: createFlashLimiter lets a flash through only when the last allowed one was at least 1/3 s ago', () => {
  const first = [10, 10.1, 10.3, 10.34, 10.5, 10.68];
  const dense = [];
  for (let t = 0; t < 10; t += 0.05) dense.push(t);
  const [a, b, c] = ask('limiters', [first, dense, [-5]]);
  assert.deepEqual(a, [true, false, false, true, false, true], 'the first flash; a third of a second later; a refused flash does not restart the clock');
  const allowed = dense.filter((_, i) => b[i]);
  assert.equal(fourWithinASecond(allowed), false);
  assert.ok(allowed.length >= 25 && allowed.length <= 31, `${allowed.length} of 200 flashes allowed`);
  assert.equal(c[0], true, 'times before zero are fine');
});

test('item 16: slewToward moves at most maxChange toward the target and never overshoots', () => {
  const calls = [[0.1, 0.7, 0.05], [0.9, 0.1, 0.2], [0.5, 0.52, 0.1], [0.5, 0.45, 0.1], [0, 1, 1], [2, 2, 1], [0.3, 0.9, 0], [0.3, 0.9, -1], [-1, 1, 0.5]];
  const got = values('src/safety.js', calls.map((c) => ['slewToward', ...c]));
  const want = [0.15, 0.7, 0.52, 0.45, 1, 2, 0.3, 0.3, -0.5];
  want.forEach((w, i) => close(got[i], w, 1e-12, `slewToward(${calls[i].join(', ')})`));
});

test('item 16: slewHue goes the short way round the colour wheel and returns a hue in [0, 360)', () => {
  const calls = [
    [350, 10, 5, 355], [10, 350, 5, 5], [10, 350, 30, 350], [355, 5, 7, 2], [350, 10, 100, 10], [0, 179, 10, 10], [0, 181, 10, 350],
    [100, 130, 10, 110], [130, 100, 10, 120], [200, 200, 10, 200], [200, 560, 10, 200], [200, 590, 10, 210], [40, 40, 0, 40], [40, 90, 0, 40], [358, 20, 30, 20],
  ];
  const got = values('src/safety.js', calls.map(([a, b, c]) => ['slewHue', a, b, c]));
  calls.forEach(([a, b, c, want], i) => {
    close(got[i], want, 1e-9, `slewHue(${a}, ${b}, ${c})`);
    assert.ok(got[i] >= 0 && got[i] < 360, `slewHue(${a}, ${b}, ${c}) is in [0, 360)`);
  });
});

test('item 16: with the limiter on, the hue turns at most 240 degrees a second, the short way, and settles within a second', () => {
  const order = [0, 6, 11, 1, 11, 6, 0, 3];
  const states = statesOf(runs({ frames: { t: 'holds', pcs: order } })[0]);
  let fastest = 0;
  for (let i = 1; i < states.length; i++) {
    const dt = states[i].time - states[i - 1].time;
    const step = hueDistance(states[i].hue, states[i - 1].hue);
    fastest = Math.max(fastest, step / dt);
    assert.ok(step <= 240 * dt + 1e-6, `hue moved ${step} degrees in ${dt} s at frame ${i}`);
  }
  assert.ok(fastest >= 200, `the hue should move at the cap when it has far to go, fastest ${fastest.toFixed(1)} deg/s`);
  const wheel = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330];
  order.forEach((pc, n) => {
    if (n === 0) return;
    const s = states[n * 100 + 79];
    const far = hueDistance(wheel[order[n - 1]], wheel[pc]);
    close(hueDistance(s.hue, wheel[pc]), 0, 3, `0.8 s into note ${n}: the hue should have arrived (${far} degrees to go), got ${s.hue}`);
  });
});

test('item 16: with the limiter on, brightness and zoom change by at most 1.5 per second even when the sound jumps', () => {
  const states = statesOf(runs({ frames: { t: 'jumps' } })[0]);
  let maxB = 0;
  let minB = 1;
  for (let i = 1; i < states.length; i++) {
    const dt = states[i].time - states[i - 1].time;
    assert.ok(Math.abs(states[i].brightness - states[i - 1].brightness) <= 1.5 * dt + 1e-9, `brightness jumped at frame ${i}`);
    assert.ok(Math.abs(states[i].zoom - states[i - 1].zoom) <= 1.5 * dt + 1e-9, `zoom jumped at frame ${i}`);
    if (i > 100) {
      maxB = Math.max(maxB, states[i].brightness);
      minB = Math.min(minB, states[i].brightness);
    }
  }
  assert.ok(maxB >= 0.5 && minB <= 0.2, `brightness should still follow the sound: it ranged ${minB.toFixed(2)} to ${maxB.toFixed(2)}`);
  const zooms = states.map((s) => s.zoom);
  assert.ok(Math.max(...zooms) > 1.4 && Math.min(...zooms.slice(100)) < 1.1, 'zoom still follows the sound');
});

test('item 16: on a 20 Hz strobe the brightness never moves faster than 1.5 per second either', () => {
  const states = strobeStates();
  for (let i = 1; i < states.length; i++) {
    const dt = states[i].time - states[i - 1].time;
    assert.ok(Math.abs(states[i].brightness - states[i - 1].brightness) <= 1.5 * dt + 1e-9);
    assert.ok(Math.abs(states[i].zoom - states[i - 1].zoom) <= 1.5 * dt + 1e-9);
  }
  // Over any 0.25 s the brightness cannot swing more than 0.375.
  for (let i = 0; i < states.length; i += 7) {
    const window = states.filter((s) => s.time >= states[i].time && s.time < states[i].time + 0.25).map((s) => s.brightness);
    assert.ok(Math.max(...window) - Math.min(...window) <= 0.375 + 1e-9);
  }
});

test('item 17: with limiter: false the state says so, hue and brightness jump straight to their targets, and flashes are not capped', () => {
  const r = runs({ opts: { limiter: false }, frames: strobe })[0];
  const [start] = runs({ opts: { limiter: false }, steps: [{ read: 'start' }] });
  assert.equal(start.reads[0].limiter, false);
  assert.equal(start.reads[0].state.limiter, false);
  const states = statesOf(r);
  assert.equal(states.at(-1).limiter, false);
  const times = flashTimes(states);
  assert.ok(fourWithinASecond(times), 'with the limiter off the strobe gets through');
  let perSecondMax = 0;
  for (let i = 0; i < times.length; i++) perSecondMax = Math.max(perSecondMax, times.filter((t) => t >= times[i] && t < times[i] + 1).length);
  assert.ok(perSecondMax >= 6, `at most ${perSecondMax} flashes in a second: the limiter should be off`);
  let jumped = false;
  for (let i = 1; i < states.length; i++) {
    const dt = states[i].time - states[i - 1].time;
    if (Math.abs(states[i].brightness - states[i - 1].brightness) > 1.5 * dt + 1e-9) jumped = true;
  }
  assert.ok(jumped, 'with the limiter off brightness is not slew-limited');
});

test('item 17: limiter off puts the hue on its target in the first frame; limiter on has not moved yet', () => {
  const first = { t: 'tone', parts: [[440, 0.5]], samples: 12000 };
  const [off, on] = runs({ opts: { limiter: false }, frames: first }, { frames: first }).map((r) => statesOf(r)[0]);
  assert.equal(off.hue, 270);
  assert.equal(off.pitchClass, 9);
  assert.equal(on.hue, 220, 'the first frame has dt 0, so a slewed hue has not moved from its start');
});

test('item 17: setLimiter changes the state flag at once and caps flashes from then on', () => {
  const half = { t: 'strobe', seconds: 5, fftSize: 512, hop: 256 };
  const r = runs({
    opts: { limiter: false },
    steps: [{ push: half }, { read: 'off' }, { setLimiter: true }, { read: 'on' }, { push: half, after: 0 }, { setLimiter: false }, { read: 'off again' }],
  })[0];
  const reads = Object.fromEntries(r.reads.map((x) => [x.label, x]));
  assert.equal(reads.off.limiter, false);
  assert.equal(reads.on.limiter, true);
  assert.equal(reads.on.state.limiter, true, 'the state getter says so at once');
  assert.equal(reads['off again'].state.limiter, false);
  const [from, to] = r.segments[1];
  const second = r.states.slice(from, to);
  assert.ok(second.every((s) => s.limiter === true));
  const times = flashTimes(r.states).filter((t) => t >= second[0].time);
  assert.ok(times.length >= 8, `${times.length} flashes after the switch`);
  assert.equal(fourWithinASecond(times), false, 'after switching the limiter on, three a second at most');
});
