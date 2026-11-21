import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask, close, values } from './helpers.mjs';

test('item 2: magnitudesFromDb turns dB into linear magnitudes, 10^(dB/20)', () => {
  const [got] = values('src/capture.js', [['magnitudesFromDb', [0, -20, -40, -6.0206, 20, -60]]]);
  const out = Array.from(got);
  const want = [1, 0.1, 0.01, 0.5, 10, 0.001];
  assert.equal(out.length, want.length);
  want.forEach((w, i) => close(out[i], w, 1e-4 * Math.max(1, w), `bin ${i}`));
});

test('item 2: magnitudesFromDb maps -Infinity, NaN and non-numbers to 0 and keeps the length', () => {
  const [a, b, c] = values('src/capture.js', [
    ['magnitudesFromDb', [-Infinity, NaN, undefined, 'x', -20]],
    ['magnitudesFromDb', []],
    ['magnitudesFromDb', new Float32Array([-20, -20])],
  ]);
  const out = Array.from(a);
  assert.equal(out.length, 5);
  assert.deepEqual(out.slice(0, 4), [0, 0, 0, 0]);
  close(out[4], 0.1, 1e-6);
  assert.equal(Array.from(b).length, 0);
  assert.equal(Array.from(c).length, 2);
});

test('item 2: frameFromAnalyser builds a frame and defaults the channel levels to 0', () => {
  const [f, g] = values('src/capture.js', [
    ['frameFromAnalyser', { db: [0, -20], sampleRate: 48000, time: 1.5, left: 0.25, right: 0.5 }],
    ['frameFromAnalyser', { db: [-20], sampleRate: 44100, time: 0 }],
  ]);
  assert.equal(f.time, 1.5);
  assert.equal(f.sampleRate, 48000);
  assert.equal(f.left, 0.25);
  assert.equal(f.right, 0.5);
  assert.equal(Array.from(f.magnitudes).length, 2);
  close(f.magnitudes[0], 1, 1e-6);
  close(f.magnitudes[1], 0.1, 1e-6);
  assert.equal(g.left, 0);
  assert.equal(g.right, 0);
});

test('item 3: detectSupport reads what the browser offers and never throws', () => {
  const got = ask('support');
  const wants = [
    { mic: false, display: false, file: true, record: false },
    { mic: false, display: false, file: true, record: false },
    { mic: true, display: false, file: true, record: false },
    { mic: false, display: true, file: true, record: false },
    { mic: true, display: true, file: true, record: true },
    { mic: false, display: false, file: true, record: true },
    { mic: false, display: false, file: true, record: false },
    { mic: false, display: false, file: true, record: false },
  ];
  const labels = ['{}', '{ navigator: {} }', 'getUserMedia only', 'getDisplayMedia only', 'all three', 'MediaRecorder only',
    'a getUserMedia that is not a function', '{ navigator: null }'];
  wants.forEach((want, i) => {
    assert.ok(got[i].ok, `detectSupport(${labels[i]}) threw ${got[i].error?.name}: ${got[i].error?.message}`);
    assert.deepEqual(got[i].value, want, labels[i]);
  });
});
