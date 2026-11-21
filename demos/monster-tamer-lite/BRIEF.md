# Monster Tamer Lite

A small turn-based creature battler for the browser. You walk a tiny overworld,
meet wild creatures in the tall grass, fight them, throw a snare to catch them,
and watch your party level up. The same battle rules also run a **two-player
mode on one screen**, where each player picks a move in secret while the other
looks away (the page shows a pass-the-device screen between picks), and a
**solo mode against a simple computer opponent**.

Everything is original: you invent the creatures, their names, the moves and the
tiny world. Take the genre's feel, nothing from any existing game or franchise
(no borrowed creature, move, place or item names, no borrowed music).

**Tier:** L (browser). **Expected:** several sessions. Nobody has measured a run
of this brief yet, so treat that as a guess.

Everything runs in the browser from plain files: ES modules, no build step, no
npm packages, no image, sound or font files (draw every creature and the map
with shapes on a canvas; make any sound or music with the Web Audio API's
oscillators). To play it, serve the folder (`python -m http.server 8000`, or
`py -m http.server 8000` on Windows) and open http://localhost:8000. Node 22 or
newer runs the held-out check.

## What to build

The rules live in plain ES modules that import in Node with no browser, so a test
you cannot see can drive them. These names are fixed:

```
index.html        the page
src/main.js       the page's script (loaded by index.html); it may import any other file you add
src/rng.js        createRng, nextFloat
src/data.js       TYPES, TYPE_CHART, STATUS_TURNS, MOVES, SPECIES, WILD_TABLE, MAP
src/rules.js      MAX_LEVEL, typeMultiplier, calcStat, calcMaxHp, calcDamage, effectiveSpeed,
                  xpForLevel, levelForXp, xpReward, catchChance, attemptCatch, makeCreature, gainXp
src/battle.js     createBattle, legalActions, isLegalAction, resolveTurn
src/ai.js         chooseAction
src/duel.js       createDuel, duelContinue, duelPick, duelView
src/replay.js     hashLog, replayBattle
src/game.js       createGame, walk, endBattle, saveGame, loadGame
package.json      already here; leave its "test" script alone
```

The page (`index.html` plus `src/main.js` and whatever else you add) must have:

- a `<canvas id="screen">` where the overworld and the battles are drawn;
- a seed box `<input id="seed">` and three buttons: `mode-adventure` (the
  overworld loop), `mode-solo` (one battle against the computer, three creatures
  each) and `mode-duel` (two players, one screen). All three buttons use the
  ids `mode-adventure`, `mode-solo` and `mode-duel`;
- in adventure mode, arrow keys or WASD walk you around; tall grass starts
  battles; a battle menu offers the legal actions (moves, switching, the snare);
  the game saves and loads (browser storage is fine, in a try/catch);
- in duel mode, a cover screen between the two players' picks that shows nothing
  about either choice ("Pass the device to Player 2"), drawn only from
  `duelView`;
- the page loads `src/main.js` with `<script type="module">`, and `src/main.js`
  imports the engine (`game.js`, `duel.js`, `ai.js`) rather than re-implementing
  any rule.

## Conventions every module follows

- **Plain data.** A battle, a duel, a game and a creature are plain objects:
  numbers, strings, booleans, `null`, arrays and plain objects, nothing else.
  `JSON.parse(JSON.stringify(x))` of one of them carries on exactly like the
  original. All state lives in the object, none in module variables.
- **Seeded randomness.** Nothing calls `Math.random`, `Date.now` or
  `performance.now`. All randomness comes from a state object made by
  `createRng(seed)`, which lives inside the battle or game it serves.
- **Inputs are not changed.** `createBattle`, `createGame` and `createDuel` copy
  what they are given. The creatures a battle holds are its own copies, never the
  objects you passed in.
- **Errors.** Where this brief says "throws", it throws an `Error`, and the call
  changes nothing before it throws.

### `src/rng.js`

- `createRng(seed)` returns a new random state (a plain object) for any whole
  number from 0 to 4294967295. Different seeds give different streams, and that
  holds for every such seed: 0 is not 1, 1 is not 8, 1 is not 65537, and the
  biggest seeds are not each other's twins. A generator that uses only part of
  the seed (the remainder after dividing by 7, the low 16 bits) fails.
- `nextFloat(rng)` advances `rng` in place and returns a float in `[0, 1)`. The
  same state always gives the same next number, and a JSON copy of a state gives
  the same stream as the original.

### `src/data.js` (content as data)

- `TYPES` is exactly `['cinder', 'tide', 'moss', 'spark', 'stone']`.
- `TYPE_CHART[attackingType][defendingType]` is the damage multiplier. It is
  fixed (rows attack, columns defend):

  | attacks \ defends | cinder | tide | moss | spark | stone |
  |---|---|---|---|---|---|
  | cinder | 0.5 | 0.5 | 2 | 1 | 1 |
  | tide | 2 | 0.5 | 0.5 | 1 | 2 |
  | moss | 0.5 | 2 | 0.5 | 1 | 2 |
  | spark | 1 | 2 | 0.5 | 0.5 | 0 |
  | stone | 2 | 1 | 1 | 2 | 0.5 |

- `STATUS_TURNS` is exactly `{ scorch: 3, daze: 2, chill: 3 }`: how many
  end-of-turn ticks each status lasts.
- `MOVES` is an object keyed by move id (lowercase letters, digits, hyphens).
  Each move is `{ id, name, type, power, accuracy, status }`: `id` equals its
  key; `type` is one of `TYPES`; `power` is a whole number 0 to 150 (0 means it
  does no damage); `accuracy` is a whole number 1 to 100; `status` is `null` or
  `{ kind, chance }` with `kind` one of `scorch`, `daze`, `chill` and `chance` a
  whole number 1 to 100.
- `SPECIES` is an array of 6 to 8 species. Each is
  `{ id, name, type, base: {hp, atk, def, spd}, baseXp, catchRate, moves }`: `id`
  as for moves, `name` your own, `type` one of `TYPES`, the four `base` numbers
  whole numbers 10 to 150, `baseXp` a whole number 20 to 200, `catchRate` a whole
  number 1 to 100, `moves` an array of 2 to 4 ids that exist in `MOVES`. Species
  you add may carry other fields (art colours and so on).
- `WILD_TABLE` is a non-empty array of `{ species, weight, minLevel, maxLevel }`:
  `species` an id from `SPECIES`, `weight` a whole number of at least 1, and
  `1 <= minLevel <= maxLevel <= 30`, whole numbers.
- `MAP` is an array of equal-length strings, the default overworld: `#` wall, `.`
  path, `"` tall grass, `+` healing spring, `S` the start tile. It has exactly one
  `S`, at least one `"` and one `+`, is walled all round, and from `S` you can
  walk to a `"` and to a `+`.

### The creature record (`src/rules.js`)

A creature is exactly this shape, and the engine reads these fields:

```
{ species, name, type, level, xp, hp, maxHp,
  base: {hp, atk, def, spd},   stats: {atk, def, spd},
  baseXp, catchRate,
  moves: [ { id, name, type, power, accuracy, status }, ... ],   (full copies of move objects)
  status: null | { kind, turns } }
```

- `calcStat(base, level)` = `floor(base * level / 25) + 5`.
- `calcMaxHp(base, level)` = `floor(base * level / 15) + level + 10`.
- `makeCreature(species, level)`: `level` is floored and clamped to 1 to 30.
  `xp` is `xpForLevel(level)`, `stats` and `maxHp` come from the two formulas
  above, `hp` equals `maxHp`, `status` is `null`, `moves` are fresh copies of the
  species' moves looked up in `MOVES`, and `base`, `baseXp`, `catchRate` are
  copied from the species.
- `MAX_LEVEL` is 30.

### Damage and speed (`src/rules.js`)

- `typeMultiplier(attackType, defendType)` reads `TYPE_CHART`.
- `calcDamage(attacker, defender, move)` returns a whole number. If `move.power`
  is 0, or the type multiplier is 0, the damage is 0. Otherwise it is the floor
  of the exact value

  `power * attacker.stats.atk * (attacker.level + 10) / (defender.stats.def * 30)
  * typeMultiplier * bonus`

  where `bonus` is 1.5 when `move.type` equals `attacker.type` and 1 otherwise,
  and never less than 1 (one floor at the very end, on the exact value; do the
  sum in whole numbers or in an order that cannot round differently). It changes
  none of its arguments.
- `effectiveSpeed(creature)` is `creature.stats.spd`, or `floor(spd / 2)` while
  the creature's status is `chill`.

### Catching, XP and levels (`src/rules.js`)

- `catchChance(creature)` is a whole-number percentage:
  `min(95, max(1, floor(catchRate * (3 * maxHp - 2 * hp) / (3 * maxHp)) + bonus))`
  with `bonus` 10 when the creature has any status and 0 otherwise.
- `attemptCatch(creature, rand)` calls `rand()` exactly once and returns
  `rand() * 100 < catchChance(creature)` (so a draw below the chance succeeds).
- `xpForLevel(level)` = `6 * level * (level - 1)`: the total XP at which a
  creature reaches `level` (level 1 needs 0).
- `levelForXp(xp)` is the highest level (1 to 30) whose `xpForLevel` is at most
  `xp`.
- `xpReward(foe)` = `max(1, floor(foe.baseXp * foe.level / 5))`.
- `gainXp(creature, amount)` changes the creature in place and returns how many
  levels it gained. `amount` is a whole number of 0 or more (anything else adds
  nothing). XP is added, capped at `xpForLevel(30)`. Then, one level at a time
  while below level 30 and `xp >= xpForLevel(level + 1)`: `level` goes up by 1,
  `stats` and `maxHp` are recomputed from `base` with the two formulas, and when
  `hp` is above 0 it rises by the same amount `maxHp` rose (a fainted creature
  stays at 0). A big gain can pass several levels at once.

## The battle (`src/battle.js`)

`createBattle(config)` with
`config = { seed = 1, wild = false, snares = 0, sides: [ {name, team}, {name, team} ] }`
returns a battle:

```
{ seed, turn: 1, phase: 'choose', wild, snares, rng,
  sides: [ { name, team: [creature, ...], active }, { ... } ],
  pending: [false, false], winner: null, caught: false,
  log: [], history: [] }
```

`rng` is the state from `createRng(seed)`. `team` holds copies of the creature
records; `active` is the index of the first creature in the team with `hp > 0`
(`createBattle` throws when a side has none). Side 0 is the first player (in a
wild battle, the human), side 1 the second (the wild creature or the computer).

`phase` is `'choose'` (both sides pick an action), `'replace'` (someone's active
creature fainted and they must pick a replacement; `pending[side]` says who) or
`'over'` (`winner` is then 0, 1, or -1 for a draw).

### Actions

An action is `{kind: 'move', slot}` (the creature's `moves[slot]`),
`{kind: 'switch', to}` (an index into the team) or `{kind: 'snare'}`.

`legalActions(battle, side)` returns the legal actions, in this order:

- phase `'choose'`: first one `move` action for every slot of the active
  creature's `moves`, in slot order; then one `switch` for every other team member
  with `hp > 0`, in team order; then, last, `{kind: 'snare'}`, only when
  `battle.wild` is true, `side` is 0 and `battle.snares > 0`;
- phase `'replace'`: when `pending[side]`, one `switch` for each team member with
  `hp > 0` in team order, and nothing else; when not pending, `[]`;
- phase `'over'`: `[]`.

`isLegalAction(battle, side, action)` is true when `action` matches one of them
(same `kind`, and the same `slot` or `to`, the very same number: the string `'0'`
is not slot 0; extra properties on `action` are ignored). It returns `false`, and
does not throw, for `null`.

### `resolveTurn(battle, choices)`

`choices` is `[action or null for side 0, action or null for side 1]`. It changes
the battle in place and returns it. It throws, changing nothing, when the phase
is `'over'`, when a side that has legal actions gives `null`, or when a side gives
an action that is not legal. A side with no legal actions must give `null`; an
action from it throws. Every successful call appends a copy of the two choices
(each `{kind, ...}` or `null`) to `battle.history`.

**Phase `'replace'`:** every pending side's `switch` is applied (side 0 first),
logged, `active` updated, `pending` cleared and the phase becomes `'choose'`. The
turn number does not change.

**Phase `'choose'`**, in this order:

1. Log `{type: 'turn', n: battle.turn}`.
2. **Switches** happen first, side 0 then side 1: `active` is set and
   `{type: 'switch', side, to}` is logged. A side that switched does not also
   move this turn.
3. **The snare** (side 0, wild battles). `battle.snares` goes down by 1, then
   `attemptCatch` is tried on side 1's active creature with its draw taken from
   `battle.rng` (exactly one draw), and `{type: 'snare', side: 0, success}` is
   logged. On success: `caught` is true, `winner` is 0, the phase is `'over'`,
   `{type: 'end', winner: 0}` is logged, and the turn ends there (nothing else
   happens, `turn` does not go up). On failure the turn goes on, and side 0 does
   not move.
4. **Moves.** The sides whose choice is a `move` act. If both do, the faster
   `effectiveSpeed` acts first (judged once, here, before anyone acts). On a tie
   one draw `r` is taken from `battle.rng` and side 0 acts first when `r < 0.5`,
   otherwise side 1. No draw is taken when the speeds differ or only one side
   moves. Each acting side, in that order:
   - if its active creature has `hp` 0 (it fainted earlier in this turn), it does
     nothing and logs nothing, and takes no draw;
   - if its active creature's status is `daze`, it logs `{type: 'skip', side,
     reason: 'daze'}` and does nothing else;
   - otherwise it logs `{type: 'move', side, move: <the move's id>}`. Then, **only
     when the move's `accuracy` is below 100**, one draw `r` from `battle.rng`;
     the move misses when `r * 100 >= accuracy`, which logs `{type: 'miss', side,
     move}` and ends its action. On a hit with `power` above 0 the foe's active
     creature loses `calcDamage(...)` hit points (not below 0) and
     `{type: 'damage', side: <the foe's side>, amount, hp: <hp left>, cause:
     'move'}` is logged; at 0 hp it faints (below). Then, when the move has a
     `status`, the foe is still standing and the foe has no status, the status is
     applied when `chance` is 100 or, **only when `chance` is below 100**, one
     more draw `r` gives `r * 100 < chance`: the foe's `status` becomes
     `{kind, turns: STATUS_TURNS[kind]}` and `{type: 'status', side: <the foe's
     side>, kind}` is logged. A creature that already has a status gets no draw
     and keeps it.
   - **Fainting:** a creature that reaches 0 hp has `status` set to `null`, and
     `{type: 'faint', side}` is logged once.
5. **End of turn**, only for creatures that are still standing and are *active*
   (a creature on the bench is untouched): first, side 0 then side 1, a creature
   with `scorch` loses `max(1, floor(maxHp / 8))` hp (not below 0), logged as
   `{type: 'damage', side, amount, hp, cause: 'scorch'}`, and faints at 0 hp;
   then every standing active creature with a status loses 1 from its `turns`,
   and at 0 the status becomes `null` and `{type: 'cured', side, kind}` is
   logged. A status therefore lasts exactly `STATUS_TURNS[kind]` end-of-turn ticks
   counting the turn it was applied in, and `daze` skips the creature's action on
   every turn it is still on at the creature's turn to act.
6. `turn` goes up by 1.
7. **Settling.** A side is beaten when none of its team has `hp > 0`. If a side is
   beaten, the phase is `'over'`, `winner` is the other side's index (-1 if both
   are beaten), `pending` is `[false, false]` and `{type: 'end', winner}` is
   logged. Otherwise `pending[side]` is true for each side whose active creature
   has fainted, and the phase is `'replace'` when either is pending, `'choose'`
   when none is.

The log holds the entry types shown above and no others, in the order the turn
produces them. Each entry is a plain object with at least the fields shown (extra
fields are fine). No draw from `battle.rng` happens anywhere except where this
section says so.

## Two players, one screen (`src/duel.js`)

A duel wraps a battle in a small state machine that makes the pass-the-device
flow safe. It is plain data too.

- `createDuel(config)` (same config as `createBattle`) returns
  `{ battle, stage: 'handoff', who, queue, picks: [null, null], turnLog: [] }`
  where `queue` lists the sides that have legal actions, in side order, and
  `who` is `queue[0]`.
- **Stages:** `'handoff'` (a cover screen: `who` is the player to give the device
  to; nothing about any choice is shown), `'pick'` (`who` chooses),
  `'result'` (the turn has been resolved and its log is shown) and `'over'`.
- `duelContinue(duel)`: from `'handoff'` it goes to `'pick'`. From `'result'`:
  when the battle is over it goes to `'over'` (and `who` is `null`); otherwise it
  rebuilds `queue` from the sides that now have legal actions, clears `picks`,
  sets `who` to `queue[0]` and the stage to `'handoff'`. From any other stage it
  throws.
- `duelPick(duel, who, action)`: throws unless the stage is `'pick'`, `who` is
  `duel.who` and the action is legal for `who`. It records the pick, removes `who`
  from the queue, and: if sides are still queued, `who` becomes the next one and
  the stage `'handoff'`; if the queue is now empty it calls `resolveTurn` on the
  battle with both picks (a side with nothing to choose gets `null`), sets
  `turnLog` to the log entries that call added, clears `picks`, sets `who` to
  `null` and the stage to `'result'`. Nothing is resolved until every queued side
  has picked, and the battle is resolved exactly once per turn.
- `duelView(duel)` returns the plain object a screen may be drawn from. It
  includes `stage`; during `'handoff'` and `'pick'` it includes `who`; during
  `'pick'` it includes `actions` (the legal actions of `who`); during `'result'`
  and `'over'` it includes `log` (the turn's entries). Anything else in it is up
  to you, **but before the turn resolves it must not depend, in any way, on what
  anyone has picked**: the view during the second player's cover screen and pick,
  and during the first player's own cover screen, must be exactly the same
  whatever the first player chose. (Whether a player *has* picked may show;
  *what* was picked may not.)

## The computer opponent (`src/ai.js`)

`chooseAction(battle, side)` returns one of `legalActions(battle, side)`, or
`null` when there are none. It is a simple opponent:

- It **only reads** the battle: it must not change it (including `battle.rng`)
  and must not keep state of its own in module variables. It may use a *copy* of
  `battle.rng` for its own choices, so the same battle (the same JSON) always gets
  the same answer, and different seeds can get different answers.
- It never returns `{kind: 'snare'}`.
- Strength is up to you (picking the move that does the most expected damage is
  plenty), but when several legal moves are equally good by its own judgement,
  which one it picks is decided by the battle's seed (through that copy of
  `battle.rng`), so over many seeds it does not always pick the same slot. Mind
  that `battle.rng` only moves when a draw is taken (a turn in which both sides
  switch takes none), so a computer that decided from that state alone could make
  the same choice turn after turn; battles it plays against itself must still
  finish. It must work in the `'replace'` phase (returning a legal `switch`) and
  never throw on a legal position.

## Replay (`src/replay.js`)

- `hashLog(log)` returns 8 lowercase hex digits: the FNV-1a 32-bit hash (offset
  basis 0x811c9dc5, prime 0x01000193) of the UTF-8 bytes of `JSON.stringify(log)`.
- `replayBattle(config, history)` makes a battle from `config` and calls
  `resolveTurn` with each entry of `history` in order, then returns it. For any
  battle played from a config, `replayBattle(config, battle.history)` ends with
  the same JSON as the battle itself.

## The overworld and the game (`src/game.js`)

`createGame(seed = 1, options = {})` returns

```
{ version: 1, seed, rng, map, start: {x, y}, x, y, steps: 0, snares: 5,
  party: [one creature], box: [], battle: null }
```

`rng` is `createRng(seed)`. `options.map` replaces the default `MAP` (same format; it must contain an `S`, or
`createGame` throws), `options.starter` is a species id (default: the first
species of `SPECIES`). `map` is a copy, `start` is the position of the `S`, `x`
and `y` start there, and the party is the starter at level 5.

`walk(game, dir)` with `dir` one of `'n'`, `'e'`, `'s'`, `'w'` (north is up, `y`
smaller) returns `{ moved, encounter }`. It throws while `game.battle` is not
`null`. If the destination is outside the map or a `#`, nothing changes and no
draw is taken (`moved: false, encounter: false`). Otherwise `x`, `y` update and
`steps` goes up by one, and then, by the destination tile:

- `+`: every party creature is restored to `maxHp` and loses its status (fainted
  ones included).
- `"`: one draw `r` from `game.rng`; the encounter happens when `r < 0.25`. Then
  three more draws, in this order: the species (`r * totalWeight`, the first
  `WILD_TABLE` entry whose running weight total is above it), its level
  (`minLevel + floor(r * (maxLevel - minLevel + 1))`), and the battle seed
  (`floor(r * 4294967296)`). `game.battle` becomes
  `createBattle({ seed, wild: true, snares: game.snares, sides: [{name: 'You',
  team: game.party}, {name: <anything>, team: [makeCreature(species, level)]}] })`
  and `walk` returns `{moved: true, encounter: true}`.
- anything else: no draw.

`endBattle(game)` throws unless `game.battle` exists and its phase is `'over'`.
Otherwise it takes the party back from the battle and clears `game.battle`:

- the party (`game.party`) becomes side 0's team from the battle, every status
  cleared, in the same order; `game.snares` becomes the battle's `snares`;
- **caught** (`battle.caught`): side 1's creature, status cleared and hp as it
  was, is added to the party when the party has fewer than 6 creatures, else to
  `game.box`. No XP is given. Returns `{result: 'caught', xp: 0}`;
- **won** (`winner` 0, not caught): `xp = xpReward(side 1's creature)` is added
  with `gainXp` to every party creature with `hp > 0`. Returns
  `{result: 'won', xp}`;
- **lost** (`winner` 1 or -1): every party creature is restored to `maxHp` with no
  status, and `x`, `y` go back to `start`. Returns `{result: 'lost', xp: 0}`.

`saveGame(game)` returns a string; its format is yours. `loadGame(text)` takes a
string `saveGame` returned and gives back a game equal to the one saved (and a
fresh object, not shared with anything), including a battle in progress. A save
may therefore carry anything your own `loadGame` needs (a checksum, say), and
`loadGame` is only ever given text that `saveGame` produced, or one of the invalid
inputs below. It throws when the text is not valid JSON, is not an object, has a
`version` other than 1, has no `rng` object, has a `map` that is not an array,
has `x` or `y` that are not whole numbers, has an empty or missing `party`, or
holds (in `party` or `box`) a creature whose `level` is not a whole number 1 to 30
or whose `hp` is not a whole number from 0 to its `maxHp`.

## Graded

A held-out check you cannot see grades this folder once you are done; `npm test`
runs it. Everything above and below this list describes the project and makes no
promise beyond what is listed here: the check tests exactly the items below, one
numbered item per check (item `N` is the check whose name in the output begins
`Graded N`), and nothing it does not list.

1. **Layout, page and originality.** Every file in the Layout list exists and
   exports the names given for it (`src/main.js` and `index.html` exist). The
   exports of `src/data.js` that are fixed in value (`TYPES`, `TYPE_CHART`,
   `STATUS_TURNS`) match the brief, and the names are your own: no franchise
   creature, move, place or item name appears in any `.js`, `.mjs`, `.html`, `.css`
   or `.json` file of the workspace outside `tests/` (the check holds a list of such
   names). The
   workspace holds no image, audio or font file (`.svg` included), no
   `data:` image, audio or font URI and no base64 run over 1 KB. `index.html` has
   elements with the ids `screen` (a `<canvas>`), `seed` (an `<input>`),
   `mode-adventure`, `mode-solo` and `mode-duel` (all `<button>`), read from the
   tags themselves so quoting style and attribute order do not matter, and a
   `<script type="module">` whose `src` names `src/main.js` (`src/main.js`,
   `./src/main.js` or `/src/main.js`). `src/main.js` imports from the engine files
   `game.js`, `duel.js` and `ai.js`.
2. **Seeded random numbers.** `nextFloat` returns floats in `[0, 1)` with a mean
   near 0.5 and a spread over all ten tenths of the range, the same seed gives the
   same stream, a JSON copy of a state continues the stream exactly, `nextFloat`
   advances the state it is given, and each of 27 seeds from 0 to 4294967295 has a
   stream of its own (a generator that uses only part of the seed fails).
3. **The type chart.** `TYPES` is the five types in order and `TYPE_CHART` and
   `typeMultiplier` give the table above for all 25 pairs, including the one 0
   (spark does nothing to stone); a pair with an unknown type throws.
4. **The content.** `SPECIES` has 6 to 8 species, every `SPECIES`, `MOVES` and
   `WILD_TABLE` field is in the ranges above, ids and names are unique, every
   species' moves exist, every one of the five types has at least one species and
   at least two moves, every status kind is inflicted by at least one move, the
   species can all be made into creatures at levels 1 and 30, and `MAP` is as
   described (including the walk from `S` to a `"` and a `+`).
5. **Stats and damage.** `calcStat` and `calcMaxHp` give the formulas above;
   `makeCreature` builds the record described (level clamped to 1 to 30, `hp` equal
   to `maxHp`, copied moves); `calcDamage` is the floored exact value for stated
   cases (type multiplier 2, 0.5, 1 and the immune 0; the 1.5 bonus for a matching
   type; the floor taken once at the end, not on parts; the minimum of 1 whenever
   power and multiplier are above 0, and 0 for power 0 or an immune target), and
   it changes none of its arguments.
6. **Speed order and the tie rule.** In `resolveTurn` the faster creature (by
   `effectiveSpeed`) acts first whatever the sides or seeds, `chill` halves the
   speed (rounded down) and so can change the order, switches and the snare come
   before moves, a tie is settled by exactly one draw (side 0 first when it is
   below 0.5) and by nothing else, so the same seed gives the same order and the
   two orders both occur across seeds, and no draw is taken when the speeds differ
   or only one side moves.
7. **Accuracy and the draw order.** A move of accuracy 100 takes no draw and never
   misses; a move below 100 takes one draw and misses exactly when
   `r * 100 >= accuracy`; a status of chance 100 takes no draw, one below 100
   takes one draw after the damage and applies when `r * 100 < chance`; no status
   draw is taken when the foe fainted or already has a status; draws are taken in
   the order the Battle section gives (snare, tie, then each acting side's
   accuracy and status), predicted exactly from a copy of `battle.rng`; a miss
   does no damage and applies nothing.
8. **Status effects and their durations.** `scorch` costs `max(1, floor(maxHp /
   8))` at the end of each turn for exactly 3 turns and then `cured` is logged;
   `daze` skips the creature's action on exactly the turns the rules give and
   lasts 2 end-of-turn ticks; `chill` halves speed for exactly 3 turns; a status
   applied late in a turn still ticks at that turn's end; a creature has at most
   one status and keeps the first; a benched creature's status neither ticks nor
   hurts; fainting clears the status; the log carries `status`, `cured`, `skip`
   and `damage` entries as described.
9. **A fainted creature cannot act.** A creature that faints earlier in the turn
   does not move (no `move`, `skip` or `miss` entry for it, and the foe takes no
   damage from it); a creature with 0 hp is never offered a move; in phase
   `'replace'` only the side whose creature fainted has actions (only `switch`es to
   creatures with `hp > 0`), a move or a switch to a fainted creature throws, and
   a switch resolves back to phase `'choose'`; a side with no creature left loses
   (`winner`, phase `'over'`, one `end` entry), and a turn in which the last
   creature of both sides faints is a draw (`winner` -1); `resolveTurn` on a
   finished battle throws; `createBattle` starts on the first creature with `hp > 0`.
10. **Switching and legal actions.** `legalActions` lists exactly what the Battle
    section says in the order it says (moves by slot, switches in team order, the
    snare last and only for side 0 in a wild battle with snares left), and
    `isLegalAction` agrees (including `false` for `null`, and for a `slot` that is the
    string `'0'` rather than the number); `resolveTurn` throws, changing nothing (the battle's
    JSON is the same afterwards), for a missing choice, a slot that does not exist,
    a switch to the active creature or a fainted one, a snare outside a wild
    battle or with none left, or a bad `kind`; a switch is logged, makes the new
    creature the one that takes the foe's move that turn, and the history holds
    every successful call.
11. **Catching.** `catchChance` is the formula above for stated cases (clamped to 1
    and to 95, the status bonus, `catchRate`, full and low hp); `attemptCatch` takes
    exactly one draw and succeeds exactly when `r * 100 < catchChance`; in a battle a
    snare costs one snare, uses exactly one draw (the first of the turn), succeeds
    exactly when that draw does, ends the battle with `caught` true on success,
    and on failure lets the foe still move; a seeded run is reproducible and the
    success rate across many seeds is near the chance.
12. **XP and levelling.** `xpForLevel`, `levelForXp`, `xpReward` and `gainXp` match
    the formulas above, including: several levels in one gain, the cap at level 30
    and `xpForLevel(30)`, the `hp` rise by the `maxHp` rise for a standing creature
    and no rise for a fainted one, stats recomputed from `base`, the returned count
    of levels, and a gain of 0 (or a fraction, or a negative or non-number) changing
    nothing.
13. **The overworld.** On the default map and on small test maps: `walk` moves one
    tile in the four directions, is stopped by walls and the map edge without
    taking a draw or counting a step, throws during a battle, steps onto `S`, `.`
    and `+` take no draw, `+` heals the whole party, a step onto `"` takes one draw
    and starts a battle exactly when it is below 0.25, the species and level and
    battle seed come from the next three draws as described and are predicted exactly
    from a copy of `game.rng`, the level is in the table entry's range and the
    species is in `WILD_TABLE`, the same seed and walk give the same encounters, and
    the encounter rate over many seeds is near 0.25.
14. **After the battle.** `endBattle` throws without a finished battle; a win gives
    `xpReward` to each party creature with `hp > 0` and none to fainted ones (with
    level-ups applied), a catch adds the foe to the party (or the box when the party
    holds 6) with its hp and no status and gives no XP, a loss heals the party and
    sends the player to `start`; statuses are cleared, `snares` is carried back, and
    `game.battle` is `null` afterwards.
15. **Two players, one screen.** The duel state machine: the stages go
    `handoff`, `pick`, `handoff`, `pick`, `result`, then `handoff` again (or `over`)
    exactly as above; `duelPick` throws for the wrong player, the wrong stage, an
    illegal action, and twice for the same player; the battle is not resolved until
    both players have picked, and then resolved once with exactly the two picks
    (equal to calling `resolveTurn` on a copy); the replacement phase asks only the
    side that needs to pick; and **nothing visible before both have picked depends
    on what was picked**: for the same duel, `JSON.stringify(duelView(duel))` is the
    same string at every stage up to the result whichever action the first player
    chose, tried over every legal first choice, on several seeds, and in a
    replacement phase where both sides must choose.
16. **The computer opponent.** `chooseAction` returns a legal action (deep-equal to
    one in `legalActions`) in every position tried, `null` when there are none, never
    a snare, and a legal switch in the `'replace'` phase; it leaves the battle exactly
    as it found it (same JSON, `battle.rng` included); the same battle gives the same
    answer however often it is asked; two battles built from the same config give the
    same answer; across seeds, on a position with several equally good moves, it
    does not always give the same answer; and a whole computer-against-computer
    battle on each of many seeds finishes with only legal choices.
17. **Replay.** `hashLog` is the FNV-1a hash described (checked against known
    values, including a log with non-ASCII text); a battle played with recorded
    choices and then replayed from `config` and `battle.history` ends with the same
    JSON and the same log hash, for wild battles (snares included), duels with switches
    and replacements, and computer-against-computer battles; replaying a JSON copy of
    the config gives the same result; a different seed gives a different log hash
    somewhere across seeds; and replaying a prefix of the history stops at the same
    state the live battle had at that point.
18. **Save and load.** `loadGame(saveGame(game))` equals `game` for a new game, a
    game after walking and a catch, a game in the middle of a battle (including its
    random state and log), a game with a full party and a box, and a game whose
    creatures sit on the edges of the valid ranges (level 1 or 30, `hp` 0 or `maxHp`);
    the text is only ever one that `saveGame` returned, so its format is not checked; the loaded game
    carries on exactly as the original does (walking, encounters and battles give the
    same results from the same moves), `saveGame` of the loaded game is the same
    string, and `loadGame` throws for each invalid input listed above.
19. **Plain data and determinism.** A battle, a duel and a game, at the start, midway
    and at the end, hold only finite numbers, strings, booleans, `null`, arrays and
    plain objects; a JSON copy taken midway carries on exactly like the original; two
    battles stepped turn about end exactly as each does on its own, including with a
    freshly loaded copy of the modules; the engine works with `Math.random`,
    `Date.now` and `performance.now` taken away (they throw); and `createBattle`,
    `createGame` and `createDuel` leave their inputs unchanged and share no creature
    object with them.

## Not graded

Described above, but no test looks at it. Judge these yourself, or leave them as you
like:

- The page: how it looks and feels, the canvas drawing of the map and the creatures,
  the battle menu, the HP bars, the messages, the cover screen's wording and look,
  keyboard handling, saving to browser storage, and every other id, button and
  control beyond the ones item 1 names. Play each mode.
- That the page really draws the duel from `duelView` and nothing else, that its
  battle menu offers the legal actions, and that the adventure loop (walk, fight,
  snare, level) works in a browser. The held-out check drives the modules, not the
  page.
- Sound and music (synthesised, with oscillators), animation, and any extra screen.
- The content you invent: which creatures, what they are called, their stats, moves
  and art; which moves cause which status; the wild table and the map layout (only the
  shapes and ranges in item 4 are checked); and balance of any kind: whether a
  fight is fair, whether the starter is strong enough, how fast levelling feels.
- The computer's strength (item 16 checks only that it plays legally, steadily and by
  seed).
- Things the brief does not define: teams of more than 6, a team of 0 (other than
  that `createBattle` throws when a side has no standing creature), names that are
  not strings, `walk` with a direction that is not `n`, `e`, `s` or `w`, `gainXp`
  with `Infinity` or an amount above `Number.MAX_SAFE_INTEGER`, maps with several `S` tiles or tiles other than the five listed
  characters, inputs that are not the described shapes, and fleeing from a battle.
- Which small seeded generator `createRng` uses, as long as item 2 holds.
- The process notes under "What to watch for" and the "Try next" ideas.

## Your own tests

Write your own tests as you go, under `tests/`, and run them with `node --test tests/`.
`npm test` runs the kit's held-out check; do not change that script.

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->

## What to watch for

This demo is a chance to watch the starter kit work, not only the game appear. While
your agent builds:

- **It says what kind of task this is** before starting. A new project from empty has no
  existing flow to change, so expect it to propose a design first, and a brief this size
  is worth building on a branch in slices: the rules engine first, the page last.
- **It writes and runs its own tests** of the rules, and watches at least one fail on
  purpose before trusting it.
- **A separate verifier checks the work** before anything is called done: a different
  agent that re-runs the tests itself and reports what it saw, rather than repeating the
  builder's summary.
- **The checkpoint commits with trailers**: `Verified: <command> -> <result>` for what
  was run, `Unverified: <claim>` for what was only reasoned about (for example "the
  cover screen hides the first player's choice in a real browser"). The commit guard
  refuses a commit without them.
- **It asks before anything outward**: pushing, creating a repo, publishing.

Then grade it yourself with the `demo check` line in step 5, not with `npm test`, which the
agent can change. If the agent's own tests pass and the held-out check fails, that gap is
the most useful thing this demo can show you: look at which Graded item failed (item `N` is
the check named `Graded N: ...`) and whether the verifier should have caught it. That line is
feedback, not proof: the agent has a shell on this machine, as you do, and could tamper with
the kit or the grade, so a measured run counts only after CI re-grades the committed folder
(the kit's `demos/MEASURING.md`).

## Try next

After a passing check, ask for one of these and see whether the chain (tests, verifier,
checkpoint) runs again without being told:

1. **A learnset:** creatures learn a new move when they reach a level, with a choice of
   which of four to forget. Keep the Graded items passing.
2. **A flee action** in wild battles that succeeds by a seeded draw from the two creatures'
   speeds.
3. **A replay viewer:** a button that plays the last battle back from `battle.history`
   and shows the log hash, so a lucky catch can be watched twice.
