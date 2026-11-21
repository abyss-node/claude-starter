// Pitch class (0 = C ... 9 = A ... 11 = B) to hue in degrees, per preset.

export const PRESETS = Object.freeze({
  wheel: Object.freeze({
    label: 'Chromatic wheel',
    hues: Object.freeze([0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]),
  }),
  fifths: Object.freeze({
    label: 'Circle of fifths',
    hues: Object.freeze([0, 210, 60, 270, 120, 330, 180, 30, 240, 90, 300, 150]),
  }),
  ember: Object.freeze({
    label: 'Ember to ice',
    hues: Object.freeze([0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220]),
  }),
});

export const PRESET_NAMES = Object.freeze(Object.keys(PRESETS));

export function hueForPitchClass(pitchClass, preset = 'wheel') {
  if (!Object.hasOwn(PRESETS, preset)) throw new RangeError(`unknown preset: ${String(preset)}`);
  if (!Number.isInteger(pitchClass) || pitchClass < 0 || pitchClass > 11) {
    throw new RangeError(`pitch class must be a whole number from 0 to 11, got ${String(pitchClass)}`);
  }
  return PRESETS[preset].hues[pitchClass];
}
