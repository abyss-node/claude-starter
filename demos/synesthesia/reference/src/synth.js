// Turns analysis frames into one visual state per frame. Pure: no DOM, no clock, no Math.random.

import { balance, chroma, estimateMode, loudness, spectralCentroid, strongestPitchClass } from './analysis.js';
import { PRESETS, hueForPitchClass } from './palette.js';
import { createOnsetDetector, estimateTempo } from './onsets.js';
import {
  MAX_BRIGHTNESS_SLEW,
  MAX_HUE_SLEW,
  MAX_ZOOM_SLEW,
  createFlashLimiter,
  slewHue,
  slewToward,
} from './safety.js';

export const PATTERN_COUNT = 6;
export const IDLE_LOUDNESS = 0.05;
export const IDLE_HOLD = 1.5; // seconds of quiet before the state counts as idle
export const PULSE_TAU = 0.15; // seconds
export const WARMTH_SLEW = 2; // per second
export const START_HUE = 220;
export const IDLE_BRIGHTNESS = 0.1;
export const IDLE_SPEED = 0.1;

const clamp01 = (x) => Math.min(1, Math.max(0, x));

// mulberry32: any whole number 0..4294967295 gives its own stream of floats in [0, 1).
export function createRng(seed) {
  let a = Number(seed) >>> 0;
  return function rng() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// 8 lowercase hex digits: FNV-1a over the state's JSON with sorted keys and numbers rounded to 6 places.
export function stateHash(state) {
  const text = JSON.stringify(state, (key, value) => {
    if (typeof value === 'number') return Math.round(value * 1e6) / 1e6;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return Object.fromEntries(Object.keys(value).sort().map((k) => [k, value[k]]));
    }
    return value;
  });
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

export function createSynth({ seed = 1, preset = 'wheel', limiter = true } = {}) {
  if (!Object.hasOwn(PRESETS, preset)) throw new RangeError(`unknown preset: ${String(preset)}`);
  const rng = createRng(seed);
  const detector = createOnsetDetector();
  const flashLimiter = createFlashLimiter();

  let presetName = preset;
  let limiterOn = Boolean(limiter);
  let lastTime = null;
  let lastLoud = -Infinity;
  let heldPitch = null;
  let onsetTimes = [];

  const s = {
    time: 0,
    idle: true,
    loudness: 0,
    centroid: 0,
    detail: 0,
    pitchClass: null,
    mode: null,
    preset: presetName,
    hue: START_HUE,
    warmth: 0,
    palette: 'neutral',
    brightness: IDLE_BRIGHTNESS,
    zoom: 1,
    pulse: 0,
    onsets: 0,
    flashes: 0,
    pattern: Math.floor(rng() * PATTERN_COUNT),
    tempo: 0,
    speed: IDLE_SPEED,
    phase: 0,
    drift: 0,
    limiter: limiterOn,
  };

  function nextPattern() {
    return (s.pattern + 1 + Math.floor(rng() * (PATTERN_COUNT - 1))) % PATTERN_COUNT;
  }

  function push(frame) {
    const given = Number(frame?.time);
    const t = lastTime === null ? (Number.isFinite(given) ? given : 0) : Math.max(lastTime, Number.isFinite(given) ? given : lastTime);
    const dt = lastTime === null ? 0 : t - lastTime;
    lastTime = t;

    const loud = loudness(frame);
    const quiet = loud < IDLE_LOUDNESS;
    if (!quiet) lastLoud = t;
    const idle = quiet && t - lastLoud >= IDLE_HOLD;
    const onset = detector.push(frame, t) && !quiet;

    s.pulse *= Math.exp(-dt / PULSE_TAU);
    if (onset) {
      s.onsets += 1;
      onsetTimes = [...onsetTimes, t].slice(-9);
      const allowed = limiterOn ? flashLimiter.allow(t) : (flashLimiter.note(t), true);
      if (allowed) {
        s.flashes += 1;
        s.pulse = 1;
        s.pattern = nextPattern();
      }
    }
    if (idle) onsetTimes = [];

    let mode = { mode: null, root: null };
    let pitchClass = null;
    if (!idle) {
      const c = chroma(frame);
      mode = estimateMode(c);
      pitchClass = mode.root ?? strongestPitchClass(c);
      if (pitchClass !== null) heldPitch = pitchClass;
    }

    const centroid = spectralCentroid(frame);
    const targetHue = heldPitch === null ? s.hue : hueForPitchClass(heldPitch, presetName);
    s.hue = limiterOn ? slewHue(s.hue, targetHue, MAX_HUE_SLEW * dt) : ((targetHue % 360) + 360) % 360;

    const targetWarmth = mode.mode === 'major' ? 1 : mode.mode === 'minor' ? -1 : 0;
    s.warmth = slewToward(s.warmth, targetWarmth, WARMTH_SLEW * dt);

    const targetBrightness = clamp01(IDLE_BRIGHTNESS + 0.6 * loud + 0.3 * s.pulse);
    s.brightness = limiterOn ? slewToward(s.brightness, targetBrightness, MAX_BRIGHTNESS_SLEW * dt) : targetBrightness;
    const targetZoom = 1 + 0.5 * loud;
    s.zoom = limiterOn ? slewToward(s.zoom, targetZoom, MAX_ZOOM_SLEW * dt) : targetZoom;

    s.tempo = idle ? 0 : estimateTempo(onsetTimes);
    s.speed = idle ? IDLE_SPEED : s.tempo > 0 ? s.tempo / 120 : 0.5;
    s.phase += s.speed * dt;

    s.time = t;
    s.idle = idle;
    s.loudness = loud;
    s.centroid = centroid;
    s.detail = idle || !(centroid > 0) ? 0 : clamp01(Math.log10(centroid / 100) / 2);
    s.pitchClass = pitchClass;
    s.mode = mode.mode;
    s.preset = presetName;
    s.palette = s.warmth > 0.3 ? 'warm' : s.warmth < -0.3 ? 'cool' : 'neutral';
    s.drift = idle ? 0 : balance(frame);
    s.limiter = limiterOn;
    return { ...s };
  }

  return {
    push,
    get state() {
      return { ...s };
    },
    get preset() {
      return presetName;
    },
    get limiter() {
      return limiterOn;
    },
    setPreset(name) {
      if (!Object.hasOwn(PRESETS, name)) throw new RangeError(`unknown preset: ${String(name)}`);
      presetName = name;
      s.preset = name;
    },
    setLimiter(on) {
      limiterOn = Boolean(on);
      s.limiter = limiterOn;
    },
  };
}
