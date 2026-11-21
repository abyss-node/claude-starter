# Synesthesia: colour that follows sound

**Tier:** M, browser. **Expected:** one or two sessions. **Needs:** Node 22 or newer and Python 3 (only to serve the page). No npm packages.

## What to build

A full-screen page of live, trippy visuals driven by sound. The sound comes from one of three places: the **microphone**, **tab or device audio**, or an **audio file** you drop on the page. Pitch becomes colour, loudness becomes brightness and zoom, hits become pulses and a switch of block pattern, brightness of timbre becomes detail, major or minor becomes a warm or cool palette, tempo sets the speed of the motion, and the left/right balance makes the picture drift sideways.

Because it flashes in time with sound, a **photosensitivity limiter** is **on by default**, and the first time anyone opens the page a **warning** is shown before any sound source can be used.

Everything runs in the browser from plain files: ES modules, no build step, no npm packages, no images, sounds or fonts (draw on a canvas; nothing is loaded from the network). To try it, serve the folder (`python -m http.server 8000`, or `py -m http.server 8000` on Windows) and open http://localhost:8000.

- **Sources.** A **Microphone** button (`getUserMedia`), a **Tab or device audio** button (`getDisplayMedia` with audio: browsers differ a lot in whether and what they can share, so the page must say so in words), and an **Audio file** input plus drag-and-drop (decode it and play it while it is analysed). The page reads what the browser offers with `detectSupport` and greys out what it cannot do.
- **Colour presets.** A select that switches the pitch-to-hue table live (three are fixed below; add more if you like).
- **The limiter.** A checkbox, checked by default. Unchecking it is allowed but the page should say what that means.
- **Recording** (optional): a Record button that saves the canvas with `MediaRecorder`. The held-out check does not test it.
- Give your own names to anything you name. Genre feel only: nothing in this brief is a copy of an existing visualiser.

## Layout

The logic lives in plain ES modules so it can be tested with no browser, no DOM and no audio device. These names are fixed, because a test you cannot see imports them:

```
index.html        the page
src/analysis.js   binFrequency, chroma, loudness, spectralCentroid, balance, estimateMode
src/palette.js    PRESETS, hueForPitchClass
src/onsets.js     createOnsetDetector, estimateTempo
src/safety.js     MAX_FLASHES_PER_SECOND, MAX_BRIGHTNESS_SLEW, MAX_ZOOM_SLEW, MAX_HUE_SLEW, createFlashLimiter,
                  slewToward, slewHue, WARNING_KEY, WARNING_TEXT, shouldShowWarning, acknowledgeWarning
src/capture.js    magnitudesFromDb, frameFromAnalyser, detectSupport
src/synth.js      PATTERN_COUNT, createRng, createSynth, stateHash
package.json      already here; leave its "test" script alone
```

Anything else (`src/main.js`, drawing, capture glue) is yours to name. Each fixed module may export more than the names above.

### Frames

Every module that listens takes **analysis frames**: plain objects

```
{ time, sampleRate, magnitudes, left, right }
```

`time` is seconds. `magnitudes` is an array (or typed array) of **linear** FFT magnitudes, scaled so a sine of amplitude A gives a peak near A, for bins 0 to N-1 where N is its length (in a browser, an `AnalyserNode`'s `frequencyBinCount`). **Bin k is at `k * sampleRate / (2 * N)` Hz.** `left` and `right` are the RMS levels of the two channels (0 to 1) and may be missing. The tests use N of 256, 512, 1024, 2048 and 4096 at 44.1 and 48 kHz, and frame rates from about 20 to 200 a second: **work in seconds, never in frames, and never assume a size.** A magnitude that is not a finite number above 0 counts as 0.

### Analysis (`src/analysis.js`)

- `binFrequency(k, binCount, sampleRate)` is `k * sampleRate / (2 * binCount)`.
- `chroma(frame)` returns 12 numbers, energy per pitch class (0 = C, 9 = A, 11 = B). For every bin k from 1 up whose frequency f is from 55 to 4200 Hz inclusive, take the nearest semitone `n = round(12 * log2(f / 440))`, the pitch class `(n + 9) mod 12` (never negative), and add the bin's **magnitude squared** to it.
- `loudness(frame)`: let `level` be the square root of the sum of the squares of bins 1 and up; `dB = 20 * log10(max(level, 1e-9))`; loudness is `(dB + 60) / 60` limited to 0..1 (-60 dB is 0, 0 dB is 1). Silence is 0.
- `spectralCentroid(frame)` is the magnitude-weighted mean frequency of bins 1 and up, in Hz; 0 for silence.
- `balance(frame)` is `(right - left) / (right + left)`, from -1 to 1; 0 when both are 0 or missing. A level that is not a number, or is negative, counts as 0.
- `estimateMode(chromaVector)` returns `{ mode, root }`. Let `total` be the sum of the 12 values. For each root r from 0 to 11, a major triad scores `(c[r] + c[r+4] + c[r+7]) / total` and a minor triad `(c[r] + c[r+3] + c[r+7]) / total` (indexes mod 12). Take the best major score M (lowest root on a tie) and the best minor score m. If `M - m > 0.1` the answer is `{ mode: 'major', root }` with M's root; if `m - M > 0.1`, `{ mode: 'minor', root }` with m's root; otherwise `{ mode: null, root: null }`. A silent chroma, a missing one or a short one gives null.

### Colours (`src/palette.js`)

`PRESETS` is an object with at least these three entries, each `{ label, hues }` with a non-empty label and 12 hues in degrees, indexed by pitch class:

```
wheel   [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
fifths  [0, 210, 60, 270, 120, 330, 180, 30, 240, 90, 300, 150]
ember   [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220]
```

`hueForPitchClass(pitchClass, preset = 'wheel')` returns `PRESETS[preset].hues[pitchClass]`. It throws a `RangeError` for a preset that is not one of the entries (inherited names like `toString` included) and for a pitch class that is not a whole number from 0 to 11.

### Onsets and tempo (`src/onsets.js`)

- `createOnsetDetector()` returns `{ push(frame, time = frame.time) }`, which returns `true` when this frame starts an onset: a sudden rise in energy across the spectrum (a click, a drum hit, a tone starting). Spectral flux (the sum over bins of the increase since the last frame) against a moving threshold works. **Two onsets are never less than 0.1 s apart.** A held tone or steady noise must not keep firing.
- `estimateTempo(times)` takes onset times in seconds, ascending. It uses only the **last nine**; with fewer than four it returns 0. It takes the **median** gap between them, turns that into beats per minute (`60 / gap`) and then **doubles or halves until the value is in [72, 144)**.

### The synth (`src/synth.js`)

- `createSynth({ seed = 1, preset = 'wheel', limiter = true } = {})` returns `{ push(frame), state, preset, limiter, setPreset(name), setLimiter(on) }`. An unknown `preset` throws a `RangeError`, and so does `setPreset` (which then changes nothing).
- `push(frame)` takes one frame, in time order, and returns the **visual state** for it: a **new plain object each call**, JSON-safe, that nothing later changes. `state` (a getter) returns a copy of the latest one; before the first frame it is the starting state: idle, hue 220, brightness 0.1, zoom 1, pulse 0, no onsets or flashes, `phase` 0.
- `createRng(seed)` returns a function giving floats in [0, 1); the same seed gives the same stream and every whole number from 0 to 4294967295 gets its own stream. `stateHash(state)` returns 8 lower-case hex digits that depend on every field of the state (numbers to 6 decimal places, keys in any order). Never `Math.random`, `Date.now` or `performance.now` inside these modules.

The state has these fields. `dt` below is this frame's `time` minus the last one (0 for the first frame):

| field | meaning |
|---|---|
| `time` | seconds. Never goes backwards: a frame time earlier than the last one, or one that is not a finite number, counts as the last one (0 for the very first frame) |
| `idle` | true once the sound has been **quiet** (loudness below 0.05) for a hold of between 1 and 2 seconds without a break; true from the first frame when that frame is silent |
| `loudness`, `centroid` | from `loudness(frame)` and `spectralCentroid(frame)` |
| `detail` | `log10(centroid / 100) / 2` limited to 0..1 (100 Hz is 0, 10 kHz is 1); 0 when idle |
| `pitchClass` | 0..11 or null: the root of the triad `estimateMode(chroma(frame))` recognises, else the strongest class of `chroma(frame)`; null when idle or when there is no energy in range |
| `mode` | `'major'`, `'minor'` or null, from `estimateMode`; null when idle |
| `preset`, `limiter` | the current preset name and limiter setting |
| `hue` | degrees in [0, 360): the hue of the last pitch class seen in the current preset; 220 before any |
| `warmth`, `palette` | warmth moves toward +1 (major), -1 (minor) or 0 (anything else) by at most 2 per second; `palette` is `'warm'` above 0.3, `'cool'` below -0.3, else `'neutral'` |
| `brightness` | toward `min(1, 0.1 + 0.6 * loudness + 0.3 * pulse)` |
| `zoom` | toward `1 + 0.5 * loudness` |
| `pulse` | 1 on a flash frame, then fading: it only falls between flashes and is under 0.1 half a second later |
| `onsets`, `flashes` | counts since the start. Every onset heard while the sound is not quiet counts in `onsets`; a **flash** is an onset the limiter lets through. A flash makes `pulse` 1 and switches `pattern` |
| `pattern` | a whole number from 0 to `PATTERN_COUNT - 1`, the block layout. It is drawn from the seeded stream and, on every flash, changes to a different one; it changes at no other time |
| `tempo` | `estimateTempo` of the last nine onset times (0 when idle or with fewer than four) |
| `speed` | 0.1 when idle, `tempo / 120` when there is a tempo, 0.5 for sound with no tempo yet |
| `phase` | adds `speed * dt` each frame, starting at 0 |
| `drift` | `balance(frame)`; 0 when idle |

With the limiter **on**, `hue` turns at most `MAX_HUE_SLEW * dt` degrees a frame along the **shorter** arc, `brightness` moves at most `MAX_BRIGHTNESS_SLEW * dt` and `zoom` at most `MAX_ZOOM_SLEW * dt`, and a flash is only allowed if the limiter says so. With it **off**, hue, brightness and zoom jump to their targets in the same frame and every onset is a flash. `setLimiter` can switch it at any time.

### Safety (`src/safety.js`)

- `MAX_FLASHES_PER_SECOND` is 3, `MAX_BRIGHTNESS_SLEW` is 1.5 (per second), `MAX_ZOOM_SLEW` is 1.5 (per second) and `MAX_HUE_SLEW` is 240 (degrees per second). Together they are this page's reading of WCAG 2.3.1: no more than three flashes in any second, and no big luminance swings.
- `createFlashLimiter()` returns `{ allow(time), note(time) }`. `allow(time)` is true when no flash has been allowed in the last third of a second (the last allowed flash was at least `1 / 3` s ago, with a rounding allowance of 1e-9 s), and then records `time`; a refused call records nothing. `note(time)` records a flash that happened without asking.
- `slewToward(current, target, maxChange)` moves `current` toward `target` by at most `maxChange` (a negative `maxChange` counts as 0) and never past it.
- `slewHue(current, target, maxChange)` does the same along the shorter arc of the colour wheel and returns a hue in [0, 360).
- `WARNING_KEY` is the storage key (a non-empty string), `WARNING_TEXT` the warning shown on a first run. `shouldShowWarning(storage)` is true unless `storage.getItem(WARNING_KEY)` is `'yes'`; with no usable storage (missing, or a call throws) it is true. `acknowledgeWarning(storage)` stores `'yes'` and returns true, or returns false when it cannot; neither ever throws.

### Capture helpers (`src/capture.js`)

- `magnitudesFromDb(db)` turns an array of decibel values (what `getFloatFrequencyData` fills) into linear magnitudes `10 ** (dB / 20)`; `-Infinity`, NaN and anything that is not a finite number become 0. Same length.
- `frameFromAnalyser({ db, sampleRate, time, left = 0, right = 0 })` returns a frame.
- `detectSupport(env = globalThis)` returns at least `{ mic, display, file, record }`, all booleans: `mic` is true when `env.navigator.mediaDevices.getUserMedia` is a function, `display` the same for `getDisplayMedia`, `record` when `env.MediaRecorder` is a function, `file` always true. It never throws, whatever is missing.

### The page (`index.html`)

It loads its code with `<script type="module">` and has these elements, by id:

| id | what |
|---|---|
| `stage` | the `<canvas>` |
| `warning` | the first-run warning (shown in the markup; script hides it once acknowledged) |
| `warning-ok` | its `<button>` |
| `source-mic`, `source-tab` | `<button>`s |
| `source-file` | `<input type="file">` |
| `preset` | a `<select>` |
| `limiter` | `<input type="checkbox">`, **`checked` in the markup**, not disabled |
| `record` | a `<button>` |

No source may open before the warning has been acknowledged on a first run. The page's own code (`index.html` plus the modules it loads, apart from the six above) calls `createSynth`, `shouldShowWarning`, `acknowledgeWarning`, `getUserMedia` and `getDisplayMedia`. Your own modules may be `.js` or `.mjs` files, imported relative to the importing file (`./audio.js`) or from the root of the served folder (`/src/audio.js`); the held-out check follows both.

## Graded

A held-out check you cannot see grades this folder. Prose elsewhere in this brief describes the project and makes no extra promises: only the numbered contracts below are checked, and each is checked by at least one test. The tests build their own sounds (sines, chords, clicks, a strobe, noise) and turn them into frames with an FFT of their own.

1. **Layout.** The files exist and the six modules export the names under Layout; `MAX_FLASHES_PER_SECOND`, `MAX_BRIGHTNESS_SLEW`, `MAX_ZOOM_SLEW` and `MAX_HUE_SLEW` are 3, 1.5, 1.5 and 240; `PATTERN_COUNT` is a whole number from 3 to 12.
2. **dB to frames.** `magnitudesFromDb` gives `10 ** (dB / 20)` and 0 for non-finite values, same length; `frameFromAnalyser` builds `{ time, sampleRate, magnitudes, left, right }` with both levels defaulting to 0.
3. **Support.** `detectSupport` reports `mic`, `display`, `record` from what is a function and `file` as true, and does not throw on `{}`, `{ navigator: null }` or odd values.
4. **Bins and chroma.** `binFrequency` is `k * sampleRate / (2 * binCount)`. A sine on each of the 12 notes (and in three octaves, and at 48 kHz) puts at least 90% (85% at 48 kHz) of `chroma`'s energy in its own pitch class; energy below 55 Hz and above 4200 Hz is not counted; silence is all zeros; `chroma` adds magnitude squared.
5. **Mode.** `estimateMode` gives major or minor and the root for triads (C, D, A, F# minor, and so on), null for a single note, a fifth, silence or bad input, and keeps the margin: C-E-G with a half-strength E-flat is still major, with a 0.9-strength E-flat it is null; unequal triad notes still give the right root. A C major and a C minor triad built from sines are recognised through `chroma`.
6. **Presets.** The three tables above, exactly; `hueForPitchClass` reads them for every pitch class, defaults to `wheel`, and throws `RangeError` for unknown presets (inherited names too) and bad pitch classes.
7. **Pitch to hue.** A sine at A440 gives `pitchClass` 9 and, once the hue has settled, 270 (wheel), 90 (fifths) and 180 (ember); other notes land on their tables; `setPreset` switches the colour live and the state names the preset; an unknown preset throws and changes nothing; a recognised triad colours by its **root**, not its loudest note.
8. **Loudness.** `loudness` is the formula above (checked on single-bin frames, including clamping and that bin 0 is ignored); on a held tone `brightness` ends within 0.03 of `0.1 + 0.6 * loudness` and `zoom` within 0.03 of `1 + 0.5 * loudness`, and louder is brighter and closer; a tone near -40 dBFS is not idle.
9. **Centroid and detail.** `spectralCentroid` weights by magnitude (not energy), ignores bin 0 and uses the frame's sample rate; on held sines the state's `centroid` is within 3% of the frequency and `detail` within 0.03 of the formula (220 Hz about 0.17, 1 kHz 0.5, 4 kHz about 0.8), clamped to 0..1.
10. **Warm and cool.** Held C major triad: `mode` major, `palette` warm, `warmth` 1; C minor: minor, cool, -1; a single note: null, neutral, 0. `warmth` never moves faster than 2 per second, gets from warm to cool within 1.5 s, and the palette labels switch at +-0.3; silence returns it to 0.
11. **Idle.** Silence is idle from the first frame, with no onsets, flashes or pulse, brightness at most 0.35, zoom at most 1.05, speed above 0 and at most 0.2, and zero detail, tempo and drift, null pitch class and mode, neutral palette; faint noise (-60 dB and below) counts as silence; when music stops the state is idle within 2 s (and not while it plays), brightness drops to at most 0.35, and no flash happens in the silence.
12. **Onsets and pulses.** A click track at 120 BPM (4 ms noise bursts, frames from a 2048-point FFT every 512 samples) gives one onset and one flash per click (within 2 over 12 s), about every 0.5 s, each starting within 0.15 s after its click; the same at 90 and 140 BPM. On a flash `pulse` is 1 and `pattern` changes to a different one; between flashes the pattern holds and the pulse only fades, to under 0.1 before the next click; at least 3 different patterns show up. Onsets are at least 0.1 s apart; a held tone gives at most 2 onsets in 6 s, one that fades out over 0.3 s at most 2 in 5 s (only a rise counts), and steady noise at most 3.
13. **Tempo.** `estimateTempo`: the median gap of the last nine onsets, folded into [72, 144) (60 BPM gives 120, 240 gives 120, 150 gives 75, 30 gives 120), 0 with fewer than four onsets, robust to one odd gap, and four gaps of 0.5 then four of 0.4 give 60 / 0.45. In the synth a click track at 90, 120 and 135 BPM gives a `tempo` within 4 of it, `speed` equal to `tempo / 120`, no tempo before four onsets and no idle between clicks; a change from 120 to 90 BPM is followed; sound with no beat has `speed` 0.5; `phase` grows by `speed * dt` every frame.
14. **Stereo.** `balance` is `(right - left) / (right + left)` with 0, missing, non-finite and negative levels handled as above; `drift` is that balance (0.5 for a right channel three times the left, -0.5 the other way, 0 for mono, for frames without levels and when idle), both for hand-made levels and for two real channels.
15. **Limiter on by default.** `createSynth()` has `limiter` true, in the object and in the state. A 20 Hz strobe (1 kHz tone gated 25 ms on, 25 ms off, 512-point frames) over 10 s never has four flashes inside one second, still gets between 20 and 31 flashes (it is not blocked), and is heard as more onsets than flashes; a train of loud bursts five times a second is held to three a second too. On both signals an onset the limiter refuses shows nothing: `pulse` rises and `pattern` switches only on frames where `flashes` went up. `createFlashLimiter`: the first call is true (also at a negative time), a call less than a third of a second after the last allowed one is false and does not restart the clock, and 20 calls a second for 10 s let 25 to 31 through.
16. **Slew limits.** `slewToward` and `slewHue` do what the cases above say (short way round, no overshoot, wrapped result, 0 or negative limit stays put). With the limiter on and single notes held a second each, `hue` never turns faster than 240 degrees a second, does go that fast on a big jump, and reaches each new note's hue within 0.8 s (also a 60-degree jump the short way); with sound jumping between loud and silent every second, and on the strobe, `brightness` and `zoom` never move faster than 1.5 per second, and still follow the sound.
17. **Limiter off.** `createSynth({ limiter: false })` has `limiter` false; on the strobe it lets four flashes into one second and at some point six or more, and brightness moves faster than 1.5 per second; its first frame puts the hue exactly on its target (A440 on the wheel: 270) where a limited synth is still at 220. `setLimiter` changes `limiter` in the object and the state at once, and after switching on no four flashes fit in one second.
18. **First-run warning.** `shouldShowWarning` and `acknowledgeWarning` behave as above on a fake storage: true on a first run, false after acknowledging, true for any value but `'yes'` or when storage is missing or throws; `acknowledgeWarning` returns true when it saved and false when it could not. `WARNING_TEXT` is at least 80 characters and mentions flashing, photosensitivity (or epilepsy or seizures) and the limiter.
19. **Determinism.** `createRng` gives floats in [0, 1) and the same stream for the same seed, and a stream of its own for each of 12 seeds (0, 1, 2, 7, 8, 255, 256, 65535, 65536, 65537, 999999, 4294967295). The same frames and seed give the same `stateHash` on every frame, run after run, with `Math.random` and `Date.now` throwing; defaults are seed 1, limiter on, preset wheel; each of the 12 seeds gives a different run on a click track; **the seed changes the `pattern` field and nothing else**. `stateHash` is 8 hex digits, ignores key order and changes when any single field changes. Each `push` returns its own object that nothing changes afterwards, and edits to a returned state or to a copy from `state` do not reach the synth.
20. **Well-formed state.** On 2800 hostile frames (empty or odd-length magnitudes; NaN, infinite, negative, huge, missing or text values; sample rates that are missing, 0, negative or NaN; times going back, missing or NaN; levels that are NaN or text) with the limiter on and off, every number in the state is finite and in range (`loudness`, `detail`, `brightness`, `pulse` 0..1; `zoom` 1..1.5; `warmth`, `drift` -1..1; `speed` 0..2; `hue` in [0, 360); `centroid` 0 or more; `tempo` 0 or in [72, 144); `pattern` a whole number below `PATTERN_COUNT`; `pitchClass` null or 0..11), the state survives `JSON.parse(JSON.stringify(state))` unchanged, `time`, `phase`, `onsets` and `flashes` never go down, `onsets` and `flashes` rise by at most 1 a frame, `flashes` never exceeds `onsets`, and nothing throws.
21. **The page.** `index.html` has the elements in the table (right kind of tag, a file input for `source-file`, `limiter` a checkbox that is `checked` and not disabled, `warning` not hidden in the markup), a `<script type="module">` that loads a module from the workspace (a `.js` or `.mjs` file, written relative or from the root with a leading `/`, in the page or in a module it imports), and page-level code, found by following those imports, that calls `createSynth(`, `shouldShowWarning(`, `acknowledgeWarning(`, `getUserMedia(` and `getDisplayMedia(`. The ids are read from the tags themselves (quoting and attribute order do not matter); comments and script bodies are not searched for ids.

## Not graded

The brief describes these, or you might assume them, but the held-out check does not test them. They are yours to judge, in a browser or by reading.

- Whether the microphone, tab or device audio, or file path actually works: `getUserMedia`, `getDisplayMedia`, `decodeAudioData`, the `AnalyserNode` wiring, the permission prompts, and how each browser differs. The tests never touch audio hardware.
- How the visuals look or feel: the drawing, the colours, whether the block patterns are distinct, whether the motion matches the music, whether the picture is actually "trippy". The tests read the state, not the pixels.
- Whether the warning really shows on a first run and hides afterwards, whether sources stay disabled until it is acknowledged, and what the page says about browser support. The page tests read ids, attributes and the names the code calls.
- Recording with `MediaRecorder`.
- Real music: the pitch, mode and beat estimates are crude on anything but clean test signals, and the tests only use clean ones.
- Inputs the brief does not define: `createSynth` with a seed that is not a whole number; `push` with no frame at all; `estimateMode` with a vector of the wrong length beyond "short gives null"; `slewToward` with non-numbers; `createFlashLimiter` called with times going backwards.
- The exact onset algorithm, the pulse's fade constant (any fade that meets item 12 passes), the exact idle hold (between 1 and 2 s), the hash function and which small seeded generator `createRng` uses, as long as items 12, 11 and 19 hold.
- Working conditions: that `package.json`'s `test` script is left alone, that your own tests are under `tests/`, and the `python -m http.server` command.

## Your own tests

Write your own tests as you go, under `tests/`, and run them with `node --test tests/`. Build your own test sounds from sines and noise and your own FFT. `npm test` runs the kit's held-out check; do not change that script.

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->

## What to watch for

This demo exists to show the kit's chain working, not just to get a page built.

- **Your tests passing is not the check passing.** The held-out check was written by someone else against the rules above. If the agent says "done" on the strength of its own tests, ask whether the held-out check ran.
- **Grade it yourself** with the `demo check` line in step 5, not with `npm test`, which the agent can change. If the agent rewrites `test` in `package.json`, `npm test` can pass while that line still says `FAIL`. That line is feedback, not proof: the agent has a shell on this machine, as you do, and could tamper with the kit or the grade, so a measured run counts only after CI re-grades the committed folder (the kit's `demos/MEASURING.md`).
- **The safety claim is checkable, so check it.** A limiter that "should" cap flashes at three a second is a claim; the strobe test is the evidence. If the agent reports the limiter works, ask what signal it fed in and what it counted.
- **The verifier.** Before claiming done, the agent should hand the work to the verifier agent, which re-runs the check itself rather than trusting the summary. If it reports FAIL, that is the system working.
- **The checkpoint.** The commit should carry `Verified:` lines for what was actually run (with the PASS/FAIL count) and `Unverified:` lines for what was only reasoned about, such as "the visuals look right" or "the microphone works in Chrome". The commit guard rejects a commit without them.
- **Nothing outward without your yes.** No push, no repo creation, unless you say so.

## Try afterwards

1. Open it, pick **Audio file**, drop in a song you like, and watch how often the limiter holds a flash back. Then turn the limiter off on a short clip and see the difference (not if anyone watching is sensitive to flashing light).
2. Add a preset of your own and a second block pattern; the tests only need the first three presets to stay as they are.
3. Make the tempo estimate better than the median gap: try an autocorrelation of the onset strength, and see what it does on real music that the clean tests never exercise.
