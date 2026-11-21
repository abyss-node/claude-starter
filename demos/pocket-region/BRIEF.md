# Pocket Region

A small top-down role-playing game in the style of the handheld classics: a tile map you walk around, people to talk to, tall grass with wild creatures in it, a turn-based battle, a bag of items, and a save you can load. Single player, in the browser, every town and creature and tune your own.

**Tier:** L (browser). **Expected:** several sessions; the engine is the bulk of it. Nobody has measured a run of this brief yet, so treat that as a guess. **Needs:** Node 22 or newer (the held-out check) and Python 3 (only to serve the page). No npm packages.

Everything runs in the browser from plain files: ES modules, no build step, no packages, **no image, sound or font files** (draw everything on a canvas with rectangles, lines and text; make the music with the Web Audio API). To play it, serve the folder (`python -m http.server 8000`, or `py -m http.server 8000` on Windows) and open http://localhost:8000.

**Make it your own.** The genre is the only thing borrowed. Invent the towns, the people, the creatures, the moves and the tunes. Do not use the names, creatures, places or terms of any existing game or franchise; the held-out check scans your content for a list of them.

## What to build

- **The engine**, in plain ES modules under `src/` that import in Node with no browser (the layout is fixed below). This is the part that gets graded.
- **The shipped world**, `src/content.js`: at least three small towns and one route between them, people to talk to, a gated door, wild creatures on the route, and an ending you can reach. Written as data.
- **The page**: `index.html` and `src/main.js` (and anything else you like): the map drawn on a canvas, the player walking with the arrow keys, talk/confirm and choose keys, the battle screen, the bag, save and load (browser storage is fine for the save), and music and sound effects synthesized with Web Audio. All of this is yours to judge, none of it is graded.

## Layout

These names are fixed, because a test you cannot see imports them. Every module is importable with no DOM, keeps no state of its own, never calls `Math.random`, `Date.now` or `performance.now`, and treats everything it is given as read-only (it returns new values; a test hands it frozen objects).

```
index.html         the page
src/main.js        the browser shell (not graded)
src/rng.js         makeRng, rngNext
src/map.js         tileAt, blockedReason, canEnter
src/movement.js    movePlayer
src/dialogue.js    startDialogue, advanceDialogue
src/battle.js      makeCreature, damage, activeIndex, startBattle, enemyChoose, takeTurn
src/inventory.js   countOf, addItem, removeItem, useItem
src/save.js        canonicalJson, saveGame, loadGame
src/game.js        newGame, step, isEnded
src/content.js     export const CONTENT
package.json       already here; leave its "test" script alone
```

**Everything is plain data**: numbers, strings, booleans, `null`, arrays and plain objects. A game, a battle and a save all survive a JSON copy and carry on the same. (The one exception to "returns new values" is `rngNext`, which advances the generator state it is given.)

## The data

`content` (the `CONTENT` of `src/content.js`, and what the engine functions below take as their first argument) is:

```
{
  title, endFlag,
  start:   { map, x, y, facing, party: [{ species, level }], inventory: { itemId: count } },
  maps:    { [mapId]: map },
  trees:   { [treeId]: tree },
  species: { [speciesId]: { id, name, type, hp, atk, def, spd, moves: [moveId, ...] } },
  moves:   { [moveId]: { id, name, type, power, accuracy, priority? } },
  items:   { [itemId]: { id, name, kind: 'heal' | 'revive' | 'key', amount? } },
  walkthrough: { seed, inputs: [input, ...] }
}
```

**A map** is `{ id, name, width, height, rows, warps, gates, npcs, encounterRate?, encounters? }`.

- `rows` is `height` strings of `width` characters each; `rows[y][x]` is the tile at column `x`, row `y` (`0, 0` is the top left). Tiles: `.` floor and `,` tall grass are walkable; `#` wall, `~` water and `T` tree block; any other character blocks too.
- `warps`: `[{ x, y, to, tx, ty, facing? }]`. Stepping onto the tile `(x, y)` puts the player on tile `(tx, ty)` of map `to`.
- `gates`: `[{ x, y, flag }]`. The tile `(x, y)` blocks until the flag is set.
- `npcs`: `[{ id, x, y, tree }]`. A person stands still on a tile, which blocks, and speaks the dialogue tree `tree`.
- `encounterRate` (a percentage, default 0) and `encounters`: `[{ species, minLevel, maxLevel, weight }]` (default none): the wild creatures of the tall grass.
- `warps`, `gates` and `npcs` may be left out of a map.

**Flags** are an object with a key for each flag that is set, with the value `true`: `{ met_elder: true }`. A flag is set when the object has that name as its own key with the value `true`; names every object inherits (`toString`, `constructor`) are not flags until they are set, and `false` is not set.

**A dialogue tree** is `{ start, nodes }`. `start` is a node id, or a list of `{ if?, ifNot?, node }`: the first entry whose conditions hold is where the conversation starts (`if` needs that flag set, `ifNot` needs it not set, both when both are given; an entry with neither always holds). If no entry holds there is no conversation. A node is:

```
{ text, set?: [flag, ...], give?: [{ item, count? }], choices?: [{ text, next, set?, if?, ifNot? }], next?, battle?: { party: [{ species, level }], win?: flag } }
```

**Creatures** are made by `makeCreature`; a creature is `{ species, name, type, level, hp, maxHp, atk, def, spd, moves }`. **Types** are `ember`, `moss`, `brine` and `plain`: ember beats moss, moss beats brine, brine beats ember; plain beats and loses to nothing.

**The game** (what `newGame` returns and `step` changes) is:

```
{ player: { map, x, y, facing }, flags, inventory, party: [creature, ...], rng,
  mode: 'world' | 'dialogue' | 'battle', dialogue: null | { tree, view }, battle: null | battle }
```

`facing` is `'up'`, `'down'`, `'left'` or `'right'`; `inventory` is `{ itemId: count }` with no key for a count of 0.

## The engine

### `src/rng.js`

- `makeRng(seed)` returns a generator state for a whole-number seed from 0 to 4294967295. The state is plain data.
- `rngNext(rng)` draws one number in `[0, 1)` and **advances the state in place**. Any small seeded generator will do (mulberry32 is a common choice). The same seed gives the same stream, different seeds give different streams (for every whole number in the range, not only the small ones), and a JSON copy of a state carries on exactly like the original. Two generators never affect each other. The first draws of neighbouring seeds (1, 2, 3, ...) must look unrelated to each other, so mix the seed in before drawing: items 9 and 15 use the first draws of seeds 1 to 80 as chances, and a generator whose first draw barely changes from one seed to the next gives every one of them the same outcome.

### `src/map.js`

- `tileAt(map, x, y)`: the tile character, or `null` outside the map (and for a coordinate that is not a whole number).
- `blockedReason(map, x, y, flags)`: `null` if the tile can be entered, otherwise why not: `'edge'` (outside the map), `'tile'` (a blocking tile), `'npc'` (a person stands there) or `'gate'` (a gate whose flag is not set). When several apply the first of that order is named: a person standing on a wall is `'tile'`.
- `canEnter(map, x, y, flags)`: `blockedReason(...) === null`.

### `src/movement.js`

`movePlayer(content, flags, player, dir)` with `dir` one of `'up'`, `'down'`, `'left'`, `'right'` returns `{ player, moved, blocked, warped }` and changes nothing it was given. The player is always turned to face `dir`. If the tile one step that way can be entered, the player is on it (`moved: true`, `blocked: null`). Otherwise the player stays put (`moved: false`) and `blocked` is the reason from `blockedReason` for that tile.

**Warps:** if the tile entered is a warp tile of the player's map, the player ends on the warp's `(tx, ty)` of its map `to` instead (`warped: true`; `moved` is `true`), facing the warp's `facing` if it has one and otherwise the direction moved. The landing does not trigger a warp, even when it is itself a warp tile. Standing on a warp tile, or leaving it, does nothing; only entering it warps. A warp tile that is blocked (a closed gate, a person, a wall) does not warp.

### `src/dialogue.js`

Both functions take a `game` (any object with `flags` and `inventory`, and whatever else) and return `{ game, view }`, where `game` is a new object with `flags` and `inventory` replaced and everything else carried along. A `view` is `{ node, text, choices, ended, battle }`: the node id, its text, the texts of the **visible** choices, `false`, and `null`. A conversation that is over has the view `{ node: null, text: '', choices: [], ended: true, battle: null }`.

- `startDialogue(tree, game)` picks the start node (see above) and enters it. No start node: the over view, the game unchanged.
- **Entering a node** sets its `set` flags and adds its `give` items (a missing `count` is 1; counts add to what is held), then works out which choices are visible. A choice is visible when its `if` flag is set and its `ifNot` flag is not (each only if given). The flags a node sets count immediately for its own choices.
- `advanceDialogue(tree, game, view, choice)`:
  - if the view is over, it stays over (the same view and an equal game);
  - if the node has visible choices, `choice` must be a whole number from 0 up to the number of visible choices minus 1 (an index into the visible list), or it throws a `RangeError`. The chosen choice's `set` flags are set, and then the node named by its `next` is entered; a `next` of `null` or none ends the conversation. The node's own `next` is not used;
  - if it has no visible choices (none given, or all hidden), `choice` is ignored: if the node has `battle`, the conversation ends with the view's `battle` set to that `battle` object (the node's `next` is not used); otherwise it enters the node named by `next`, or ends if there is none;
  - a `battle` on a node that has visible choices does nothing.
- A `battle`, then, only ever shows up in an over view. Looping back to a node enters it again, with its effects.

### `src/battle.js`

- `makeCreature(content, speciesId, level)`: `maxHp = floor(hp * level / 10) + level + 10`, and `atk`, `def` and `spd` each `floor(base * level / 10) + 5`, from the species' base stats. The creature starts at full hp (`hp` equals `maxHp`), with the species' `name` and `type`, its `level`, and a **copy** of its `moves` list.
- `damage(attacker, defender, move)`: 0 if `move.power` is 0 or less. Otherwise start from `floor(power * attacker.atk / defender.def) + 2`; then, if the move's type is the attacker's type, `floor(x * 3 / 2)`; then, if the move's type beats the defender's type, `x * 2`, or else if the defender's type beats the move's type, `floor(x / 2)`; otherwise unchanged. That order, all whole numbers.
- `activeIndex(party)`: the index of the first creature with `hp` above 0, or `-1`.
- `startBattle(content, playerParty, enemyParty, seed, options)`: a new battle `{ playerParty, enemyParty, turn: 0, over: false, winner: null, wild, rng: makeRng(seed), log: [] }` with **copies** of the two parties; `wild` is `options.wild` as a boolean (`false` without options). The battle is plain data. (The game adds one more field, `winFlag`, to a battle it starts.)
- `enemyChoose(content, battle)`: the move slot the enemy's active creature uses: the one that would do the most `damage` to the player's active creature, the lowest slot when several tie. Accuracy and priority are ignored.
- `takeTurn(content, battle, action)` returns a new battle and changes nothing it was given. `action` is `{ type: 'move', slot }` (the slot of the player's active creature's move list; any other slot is a `RangeError`) or `{ type: 'run' }`. A battle that is already over comes back as a new battle equal to the one given, whatever the action (this is checked before the slot).
  - **Move:** `turn` goes up by one. The player's active creature uses its slot and the enemy's active creature uses the `enemyChoose` slot. The side whose move has the higher `priority` (default 0) goes first; equal priority, the creature with the higher `spd`; still equal, the player. Each attack, in that order, **if its attacker still has hp above 0**: draws one number from the battle's own `rng` (every attack draws, even a move that cannot miss; an attacker that is down draws nothing), hits when `draw * 100 < accuracy`, does `damage` to the opposing **active** creature when it hits (hp never below 0), and adds a log entry `{ turn, actor: 'player' | 'enemy', move, hit, damage, targetHp }` (`move` is the move id; `damage` is 0 on a miss; `targetHp` is the target's hp afterwards). A creature knocked out by the first attack does not get its own attack.
  - The next creature of a party takes over when the active one has fallen: the active creature is always the first one with hp above 0. If one side has no creature standing when the turn ends the battle is `over`, and `winner` is `'player'` or `'enemy'`.
  - **Run:** in a `wild` battle, the battle is over at once with `winner: 'fled'`, `turn` up by one, no draw, no damage, and the log gains `{ turn, actor: 'player', action: 'run' }`. In a battle that is not wild nothing happens (a new battle equal to the one given).

### `src/inventory.js`

- `countOf(inv, id)` is the count, 0 for an item not held (and for a name an object inherits, such as `toString`). `addItem(inv, id, n = 1)` and `removeItem(inv, id, n = 1)` return new inventories; a count that reaches 0 leaves no key. `removeItem` throws a `RangeError` if fewer than `n` are held.
- `useItem(content, inventory, party, itemId, index)` uses an item on `party[index]` and returns `{ ok, reason, inventory, party }` with new objects. **`heal`** adds `amount` hp, up to `maxHp`. **`revive`** brings a creature with 0 hp back to `max(1, floor(maxHp / 2))`. **`key`** items cannot be used. On success `ok` is `true`, `reason` is `null`, and exactly one of the item is gone (so an item with a count of 1 leaves the inventory). On failure `ok` is `false`, nothing is used up, nothing changes, and `reason` is the first of these that applies, in this order: `'none'` (none held, or no such item), `'key'`, `'bad-target'` (`index` is not a whole number naming a party member), then `'fainted'` (a heal on a creature with 0 hp), `'full'` (a heal on a creature at `maxHp`) or `'alive'` (a revive on a creature with hp above 0).

### `src/save.js`

- `canonicalJson(value)`: JSON text with object keys in ascending order by code unit (`<` on the strings, not a locale order), no whitespace, arrays in their own order, strings and numbers written as `JSON.stringify` writes them, except that `-0` is `0`. It throws a `TypeError` for `NaN`, `Infinity`, `undefined`, functions, symbols and bigints, anywhere inside the value (an `undefined` property is an error, not left out).
- `saveGame(game)` returns `canonicalJson({ version: 1, game })`. `loadGame(text)` returns the game, a fresh copy each time. It throws for text that is not JSON, for a save that is not an object with `version` exactly `1`, and for a save with no `game` object.
- Loading a save and carrying on gives exactly the states the original game would have given: the generator's state is part of the game, and the game holds the whole state of a conversation or a battle.

### `src/game.js`

`newGame(content, seed)` returns the game described above: `player` from `content.start`, `flags` empty, `inventory` a copy of the start inventory, `party` made with `makeCreature` from the start party, `rng` from the seed, mode `'world'`. `isEnded(content, game)` is whether `content.endFlag` is set.

`step(content, game, input)` returns the next game (a new object, plain data; the one it was given is not changed). `input` is a string: `'up'`, `'down'`, `'left'`, `'right'`, `'action'`, `'run'`, `'choose:N'` (N whole-number digits), `'move:N'` (the same) or `'use:ITEM:N'` (an item id with no colon in it, and a party index). **Any input a mode does not take, and anything that is not one of these strings, changes nothing.**

- **World:**
  - A direction goes through `movePlayer`. If the player moved onto a `,` tile without warping, a wild encounter is rolled (below).
  - `'action'` talks to the person on the tile the player faces (the neighbouring tile in `facing`'s direction), if any: `startDialogue` on that person's tree; mode `'dialogue'` and `dialogue: { tree: <tree id>, view }` unless the conversation is over at once. The game's `flags` and `inventory` take what entering the start node did. Nobody there: nothing.
  - `'use:ITEM:N'` is `useItem` on party member N; on success the inventory and party are replaced, on failure nothing changes.
- **Dialogue:** `'action'` advances a conversation whose view has no choices; `'choose:N'` picks visible choice N (ignored if there is no such choice). `game.dialogue.view` is the latest view and `flags` and `inventory` follow the conversation. When the conversation is over the mode is `'world'` and `dialogue` is `null`; if the over view names a `battle`, a trainer battle starts (below).
- **Battle:** `'move:N'` plays a turn with slot N of the player's active creature (ignored when it has no such slot); `'run'` plays a run. While the battle runs the game's own `party` stays as it was (the battle works on its copy). When the battle is over the player's party is replaced by the battle's party (so lost hp stays lost), and: a `'player'` win sets the battle's `winFlag` if it has one; an `'enemy'` win is a **blackout**: the player is put back at `content.start` (map, tile, facing), every creature in the party is healed to `maxHp`, flags and inventory are kept; `'fled'` just leaves. Then mode `'world'` and `battle: null`.
- **Wild encounters.** After a step onto a `,` tile (not by a warp), exactly this, with the game's `rng`: draw `a`. If `a * 100 < encounterRate` (0 without one) and the map has a non-empty `encounters` list: draw `b`, pick the first entry whose running total of `weight`s is above `b * (total weight)` (the last entry if none is); draw `c`, level `minLevel + floor(c * (maxLevel - minLevel + 1))`; draw `d`, battle seed `floor(d * 4294967296)`; the battle starts as `startBattle(content, party, [that creature], seed, { wild: true })` with `winFlag: null`, mode `'battle'`. Without a hit only `a` is drawn. No draw is made for any other move (floor, a blocked move, a warp, turning, other inputs).
- **Trainer battles** (from a conversation): the enemy party is the `battle.party` made with `makeCreature`; one draw `d` from the game's `rng`, seed `floor(d * 4294967296)`; `startBattle(content, party, enemyParty, seed, { wild: false })` with `winFlag` the `battle.win` flag (or `null`).

### The shipped world, `src/content.js`

`CONTENT` is the data described above, with your own towns, route, people, creatures, moves and items, and:

- a `title` (text) and at least four maps: at least three towns with people in them and a route with tall grass and `encounters`. A map with a non-empty `encounters` list is a route and any other map is a town, so a town has no `encounters` (it may still have a `,` tile or two for show);
- at least four people with unique ids, each speaking a tree, at least four trees, and at least two places in the trees where the player chooses between two or more things;
- at least one gate, whose flag a conversation sets; and an `endFlag` that something sets, so the game can be finished; every flag that is read (by a gate, an `if`, an `ifNot` or a start list) is set somewhere (by a node, a choice or a `battle.win`);
- tiles only from `. , # ~ T`; every map's `id` is its key, `height` is the number of rows and every row is `width` long; warps start on a walkable tile and land on a walkable tile that no person stands on; gates and people stand on walkable tiles (a gate may stand on a warp tile); every map can be reached from the start by following warps; the start tile is walkable;
- at least four creatures (types among the four, 1 to 4 moves each, base stats that are whole numbers of 1 or more), four moves (types among the four, whole-number power of 0 or more, accuracy above 0 and at most 100), and one healing item (items are `heal` with an `amount` above 0, `revive` or `key`); every `id` is its key; a start party of at least one;
- a route's `encounterRate` is above 0 and at most 100, its entries have whole-number levels from 1 to 100 with `minLevel` at most `maxLevel`, and weights above 0;
- every dialogue node has non-empty `text`, and every tree, node, item, species and move named anywhere (a `start`, `next`, `give`, `battle`, an encounter, the start party) exists;
- `walkthrough`: `{ seed, inputs }`, a whole-number seed and a list of the inputs above that, played with `newGame(CONTENT, seed)` and `step`, reach the ending. The walkthrough has to talk to someone, fight a battle, walk through a gate (a step in the world onto a gate's tile that moves the player; a gate that is also a warp tile counts), and visit at least three maps.

## Graded

A held-out check grades `src/` once you are done. It is not in this folder. Everything above and below this list describes the project and the shape of the code, and makes no promise beyond what is listed here: the check tests exactly the items below, one numbered item per check (item `N` is the check whose name in the output begins `Graded N`), and nothing it does not list.

1. **Layout.** The modules exist, import in Node with no browser, and export the names under Layout (functions, and `CONTENT`); `CONTENT` has `start`, `endFlag`, `maps`, `trees`, `species`, `moves`, `items` and `walkthrough`.
2. **Tiles.** `tileAt` reads the grid and gives `null` outside it and for non-whole coordinates. `blockedReason` and `canEnter` follow the rules above: floor and grass walkable; wall, water, tree and any unknown character blocking; the edge, a person, a closed gate (`'gate'`, until its flag is `true`; an inherited name such as `constructor` is not a set flag); the order of reasons when several apply; maps without `npcs` or `gates` lists work.
3. **Movement.** `movePlayer` moves one tile in each direction, turns the player even when blocked, leaves the position alone when blocked, names the reason (`'tile'`, `'edge'` at all four sides, `'npc'`, `'gate'`), opens a gate with its flag, returns a new player object and changes none of its (frozen) inputs.
4. **Warps.** Stepping onto a warp tile lands on the stated `(tx, ty)` of the stated map, facing as the warp says or in the direction moved; a landing on a warp tile does not warp again; a warp tile behind a closed gate does not warp; standing on or leaving a warp tile does nothing; there-and-back trips land on each warp's own tile; the warp is chosen by its coordinates on the player's own map.
5. **Dialogue trees.** `startDialogue` and `advanceDialogue` follow choices and `next`s, set flags and give items (`count` defaulting to 1, stacking), apply a choice's `set` before the next node's effects, carry the other fields of the game along, end on `null` or no `next`, loop with effects applied again, keep an over view over, return the exact view shapes above, and throw `RangeError` for any invalid `choice` (including `undefined`, a string, `NaN`, `1.5`) when the node has visible choices. Inputs are frozen.
6. **Dialogue conditions.** Start lists pick the first entry whose `if` and `ifNot` hold; no match is an over view with the game unchanged; flags are own keys with the value `true` (`toString` and `{ f: false }` are not set); `if` and `ifNot` hide choices and indexes count the visible ones; flags a node sets count for its own choices; a node whose choices are all hidden behaves as one with none; a `battle` on a node without visible choices ends the conversation with that `battle` in the view, and on a node with visible choices does nothing.
7. **The gated door.** Through `step` on a fixture world: before the flag the gate stops the player however often they try, a flag that is not the gate's does nothing, a conversation choice that does not set the flag does not open it, the choice that sets it does (on entering the node), the same walk then passes the gate and takes the warp beyond, the flag set directly also opens it, and the flag survives a trip through a warp.
8. **Stats and damage.** `makeCreature` gives the exact stats (levels 1, 4, 5, 6, 8 and 100 are tried), copies the move list, and starts at full hp. `damage` gives the exact figures for neutral, same-type, super-effective and resisted moves, for the same-type bonus applied before the type multiplier (a `moss` move from a `moss` creature into `ember` is 58 then 29, not 19 then 28), for the floors, and 0 for a power of 0.
9. **Turn order and chance.** Faster first; priority before speed; equal priority falls back to speed; a tie goes to the player; the log entries are exactly `{ turn, actor, move, hit, damage, targetHp }`; a creature knocked out before its attack does not attack and draws nothing; every attack draws exactly once from the battle's `rng`, in the order the attacks happen, whatever its accuracy; `hit` is `draw * 100 < accuracy` (checked on seeds 1 to 40, with accuracy 50, 100 and a power-0 move; all four mixes of hit and miss over two attacks must appear among them); a miss does no damage; the turn count goes up by one per turn; the input battle is unchanged.
10. **Battle flow.** `activeIndex`; `startBattle` copies the parties and sets `turn` 0, `over` false, `winner` null, `wild`, an empty log and `rng` equal to `makeRng(seed)`; hp stops at 0; a win for the player and for the enemy; a finished battle ignores further turns and comes back as a new, equal battle (even for a slot that does not exist); the next creature steps in on either side; an unknown slot throws `RangeError`; slots are the active creature's own; running from a wild battle (`winner: 'fled'`, `turn` + 1, no draw, no damage, the log entry `{ turn, actor: 'player', action: 'run' }`) and not from a trainer battle; `enemyChoose` picks the highest damage, ties to the lowest slot, ignoring accuracy and priority, and looks at the creatures that are active.
11. **Items.** `countOf`, `addItem`, `removeItem` as above (no key left at 0, `RangeError` when short, inherited names are not items). Heal adds its amount up to `maxHp`; revive restores `max(1, floor(maxHp / 2))`; only the target changes; each use takes exactly one item and the last one leaves the inventory; a third use of two items fails with `'none'`; every failure (`'full'`, `'fainted'`, `'alive'`, `'key'`, `'none'`, `'bad-target'` for a negative, too large, fractional or non-number index) leaves the inventory and party as they were, with the reasons in the stated order; inputs are frozen.
12. **The generator.** `makeRng` and `rngNext`: draws in `[0, 1)`; the same seed gives the same stream; 27 different seeds across the whole range (0, 1, 8, 65537, 4294967295 and others) give 27 different streams; 10,000 draws are nearly all different, with a mean near 0.5 and about a tenth below 0.1; the state is plain data and a JSON copy carries on the same; a draw advances the state in place; generators do not share anything, and making one does not disturb another.
13. **Canonical JSON.** Keys sorted by code unit (upper case before lower, `"10"` before `"9"`, `""` first, non-ASCII last), no whitespace, arrays in order, nested; `-0` is `0`; strings and numbers as `JSON.stringify` writes them; an own key `__proto__` is written like any other; `NaN`, `Infinity`, `-Infinity`, `undefined` (also as a property or array element), functions, symbols and bigints throw `TypeError`, also deep inside.
14. **Save and load.** For a game walking, mid-conversation (also after a choice), mid-battle and with hand-edited flags, inventory and party hp: `saveGame` is exactly `canonicalJson({ version: 1, game })`; `loadGame` gives a game equal to the original, byte for byte under `canonicalJson`; saving it again gives the same text; each load is an independent copy; position, flags, inventory, party and `rng` come back; flags set in a different order save to the same text; the loaded game and the original, given the same inputs, are equal after every step (with the clocks and `Math.random` taken away); saving at any point of a long run and carrying on from the load ends where the straight run ends; a different version, a missing version, `'1'` as the version, text that is not JSON, empty text, `undefined`, and an array throw; a game holding `NaN` cannot be saved.
15. **Encounters.** On a fixture with `encounterRate` 100, 0 and 35, and weighted entries: the draws are exactly `a`, then `b`, `c`, `d` only when the encounter happens; the species is chosen by running totals of the weights (`b * total`), the level by `minLevel + floor(c * span)` with both ends reachable, the battle's `rng` is `makeRng(floor(d * 4294967296))`, the battle is wild with a full-hp enemy and the player's party, mode `'battle'`, `winFlag` `null`, and the game's `rng` has advanced by exactly the draws made; a missing or empty `encounters` list and a missing rate still draw `a`; grass to grass draws again; there is no draw for a move on floor, a move onto a warp tile, a warp that lands on grass, a blocked move onto grass, turning, or `'action'`. `Math.random` and the clocks are taken away.
16. **The game loop.** `newGame`'s fields (copies, not shares; `rng` equal to `makeRng(seed)`; plain data); `isEnded`; `step` is pure and plain; ignored inputs change nothing in every mode (including non-strings, `null`, `undefined`, arrays, malformed `choose:`, `move:` and `use:`); movement and turning; `'action'` talks only to a person on the faced tile and a start node's effects apply at once; a tree with no matching start does nothing; in a conversation only `'action'` (when there are no choices) and `'choose:N'` count, and `game.dialogue.view` follows; a conversation ending in a battle starts a trainer battle with the stated draw, enemy party, `winFlag` and seed, taking exactly one draw; in a battle only `move:N` and `run` count; the game's `party` stays as it was while a battle runs; a win sets the flag and keeps lost hp (14 of 35 after the check's fight); a blackout puts the player at the start, heals, keeps flags and items, and does not happen while a second creature stands; a wild battle run from or won keeps hp and sets no flag and `run` draws nothing; `use:ITEM:N` in the world, and not in a conversation or a battle; the same seed and inputs give the same game.
17. **The shipped world.** `CONTENT` is plain data satisfying the list under "The shipped world": legal tiles and rectangular maps, warps that start on and land on walkable tiles (and not on a person), every map reachable from the start by warps, every npc tree and node and item and species and move reference resolving, every flag that is read being set somewhere (including each gate's), `endFlag` set by something, branching conversations, the sizes asked for, and none of a list of existing franchise words anywhere in it.
18. **The shipped walkthrough.** `CONTENT.walkthrough` is a seed and 20 to 20,000 valid inputs; played from `newGame(CONTENT, seed)` it sets `endFlag` and ends in mode `'world'`, passes through a dialogue, a battle, a gate and at least three maps (it passes a gate when a step in the world onto the gate's tile moves the player; the gate may stand on a warp tile, so the player may be sent on at once), gives the same final game when run twice, and the same when saved and loaded after 25%, 50% and 90% of its inputs; `Math.random` and the clocks are taken away throughout.
19. **A scripted playthrough.** On the check's own world (a town with a gate and a sage, a wild map, a keep with a chief), a fixed list of 22 inputs (talk, choose, walk through the gate and the warps, fight with two `'move:0'`, talk again) reaches the ending flag from every seed tried (0, 1, 2, 1234, 4294967295), with the stated mode, position, flags, inventory and party hp at each marked step, the same end state for every seed (apart from the generator's state), and the same game through a save and load at every step.

## Not graded

Described above, but no test looks at it. Judge these yourself, or leave them as you like:

- The page: how it looks, sounds and feels; the canvas drawing, the walking, the battle screen, the bag, the save and load buttons, the music and sound effects, and whether the keys do what you say they do. Play it from the start to the ending.
- Whether `src/main.js` uses the engine correctly (the held-out check does not load it), and that there are no images, sounds or fonts as files.
- The story, the writing, the names, the quality of the towns and the balance of the battles, beyond the structural list in item 17 and the franchise-word scan.
- Anything the data format leaves open beyond the content rules above: a `priority` that is not 0 or 1, text of any length or kind, the number of warps, gates and people, the size of the maps.
- Unknown directions given to `movePlayer`, a `content` with a missing map, inputs like `'choose:007'`, huge numbers, or a party of more than a handful.
- How a battle is drawn, whether the enemy's move choice is clever (it is fixed above), and any experience points, evolution, catching or shops you add on top.
- Which small seeded generator you use, as long as items 12 and 15 hold.

## Your own tests

Write your own tests as you go, under `tests/`, and run them with `node --test tests/`. `npm test` runs the kit's held-out check; do not change that script.

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->

## What to watch for

This demo is a chance to watch the starter kit work, not only the game appear. While your agent builds:

- **It says what kind of task this is** before starting. A new project from empty has no existing flow to change, so expect it to propose a design first, and probably to build the engine on a branch in slices (map and movement, then dialogue, then battle, then save).
- **It writes and runs its own tests** of the engine, and watches at least one fail on purpose before trusting it.
- **A separate verifier checks the work** before anything is called done: a different agent that re-runs the tests itself and reports what it saw, rather than repeating the builder's summary.
- **The checkpoint commits with trailers**: `Verified: <command> -> <result>` for what was run, `Unverified: <claim>` for what was only reasoned about (for example "the music sounds fine" or "the page plays through to the ending"). The commit guard refuses a commit without them.
- **It asks before anything outward**: pushing, creating a repo, publishing.

Then grade it yourself with the `demo check` line in step 5, not with `npm test`, which the agent can change. If the agent's own tests pass and the held-out check fails, that gap is the most useful thing this demo can show you: look at which Graded item failed (item `N` is the check named `Graded N: ...`) and whether the verifier should have caught it. That line is feedback, not proof: the agent has a shell on this machine, as you do, and could tamper with the kit or the grade, so a measured run counts only after CI re-grades the committed folder (the kit's `demos/MEASURING.md`).

## Try next

After a passing check, ask for one of these and see whether the chain (tests, verifier, checkpoint) runs again without being told:

1. **Experience points**: a winning creature gains experience from the enemy's level and levels up at a threshold, which raises its stats by `makeCreature`'s formula. Keep the Graded items passing.
2. **A shop** in one town: buy and sell with a coin count in the game, saved and loaded with everything else.
3. **A second route** with its own wild creatures, and a gate on it that a different conversation opens.
