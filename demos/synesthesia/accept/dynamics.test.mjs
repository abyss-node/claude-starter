import { test } from 'node:test';
import assert from 'node:assert/strict';
import { close, runs, statesOf } from './helpers.mjs';
import { expectedLoudness, framesOf } from './signals.mjs';

const tone = (freq, amp, seconds = 3, extra = {}) => ({ t: 'tone', parts: [[freq, amp]], seconds, ...extra });
const last = (job) => statesOf(runs(job)[0]).at(-1);

test('item 8: brightness follows 0.1 + 0.6 * loudness and zoom follows 1 + 0.5 * loudness on a held tone', () => {
  const seen = [];
  for (const amp of [0.02, 0.1, 0.5]) {
    const sound = tone(440, amp);
    const s = last({ frames: sound });
    const L = expectedLoudness(framesOf(sound).at(-1));
    close(s.loudness, L, 1e-9, `loudness field at amplitude ${amp}`);
    close(s.brightness, 0.1 + 0.6 * L, 0.03, `brightness at amplitude ${amp}`);
    close(s.zoom, 1 + 0.5 * L, 0.03, `zoom at amplitude ${amp}`);
    seen.push(s);
  }
  assert.ok(seen[0].brightness < seen[1].brightness && seen[1].brightness < seen[2].brightness, 'louder is brighter');
  assert.ok(seen[0].zoom < seen[1].zoom && seen[1].zoom < seen[2].zoom, 'louder is closer');
  assert.ok(seen[2].brightness - seen[0].brightness > 0.1);
});

test('item 8: a quiet but audible tone (about -40 dBFS) is not idle', () => {
  const s = last({ frames: tone(440, 0.01) });
  assert.equal(s.idle, false);
  assert.ok(s.loudness > 0.2 && s.loudness < 0.6, `loudness ${s.loudness}`);
});

test('item 9: centroid is reported in Hz and detail is log10(centroid / 100) / 2 limited to 0..1', () => {
  const want = [[220, 0.171], [1000, 0.5], [4000, 0.801], [9000, 0.977]];
  const got = runs(...want.map(([freq]) => ({ frames: tone(freq, 0.3) })), { frames: tone(70, 0.3) }, { frames: tone(20000, 0.3, 2, { fftSize: 8192 }) });
  const details = [];
  want.forEach(([freq, detail], i) => {
    const s = statesOf(got[i]).at(-1);
    close(s.centroid / freq, 1, 0.03, `centroid of a ${freq} Hz sine is ${s.centroid}`);
    close(s.detail, detail, 0.03, `detail at ${freq} Hz`);
    details.push(s.detail);
  });
  assert.ok(details.every((d, i) => i === 0 || d > details[i - 1]), 'higher sounds have more detail');
  const low = statesOf(got[4]).at(-1);
  assert.ok(low.detail >= 0 && low.detail < 0.01, `a 70 Hz tone is under 100 Hz: detail ${low.detail}`);
  const bright = statesOf(got[5]).at(-1);
  assert.ok(bright.detail <= 1 && bright.detail > 0.99, `detail clamps at 1, got ${bright.detail}`);
});

test('item 11: silence is calm: idle, no onsets or flashes, dim, slow, no detail, no drift', () => {
  const states = statesOf(runs({ frames: { t: 'silence', seconds: 4 } })[0]);
  for (const s of states) {
    assert.equal(s.idle, true);
    assert.equal(s.onsets, 0);
    assert.equal(s.flashes, 0);
    assert.equal(s.pulse, 0);
    assert.equal(s.loudness, 0);
    assert.equal(s.detail, 0);
    assert.equal(s.tempo, 0);
    assert.equal(s.pitchClass, null);
    assert.equal(s.mode, null);
    assert.equal(s.palette, 'neutral');
    assert.equal(s.drift, 0);
    assert.ok(s.brightness <= 0.35, `brightness ${s.brightness}`);
    assert.ok(s.zoom <= 1.05, `zoom ${s.zoom}`);
    assert.ok(s.speed > 0 && s.speed <= 0.2, `speed ${s.speed}`);
  }
  assert.ok(states.at(-1).phase > 0, 'the picture still moves, slowly');
});

test('item 11: faint noise (-60 dB and below) counts as silence', () => {
  const states = statesOf(runs({ frames: { t: 'noise', amp: 0.0004, seed: 3, seconds: 4, fftSize: 2048, hop: 512 } })[0]);
  assert.ok(states.every((s) => s.idle && s.flashes === 0 && s.detail === 0 && s.speed <= 0.2), 'faint noise is idle: no flashes, no detail, slow');
});

test('item 11: after the music stops the state is idle within 2 seconds and quiet again, with no flashes in the silence', () => {
  const r = runs({ steps: [{ push: tone(440, 0.5, 3) }, { push: { t: 'silence', seconds: 4 }, after: 0.05 }] })[0];
  const states = statesOf(r);
  const musicEnd = r.segments[0][1];
  const stopAt = states[musicEnd - 1].time;
  const after = states.filter((s) => s.time > stopAt);
  assert.equal(states[musicEnd - 1].idle, false, 'not idle while the music plays');
  const flashesAtStop = states[musicEnd - 1].flashes;
  assert.ok(after.every((s) => s.flashes === flashesAtStop), 'no flash in the silence');
  const settled = after.filter((s) => s.time >= stopAt + 2);
  assert.ok(settled.length > 10);
  for (const s of settled) {
    assert.equal(s.idle, true, `idle at ${(s.time - stopAt).toFixed(2)} s after the end`);
    assert.ok(s.brightness <= 0.35 && s.pulse < 0.05 && s.tempo === 0);
  }
});

test('item 14: drift is the left/right balance, (right - left) / (right + left)', () => {
  const cases = [[0.2, 0.6, 0.5], [0.6, 0.2, -0.5], [0.4, 0.4, 0], [0.5, 0, -1], [0, 0.5, 1]];
  const got = runs(...cases.map(([l, r]) => ({ frames: { t: 'levels', of: tone(440, 1, 2), left: l / Math.SQRT2, right: r / Math.SQRT2 } })));
  cases.forEach(([l, r, drift], i) => close(statesOf(got[i]).at(-1).drift, drift, 1e-6, `left ${l}, right ${r}`));
});

test('item 14: stereo made of two real channels drifts toward the louder side; mono and silence do not drift', () => {
  const stereo = (left, right) => ({ t: 'stereo', left: [[440, left]], right: [[440, right]], seconds: 2.2 });
  const [right, left, mono, bare, quiet] = runs(
    { frames: stereo(0.2, 0.6) },
    { frames: stereo(0.6, 0.2) },
    { frames: tone(440, 0.5) },
    { frames: { t: 'bare', of: tone(440, 0.5) } },
    { frames: { t: 'levels', of: { t: 'silence', seconds: 2 }, left: 0.3, right: 0.1 } },
  ).map((r) => statesOf(r).at(-1));
  close(right.drift, 0.5, 0.02, 'louder right channel');
  close(left.drift, -0.5, 0.02, 'louder left channel');
  assert.equal(mono.drift, 0, 'the same signal on both sides');
  assert.equal(bare.drift, 0, 'frames with no channel levels');
  assert.equal(quiet.drift, 0, 'idle does not drift');
});
