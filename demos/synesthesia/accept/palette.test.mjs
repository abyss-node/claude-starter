import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask, notRefused, values } from './helpers.mjs';

const TABLES = {
  wheel: [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330],
  fifths: [0, 210, 60, 270, 120, 330, 180, 30, 240, 90, 300, 150],
  ember: [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220],
};

test('item 6: PRESETS holds the three tables from the brief, each with a label', () => {
  const presets = ask('presets');
  for (const [name, hues] of Object.entries(TABLES)) {
    assert.ok(presets[name], `PRESETS has no "${name}"`);
    assert.deepEqual(presets[name].hues, hues, `PRESETS.${name}.hues`);
    assert.equal(typeof presets[name].label, 'string');
    assert.ok(presets[name].label.trim().length > 0, `PRESETS.${name}.label is empty`);
  }
});

test('item 6: hueForPitchClass gives the table entry for every pitch class, and wheel is the default', () => {
  const calls = [];
  const wants = [];
  for (const [name, hues] of Object.entries(TABLES)) {
    for (let pc = 0; pc < 12; pc++) { calls.push(['hueForPitchClass', pc, name]); wants.push([`${name} pitch class ${pc}`, hues[pc]]); }
  }
  for (let pc = 0; pc < 12; pc++) { calls.push(['hueForPitchClass', pc]); wants.push([`default preset, pitch class ${pc}`, TABLES.wheel[pc]]); }
  const got = values('src/palette.js', calls);
  wants.forEach(([label, want], i) => assert.equal(got[i], want, label));
});

test('item 6: hueForPitchClass throws RangeError for an unknown preset or a pitch class that is not 0 to 11', () => {
  const calls = [['hueForPitchClass', 0, 'nope'], ['hueForPitchClass', 0, 'toString']];
  for (const bad of [-1, 12, 1.5, NaN, '3', null, undefined]) calls.push(['hueForPitchClass', bad, 'wheel']);
  assert.deepEqual(notRefused('src/palette.js', calls), []);
});
