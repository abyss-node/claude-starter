import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { ask, workspace } from './helpers.mjs';

const EXPORTS = {
  'src/analysis.js': ['binFrequency', 'chroma', 'loudness', 'spectralCentroid', 'balance', 'estimateMode'],
  'src/palette.js': ['PRESETS', 'hueForPitchClass'],
  'src/onsets.js': ['createOnsetDetector', 'estimateTempo'],
  'src/safety.js': [
    'MAX_FLASHES_PER_SECOND', 'MAX_BRIGHTNESS_SLEW', 'MAX_ZOOM_SLEW', 'MAX_HUE_SLEW', 'createFlashLimiter',
    'slewToward', 'slewHue', 'WARNING_KEY', 'WARNING_TEXT', 'shouldShowWarning', 'acknowledgeWarning',
  ],
  'src/capture.js': ['magnitudesFromDb', 'frameFromAnalyser', 'detectSupport'],
  'src/synth.js': ['PATTERN_COUNT', 'createRng', 'createSynth', 'stateHash'],
};

const layout = () => ask('layout', Object.keys(EXPORTS));

test('item 1: the files exist and the modules export the fixed names', () => {
  assert.ok(existsSync(join(workspace(), 'index.html')), 'index.html is missing');
  for (const file of Object.keys(EXPORTS)) assert.ok(existsSync(join(workspace(), file)), `${file} is missing`);
  const { modules } = layout();
  for (const [file, names] of Object.entries(EXPORTS)) {
    assert.equal(modules[file].error, undefined, `${file} did not load: ${modules[file].error}`);
    for (const name of names) assert.ok(modules[file].names.includes(name), `${file} does not export ${name}`);
  }
});

test('item 1: the limiter constants have the values the brief gives', () => {
  const { constants: c } = layout();
  assert.equal(c.MAX_FLASHES_PER_SECOND, 3);
  assert.equal(c.MAX_BRIGHTNESS_SLEW, 1.5);
  assert.equal(c.MAX_ZOOM_SLEW, 1.5);
  assert.equal(c.MAX_HUE_SLEW, 240);
  assert.ok(Number.isInteger(c.PATTERN_COUNT) && c.PATTERN_COUNT >= 3 && c.PATTERN_COUNT <= 12, 'PATTERN_COUNT should be a whole number from 3 to 12');
});
