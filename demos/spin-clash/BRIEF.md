# Spin Clash

Two spinning tops in a bowl, seen from above. Each player picks a top, sets its
mass, radius and friction on sliders, and steers it from the keyboard. A mode
select offers two players or a solo game against a computer-driven top. The bowl
pulls the tops towards the middle, so they keep meeting. A top loses when it is
knocked over the rim (ring-out) or when its spin runs down (spin-down). The last
top still in play wins.

Everything runs in the browser from plain files: ES modules, no build step, no
npm packages, no images, sounds or fonts (draw everything on a canvas). To play
it, serve the folder (`python -m http.server 8000`, or `py -m http.server 8000`
on Windows) and open http://localhost:8000.

## What to build

- `src/physics.js`: the whole game simulation, importable on its own with no
  browser. This is the part that gets graded, so its shape is fixed below.
- `src/ai.js`: the computer opponent, importable on its own with no browser
  (shape below). This is graded too.
- `index.html` and any other front-end files you want (for example
  `src/main.js`): the bowl on a canvas, two tops, per-top sliders for mass,
  radius and friction, a seed box, a start/restart button, a **mode select**
  (Two players, or Solo vs computer), keyboard steering, each top's spin shown
  somewhere, and a message naming the winner and how the other top lost.
  In Two players mode one player steers Top A on W A S D and the other steers
  Top B on the arrow keys. In Solo mode the player steers Top A (W A S D and the
  arrow keys both work) and `src/ai.js` steers Top B. The page records the inputs
  of both tops every tick whatever the mode, so Replay works in both.
- The page advances the simulation in fixed steps of `DT`, however fast the
  screen refreshes (an accumulator loop), so a match plays the same on a 60 Hz
  and a 144 Hz monitor.
- Give the tops names of your own. A few to start from: Kestrel (light, quick,
  slippery), Old Ballast (heavy, wide), Thistle (grippy), Lantern (all-round).

## The physics module

`src/physics.js` exports:

- `DT`: the fixed timestep in seconds (for example `1 / 60`), at most 0.05.
- `createWorld(config)`: returns a new world.
- `step(world, inputs)`: advances the world by exactly one tick of `DT`,
  changes it in place and returns it.
- `collide(world, i, j)`: resolves contact between tops `i` and `j`.

**The world is plain data**: numbers, strings, booleans, `null`, arrays and
plain objects, nothing else. A `JSON.parse(JSON.stringify(world))` copy must
carry on stepping exactly like the original. All state lives in the world, none
in module variables.

**`config`** (every field optional; `createWorld` must not modify the object it
is given):

| field | meaning | default |
|---|---|---|
| `seed` | integer; picks everything the config leaves out | 1 |
| `arenaRadius` | the rim, as a distance from the centre `(0, 0)` | 1 |
| `slope` | how hard the bowl pulls a top towards the centre (pull grows with distance); `0` is a flat floor | your choice, above 0 |
| `steer` | how hard a full input pushes a top | your choice |
| `minSpin` | a top at or below this spin has spun down | 4 |
| `friction` | `false` turns every kind of friction and energy loss off | `true` |
| `tops` | an array of top settings, one per top | two tops |

Each entry in `tops` may give `name`, `mass`, `radius`, `friction`, `x`, `y`,
`vx`, `vy` and `spin`. The seed fills in whatever is left out (start position,
starting drift, starting spin), so two different seeds start differently. The
sliders clamp: `mass` to 0.5–3, `radius` to 0.05–0.2, `friction` to 0–1.

**The world** has at least `tick` (0 at the start, +1 per `step`), `winner` and
`tops`. Each top has `name`, `mass`, `radius`, `friction`, `x`, `y`, `vx`, `vy`,
`spin` (radians per second, never negative) and `status`, which is `'in'`,
`'ringout'` or `'spundown'`. The held-out check reads nothing else on a world by
name, so any other state you need (your settings included) is yours to lay out,
but it has to live in the world too, and travel with a JSON copy of it.

**`inputs`** is optional: an array with one entry per top, each `{x, y}` or
`null`. Values are clamped to -1..1, and anything that is not a finite number
counts as 0.

**One tick**, in this order:
1. Every top still `'in'` moves: the bowl's pull, its steering input, and (with
   friction on) drag and spin loss.
2. Touching pairs of in-play tops are resolved with `collide`.
3. A top whose centre is farther than `arenaRadius` from `(0, 0)` becomes
   `'ringout'`; otherwise a top whose spin is at or below `minSpin` becomes
   `'spundown'`. A top that is out stays exactly as it was and takes no further
   part.
4. `tick` goes up by one. If the world has two or more tops and at most one is
   still `'in'`, `winner` is set once, to that top's index, or `-1` when none is
   left. Until then it is `null`.

**`collide(world, i, j)`**: when the two tops overlap and are moving towards
each other, apply an equal and opposite impulse, leave them moving apart, and
return `true`. Otherwise return `false` and leave their velocities and spins
alone (pushing overlapping tops apart is fine). With friction off the bounce is
perfectly elastic and spin does not change. With friction on a clash may lose
energy and spin, never gain it.

**Spin only ever goes down.** Nothing raises a top's spin: not steering, not a
collision, not the bowl. With friction on, every top in play loses at least 0.5
radians per second of spin every second, so every match ends.

**Energy**, where the brief mentions it, is translation plus spin, with a top
treated as a solid disc: the sum over tops of `½·m·(vx² + vy²) + ½·I·spin²`,
with `I = ½·m·radius²`.

**Determinism:** the physics never calls `Math.random`, `Date.now` or
`performance.now`. Randomness comes from a small seeded generator whose state
is stored in the world.

## The computer opponent

`src/ai.js` exports `aiInput(world, index)`: the input for the top at `index`,
returned as `{x, y}` with each a finite number from -1 to 1. The page calls it
once per tick, before `step`, and passes the result in `inputs` like a keyboard
input, so the physics does not know a computer is playing.

- **It only reads the world.** It must not change the world, keep any state in
  module variables (a cache of earlier answers counts), or call `Math.random`,
  `Date.now` or `performance.now`. All it
  knows is the world it is given, so the same world always gets the same answer
  and the same seed gives the same match.
- It steers `index` against the nearest other top still `'in'`. If `index` is out,
  or no other top is in play, it returns `{x: 0, y: 0}`; it never throws on a
  finished match or a one-top world.
- **A simple opponent, not a strong one.** It should be able to ring out a top
  that does nothing, and a top that runs away from it should sometimes get away.
  For example, aim at where the other top is now and not where it is going, and
  stay off the rim yourself.

Two scripted opponents are used to judge it, both the same in every run. The
computer is always Top B (index 1) and the scripted one Top A (index 0); both
tops are 1.4 mass, 0.12 radius and 0.4 friction, and the match starts from the
seed with everything else left at its default:

- **Idle:** Top A gives input `null` on every tick.
- **Dodger:** Top A, each tick, steers straight for the centre if it is farther
  than 0.6 of the rim from the centre (the rim is 1, the default, in every solo
  match); otherwise it steers straight away from the nearest other top still in
  play (a unit vector from that top to itself).

## Graded

A held-out check you cannot see grades `src/physics.js` and `src/ai.js`; `npm test`
runs it. Everything above and below this list describes the project and the shape
of the code, and makes no promise beyond what is listed here: the check tests
exactly the items below, one numbered item per check (item `N` is the check whose
name in the output begins `Graded N`), and nothing it does not list.

1. **The world's shape.** `createWorld` returns the world described above: every
   top starts `'in'` and spinning, `tick` is 0, `winner` is `null`. Slider values
   outside their ranges are clamped, and the names you give are kept. A config
   with no `tops` gets two tops, a config with no `seed` starts exactly like seed
   1, and a configured negative spin never stays negative.
2. **Determinism.** The same seed and the same inputs give exactly the same state
   after 600 ticks, even when two worlds are stepped turn about, and a different
   seed starts differently. The physics works with `Math.random`, `Date.now` and
   `performance.now` taken away (they throw), including in the awkward corners:
   tops that share a centre (in `step` and in `collide` called directly), friction
   off with four tops, and a top outside the rim. Two worlds whose settings differ
   (`slope`, `steer`, `arenaRadius`, `minSpin`, `friction`), stepped turn about,
   each end exactly as the same world stepped on its own.
3. **The world is plain data.** At the start, mid-match and after 800 ticks it
   holds only finite numbers, strings, booleans, `null`, arrays and plain
   objects. A JSON copy taken mid-match carries on exactly like the original,
   and so does a second copy stepped on a freshly loaded copy of
   `src/physics.js` that has never made a world.
4. **Nothing blows up.** No position, velocity or spin becomes NaN or Infinity in
   10,000 ticks, even with three tops stacked on the same spot, absurd slider
   values or garbage inputs.
5. **Spin only goes down.** No top's spin ever rises. A lone top's spin never
   rises, with friction on or off and whatever its inputs, and in matches of two
   to four tops, with random inputs, no top's spin is higher after a tick than
   before it, collisions included. With friction on a lone top's spin falls,
   every top in play loses at least 0.5 radians per second of spin each second
   whatever its own friction (zero included, and a top with little spin left is
   no exception), and a friction-1 top starting at spin 20 spins down within
   3,600 ticks.
6. **One clash.** `collide` on two overlapping tops that are closing returns
   `true`. Total momentum is the same before and after one `collide` between two
   tops, with friction on and off; afterwards they are moving apart, and calling
   `collide` again on the separating pair returns `false` and does nothing. With
   friction on no top's spin is higher after `collide` than before, whether the
   tops' own friction is high, low or zero and whichever top is the heavier, and
   total energy does not rise. With friction off both spins are exactly
   unchanged and the bounce is perfectly elastic (total energy the same to one
   part in a billion). Two tops that do not touch (centres farther apart than the
   sum of their radii, even while closing on each other) get `false` from
   `collide` and keep their velocities and spins. This is tried on fixed clashes
   and on forty seeded ones.
7. **Energy with friction off.** With friction off and a flat floor (`slope: 0`),
   total energy stays within one part in a million through a head-on collision
   run through `step`.
8. **Ring-out and spin-down on tick 1.** A top whose centre is outside the rim
   (default rim 1, or the config's `arenaRadius`) is `'ringout'` after the first
   `step`, and the other top is the winner. The rim is judged on the centre: a wide top whose centre is inside
   but whose edge overhangs is still `'in'`. A top past the rim whose spin is also
   at or below `minSpin` is `'ringout'`, not `'spundown'`; a top inside the rim at
   or below `minSpin` is `'spundown'`. When no top is left on the same tick,
   `winner` is `-1`.
9. **Replay.** Replaying a recorded match (the same config and the same list of
   inputs) gives the same winner on the same tick and the same end state, the
   match ends within 7,200 ticks with friction on, and the config object is left
   untouched even when its sliders are out of range (the clamped values must not
   be written back into it) and when it leaves fields out (the defaults must not
   be written back).
10. **The computer's answer is valid.** `aiInput` returns `{x, y}` of finite
    numbers from -1 to 1 on every tick of a match, and leaves the world exactly as
    it found it. A top that is out, the winner of a finished match and the only
    top in a world with one top each get `{x: 0, y: 0}`: there is nothing to steer
    against, and nothing throws.
11. **The computer is deterministic.** The same seed gives the same match: two
    solo matches from one seed (against the idle and then the dodger opponent),
    played turn about with a third match from another seed, end in the same state
    with the same recorded inputs; the other seed does not. Each of those matches
    also ends the same as the same match played alone, from its first tick, on a
    freshly loaded copy of `src/ai.js`, so no answer may leak from one match into
    another. This holds with `Math.random` and the clocks taken away. A JSON copy
    of the world gets the same answer from `aiInput` as the original.
12. **It beats an idle top.** Against the idle opponent, over seeds 1 to 20, the
    computer wins (it is the winner, by index 1) at least 12 matches within 900
    ticks.
13. **It can be beaten.** Against the dodger opponent, over seeds 1 to 20, the
    computer does not win every match within 1,800 ticks: at least one match is
    lost, drawn or still undecided.
14. **Solo matches replay.** Replaying the recorded inputs of both tops, without
    calling `aiInput`, gives the same winner, the same tick and the same end
    state as the live solo match. Six matches are replayed (idle and dodger,
    seeds 2, 5 and 11), and at least four of them end within 2,400 ticks.
15. **The config fields do what the table says.** Every field a top setting may
    give (`name`, `mass`, `radius`, `friction`, `x`, `y`, `vx`, `vy`, `spin`) is
    used as given when it is in range. `minSpin` defaults to 4, and a top at or
    below it has spun down (also when `minSpin` is given). `friction` defaults to
    on, so spin and speed fall; with `friction: false` spin stays as it was,
    steering included, and a top coasting on a flat floor keeps its speed. `slope` defaults to above 0; the bowl pulls a top at
    rest towards the centre along x and along y, harder the farther out it is
    and the bigger the slope; `slope: 0` pulls nothing. A bigger `steer` pushes
    harder.
16. **Steering and `step`'s return.** `step` returns the very world it was given,
    with or without `inputs`, and advances it by one tick. `inputs[i]` steers top
    `i` and no other: a positive `x` pushes towards +x and a positive `y` towards
    +y. Values are clamped to -1..1 (an `x` of 3 steers exactly as 1), and
    anything that is not a finite number counts as 0: NaN, `Infinity` (it does not
    become 1), strings (`'1'` too), booleans, `null`, arrays and `{}`.
17. **A top that is out, and the winner.** A top that is out (`'ringout'` or
    `'spundown'`) stays exactly as it was from then on (position, velocity, spin,
    status), whatever its inputs and the bowl would do, and takes no part in
    clashes: a top thrown through it moves as if it were alone. `winner` is set
    once: the last top in play wins on the tick it is the last, and stays the
    winner when it later spins down. While two or more tops are in play it is
    `null`, and in a world of one top it stays `null`. `tick` goes up by one on
    every `step`, a decided match included.
18. **Every pair clashes.** In a world of four tops each of the six pairs, thrown
    head-on at each other through `step`, bounces: tops are resolved pair by
    pair across the whole list, not only neighbours in it.
19. **The computer steers against the nearest top.** In worlds of three and four
    tops its answer for any index is exactly the answer it gives in a world that
    holds only itself and its nearest other top still in play (the others change
    nothing), and a nearer top that is out of play is not chosen.

## Not graded

Described above, but no test looks at it. Judge these yourself, or leave them
as you like:

- The page: how it feels and looks, the canvas drawing, the sliders, the seed
  box, the start/restart button, the mode select, the keyboard controls, the
  spin display, the winner message, the page's own Replay, and the
  accumulator loop that steps in fixed `DT` chunks at any refresh rate. Play a
  few rounds of each mode.
- That the page records both tops' inputs every tick and calls `aiInput` once per
  tick before `step`; the held-out check does that itself.
- No npm packages, no build step, no image, audio or font files and original
  names. A separate rule on every grade scans for the files and the names; the
  held-out check does not, and it keeps whatever top name it is given.
- Working conditions: that `package.json`'s `test` script is left alone, that your
  own tests are under `tests/`, and the `python -m http.server` command.
- The numbers the brief leaves to you: the value of `DT` (only 0 < `DT` <= 0.05 is
  checked), the default `slope` and `steer`, the exact pull law, how much drag
  and spin loss friction adds beyond the 0.5 radians per second floor, and how
  much a friction-on clash loses.
- Which of the left-out fields the seed fills in, and how (start position,
  drift, spin): the check only needs different seeds to start differently and the
  fields you do give to be used as given.
- Whether overlapping tops are pushed apart (the brief allows it), what
  `collide` does for tops exactly touching, and which generator the seed feeds
  (only that the state lives in the world and the same seed gives the same
  match).
- Unusual config values: a `minSpin` or `steer` of 0, non-integer or negative
  seeds, more than four tops, and sliders that are not numbers. (A finite slider
  value out of its range, zero and negative included, is item 1's clamping. Other
  absurd numbers, and garbage in places the Graded items do not name, are only
  checked to stay finite, item 4.)
- The computer's strength beyond the two scripted opponents: how it plays as
  Top A, against tops of unequal build, or against a person, and the hints that
  it aims at where the other top is now and stays off the rim.

## Your own tests

Write your own tests as you go, under `tests/`, and run them with
`node --test tests/`. `npm test` runs the kit's held-out check; do not change that
script.

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->

## What to watch for

This demo is a chance to watch the starter kit work, not only the game appear.
While your agent builds:

- **It says what kind of task this is** before starting. A new project from
  empty has no existing flow to change, so expect it to propose a design first.
- **It writes and runs its own tests** of the physics, and watches at least one
  fail on purpose before trusting it.
- **A separate verifier checks the work** before anything is called done: a
  different agent that re-runs the tests itself and reports what it saw, rather
  than repeating the builder's summary.
- **The checkpoint commits with trailers**: `Verified: <command> -> <result>`
  for what was run, `Unverified: <claim>` for what was only reasoned about (for
  example "the page plays well at 144 Hz"). The commit guard refuses a commit
  without them.
- **It asks before anything outward**: pushing, creating a repo, publishing.

Then grade it yourself with the `demo check` line in step 5, not with `npm test`,
which the agent can change. If the agent's own tests pass and the held-out check
fails, that gap is the most useful thing this demo can show you: look at which
Graded item failed (item `N` is the check named `Graded N: ...`) and whether the
verifier should have caught it. That line is feedback, not proof: the
agent has a shell on this machine, as you do, and could tamper with the kit or the
grade, so a measured run counts only after CI re-grades the committed folder (the
kit's `demos/MEASURING.md`).

## Try next

After a passing check, ask for one of these and see whether the chain (tests,
verifier, checkpoint) runs again without being told:

1. A **Replay** button that plays the last match back from its recorded inputs,
   so a lucky ring-out can be watched twice.
2. A **tie-break** for a double spin-down on the same tick: the top with more
   spin left wins instead of a draw.
3. A **wobble** that grows as spin falls, drawn from the world's seeded
   generator, so a nearly spent top drifts. Keep the Graded items passing.
