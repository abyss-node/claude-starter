// All game content as data. Nothing in here is code.

export const TYPES = ['cinder', 'tide', 'moss', 'spark', 'stone'];

// TYPE_CHART[attackingType][defendingType] is the damage multiplier.
export const TYPE_CHART = {
  cinder: { cinder: 0.5, tide: 0.5, moss: 2, spark: 1, stone: 1 },
  tide:   { cinder: 2, tide: 0.5, moss: 0.5, spark: 1, stone: 2 },
  moss:   { cinder: 0.5, tide: 2, moss: 0.5, spark: 1, stone: 2 },
  spark:  { cinder: 1, tide: 2, moss: 0.5, spark: 0.5, stone: 0 },
  stone:  { cinder: 2, tide: 1, moss: 1, spark: 2, stone: 0.5 },
};

// How many end-of-turn ticks each status lasts.
export const STATUS_TURNS = { scorch: 3, daze: 2, chill: 3 };

export const MOVES = {
  'wick-flick':  { id: 'wick-flick', name: 'Wick Flick', type: 'cinder', power: 40, accuracy: 100, status: null },
  'ash-burst':   { id: 'ash-burst', name: 'Ash Burst', type: 'cinder', power: 70, accuracy: 90, status: { kind: 'scorch', chance: 30 } },
  'splashjab':   { id: 'splashjab', name: 'Splashjab', type: 'tide', power: 40, accuracy: 100, status: null },
  'undertow':    { id: 'undertow', name: 'Undertow', type: 'tide', power: 65, accuracy: 95, status: { kind: 'chill', chance: 30 } },
  'leaf-lash':   { id: 'leaf-lash', name: 'Leaf Lash', type: 'moss', power: 45, accuracy: 100, status: null },
  'spore-puff':  { id: 'spore-puff', name: 'Spore Puff', type: 'moss', power: 0, accuracy: 85, status: { kind: 'daze', chance: 100 } },
  'static-nip':  { id: 'static-nip', name: 'Static Nip', type: 'spark', power: 40, accuracy: 100, status: null },
  'jolt-hum':    { id: 'jolt-hum', name: 'Jolt Hum', type: 'spark', power: 60, accuracy: 90, status: { kind: 'daze', chance: 20 } },
  'pebble-toss': { id: 'pebble-toss', name: 'Pebble Toss', type: 'stone', power: 45, accuracy: 100, status: null },
  'boulder-drop': { id: 'boulder-drop', name: 'Boulder Drop', type: 'stone', power: 80, accuracy: 80, status: null },
};

export const SPECIES = [
  { id: 'wickling', name: 'Wickling', type: 'cinder', base: { hp: 44, atk: 52, def: 40, spd: 55 }, baseXp: 60, catchRate: 45, moves: ['wick-flick', 'ash-burst', 'pebble-toss'], hue: 18 },
  { id: 'embermoth', name: 'Embermoth', type: 'cinder', base: { hp: 40, atk: 60, def: 35, spd: 70 }, baseXp: 70, catchRate: 35, moves: ['wick-flick', 'ash-burst', 'jolt-hum'], hue: 36 },
  { id: 'puddlop', name: 'Puddlop', type: 'tide', base: { hp: 60, atk: 45, def: 50, spd: 35 }, baseXp: 55, catchRate: 55, moves: ['splashjab', 'undertow', 'leaf-lash'], hue: 200 },
  { id: 'kelpjaw', name: 'Kelpjaw', type: 'tide', base: { hp: 55, atk: 62, def: 45, spd: 50 }, baseXp: 80, catchRate: 30, moves: ['splashjab', 'undertow', 'static-nip'], hue: 175 },
  { id: 'mossnub', name: 'Mossnub', type: 'moss', base: { hp: 65, atk: 40, def: 60, spd: 25 }, baseXp: 50, catchRate: 60, moves: ['leaf-lash', 'spore-puff', 'pebble-toss'], hue: 110 },
  { id: 'zapwren', name: 'Zapwren', type: 'spark', base: { hp: 38, atk: 55, def: 35, spd: 80 }, baseXp: 75, catchRate: 40, moves: ['static-nip', 'jolt-hum', 'wick-flick'], hue: 55 },
  { id: 'pebblepaw', name: 'Pebblepaw', type: 'stone', base: { hp: 58, atk: 58, def: 65, spd: 30 }, baseXp: 70, catchRate: 40, moves: ['pebble-toss', 'boulder-drop', 'splashjab'], hue: 30 },
];

// Tall-grass encounters: weighted pick, then a level in [minLevel, maxLevel].
export const WILD_TABLE = [
  { species: 'mossnub', weight: 4, minLevel: 2, maxLevel: 5 },
  { species: 'puddlop', weight: 3, minLevel: 2, maxLevel: 5 },
  { species: 'zapwren', weight: 2, minLevel: 3, maxLevel: 6 },
  { species: 'pebblepaw', weight: 2, minLevel: 3, maxLevel: 6 },
  { species: 'kelpjaw', weight: 1, minLevel: 4, maxLevel: 7 },
];

// '#' wall, '.' path, '"' tall grass, '+' healing spring, 'S' where you start.
export const MAP = [
  '##############',
  '#S...."""....#',
  '#.####.""".#.#',
  '#....#..+..#.#',
  '#.""".###....#',
  '#.""".#"""...#',
  '#.....#.""...#',
  '##############',
];

export const ENCOUNTER_RATE = 0.25;
export const START_SNARES = 5;
export const PARTY_MAX = 6;
