import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask, close, flashTimes, median, runs, statesOf, values } from './helpers.mjs';
import { clickTimes } from './signals.mjs';

const clicks = (bpm, seconds = 12) => ({ t: 'clicks', bpm, seconds, fftSize: 2048, hop: 512 });
const ran = (bpm, seconds) => statesOf(runs({ frames: clicks(bpm, seconds) })[0]);

test('item 12: a click track at 120 BPM gives one onset and one pulse per click, at 2 per second', () => {
  const states = ran(120);
  const n = clickTimes(120, 12).length;
  const last = states.at(-1);
  assert.ok(last.onsets >= n - 2 && last.onsets <= n + 2, `${last.onsets} onsets for ${n} clicks`);
  assert.equal(last.flashes, last.onsets, 'at 2 per second the limiter holds nothing back');
  const times = flashTimes(states);
  const gaps = times.slice(1).map((t, i) => t - times[i]);
  close(median(gaps), 0.5, 0.025, 'median time between pulses');
  assert.ok(gaps.every((g) => g > 0.4 && g < 0.6), `pulses should be regular, gaps ${gaps.map((g) => g.toFixed(3)).join(' ')}`);
  const rate = times.length / (last.time - 0.25);
  assert.ok(rate > 1.8 && rate < 2.2, 'about 2 pulses per second');
});

test('item 12: each pulse starts within 0.15 s after its click', () => {
  const times = flashTimes(ran(120));
  const clicksAt = clickTimes(120, 12);
  for (const t of times) {
    const before = clicksAt.filter((c) => c <= t + 1e-9).pop();
    assert.ok(before !== undefined && t - before <= 0.15, `a pulse at ${t.toFixed(3)} s has no click in the 0.15 s before it`);
  }
});

test('item 12: other tempos also give one pulse per click (90 and 140 BPM)', () => {
  for (const bpm of [90, 140]) {
    const last = ran(bpm).at(-1);
    const n = clickTimes(bpm, 12).length;
    assert.ok(Math.abs(last.onsets - n) <= 2, `${bpm} BPM: ${last.onsets} onsets for ${n} clicks`);
    assert.ok(Math.abs(last.flashes - n) <= 2, `${bpm} BPM: ${last.flashes} pulses for ${n} clicks`);
  }
});

test('item 12: a pulse is pulse = 1 and a new pattern, then the pulse fades and the pattern holds until the next one', () => {
  const states = ran(120);
  const patternCount = ask('layout', ['src/synth.js']).constants.PATTERN_COUNT;
  const used = new Set();
  for (let i = 1; i < states.length; i++) {
    const s = states[i];
    const p = states[i - 1];
    assert.ok(Number.isInteger(s.pattern) && s.pattern >= 0 && s.pattern < patternCount, `pattern ${s.pattern}`);
    used.add(s.pattern);
    if (s.flashes > p.flashes) {
      assert.equal(s.flashes, p.flashes + 1);
      close(s.pulse, 1, 1e-9, 'pulse on a flash frame');
      assert.notEqual(s.pattern, p.pattern, 'every pulse switches the block pattern');
    } else {
      assert.equal(s.pattern, p.pattern, 'the pattern only changes on a pulse');
      assert.ok(s.pulse <= p.pulse + 1e-12, 'the pulse only fades between flashes');
    }
  }
  assert.ok(used.size >= 3, `the patterns should vary, saw ${[...used].join(',')}`);
  // Just before each pulse (after about 0.45 s) the previous one has faded away.
  const flashes = states.filter((s, i) => i > 0 && s.flashes > states[i - 1].flashes);
  for (let k = 1; k < flashes.length; k++) {
    const before = states.filter((s) => s.time < flashes[k].time && s.time > flashes[k].time - 0.05).at(-1);
    assert.ok(before.pulse < 0.1, `pulse ${before.pulse} just before the next one`);
  }
});

test('item 12: onsets are never closer than 0.1 s, and a held tone or steady noise does not keep firing', () => {
  const [fast, held, hiss] = runs(
    { frames: clicks(150, 8) },
    { frames: { t: 'tone', parts: [[440, 0.5]], seconds: 6 } },
    { frames: { t: 'noise', amp: 0.1, seed: 5, seconds: 6, fftSize: 2048, hop: 512 } },
  ).map(statesOf);
  const onsetTimes = flashTimes(fast, 'onsets');
  for (let i = 1; i < onsetTimes.length; i++) assert.ok(onsetTimes[i] - onsetTimes[i - 1] >= 0.1 - 1e-9, 'two onsets less than 0.1 s apart');
  assert.ok(held.at(-1).onsets <= 2, `a held tone gave ${held.at(-1).onsets} onsets`);
  assert.ok(hiss.at(-1).onsets <= 3, `steady noise gave ${hiss.at(-1).onsets} onsets`);
});

test('item 12: only a rise counts: a tone that fades out over 0.3 s gives no onset', () => {
  const last = statesOf(runs({ frames: { t: 'fade' } })[0]).at(-1);
  assert.ok(last.onsets <= 2, `a fading tone gave ${last.onsets} onsets`);
});

test('item 13: estimateTempo is the median gap of the last nine onsets, folded into [72, 144) BPM; fewer than four onsets give 0', () => {
  const every = (gap, n, from = 0) => Array.from({ length: n }, (_, i) => from + i * gap);
  const cases = [
    [every(0.5, 5), 120], [every(60 / 90, 8), 90], [every(60 / 75, 6), 75], [every(60 / 140, 6), 140],
    [every(1, 6), 120], [every(0.25, 9), 120], [every(0.4, 6), 75], [every(2, 6), 120],
  ];
  const got = values('src/onsets.js', [...cases.map(([t]) => ['estimateTempo', t]), ['estimateTempo', []], ['estimateTempo', every(0.5, 3)], ['estimateTempo', every(0.5, 4)], ['estimateTempo', undefined]]);
  cases.forEach(([, want], i) => close(got[i], want, 1e-9, `case ${i}`));
  assert.equal(got[8], 0);
  assert.equal(got[9], 0, 'three onsets are not enough');
  assert.ok(got[10] > 0, 'four are');
  assert.equal(got[11], 0);
});

test('item 13: estimateTempo ignores an odd gap (median, not mean) and only looks at the last nine onsets', () => {
  const jitter = [0, 0.5, 1.02, 1.5, 2.01, 2.5, 3.0, 3.52, 4.0];
  const withOutlier = [0, 0.5, 1, 1.2, 1.7, 2.2, 2.7, 3.2, 3.7];
  const slowThenFast = [...Array.from({ length: 12 }, (_, i) => i * (60 / 90)), ...Array.from({ length: 9 }, (_, i) => 10 + i * 0.5)];
  const halfAndHalf = [0, 0.5, 1, 1.5, 2, 2.4, 2.8, 3.2, 3.6];
  const tenAt90 = Array.from({ length: 10 }, (_, i) => i * (60 / 90));
  const got = values('src/onsets.js', [jitter, withOutlier, slowThenFast, halfAndHalf, tenAt90, tenAt90.slice(-9)].map((t) => ['estimateTempo', t]));
  close(got[0], 120, 3);
  close(got[1], 120, 1e-9);
  close(got[2], 120, 1e-9);
  close(got[3], 60 / 0.45, 1e-9, 'four gaps of 0.5 and four of 0.4: the median of eight gaps is 0.45');
  close(got[4], got[5], 1e-9);
});

test('item 13: the synth reports tempo and speed = tempo / 120 once it has heard a steady beat', () => {
  for (const bpm of [90, 120, 135]) {
    const states = ran(bpm);
    const last = states.at(-1);
    close(last.tempo, bpm, 4, `${bpm} BPM click track`);
    close(last.speed, last.tempo / 120, 1e-9, 'speed is tempo / 120');
    assert.ok(states.slice(0, 5).every((s) => s.tempo === 0), 'no tempo before four onsets');
    assert.equal(last.idle, false);
  }
});

test('item 13: a tempo change is followed (120 then 90 BPM)', () => {
  const r = runs({ steps: [{ push: clicks(120, 10) }, { push: clicks(90, 12), after: 0 }] })[0];
  const states = statesOf(r);
  close(states.at(-1).tempo, 90, 5);
  close(states[r.segments[0][1] - 1].tempo, 120, 4);
});

test('item 13: with sound but no beat the speed is 0.5; the phase advances by speed * dt every frame', () => {
  const [held, beat] = runs({ frames: { t: 'tone', parts: [[440, 0.5]], seconds: 3 } }, { frames: clicks(120, 8) }).map(statesOf);
  const last = held.at(-1);
  assert.equal(last.tempo, 0);
  assert.equal(last.speed, 0.5);
  assert.equal(held[0].phase, 0, 'the first frame has dt 0');
  for (let i = 1; i < held.length; i++) {
    close(held[i].phase - held[i - 1].phase, held[i].speed * (held[i].time - held[i - 1].time), 1e-9, `phase step at frame ${i}`);
  }
  for (let i = 1; i < beat.length; i++) {
    close(beat[i].phase - beat[i - 1].phase, beat[i].speed * (beat[i].time - beat[i - 1].time), 1e-9);
  }
});
