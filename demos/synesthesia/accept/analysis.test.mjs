import { test } from 'node:test';
import assert from 'node:assert/strict';
import { call, close, values } from './helpers.mjs';
import { NOTE, SR, binFor, binHz } from './signals.mjs';

// A sound whose first frame is used: 8192-point FFT at 44.1 kHz unless said otherwise.
const frameOf = (parts, extra = {}) => ({ $frame: { t: 'tone', parts, seconds: 0.3, ...extra } });
const binsFrame = (binCount, bins, extra = {}) => ({ $frame: { t: 'bins', binCount, bins, time: 0, ...extra } });

test('item 4: bin k of N magnitudes is at k * sampleRate / (2N) Hz', () => {
  const got = values('src/analysis.js', [
    ['binFrequency', 0, 1024, 44100], ['binFrequency', 1, 1024, 44100], ['binFrequency', 10, 1024, 44100],
    ['binFrequency', 100, 4096, 48000], ['binFrequency', 512, 512, 32000],
  ]);
  close(got[0], 0, 1e-9);
  close(got[1], 44100 / 2048, 1e-9);
  close(got[2], 215.33203125, 1e-6);
  close(got[3], 585.9375, 1e-6);
  close(got[4], 16000, 1e-6);
});

const CASES = [
  ['C4', NOTE.C4, 0], ['C#4', NOTE.Db4, 1], ['D4', NOTE.D4, 2], ['Eb4', NOTE.Eb4, 3], ['E4', NOTE.E4, 4],
  ['F4', NOTE.F4, 5], ['F#4', NOTE.Gb4, 6], ['G4', NOTE.G4, 7], ['Ab4', NOTE.Ab4, 8], ['A4', 440, 9],
  ['Bb4', NOTE.Bb4, 10], ['B4', NOTE.B4, 11], ['A2', 110, 9], ['F#6', 1479.98, 6], ['C3', 130.8128, 0],
];

test('item 4: chroma puts a sine at 8192 / 44.1 kHz in its own pitch class (12 notes and 3 octaves)', () => {
  const got = call('src/analysis.js', CASES.map(([, freq]) => ['chroma', frameOf([[freq, 0.5]])]));
  CASES.forEach(([name, , pc], i) => {
    const c = Array.from(got[i]);
    assert.equal(c.length, 12, `${name}: chroma has 12 values`);
    const total = c.reduce((a, b) => a + b, 0);
    assert.ok(c.every((v) => v >= 0), `${name}: no negative energy`);
    assert.ok(total > 0, `${name}: some energy`);
    assert.ok(c[pc] / total >= 0.9, `${name}: pitch class ${pc} should hold at least 90% of the energy, got ${(c[pc] / total).toFixed(3)} (${c.map((v) => v.toFixed(3)).join(' ')})`);
  });
});

test('item 4: chroma works at another sample rate and bin count (48 kHz, 4096 bins)', () => {
  const cases = [['A4', 440, 9], ['E4', NOTE.E4, 4], ['Bb3', 233.0819, 10]];
  const got = call('src/analysis.js', cases.map(([, freq]) => ['chroma', frameOf([[freq, 0.5]], { sampleRate: 48000, fftSize: 8192 })]));
  cases.forEach(([name, , pc], i) => {
    const c = Array.from(got[i]);
    const total = c.reduce((a, b) => a + b, 0);
    assert.ok(c[pc] / total >= 0.85, `${name} at 48 kHz: pitch class ${pc} holds ${(c[pc] / total).toFixed(3)}`);
  });
});

test('item 4: chroma ignores energy below 55 Hz and above 4200 Hz, and silence has none', () => {
  const [a, low, high, higher, silence, empty] = call('src/analysis.js', [
    ['chroma', frameOf([[440, 0.5]])], ['chroma', frameOf([[30, 0.5]])], ['chroma', frameOf([[9000, 0.5]])], ['chroma', frameOf([[5000, 0.5]])],
    ['chroma', binsFrame(512, {})], ['chroma', { time: 0, sampleRate: SR, magnitudes: [] }],
  ]);
  const total = (c) => Array.from(c).reduce((x, y) => x + y, 0);
  const A = total(a);
  assert.ok(total(low) < A * 1e-3, 'a 30 Hz tone is below the pitch range');
  assert.ok(total(high) < A * 1e-3, 'a 9 kHz tone is above the pitch range');
  assert.ok(total(higher) < A * 1e-3, 'a 5 kHz tone is above the pitch range');
  assert.deepEqual(Array.from(silence), new Array(12).fill(0));
  assert.equal(Array.from(empty).length, 12);
});

test('item 4: chroma adds up the energy (magnitude squared) of all the bins of a class', () => {
  const bins = 4096;
  const [got] = call('src/analysis.js', [['chroma', binsFrame(bins, { [binFor(440, bins)]: 0.3, [binFor(880, bins)]: 0.4 })]]);
  const c = Array.from(got);
  close(c[9], 0.09 + 0.16, 1e-9, 'A energy');
  assert.equal(c.reduce((a, b) => a + b, 0), c[9]);
});

const vec = (...pcs) => {
  const v = new Array(12).fill(0);
  for (const p of pcs) v[p] += 1;
  return v;
};

test('item 5: estimateMode finds major and minor triads at their root', () => {
  const cases = [
    [vec(0, 4, 7), 'major', 0], [vec(0, 3, 7), 'minor', 0], [vec(2, 6, 9), 'major', 2], [vec(6, 9, 1), 'minor', 6],
    [vec(9, 1, 4), 'major', 9], [vec(11, 2, 6), 'minor', 11], [vec(10, 2, 5), 'major', 10], [vec(7, 10, 2), 'minor', 7],
  ];
  const got = values('src/analysis.js', cases.map(([v]) => ['estimateMode', v]));
  cases.forEach(([v, mode, root], i) => {
    assert.equal(got[i].mode, mode, `chroma ${v.join('')}`);
    assert.equal(got[i].root, root, `chroma ${v.join('')}`);
  });
});

test('item 5: estimateMode says null for a single note, a fifth, silence and bad input', () => {
  const inputs = [vec(9), vec(0, 7), new Array(12).fill(0), new Array(12).fill(1), undefined, [], [1, 2, 3]];
  const got = values('src/analysis.js', inputs.map((v) => ['estimateMode', v]));
  inputs.forEach((v, i) => {
    assert.equal(got[i].mode, null, `chroma ${JSON.stringify(v)}`);
    assert.equal(got[i].root, null, `chroma ${JSON.stringify(v)}`);
  });
});

test('item 5: estimateMode needs the best triad to beat the best triad of the other kind by more than 0.1', () => {
  // C E G with a little Eb: major still wins by 0.143 of the energy.
  const a = vec(0, 4, 7);
  a[3] = 0.5;
  // The same with Eb at 0.9: the two kinds are 0.025 apart, which is a tie.
  const b = vec(0, 4, 7);
  b[3] = 0.9;
  // Unequal amplitudes still give the root: D F A with A the strongest.
  const c = new Array(12).fill(0);
  c[2] = 0.0625; c[5] = 0.04; c[9] = 0.09;
  const [ra, rb, rc] = values('src/analysis.js', [['estimateMode', a], ['estimateMode', b], ['estimateMode', c]]);
  assert.deepEqual(ra, { mode: 'major', root: 0 });
  assert.deepEqual(rb, { mode: null, root: null });
  assert.deepEqual(rc, { mode: 'minor', root: 2 });
});

test('item 5: a triad made of sines is recognised through chroma on real frames', () => {
  const triad = (...freqs) => frameOf(freqs.map((f) => [f, 0.2]));
  const via = (frame) => ({ $call: ['chroma', frame] });
  const [maj, min, single] = call('src/analysis.js', [
    ['estimateMode', via(triad(NOTE.C4, NOTE.E4, NOTE.G4))],
    ['estimateMode', via(triad(NOTE.C4, NOTE.Eb4, NOTE.G4))],
    ['estimateMode', via(frameOf([[440, 0.5]]))],
  ]);
  assert.deepEqual(maj, { mode: 'major', root: 0 });
  assert.deepEqual(min, { mode: 'minor', root: 0 });
  assert.equal(single.mode, null);
});

test('item 8: loudness is level in dB mapped from -60 dB (0) to 0 dB (1); the DC bin does not count', () => {
  const bins = [{}, { 10: 1 }, { 10: 0.5 }, { 10: 0.01 }, { 10: 0.001 }, { 10: 0.0001 }, { 10: 5 }, { 10: 0.3, 20: 0.4 }, { 0: 9 }];
  const [silence, one, half, forty, sixty, below, above, two, dc] = call('src/analysis.js', bins.map((b) => ['loudness', binsFrame(512, b)]));
  assert.equal(silence, 0, 'silence');
  close(one, 1, 1e-9, 'level 1 is 0 dB');
  close(half, (20 * Math.log10(0.5) + 60) / 60, 1e-9, 'level 0.5');
  close(forty, 20 / 60, 1e-9, 'level 0.01 is -40 dB');
  close(sixty, 0, 1e-9, '-60 dB');
  assert.equal(below, 0, 'below -60 dB clamps to 0');
  assert.equal(above, 1, 'above 0 dB clamps to 1');
  close(two, (20 * Math.log10(0.5) + 60) / 60, 1e-9, 'level is the root of the sum of squares');
  assert.equal(dc, 0, 'bin 0 (DC) is ignored');
});

test('item 9: spectralCentroid is the magnitude-weighted mean frequency of bins 1 and up', () => {
  const C = (bins, extra) => ['spectralCentroid', binsFrame(1024, bins, extra)];
  const [silence, one, weighted, equal, dc, rate] = call('src/analysis.js', [
    C({}), C({ 40: 0.2 }), C({ 40: 0.4, 80: 0.1 }), C({ 40: 0.2, 80: 0.2 }), C({ 0: 5, 100: 0.1 }), C({ 100: 0.1 }, { sampleRate: 48000 }),
  ]);
  assert.equal(silence, 0, 'silence');
  close(one, binHz(40, 1024, SR), 1e-9);
  close(weighted, (binHz(40, 1024, SR) * 0.4 + binHz(80, 1024, SR) * 0.1) / 0.5, 1e-9, 'weights are magnitudes, not energies');
  close(equal, (binHz(40, 1024, SR) + binHz(80, 1024, SR)) / 2, 1e-9);
  close(dc, binHz(100, 1024, SR), 1e-9, 'bin 0 is ignored');
  close(rate, binHz(100, 1024, 48000), 1e-9, 'uses the frame sample rate');
});

test('item 14: balance is (right - left) / (right + left), 0 when both are silent or missing', () => {
  const B = (left, right) => ['balance', { time: 0, sampleRate: SR, magnitudes: [], left, right }];
  const [l, r, a, b, even, none, missing, nan, bare, negative] = values('src/analysis.js', [
    B(0.5, 0), B(0, 0.5), B(0.1, 0.3), B(0.3, 0.1), B(0.4, 0.4), B(0, 0), B(undefined, undefined),
    B(NaN, 0.3), ['balance', { time: 0, sampleRate: SR, magnitudes: [] }], B(-0.2, 0.3),
  ]);
  close(l, -1, 1e-12);
  close(r, 1, 1e-12);
  close(a, 0.5, 1e-12);
  close(b, -0.5, 1e-12);
  close(even, 0, 1e-12);
  assert.equal(none, 0);
  assert.equal(missing, 0);
  close(nan, 1, 1e-12, 'a level that is not a number counts as 0');
  assert.equal(bare, 0, 'no channel levels at all');
  close(negative, 1, 1e-12, 'a negative level counts as 0');
});
