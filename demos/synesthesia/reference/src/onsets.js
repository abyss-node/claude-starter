// Onset detection (spectral flux against a moving threshold) and tempo from onset times.

import { cleanMagnitudes } from './analysis.js';

export const MIN_ONSET_GAP = 0.1; // seconds
export const FLUX_FLOOR = 0.05;
export const FLUX_WINDOW = 1; // seconds of history for the moving threshold
export const FLUX_RATIO = 2;
export const TEMPO_MIN = 72;
export const TEMPO_MAX = 144;

export function createOnsetDetector() {
  let prev = null;
  let lastOnset = -Infinity;
  let history = []; // { time, flux }

  return {
    // True when this frame starts an onset. `time` defaults to frame.time.
    push(frame, time = frame?.time) {
      const m = cleanMagnitudes(frame);
      if (!prev || prev.length !== m.length) prev = new Float64Array(m.length);
      let flux = 0;
      for (let k = 1; k < m.length; k++) flux += Math.max(0, m[k] - prev[k]);
      prev = m;
      const t = Number.isFinite(time) ? time : 0;

      history = history.filter((h) => h.time > t - FLUX_WINDOW);
      const mean = history.length ? history.reduce((s, h) => s + h.flux, 0) / history.length : 0;
      const threshold = Math.max(FLUX_FLOOR, FLUX_RATIO * mean);
      const hit = flux > threshold && t - lastOnset >= MIN_ONSET_GAP;
      history.push({ time: t, flux });
      if (hit) lastOnset = t;
      return hit;
    },
  };
}

// Beats per minute from the last nine onset times (seconds, ascending): the median gap, folded by
// doubling or halving into [72, 144). 0 when there are fewer than four onsets.
export function estimateTempo(times) {
  const ts = (Array.isArray(times) ? times : Array.from(times ?? [])).filter(Number.isFinite).slice(-9);
  if (ts.length < 4) return 0;
  const gaps = [];
  for (let i = 1; i < ts.length; i++) gaps.push(ts[i] - ts[i - 1]);
  gaps.sort((a, b) => a - b);
  const mid = gaps.length >> 1;
  const median = gaps.length % 2 ? gaps[mid] : (gaps[mid - 1] + gaps[mid]) / 2;
  if (!(median > 0)) return 0;
  let bpm = 60 / median;
  while (bpm < TEMPO_MIN) bpm *= 2;
  while (bpm >= TEMPO_MAX) bpm /= 2;
  return bpm;
}
