import { test } from 'node:test';
import assert from 'node:assert/strict';
import { close, hueDistance, runs, statesOf } from './helpers.mjs';
import { NOTE } from './signals.mjs';

const tone = (parts, seconds = 3) => ({ t: 'tone', parts, seconds });
const A440 = tone([[440, 0.5]]);
const triad = (...freqs) => tone(freqs.map((f) => [f, 0.2]));
const CMAJ = triad(NOTE.C4, NOTE.E4, NOTE.G4);
const CMIN = triad(NOTE.C4, NOTE.Eb4, NOTE.G4);
const last = (job) => statesOf(runs(job)[0]).at(-1);

test('item 7: a sine at A440 gives pitch class 9 and the A hue of each preset', () => {
  const want = { wheel: 270, fifths: 90, ember: 180 };
  for (const [preset, hue] of Object.entries(want)) {
    const s = last({ frames: A440, opts: { preset } });
    assert.equal(s.pitchClass, 9, `${preset}: pitch class`);
    assert.equal(s.preset, preset);
    close(hueDistance(s.hue, hue), 0, 1, `${preset}: hue ${s.hue} should be ${hue}`);
    assert.ok(s.hue >= 0 && s.hue < 360);
  }
  const dflt = last({ frames: A440 });
  assert.equal(dflt.preset, 'wheel', 'wheel is the default preset');
  close(hueDistance(dflt.hue, 270), 0, 1);
});

test('item 7: other notes land on their own hues (C major scale degrees on the wheel and the fifths)', () => {
  const cases = [
    ['wheel', NOTE.C4, 0], ['wheel', NOTE.Eb4, 90], ['wheel', NOTE.Gb4, 180], ['wheel', NOTE.B4, 330],
    ['fifths', NOTE.Db4, 210], ['fifths', NOTE.G4, 30], ['fifths', NOTE.Eb4, 270],
  ];
  const got = runs(...cases.map(([preset, freq]) => ({ frames: tone([[freq, 0.5]]), opts: { preset } })));
  cases.forEach(([preset, freq, hue], i) => {
    const s = statesOf(got[i]).at(-1);
    close(hueDistance(s.hue, hue), 0, 1, `${preset} ${freq} Hz: hue ${s.hue} should be ${hue}`);
  });
});

test('item 7: setPreset switches the colour live; the state names the preset; an unknown preset is refused', () => {
  const [r, bad] = runs(
    {
      opts: { preset: 'wheel' },
      steps: [
        { push: A440 }, { read: 'before' }, { setPreset: 'fifths' }, { read: 'switched' },
        { push: A440, after: 0 }, { setPreset: 'nope' }, { read: 'refused' },
      ],
    },
    { opts: { preset: 'nope' }, frames: A440 },
  );
  const reads = Object.fromEntries(r.reads.map((x) => [x.label, x]));
  close(hueDistance(reads.before.state.hue, 270), 0, 1);
  assert.equal(reads.before.preset, 'wheel');
  assert.equal(reads.switched.preset, 'fifths');
  assert.equal(reads.switched.state.preset, 'fifths');
  const [from, to] = r.segments[1];
  const end = r.states[to - 1];
  assert.equal(end.preset, 'fifths');
  assert.ok(from < to);
  close(hueDistance(end.hue, 90), 0, 1, 'after the switch the hue follows the new table');
  assert.equal(r.ops[1].threw?.range, true, 'setPreset with an unknown preset throws a RangeError');
  assert.equal(reads.refused.preset, 'fifths', 'a refused preset changes nothing');
  assert.equal(bad.createError?.range, true, 'createSynth with an unknown preset throws a RangeError');
});

test('item 7: a recognised triad colours by its root, not by its loudest note', () => {
  const cmaj = last({ frames: CMAJ });
  assert.equal(cmaj.pitchClass, 0);
  close(hueDistance(cmaj.hue, 0), 0, 1);
  // D minor (D F A) with A the strongest of the three: the root D (pitch class 2) wins.
  const dmin = last({ frames: tone([[293.6648, 0.25], [349.2282, 0.2], [440, 0.3]]) });
  assert.equal(dmin.mode, 'minor');
  assert.equal(dmin.pitchClass, 2, 'the root of the triad, not its strongest note');
  close(hueDistance(dmin.hue, 60), 0, 1);
});

test('item 10: a C major triad reads warm and a C minor triad reads cool', () => {
  const maj = last({ frames: CMAJ });
  assert.equal(maj.mode, 'major');
  assert.equal(maj.palette, 'warm');
  close(maj.warmth, 1, 0.01, 'warmth of a major triad');
  const min = last({ frames: CMIN });
  assert.equal(min.mode, 'minor');
  assert.equal(min.palette, 'cool');
  close(min.warmth, -1, 0.01, 'warmth of a minor triad');
  const single = last({ frames: A440 });
  assert.equal(single.mode, null);
  assert.equal(single.palette, 'neutral');
  close(single.warmth, 0, 0.01, 'a single note is neither');
});

test('item 10: warmth moves toward +1, -1 or 0 by at most 2 per second, and gets there within 1.5 s', () => {
  const r = runs({ steps: [{ push: CMAJ }, { push: CMIN, after: 0 }] })[0];
  const states = statesOf(r);
  for (let i = 1; i < states.length; i++) {
    const dt = states[i].time - states[i - 1].time;
    assert.ok(Math.abs(states[i].warmth - states[i - 1].warmth) <= 2 * dt + 1e-9, `warmth moved ${states[i].warmth - states[i - 1].warmth} in ${dt} s`);
  }
  const switchAt = states[r.segments[0][1] - 1].time;
  const lateMin = states.filter((s) => s.time >= switchAt + 1.5 + 0.2);
  assert.ok(lateMin.length > 0);
  assert.ok(lateMin.every((s) => s.palette === 'cool' && s.warmth <= -0.99), 'cool within 1.5 s of the change to minor');
  assert.ok(states.filter((s) => Math.abs(s.warmth) < 0.3).every((s) => s.palette === 'neutral'), 'a warmth between -0.3 and 0.3 is neutral');
  assert.ok(states.filter((s) => s.warmth > 0.3).every((s) => s.palette === 'warm'));
  assert.ok(states.filter((s) => s.warmth < -0.3).every((s) => s.palette === 'cool'));
});

test('item 10: silence ends a warm palette: warmth goes back to 0', () => {
  const states = statesOf(runs({ steps: [{ push: CMAJ }, { push: { t: 'silence', seconds: 3 }, after: 0.05 }] })[0]);
  assert.equal(states.at(-1).palette, 'neutral');
  close(states.at(-1).warmth, 0, 0.01);
});
