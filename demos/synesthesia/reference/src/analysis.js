// Pure analysis of one frame: { time, sampleRate, magnitudes, left?, right? }.
// Bin k of a frame with N magnitudes sits at k * sampleRate / (2 * N) Hz.

export const MIN_PITCH_HZ = 55;
export const MAX_PITCH_HZ = 4200;
export const MODE_MARGIN = 0.1;

const DEFAULT_RATE = 44100;

export function binFrequency(k, binCount, sampleRate) {
  return (k * sampleRate) / (2 * binCount);
}

function rateOf(frame) {
  const r = Number(frame?.sampleRate);
  return Number.isFinite(r) && r > 0 ? r : DEFAULT_RATE;
}

// Finite, non-negative magnitudes; anything else counts as 0.
export function cleanMagnitudes(frame) {
  const raw = frame?.magnitudes;
  const n = raw && Number.isFinite(raw.length) ? raw.length : 0;
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const v = Number(raw[i]);
    out[i] = Number.isFinite(v) && v > 0 ? v : 0;
  }
  return out;
}

export function chroma(frame) {
  const m = cleanMagnitudes(frame);
  const rate = rateOf(frame);
  const out = new Array(12).fill(0);
  for (let k = 1; k < m.length; k++) {
    const f = binFrequency(k, m.length, rate);
    if (f < MIN_PITCH_HZ || f > MAX_PITCH_HZ) continue;
    const semitones = Math.round(12 * Math.log2(f / 440));
    const pc = (((semitones + 9) % 12) + 12) % 12;
    out[pc] += m[k] * m[k];
  }
  return out;
}

export function loudness(frame) {
  const m = cleanMagnitudes(frame);
  let sum = 0;
  for (let k = 1; k < m.length; k++) sum += m[k] * m[k];
  const db = 20 * Math.log10(Math.max(Math.sqrt(sum), 1e-9));
  return Math.min(1, Math.max(0, (db + 60) / 60));
}

export function spectralCentroid(frame) {
  const m = cleanMagnitudes(frame);
  const rate = rateOf(frame);
  let weighted = 0;
  let total = 0;
  for (let k = 1; k < m.length; k++) {
    weighted += binFrequency(k, m.length, rate) * m[k];
    total += m[k];
  }
  return total > 0 ? weighted / total : 0;
}

function level(v) {
  const x = Number(v);
  return Number.isFinite(x) && x > 0 ? x : 0;
}

export function balance(frame) {
  const l = level(frame?.left);
  const r = level(frame?.right);
  return l + r > 1e-9 ? (r - l) / (r + l) : 0;
}

export function estimateMode(chromaVector) {
  const c = Array.from({ length: 12 }, (_, i) => level(chromaVector?.[i]));
  const total = c.reduce((a, b) => a + b, 0);
  if (!(total > 1e-12)) return { mode: null, root: null };
  let major = { score: -1, root: null };
  let minor = { score: -1, root: null };
  for (let r = 0; r < 12; r++) {
    const fifth = c[(r + 7) % 12];
    const maj = (c[r] + c[(r + 4) % 12] + fifth) / total;
    const min = (c[r] + c[(r + 3) % 12] + fifth) / total;
    if (maj > major.score) major = { score: maj, root: r };
    if (min > minor.score) minor = { score: min, root: r };
  }
  if (major.score - minor.score > MODE_MARGIN) return { mode: 'major', root: major.root };
  if (minor.score - major.score > MODE_MARGIN) return { mode: 'minor', root: minor.root };
  return { mode: null, root: null };
}

export function strongestPitchClass(chromaVector) {
  let best = null;
  let bestEnergy = 0;
  for (let i = 0; i < 12; i++) {
    const e = level(chromaVector?.[i]);
    if (e > bestEnergy) {
      bestEnergy = e;
      best = i;
    }
  }
  return best;
}
