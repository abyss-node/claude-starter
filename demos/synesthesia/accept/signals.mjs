// The held-out checks' own sounds and their FFT. Nothing here touches the workspace: the tests import it to work
// out what a right answer is, and scenarios.mjs imports it to build the frames that go to the workspace's code
// (a process of its own, demos/probe.mjs), so a large frame never has to travel on a command line.
//
// framesOf(spec) turns a small plain description into frames, so a test can name a sound in a few fields and a
// scenario can rebuild it on the other side.

export const SR = 44100;

// ---------------------------------------------------------------- the FFT the tests use

const fftCache = new Map();
function plan(n) {
  let p = fftCache.get(n);
  if (p) return p;
  const cos = new Float64Array(n / 2);
  const sin = new Float64Array(n / 2);
  for (let i = 0; i < n / 2; i++) {
    cos[i] = Math.cos((2 * Math.PI * i) / n);
    sin[i] = -Math.sin((2 * Math.PI * i) / n);
  }
  const rev = new Uint32Array(n);
  const bits = Math.log2(n);
  for (let i = 0; i < n; i++) {
    let r = 0;
    for (let b = 0; b < bits; b++) if (i & (1 << b)) r |= 1 << (bits - 1 - b);
    rev[i] = r;
  }
  const hann = new Float64Array(n);
  let sum = 0;
  for (let i = 0; i < n; i++) {
    hann[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / n);
    sum += hann[i];
  }
  p = { cos, sin, rev, hann, sum };
  fftCache.set(n, p);
  return p;
}

// Linear magnitudes of bins 0..n/2-1 of a Hann-windowed n-point FFT, scaled so that a sine of
// amplitude A gives a peak of about A.
function spectrum(samples, end, n) {
  const { cos, sin, rev, hann, sum } = plan(n);
  const re = new Float64Array(n);
  const im = new Float64Array(n);
  const start = end - n;
  for (let i = 0; i < n; i++) re[rev[i]] = samples[start + i] * hann[i];
  for (let size = 2; size <= n; size <<= 1) {
    const half = size >> 1;
    const step = n / size;
    for (let i = 0; i < n; i += size) {
      for (let j = 0, k = 0; j < half; j++, k += step) {
        const a = i + j;
        const b = a + half;
        const tr = re[b] * cos[k] - im[b] * sin[k];
        const ti = re[b] * sin[k] + im[b] * cos[k];
        re[b] = re[a] - tr;
        im[b] = im[a] - ti;
        re[a] += tr;
        im[a] += ti;
      }
    }
  }
  const out = new Array(n / 2);
  for (let k = 0; k < n / 2; k++) out[k] = (2 * Math.hypot(re[k], im[k])) / sum;
  return out;
}

function rmsOf(samples, end, n) {
  let s = 0;
  for (let i = end - n; i < end; i++) s += samples[i] * samples[i];
  return Math.sqrt(s / n);
}

// Builds `seconds` of audio, sample by sample, from fn(t) -> number.
export function makeSignal(seconds, fn, sampleRate = SR) {
  const out = new Float64Array(Math.round(seconds * sampleRate));
  for (let i = 0; i < out.length; i++) out[i] = fn(i / sampleRate);
  return out;
}

// One frame per hop, each from the trailing fftSize samples. `right` defaults to `left`.
export function framesFrom(left, { right = left, sampleRate = SR, fftSize = 8192, hop = 2048 } = {}) {
  const mono = left === right ? left : left.map((v, i) => (v + right[i]) / 2);
  const frames = [];
  for (let end = fftSize; end <= mono.length; end += hop) {
    frames.push({
      time: end / sampleRate,
      sampleRate,
      magnitudes: spectrum(mono, end, fftSize),
      left: rmsOf(left, end, fftSize),
      right: rmsOf(right, end, fftSize),
    });
  }
  return frames;
}

// ---------------------------------------------------------------- signals

export const sine = (freq, amp = 0.5) => (t) => amp * Math.sin(2 * Math.PI * freq * t);
export const sum = (...fns) => (t) => fns.reduce((s, f) => s + f(t), 0);

export const NOTE = {
  C4: 261.6256, Db4: 277.1826, D4: 293.6648, Eb4: 311.1270, E4: 329.6276, F4: 349.2282,
  Gb4: 369.9944, G4: 391.9954, Ab4: 415.3047, A4: 440, Bb4: 466.1638, B4: 493.8833,
};

export function seededNoise(seed = 1) {
  let x = seed >>> 0;
  return () => {
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    return (x / 4294967296) * 2 - 1;
  };
}

// The instants at which clickTrack puts a burst.
export function clickTimes(bpm, seconds) {
  const times = [];
  for (let t = 0.25; t + 0.01 < seconds; t += 60 / bpm) times.push(t);
  return times;
}

// Short broadband bursts (4 ms of noise, fading out) at 0.25 s + k * 60/bpm.
export function clickTrack(bpm, seconds, { amp = 0.8, sampleRate = SR } = {}) {
  const out = new Float64Array(Math.round(seconds * sampleRate));
  const noise = seededNoise(99);
  const len = Math.round(0.004 * sampleRate);
  for (const t of clickTimes(bpm, seconds)) {
    const at = Math.round(t * sampleRate);
    for (let i = 0; i < len; i++) out[at + i] = amp * noise() * (1 - i / len);
  }
  return out;
}

// A 1 kHz tone gated 20 times a second (25 ms on, 25 ms off).
export function strobeSignal(seconds, { amp = 0.8, sampleRate = SR } = {}) {
  return makeSignal(seconds, (t) => (Math.floor(t * 40) % 2 === 0 ? amp * Math.sin(2 * Math.PI * 1000 * t) : 0), sampleRate);
}

// Frames built directly (no audio): `bins` maps bin index -> magnitude.
export function frameWithBins(binCount, bins, time, { sampleRate = SR, left, right } = {}) {
  const magnitudes = new Array(binCount).fill(0);
  for (const [k, v] of Object.entries(bins)) magnitudes[Number(k)] = v;
  const f = { time, sampleRate, magnitudes };
  if (left !== undefined) f.left = left;
  if (right !== undefined) f.right = right;
  return f;
}

export function binFor(freq, binCount, sampleRate = SR) {
  return Math.round((freq * 2 * binCount) / sampleRate);
}

// Bin k of N magnitudes is at k * sampleRate / (2N) Hz.
export const binHz = (k, binCount, sampleRate) => (k * sampleRate) / (2 * binCount);

// `seconds` of zero spectrum, one frame every `hop` seconds, starting at `from`.
export function silenceFrames(seconds, from = 0, { hop = 0.0464, bins = 4096, sampleRate = SR } = {}) {
  const out = [];
  for (let t = 0; t < seconds; t += hop) out.push(frameWithBins(bins, {}, from + t, { sampleRate }));
  return out;
}

// The brief's loudness formula, for a frame: the level of bins 1 and up in dB, -60 dB (0) to 0 dB (1).
export function expectedLoudness(frame) {
  let s = 0;
  for (let k = 1; k < frame.magnitudes.length; k++) s += frame.magnitudes[k] * frame.magnitudes[k];
  return Math.min(1, Math.max(0, (20 * Math.log10(Math.max(Math.sqrt(s), 1e-9)) + 60) / 60));
}

// ---------------------------------------------------------------- hostile frames

function lcg(seed) {
  let x = seed >>> 0;
  return () => {
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    return x / 4294967296;
  };
}

// Frames made to break a careless synth: empty and odd-length magnitudes, NaN, infinite, negative, huge, missing
// and text values, bad sample rates, times that go back or are missing, and levels that are not numbers.
function hostileFrames(n, seed) {
  const r = lcg(seed);
  const pick = (xs) => xs[Math.floor(r() * xs.length)];
  const lengths = [0, 1, 2, 17, 512, 4096];
  const weird = [NaN, Infinity, -Infinity, -3, 1e12, undefined, 'abc', null, 0, 1e-12];
  const frames = [];
  let t = 0;
  for (let i = 0; i < n; i++) {
    const len = pick(lengths);
    const magnitudes = Array.from({ length: len }, () => (r() < 0.15 ? pick(weird) : r() < 0.4 ? 0 : r() * (r() < 0.2 ? 2 : 0.02)));
    t += r() < 0.1 ? -r() : 0.005 + r() * 0.03;
    const timeValue = r() < 0.05 ? pick([NaN, undefined, Infinity, 'x']) : t;
    const frame = { time: timeValue, sampleRate: r() < 0.15 ? pick([undefined, 0, NaN, -5, 1e9]) : pick([44100, 48000, 22050]), magnitudes };
    if (r() < 0.7) { frame.left = r() < 0.2 ? pick(weird) : r(); frame.right = r() < 0.2 ? pick(weird) : r(); }
    frames.push(frame);
  }
  return frames;
}

// ---------------------------------------------------------------- sounds by description

const FREQS_BY_CLASS = [NOTE.C4, NOTE.Db4, NOTE.D4, NOTE.Eb4, NOTE.E4, NOTE.F4, NOTE.Gb4, NOTE.G4, NOTE.Ab4, 440, NOTE.Bb4, NOTE.B4];
const partsFn = (parts) => sum(...parts.map(([freq, amp]) => sine(freq, amp)));

/**
 * The frames a description stands for. `t` says what kind:
 *   tone     parts [[hz, amp], ...], seconds (3 by default; the sound is a little longer so the last frame is whole),
 *            or samples (an exact length); fftSize, hop, sampleRate
 *   stereo   left and right parts, seconds
 *   noise    amp, seed, seconds
 *   clicks   bpm, seconds
 *   strobe   seconds
 *   fade     a 440 Hz tone that fades out over 0.3 s starting at 3 s
 *   silence  seconds, from
 *   bins     binCount, bins { k: magnitude }, time, sampleRate: one frame
 *   holds    pcs, amp, bins: each pitch class held a second, one single-bin frame every 10 ms
 *   jumps    loud and silent in turn, a second each
 *   bursts   a loud burst train, five a second
 *   hostile  n, seed
 *   levels   of, left, right: the same frames with these channel levels
 *   bare     of: the same frames without channel levels
 *   raw      frames: as given
 */
export function framesOf(spec) {
  const opts = {};
  for (const key of ['fftSize', 'hop', 'sampleRate']) if (spec[key] !== undefined) opts[key] = spec[key];
  switch (spec.t) {
    case 'raw':
      return spec.frames;
    case 'tone': {
      const fn = partsFn(spec.parts);
      const samples = spec.samples === undefined
        ? makeSignal((spec.seconds ?? 3) + 0.2, fn, opts.sampleRate)
        : Float64Array.from({ length: spec.samples }, (_, i) => fn(i / (opts.sampleRate ?? SR)));
      return framesFrom(samples, opts);
    }
    case 'stereo':
      return framesFrom(makeSignal(spec.seconds, partsFn(spec.left)), { ...opts, right: makeSignal(spec.seconds, partsFn(spec.right)) });
    case 'noise': {
      const noise = seededNoise(spec.seed);
      return framesFrom(makeSignal(spec.seconds, () => spec.amp * noise()), opts);
    }
    case 'clicks':
      return framesFrom(clickTrack(spec.bpm, spec.seconds), opts);
    case 'strobe':
      return framesFrom(strobeSignal(spec.seconds), opts);
    case 'fade': {
      const fade = (t) => 0.5 * Math.sin(2 * Math.PI * 440 * t) * Math.min(1, Math.max(0, (3.3 - t) / 0.3));
      return framesFrom(makeSignal(5, fade), { fftSize: 8192, hop: 2048 });
    }
    case 'silence':
      return silenceFrames(spec.seconds, spec.from ?? 0);
    case 'bins':
      return [frameWithBins(spec.binCount, spec.bins, spec.time ?? 0, { sampleRate: spec.sampleRate ?? SR })];
    case 'holds': {
      const bins = spec.bins ?? 4096;
      const frames = [];
      spec.pcs.forEach((pc, n) => {
        for (let i = 0; i < 100; i++) frames.push(frameWithBins(bins, { [binFor(FREQS_BY_CLASS[pc], bins)]: spec.amp ?? 0.5 }, n + i * 0.01));
      });
      return frames;
    }
    case 'jumps': {
      const frames = [];
      for (let i = 0; i < 800; i++) {
        const t = i * 0.01;
        frames.push(frameWithBins(2048, Math.floor(t / 1) % 2 === 0 ? { 50: 0.5, 120: 0.4 } : {}, t));
      }
      return frames;
    }
    case 'bursts': {
      const frames = [];
      for (let i = 0; i < 1500; i++) {
        const t = i * 0.005;
        const on = Math.floor(t / 0.1) % 2 === 0 && t % 0.2 < 0.03;
        frames.push(frameWithBins(512, on ? { 40: 0.8, 90: 0.8, 200: 0.8 } : {}, t));
      }
      return frames;
    }
    case 'hostile':
      return hostileFrames(spec.n, spec.seed);
    case 'levels':
      return framesOf(spec.of).map((f) => ({ ...f, left: spec.left, right: spec.right }));
    case 'bare':
      return framesOf(spec.of).map(({ left: _l, right: _r, ...rest }) => rest);
    default:
      throw new Error(`framesOf: unknown sound ${JSON.stringify(spec.t)}`);
  }
}

// One frame of a description (the first), for a call that takes a single frame.
export const oneFrame = (spec) => framesOf(spec)[0];
