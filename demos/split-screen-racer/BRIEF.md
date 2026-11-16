# Kerbside Duel: a split-screen racer

**Tier:** L, browser. **Expected sessions:** 2 (the simulation and its tests first, the browser game second). A strong model may finish in one long session; a weak one may need a third.

Build a top-down racing game for the browser. Two people share one keyboard and one screen, split side by side or stacked. Or one person races a simple computer driver. Each player picks a **car** or a **bike**, and they really do drive differently. There is one hand-made track and an endless supply of seeded ones.

No npm packages. No image, audio or font files: draw everything on a canvas with code. The names here (Kerbside Duel, the Brick car, the Wisp bike, the Hollow Reach track) are placeholders. Keep anything you add original. Use a genre feel, never a name, track or vehicle from an existing racing game.

## Why top-down

Top-down, not pseudo-3D. The simulation is 2D either way, so a top-down view draws exactly what the simulation knows. Collisions and track edges are visible, so they are easy to debug. And a split-screen camera is just a translate per viewport. Pseudo-3D would add a projection layer that the tests could not see and the players would not need.

## How it must be built

The simulation lives in plain ES modules that import nothing from the browser. They are deterministic: no `Math.random`, no clocks, the same inputs giving the same result every time. A fixed timestep of 60 ticks a second. Drawing and input live in separate files that only read the simulation. Held-out tests grade the work by importing these files from Node, so the names below are the contract.

**`src/vehicles.js`**
- `VEHICLES`: plain data, `{ car: {...}, bike: {...} }`. Each has at least `topSpeed` (world units a second, on road), `accel`, `turnRate` (radians a second), `mass` and `radius` (collision circle), all positive numbers. Anything else your handling needs (grip, off-track factors, brakes) goes in here too.
- `createVehicle(kind, pose)`: `kind` is `'car'`, `'bike'`, or a data object shaped like `VEHICLES.car`. `pose` is `{ x, y, heading }`. Returns a plain object with at least `x`, `y`, `heading`, `speed` (always a magnitude, at least 0).
- `stepVehicle(vehicle, input, surface)`: advances one tick in place. `surface` is `'road'` or `'off'`. Heading 0 drives along +x, heading π/2 along +y.

An **input** is `{ throttle, brake, steer }`. Throttle and brake run from 0 to 1, steer from -1 to 1. Clamp out-of-range values. A missing or non-finite field counts as 0.

**`src/track.js`**
- `fixedTrack({ checkpoints = 8 } = {})`: your hand-made track.
- `generateTrack(seed, { checkpoints = 8 } = {})`: a track from an integer seed.
- `surfaceAt(track, x, y)`: `'road'` within `width / 2` of the centreline, `'off'` within `width / 2 + verge`, `'wall'` beyond that.

A **track** is `{ name, width, verge, centerline, checkpoints, grid }`:
- `centerline` is a list of `{ x, y }` in driving order. It is a closed loop: the last point joins the first, so the first point is not repeated at the end.
- `checkpoints` is a list of gates `{ a: {x,y}, b: {x,y} }`, in driving order. Gate 0 is the start/finish line.
- `grid` holds at least two start poses `{ x, y, heading }`.

**`src/race.js`**
- `TICK_HZ` (60) and `DT` (1/60).
- `createRace({ track, vehicles, laps = 3 })`: `vehicles` is a list of one or two kinds, such as `['car', 'bike']`. It returns `{ tick: 0, laps, track, players, finishOrder: [] }`. Each player is a vehicle object (see above) that also has `kind`, `lap: 0`, `next: 1`, `finished: false` and `finishTick: null`. Players start on the grid. They are plain mutable objects.
- `stepRace(race, inputs)`: advances exactly one tick in place, using one input per player. It moves each vehicle on the surface under it (`surfaceAt`), resolves collisions between vehicles and with the walls, updates lap progress and records finishes.
- `advanceProgress(track, progress, from, to)`: a pure function. It takes `{ lap, next }` and the segment a vehicle moved along this tick, and returns the new `{ lap, next }` without changing what it was given.
- `hashRace(race)`: returns a string that changes whenever the race state does.

**`src/ai.js`**: `aiInput(race, index)` returns the input for that player.

**`src/camera.js`**
- `splitViewports(width, height, targets, { layout = 'side', scale = 1 } = {})`: `targets` holds one or two `{ x, y }` points. It returns one viewport per target: `{ x, y, w, h, camX, camY, scale }`. The rectangle is in canvas pixels, and `camX`, `camY` is the world point at the centre of the viewport. `'side'` puts the views left and right; `'stacked'` puts them top and bottom.
- `worldToScreen(viewport, wx, wy)`: returns `{ x, y }` in canvas pixels. Screen y grows with world y.

**`index.html`** loads `src/main.js` as a module and has a `<canvas>`. `src/main.js` runs the game from `./race.js`. Serve the folder with `python -m http.server` and open it. Browsers block modules from `file://`.

The game itself: a setup screen (mode, vehicle for each player, fixed or seeded track with a seed box, split layout, laps), a countdown, and a lap and position readout in each view. It also shows a result when the race ends. Player 1 drives with WASD, player 2 with the arrow keys. In solo, player 1 may use either set. The Gamepad API is optional.

## Graded

Prose elsewhere in this brief describes the project and makes no promise beyond this list. The held-out tests check exactly these numbered contracts, and your own tests should too.

1. `VEHICLES.car` and `VEHICLES.bike` are plain data (a JSON round trip gives back an equal object) with positive finite `topSpeed`, `accel`, `turnRate`, `mass` and `radius`. The car is heavier than the bike.
2. Heading 0 drives along +x and heading π/2 along +y. `DT` is 1/60. `createVehicle(kind, pose)` accepts `'car'`, `'bike'` or a data object, and `stepVehicle` moves the vehicle one tick in place, by about its speed divided by 60 (within 5% at steady speed). An input with missing fields works: `{ throttle: 1 }` alone is full throttle with no brake and no steer.
3. On a straight at full throttle on the road, each vehicle settles within 5% of its own `topSpeed`, and the car's top speed is at least 10% above the bike's.
4. The bike reaches 90% of its top speed in under 80% of the time the car takes to reach 90% of its own, and is faster than the car after one second.
5. Turning at full steer at 60% of the bike's top speed, both vehicles hold that speed to within 15%, and the bike's turning circle is under 90% of the car's.
6. A copy of the car's data object with 1.5 times the `topSpeed`, given to `createVehicle`, settles within 5% of 1.5 times the speed.
7. With `surface` `'off'`, each vehicle's top speed is under 85% of its road top speed, and the bike's off-to-road ratio is at least 0.05 below the car's. A vehicle at its road top speed that is put on `'off'` at full throttle is below 90% of that speed 120 ticks later.
8. Inputs are clamped: finite out-of-range throttle and brake act as the nearest of 0 and 1, and steer as the nearest of -1 and 1. A missing field and NaN each count as 0.
9. Braking: full brake leaves a vehicle clearly slower than coasting after half a second (at least 5 units a second), `speed` stays finite and never below 0 while braking, and a braked vehicle is nearly stopped (under 1 unit a second) after 20 seconds.
10. `generateTrack(seed)` is deterministic: the same seed gives the same centreline and checkpoints. Seeds 1234 and 1235 give different tracks, and 25 spread-out seeds give at least 20 distinct ones.
11. Different integer seeds always give different tracks, including 0, negative seeds and seeds past 2^32: 5, -5 and 2^32 + 5 are three different tracks, as are 9 and 2^40 + 9. Each is also a valid loop (item 12).
12. The fixed track and 25 seeded tracks are valid loops: 32 to 5000 points, positive `width` and `verge`, finite coordinates, no repeated first point at the end (no zero-length segment, and the closing segment is at most 4 times the mean segment), no self-crossing, and any two points more than three road-widths apart along the road are at least one road-width apart in space.
13. `fixedTrack()` has a non-empty `name` and returns the same track on every call: the whole track, not only the centreline, and neither a call with another gate count nor a track returned earlier changes what a later plain call gives.
14. The checkpoint count matches the request: `fixedTrack` gives 8 by default and 12 when asked, `generateTrack` gives 8 by default and 5 when asked. Every gate is centred within a tenth of the road width of the centreline, runs across the road, spans at least 90% of the road width and at most road plus both verges, and lies further along the road than the gate before it.
15. `surfaceAt` is `'road'` within `width / 2` of the centreline, `'off'` within `width / 2 + verge`, and `'wall'` beyond (about 900 sampled points on each of the fixed track and seed 99, skipping points within 0.5 of an edge). Distance is to the nearest point of the centreline, not to its nearest vertex: the middle of every segment, 0.8 inside and outside each edge, is checked on the fixed track and seeds 99 and 5.
16. The grid has at least two poses on the road, facing the driving direction (within about 45 degrees of the road's direction), at least twice the larger vehicle radius apart. Checked on the fixed track and seeds 5 and 31.
17. `TICK_HZ` is 60. `createRace` returns `tick` 0, the given `laps` (3 by default), the given `track`, an empty `finishOrder`, and one player per vehicle kind, in order. Each player is a plain mutable vehicle object with `lap` 0, `next` 1, `finished` false, `finishTick` null and `speed` 0, standing on a different grid pose. `stepRace` advances `tick` by exactly one.
18. `advanceProgress`, walked along the grader's own paths on the fixed track and on seed 2024: one loop through every checkpoint in order gives lap 1 with `next` back at 1, two loops give lap 2, and after passing gates 1 and 2 the next gate is 3.
19. `advanceProgress` gives no lap for each of: cutting across to the finish line after gates 1 and 2; going round the outside of any one gate, tried in turn for every gate from 1 to the last, with `next` still waiting at that gate; driving the loop backwards.
20. `advanceProgress` is pure. Every call, including the ones that cross a gate, is given frozen copies of the progress and both points, and must not change them.
21. Replay: two AI players (car and bike, one lap, seed 4242) both finish within 12,000 ticks. Replaying their recorded inputs into a fresh race gives the same `hashRace` every 50 ticks, the same final hash and the same `finishOrder`. `finishOrder` follows `finishTick`, more than 90% of the sampled hashes are distinct, and 3,000 ticks of random inputs on the fixed track replay to identical hashes.
22. `hashRace` returns a string, and differs when one input in one tick differs and when the track differs.
23. `hashRace` differs when any one of these changes, and returns to the same string when it is changed back: `tick`, `finishOrder`, and for each player `x`, `y`, `heading`, `lap`, `next`, `finished`, `finishTick`. A change is as small as 0.001 for `x`, `y` and `heading`, so a hash of rounded positions fails.
24. Robust under abuse: 20,000 ticks of random inputs for a car and a bike on seed 5, including NaN, Infinity, -Infinity, 5, -5 and undefined, keep every number finite and every `speed` at least 0. No vehicle's centre gets past `width / 2 + verge` from the centreline, and the two vehicles never come closer than three quarters of their combined radii.
25. Ramming: for 1,200 ticks both vehicles steer at each other at full throttle, on the fixed track and on seed 5, as car and bike, bike and car, and car and car. They never overlap by more than a quarter of the combined radii, stay finite and inside the walls, and are in contact (within 1.1 times the combined radii) on at least 100 of the ticks.
26. Two overlapping vehicles, started from 10%, 30%, 50%, 65%, 80% and 90% of the combined radii apart in six different directions, are at least 95% of the combined radii apart after one `stepRace` tick, and the bike moves further than the car each time, with the car in player 0's seat and with the bike in it.
27. A player finishes on the tick its `lap` reaches `laps`: `finished` is raised on that tick, `finishTick` is `race.tick` then, and `lap` equals `laps` at the finish. `finishOrder` lists players in the order they finished, not by player number: player 1 finishing first gives `[1, 0]` over one lap, player 0 finishing first gives `[0, 1]` over two laps, and the later finisher has the later `finishTick`.
28. In a race, `stepRace` uses the surface under each vehicle. Held on the road at full throttle, a player keeps at least 95% of its speed for 120 ticks. Held on the verge it is below 90% of its road speed within 120 ticks. After 300 ticks on the verge the bike keeps a smaller share of its road speed than the car. Checked on the fixed track and seed 2024, with one player alone and with two players where one holds the road and the other the verge, in either seating.
29. Racing alone, `aiInput` gets a car and a bike one lap round the fixed track and seeds 3, 11 and 42 within 3 times the centreline length divided by the vehicle's `topSpeed` (in ticks) plus 600 ticks, with `finishOrder` `[0]` and the finish rule of item 27.
30. `splitViewports` for two targets, in `'side'` and `'stacked'`, at 800x600, 801x601, 1280x720 and 333x999: the two viewports have whole-pixel positive sizes, stay inside the canvas, do not overlap, and together cover every pixel. Side views are full height and stacked views full width. The same arguments give the same viewports.
31. Each viewport reports its own player's `x` and `y` as `camX` and `camY`, and the `scale` it was given. `worldToScreen` puts that player at the centre of its viewport at scales 1, 0.5 and 1.75, moves 10 times the scale pixels for 10 world units in x, and grows screen y with world y.
32. One target gives one viewport covering the whole canvas, whether the layout is `'side'`, `'stacked'` or not given (and with a scale of 2), at every size above, with the player at its centre.
33. `index.html` has a `<canvas>` and loads `src/main.js` with `type="module"` (quotes around the attributes are optional, and `src/main.js`, `./src/main.js` and `/src/main.js` all count), and `src/main.js` imports `./race.js`. Text inside an HTML or JavaScript comment does not count.

## Not graded

The brief describes these, but no held-out test checks them. Judge them by playing, or by your own tests.

- Feel, visuals and sound. The setup screen, countdown, lap and position readouts, result screen, split divider and every other drawn thing. Which keys do what (WASD, arrows, either set in solo), the Gamepad API, and anything `main.js` does beyond item 33.
- The browser/simulation split: that the simulation modules import nothing from the browser, that drawing and input only read the simulation, and that nothing uses `Math.random` or a clock. Only the effects reach the tests: the grader runs in Node with no DOM, and replays must match (items 21 to 23).
- No npm packages, no image, audio or font files, original names. A separate rule on every grade scans for these; the held-out tests do not.
- `Infinity` and `-Infinity` input values: treating them as 0 or clamping them are both fine. Only finite results are tested (item 24).
- Handling beyond the numbers in items 2 to 9: which way positive steer turns, how hard the brakes bite, and whether a vehicle can reverse.
- Collision physics beyond item 26 (restitution, momentum, spin), what a wall does beyond keeping vehicles inside it, and what a player does after finishing.
- `hashRace` changing when only `speed` changes (a solution may hash velocity instead), and the format of the string.
- Track details beyond items 10 to 16: the `name` of a seeded track, grid poses past the first two, how hand-made the fixed track looks, and seeds that are not integers.
- That `stepRace` calls `advanceProgress`. The AI lap tests cover laps end to end, so a solution that counts laps some other way still passes.
- How well the AI drives: only that it finishes in time (items 21 and 29), not overtaking or avoiding the other vehicle.
- Races with other than one or two vehicles, and a `laps` of 0 or one that is not a whole number.

## Done means

`npm test` passes, the browser game runs from `python -m http.server`, and the work is committed.

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->
## What to watch for

This demo exercises the starter kit's whole chain. Watch for these:

- **The verifier.** Before calling it done, the agent should hand the work to a separate verifier. That verifier re-runs `npm test` and plays through the checklist above, not just reads the agent's summary. If the agent says "done" without one, ask for it.
- **The checkpoint.** Each finished slice (simulation, tests, browser game) should go through checkpoint: verify, summarise and commit. One giant commit at the end is a smell.
- **Commit trailers.** Every commit should carry `Verified: <command> -> <result>` for what was actually run, and `Unverified: <claim>` for what was only reasoned about, such as "the bike feels lighter" or "gamepad works". The commit guard rejects commits without them.
- **Its own tests are not the grade.** The held-out check runs separately. An agent whose tests all pass can still fail it, and that gap is the point of the demo.
- **Grade it yourself** with the `demo check` line in step 5, not with `npm test`, which the agent can change. That line is feedback, not proof: the agent has a shell on this machine, as you do, and could tamper with the kit or the grade, so a measured run counts only after CI re-grades the committed folder (the kit's `demos/MEASURING.md`).

## Try next

1. Add a third vehicle, a heavy three-wheeler with low grip and a high top speed, purely as a new entry in `VEHICLES`. If anything outside the data has to change, the handling was not really data.
2. Add a ghost: record your best lap's inputs and replay them as a translucent rival. Replay determinism makes this a few dozen lines.
3. Add a minimap in the corner of each viewport, drawn from the centreline, with both players' dots.
