import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask, runs, statesOf } from './helpers.mjs';

const SEEDS = [0, 1, 2, 7, 8, 255, 256, 65535, 65536, 65537, 999999, 4294967295];
const clicks = { t: 'clicks', bpm: 120, seconds: 8, fftSize: 2048, hop: 512 };
const hashes = (r) => {
  if (r.error) throw new Error(r.error);
  return r.hashes;
};

test('item 19: createRng gives floats in [0, 1), the same stream for the same seed, and its own stream for each seed', () => {
  const seen = new Map();
  for (const got of ask('rngStreams', SEEDS, 12)) {
    assert.equal(got.error, undefined, `seed ${got.seed}: ${got.error}`);
    assert.deepEqual(got.a, got.b, `seed ${got.seed} twice`);
    assert.ok(got.a.every((v) => typeof v === 'number' && v >= 0 && v < 1), `seed ${got.seed} stays in [0, 1)`);
    assert.ok(new Set(got.a).size > 8, `seed ${got.seed} repeats itself`);
    const key = got.a.slice(0, 6).join(',');
    assert.ok(!seen.has(key), `seeds ${seen.get(key)} and ${got.seed} give the same stream`);
    seen.set(key, got.seed);
  }
});

test('item 19: the same frames and the same seed give the same state hash, on every frame, run after run', () => {
  const job = (opts) => ({ frames: clicks, opts, hash: true, ambient: true });
  const [a, again, explicit, dflt, seed1] = runs(job({ seed: 42 }), job({ seed: 42 }), job({ seed: 42, limiter: true, preset: 'wheel' }), job({}), job({ seed: 1 })).map(hashes);
  assert.deepEqual(a, again);
  assert.deepEqual(a, explicit, 'the defaults are limiter on and the wheel preset');
  assert.deepEqual(dflt, seed1, 'the default seed is 1');
  assert.ok(new Set(a).size > 20, 'the hash changes as the state does');
});

test('item 19: different seeds give different runs (12 seeds, all different)', () => {
  const got = runs(...SEEDS.map((seed) => ({ frames: clicks, opts: { seed }, hash: true })));
  const whole = new Map();
  SEEDS.forEach((seed, i) => {
    const key = hashes(got[i]).join('');
    assert.ok(!whole.has(key), `seeds ${whole.get(key)} and ${seed} give the same run`);
    whole.set(key, seed);
  });
});

test('item 19: the seed changes the block patterns and nothing else about the picture', () => {
  const [a, b] = runs({ frames: clicks, opts: { seed: 3 } }, { frames: clicks, opts: { seed: 4 } }).map(statesOf);
  const strip = ({ pattern: _p, ...rest }) => rest;
  assert.deepEqual(a.map(strip), b.map(strip));
  assert.notDeepEqual(a.map((s) => s.pattern), b.map((s) => s.pattern));
});

test('item 19: stateHash is 8 hex digits, ignores key order, and changes when any field changes', () => {
  const p = ask('hashProbes', clicks, 9);
  assert.match(p.hash, /^[0-9a-f]{8}$/);
  assert.equal(p.copy, p.hash);
  assert.equal(p.reversed, p.hash, 'key order does not matter');
  for (const key of Object.keys(p.state)) assert.notEqual(p.changed[key], p.hash, `changing ${key} should change the hash`);
  assert.notEqual(p.tiny, p.hash, 'a change of 1e-4 shows (numbers are kept to 6 places)');
});

test('item 19: every push returns its own plain object: earlier states do not change and edits to one do not leak', () => {
  const o = ask('ownership', clicks);
  assert.equal(o.distinct, o.count, 'a fresh object per frame');
  assert.deepEqual(o.later, o.atReturn, 'a state does not change after it was returned');
  o.pairs.forEach(([sa, sb], i) => assert.deepEqual(sa, sb, `frame ${i}: an edit to an earlier returned state leaked into the synth`));
  assert.notEqual(o.hueAfterCopyEdit, -1, 'the state getter returns a copy');
});

// ------------------------------------------------------------------ item 20

test('item 20: whatever a frame holds, the state stays finite, in range and plain JSON (hostile input, 4 runs)', () => {
  const { constants } = ask('layout', ['src/synth.js']);
  const PATTERN_COUNT = constants.PATTERN_COUNT;
  const jobs = [];
  for (const limiter of [true, false]) for (const seed of [7, 8]) jobs.push({ opts: { limiter }, frames: { t: 'hostile', n: 700, seed } });
  runs(...jobs).forEach((r, j) => {
    const { limiter } = jobs[j].opts;
    let prev = null;
    statesOf(r).forEach((s, i) => {
      const where = `frame ${i} (limiter ${limiter}): ${JSON.stringify(s)}`;
      for (const [k, v] of Object.entries(s)) {
        if (typeof v === 'number') assert.ok(Number.isFinite(v), `${k} is not finite: ${where}`);
      }
      assert.deepEqual(JSON.parse(JSON.stringify(s)), s, `not plain JSON: ${where}`);
      const inRange = (k, lo, hi) => assert.ok(s[k] >= lo - 1e-9 && s[k] <= hi + 1e-9, `${k} out of range: ${where}`);
      inRange('loudness', 0, 1); inRange('detail', 0, 1); inRange('brightness', 0, 1); inRange('pulse', 0, 1);
      inRange('zoom', 1, 1.5); inRange('warmth', -1, 1); inRange('drift', -1, 1); inRange('speed', 0, 2);
      assert.ok(s.hue >= 0 && s.hue < 360, `hue ${s.hue}`);
      assert.ok(Number.isInteger(s.pattern) && s.pattern >= 0 && s.pattern < PATTERN_COUNT);
      assert.ok(s.pitchClass === null || (Number.isInteger(s.pitchClass) && s.pitchClass >= 0 && s.pitchClass < 12));
      assert.ok([null, 'major', 'minor'].includes(s.mode));
      assert.ok(['warm', 'cool', 'neutral'].includes(s.palette));
      assert.equal(typeof s.idle, 'boolean');
      assert.equal(s.limiter, limiter);
      assert.ok(s.tempo === 0 || (s.tempo >= 72 && s.tempo < 144), `tempo ${s.tempo}`);
      assert.ok(s.centroid >= 0);
      assert.ok(s.flashes <= s.onsets);
      if (prev) {
        assert.ok(s.time >= prev.time, 'time never goes backwards');
        assert.ok(s.phase >= prev.phase - 1e-12, 'phase never goes backwards');
        assert.ok(s.onsets >= prev.onsets && s.flashes >= prev.flashes && s.onsets - prev.onsets <= 1 && s.flashes - prev.flashes <= 1);
      }
      prev = s;
    });
  });
});

test('item 20: a frame with no magnitudes is silence, and a frame time that goes back or is missing counts as no time passing', () => {
  const raw = (...frames) => ({ t: 'raw', frames });
  const f = (time, magnitudes = []) => ({ time, sampleRate: 44100, magnitudes });
  const [seq, noTime, junk] = runs(
    { frames: raw(f(5), f(2), f(NaN)) },
    { frames: raw(f(undefined)) },
    { frames: raw(f(0, [NaN, Infinity, -4, 'a'])) },
  ).map(statesOf);
  const [a, b, c] = seq;
  assert.equal(a.loudness, 0);
  assert.equal(b.time, 5);
  assert.equal(c.time, 5);
  assert.equal(c.phase, a.phase);
  assert.equal(noTime[0].time, 0);
  assert.equal(junk[0].loudness, 0, 'magnitudes that are not finite and positive count as 0');
});
