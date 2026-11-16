# Roulette Loom

Build a small web page that draws rolling-circle curves. A circle rolls around the inside of a fixed ring, and
a pen fixed to the rolling circle traces a looping pattern. The page shows the pen drawing it, stroke by stroke.

## What the page does

- Three controls set the curve: the ring's radius `R` and the rolling circle's radius `r`, whole numbers with
  `0 < r < R`, and the pen's distance `d` from the rolling circle's centre, a number of zero or more.
- An animated pen draws the curve from its start until it closes, then stops. The rolling circle and the pen's
  arm are drawn as it moves. Changing a control clears the drawing and starts again.
- A play and pause button, and a speed control.
- It runs from `index.html` in a browser, as ES modules, with no build step and no npm packages.

## The maths, in `src/loom.js`

The checks import this module, so keep its exports' names and what they return.

- `gcd(a, b)`: the greatest common divisor of two positive whole numbers.
- `laps(R, r)`: how many times the rolling circle travels round the ring before the curve closes, which is
  `r / gcd(R, r)`.
- `point(R, r, d, t)`: the pen's position as `{ x, y }` at angle `t` in radians, with the ring centred on the
  origin: `x = (R - r) cos t + d cos((R - r) t / r)` and `y = (R - r) sin t - d sin((R - r) t / r)`.
- `trace(R, r, d, steps)`: `steps + 1` points, evenly spaced in `t`, from `t = 0` to the angle where the curve
  closes, so the last point is back at the first. `steps` is a whole number, one or more.
- `laps`, `point` and `trace` throw a `RangeError` when `R` or `r` is not a whole number, when `r` is not
  between `0` and `R`, or when `d` is negative; `trace` also when `steps` is not a whole number, one or more.

## Done means

`npm test` passes, the page draws and animates the curve, and the work is committed.

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->
- A plan before code: the agent should say what it will build and how it will test the maths, then build.
- Tests of its own, run and seen to fail once: the rules ask for that before a test counts.
- `npm test` run by the agent itself, and its `PASS` or `FAIL` line quoted, not paraphrased.
- The verifier agent re-running `npm test` on its own and reporting the count it saw.
- Your own grade: the `demo check` line in step 5. If it disagrees with the agent's `npm test`, the agent
  changed what `npm test` runs. Your grade is feedback, not proof either: the agent has a shell on this machine,
  as you do, and could tamper with the kit or the grade, so a measured run counts only after CI re-grades the
  committed folder (the kit's `demos/MEASURING.md`).
- Nothing checks the drawing. Open the page yourself (`python -m http.server` in the folder, then
  http://localhost:8000) and judge it: that judgement is yours, and the agent's report should say it did not
  make it.
