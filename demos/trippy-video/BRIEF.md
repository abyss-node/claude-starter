# Fever Loops: a trippy maths video generator

**Tier:** M (medium). **Stack:** Python 3.9 or newer, standard library only.
**Expected:** one session, perhaps two. That is an estimate, not a measurement.

Build a command-line tool that turns a number (the seed) into a short,
looping, psychedelic animation made of maths, saved as numbered PNG frames.
The same seed always gives exactly the same frames. Run without a seed and it
picks a random one and tells you which, so a video you like can be made again. With ffmpeg installed it
can also stitch the frames into an MP4.

There is nothing to install. PNG files are written by hand with `zlib` and
`struct`; no numpy, no Pillow, nothing from pip.

## What to build

One entry point at the top of this folder: `trippy.py`. A stub is already
there; replace it. You may split the code into more modules next to it.

```
python trippy.py --seed 7 --width 320 --height 180 --fps 12 --seconds 4 --palette ember --loop --out frames
```

| Flag | Meaning | Default |
|---|---|---|
| `--seed N` | any whole number (0 and negative numbers included); picks the building blocks and their settings | a random seed, printed (see below) |
| `--width W`, `--height H` | frame size in pixels | 320, 180 |
| `--fps F` | frames per second, a whole number | 12 |
| `--seconds S` | length; decimals allowed | 4 |
| `--palette P` | a palette name, or a comma-separated list of hex colours | `acid` |
| `--loop` | make the video one seamless cycle | off |
| `--out DIR` | folder for the frames, created if missing | `frames` |
| `--mp4` | also make `DIR/video.mp4` with ffmpeg | off |

**Frames.** The tool writes `fps × seconds` frames (rounded to the nearest
whole number, at least 1) named `frame_0000.png`, `frame_0001.png`, ... in
`--out`. Each is an 8-bit RGB (or fully opaque RGBA) PNG of exactly the
requested width and height. Before writing, it deletes any old `frame_*.png`
already in that folder, so a shorter render never leaves stale frames behind.

**Random seed.** With no `--seed`, the tool picks a random whole number itself
and prints one line on standard output, exactly `seed: ` followed by the
number (for example `seed: 482913`), nothing else on that line. Running again
with `--seed 482913` and the same other flags then reproduces the same frames,
byte for byte. Two runs without `--seed`, started moments apart, normally pick
different seeds and so make different pictures. With `--seed` given, use it as
is: 0 is a seed like any other, not "no seed".

**Recipe.** Next to the frames, write `recipe.json` with at least
`"seed"` (the seed used, whether given or picked) and `"blocks"` (a list of the names of the
building blocks this seed chose). Other keys are up to you.

**Building blocks.** Make at least three, of your own design, from ideas like
domain-warped noise, kaleidoscope folding, swirls, ripples or interference
rings. The seed chooses at least two of them per video, so different seeds
give visibly different kinds of picture, not just a shifted copy.

**Colour comes only from the palette.** Compute one number `t` between 0 and
1 for each pixel, then the pixel's colour is `palette(t)`. No shading, blur,
vignette or blending after that step: every pixel must sit on the palette.

### Palettes

A **named** palette is a cosine curve. For each channel (red, green, blue):

```
colour(t) = clamp(a + b · cos(2π · (c · t + d)), 0, 1) × 255,   t in [0, 1]
```

| Name | a (r, g, b) | b (r, g, b) | c (r, g, b) | d (r, g, b) |
|---|---|---|---|---|
| `acid` | 0.50, 0.50, 0.50 | 0.50, 0.50, 0.50 | 1.00, 1.00, 1.00 | 0.00, 0.33, 0.67 |
| `ember` | 0.55, 0.35, 0.25 | 0.45, 0.35, 0.25 | 1.00, 1.00, 1.00 | 0.00, 0.08, 0.15 |
| `lagoon` | 0.25, 0.50, 0.60 | 0.25, 0.40, 0.40 | 1.00, 1.00, 1.00 | 0.50, 0.25, 0.00 |
| `dusk` | 0.50, 0.40, 0.60 | 0.50, 0.30, 0.40 | 2.00, 1.00, 1.00 | 0.25, 0.00, 0.50 |

A **hex list** such as `ff0055,22ccaa,110033` (each colour six hex digits, a
leading `#` allowed) is a ramp: the colours sit evenly spaced from `t = 0` to
`t = 1`, with straight-line blending in RGB between neighbours. It needs at
least two colours. Anything else (an unknown name, one colour, a bad hex
digit) is an error: print why and exit non-zero.

### Time and looping

Motion follows the clock, not the frame number: frame `i` shows time
`i / fps` seconds, so a higher `--fps` samples the same motion more finely.

With `--loop`, the whole video is exactly one cycle. Frame `i` of `N` shows
phase `i / N`, and phase 1 is the same picture as phase 0, so the last frame
flows into the first with no jump and no repeated frame. A longer `--seconds`
slows the cycle down; it does not add more of it. Every moving part (a spin, an
orbit, a ring phase, a colour cycle) must make a whole number of turns per
cycle, or the last frame cannot flow into the first. (An easy way: drive every
moving part from `cos` and `sin` of `2π · phase`.)

### MP4

With `--mp4`, after writing the frames, look for `ffmpeg` on the PATH. If it
is there, run it to make `DIR/video.mp4`. If it is not, print a message that
names ffmpeg and gives the command to run once it is installed, and still
exit 0: the frames are the product, the video is a bonus.

### Speed

Pure Python is slow, so keep the per-pixel work modest. A 64×36, 2 fps,
2 second render must finish in under 20 seconds on an ordinary laptop
(well under is easy). Bigger renders can take longer. The loop check also
renders 480 frames at 16×9 (about 70,000 pixels); each such render must
finish within two minutes.

## Graded

Prose elsewhere in this brief describes the project and makes no promises of
its own: what is graded is this numbered list, and what is described but not
graded is under "Not graded" below.

These are checked by held-out tests you cannot see, run against this folder. The test command in the rules file
runs them and prints the result; there is no `npm test` here.
The tests run the tool with `python -S` (no site-packages) from another folder
whose path has a space and an apostrophe in it, with `--out` set to an absolute
path. Do not assume the current directory is this folder. Any single render
that takes longer than two minutes counts as a failure.

1. 2 fps for 2 seconds gives exactly `frame_0000.png` to `frame_0003.png`;
   4 fps for 1.5 seconds gives 6 frames; 4 fps for 0.9 seconds (3.6) gives 4
   and 3 fps for 0.7 seconds (2.1) gives 2, so the count is rounded, not cut
   off or rounded up. A render that rounds to nothing (1 fps for 0.2 seconds)
   still writes 1 frame.
2. Every frame is a valid PNG (signature, chunk checksums, data length) at the
   requested size, including odd sizes such as 17×5. It is 8-bit RGB or fully
   opaque RGBA, with no interlacing.
3. The same seed rendered twice gives byte-identical frames (same SHA-256),
   even when Python's string-hash randomisation differs between the runs. This
   holds for any whole-number seed, including 0, a negative number and a number
   larger than 2³².
4. Different seeds give different frames. Seeds 5 and 6 share no frame, and
   seeds 1 to 4 give four different first frames. The edge seeds are seeds like
   any other, so a seed is never folded onto another one: the first frames
   (16×9, 1 fps, 1 second) of 0, 7, -7, 9, 2⁴⁰ + 9, 3, -3, 5, -5, 11, -11,
   2⁴⁰ + 3 and 2³² + 7 are all different from one another, and from seeds 1, 2, 4
   and 6 as well (so 0 is not folded onto 1). In particular a negative seed does not
   draw the same picture as its absolute value, and a seed wider than 32 bits
   does not draw the same picture as that seed cut down to 32 bits.
5. The animation moves (no two neighbouring frames identical) and has detail
   (at least 24 distinct colours in a 64×36 frame).
6. Every pixel of a named-palette render is within 3 (RGB distance, 0-255
   units) of that palette's curve, for all four names and for the default.
7. Every pixel of a hex-list render is within 3 of its ramp, uses at least
   8 colours of it, and reaches every part of it: with the stops evenly
   spaced, some pixel falls in each quarter of the ramp (t from 0 to 0.25,
   0.25 to 0.5, 0.5 to 0.75, 0.75 to 1), so no colour in the list is dropped.
   A leading `#` on each colour is accepted.
8. A valid hex list is accepted; an unknown name, a single colour and a bad
   hex digit are each rejected with a non-zero exit.
9. With `--loop`, frame `k` of a 6-frame render matches frame `2k` of a
   12-frame render of the same length (same phase), within 2 per channel on
   all but 1% of values, and with a mean absolute difference of at most 0.5.
10. With `--loop`, 3 fps × 2 s and 6 fps × 1 s give the same 6 frames (same
    tolerance as item 9).
11. With `--loop`, rendered tiny (16×9) at 480 fps for 1 second, for a handful
    of fixed seeds, each step is a small move: the last frame is not a copy of
    the first, and the jump from last to first is no bigger than 1.5 × the
    largest ordinary frame-to-frame change, plus 1 (mean absolute difference
    per channel, 0-255). A part that runs a non-whole number of cycles per
    loop, for example a half turn, shows here as a jump.
12. Without `--loop`, motion follows the clock: frame 1 at 2 fps matches
    frame 2 at 4 fps (both 0.5 s), and frame 1 of a 1-second render matches
    frame 1 of a 2-second render at the same fps (`--seconds` sets the length,
    not the speed). Same tolerance as item 9, without the mean limit.
13. `recipe.json` exists, carries the seed exactly as given (0, a negative
    number and a number larger than 2³² included), and names at least two
    blocks; seeds 1 to 8 do not all pick the same blocks.
14. Re-rendering fewer frames into the same folder leaves only the new frames.
15. `--mp4` with no ffmpeg on the PATH exits 0, writes the frames and mentions
    ffmpeg in its output.
16. Every Python file in this folder imports only the standard library.
17. The 64×36, 2 fps, 2 s render takes under 20 seconds.
18. With no `--seed`, the tool prints exactly one line `seed: N` on standard
    output (nothing else on that line); a second run with `--seed N` (same size, fps and length) writes frames with
    identical SHA-256s, and `recipe.json` carries that same `N`. This is
    checked on several random runs, not one, since a seed that fails to
    reproduce may show only for some seeds.
19. Six runs with no `--seed`, started at the same moment, pick at least three
    different seeds between them and do not all make the same frames (so a seed
    taken from the clock in whole seconds, which gives runs within one second at
    most two values, is not enough).

## Not graded

The brief describes these, but no held-out test checks them. They are yours to
judge, by eye or by your own tests.

- **How it looks.** Whether it looks trippy; whether different seeds give
  visibly different kinds of picture rather than a shifted copy (the tests see
  only the block names in `recipe.json`); how smooth the motion feels; how
  comfortable the flashing is. Please keep it gentle: avoid full-screen
  flashes faster than about three per second.
- **How many building blocks.** That you made at least three, of your own
  design. The tests see only that each seed names two or more and that seeds 1
  to 8 do not all name the same ones.
- **Every moving part closing its loop.** That each part makes a whole number
  of turns per cycle, for every seed. Item 11 samples a handful of fixed seeds
  and a part can slip past it; items 9 and 10 check phase, not whole turns.
- **`--mp4` with ffmpeg installed.** That `video.mp4` is made and plays. When
  ffmpeg is missing, the tests need only exit 0, the frames and the word
  "ffmpeg"; that the message gives a command that works once it is installed
  is not checked.
- **Palette details beyond the tolerance.** That a rejected palette prints why;
  that hex stops are exactly evenly spaced (item 7 only needs every quarter of
  the ramp reached); that the blend is exactly straight-line in RGB and that
  colour is exactly `palette(t)` with nothing applied afterwards (item 6 and 7
  allow a distance of 3); upper case or surrounding spaces in a palette name.
- **Flags.** The defaults for `--width`, `--height`, `--fps`, `--seconds` and
  `--out`; that `--out` is created when missing (the tests always give a
  folder that exists); how nonsense values are refused (a non-whole `--fps`, a
  zero or negative size or length); how an exact half such as 2.5 frames
  rounds.
- **Other seeds.** Whole numbers the items above do not name: the tests try a
  few small, negative and 40-bit seeds, and nothing wider than that.
- **Same frames elsewhere.** That the same seed gives the same frames on
  another machine, operating system or Python version (the tests compare runs
  on one machine only); that Python 3.9 specifically works (the tests run on
  whichever interpreter starts them).
- **Bigger renders.** The speed of anything larger than the sizes in items 11
  and 17, such as the default 320×180.
- **How the PNGs are made.** That they are written by hand with `zlib` and
  `struct`; only item 16 (standard library imports) applies.
- **The working process.** "What to watch for" and "Try next" below are about
  how the work is done; none of it is tested.

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->

## What to watch for (the kit, not the code)

This demo exists to show the kit's chain working on something real. Watch for:

- **Your own tests.** The agent should write and run its own tests before it
  says done. The held-out check is a second opinion, not a substitute.
- **The verifier.** Before claiming done, the agent should hand the work to
  the kit's verifier agent, which re-runs the checks itself rather than
  trusting the builder's report. A verdict of FAIL or PARTIAL is the system
  working.
- **The checkpoint.** The kit's checkpoint command verifies, summarises and
  commits one unit of work. Expect one checkpoint per finished piece (say, the
  PNG writer, then the renderer, then the CLI), not one giant commit at the
  end.
- **Commit trailers.** Each commit should carry `Verified: <command> -> <result>`
  for what was actually run and `Unverified: <claim>` for what was only
  reasoned about. The commit guard rejects a commit without them. "Looks
  trippy" can only ever be `Unverified:`.
- **Grade it yourself** with the `demo check` line in step 5, not with the
  agent's own report. That line is feedback, not proof: the agent has a shell
  on this machine, as you do, and could tamper with the kit or the grade, so a
  measured run counts only after CI re-grades the committed folder (the kit's
  `demos/MEASURING.md`). It checks the 19 numbered items; how the video looks
  is for your eyes.
- **Nothing outward without asking.** No pushing, publishing or repo creation
  unless you say yes.

## Try next (after it passes)

1. **A new building block.** Ask for one more (a spiral tiling, a moiré of two
   ring sets, a slow zoom) and watch whether the agent re-runs the
   determinism and palette checks after adding it.
2. **A `--preview` flag** that prints the first frame as coloured blocks in
   the terminal. Small, visible, and easy to verify by eye.
3. **Speed.** Ask for a 2× faster render at 320×180 without changing any
   frame's bytes, and see whether the agent proves "unchanged" by comparing
   SHA-256s before and after.
