import { MAP, WILD_TABLE, SPECIES, ENCOUNTER_RATE, START_SNARES, PARTY_MAX } from './data.js';
import { createRng, nextFloat } from './rng.js';
import { makeCreature, gainXp, xpReward } from './rules.js';
import { createBattle } from './battle.js';

const DIRS = { n: [0, -1], e: [1, 0], s: [0, 1], w: [-1, 0] };
const clone = (v) => JSON.parse(JSON.stringify(v));

export function createGame(seed = 1, options = {}) {
  const map = clone(options.map || MAP);
  let start = null;
  map.forEach((row, y) => {
    const x = row.indexOf('S');
    if (x !== -1 && start === null) start = { x, y };
  });
  if (!start) throw new Error('the map has no start tile S');
  const speciesId = options.starter || SPECIES[0].id;
  const species = SPECIES.find((s) => s.id === speciesId);
  if (!species) throw new Error(`unknown starter ${speciesId}`);
  return {
    version: 1,
    seed,
    rng: createRng(seed),
    map,
    start,
    x: start.x,
    y: start.y,
    steps: 0,
    snares: START_SNARES,
    party: [makeCreature(species, 5)],
    box: [],
    battle: null,
  };
}

function healParty(game) {
  for (const c of game.party) {
    c.hp = c.maxHp;
    c.status = null;
  }
}

function startWild(game) {
  const total = WILD_TABLE.reduce((n, e) => n + e.weight, 0);
  const r = nextFloat(game.rng) * total;
  let acc = 0;
  let entry = WILD_TABLE[WILD_TABLE.length - 1];
  for (const e of WILD_TABLE) {
    acc += e.weight;
    if (r < acc) { entry = e; break; }
  }
  const level = entry.minLevel + Math.floor(nextFloat(game.rng) * (entry.maxLevel - entry.minLevel + 1));
  const species = SPECIES.find((s) => s.id === entry.species);
  const foe = makeCreature(species, level);
  const seed = Math.floor(nextFloat(game.rng) * 4294967296);
  game.battle = createBattle({
    seed,
    wild: true,
    snares: game.snares,
    sides: [{ name: 'You', team: game.party }, { name: `Wild ${foe.name}`, team: [foe] }],
  });
}

export function walk(game, dir) {
  if (game.battle) throw new Error('finish the battle first');
  const d = DIRS[dir];
  if (!d) throw new Error(`unknown direction ${dir}`);
  const nx = game.x + d[0];
  const ny = game.y + d[1];
  const tile = game.map[ny] && game.map[ny][nx];
  if (tile === undefined || tile === '#') return { moved: false, encounter: false };
  game.x = nx;
  game.y = ny;
  game.steps += 1;
  if (tile === '+') healParty(game);
  if (tile === '"' && nextFloat(game.rng) < ENCOUNTER_RATE) {
    startWild(game);
    return { moved: true, encounter: true };
  }
  return { moved: true, encounter: false };
}

export function endBattle(game) {
  const b = game.battle;
  if (!b || b.phase !== 'over') throw new Error('there is no finished battle');
  const party = b.sides[0].team;
  const foe = b.sides[1].team[0];
  for (const c of party) c.status = null;
  game.party = party;
  game.snares = b.snares;
  let result;
  let xp = 0;
  if (b.caught) {
    foe.status = null;
    (game.party.length < PARTY_MAX ? game.party : game.box).push(foe);
    result = 'caught';
  } else if (b.winner === 0) {
    xp = xpReward(foe);
    for (const c of game.party) if (c.hp > 0) gainXp(c, xp);
    result = 'won';
  } else {
    healParty(game);
    game.x = game.start.x;
    game.y = game.start.y;
    result = 'lost';
  }
  game.battle = null;
  return { result, xp };
}

export function saveGame(game) {
  return JSON.stringify(game);
}

export function loadGame(text) {
  const g = JSON.parse(text);
  if (!g || typeof g !== 'object' || Array.isArray(g)) throw new Error('save is not an object');
  if (g.version !== 1) throw new Error(`unsupported save version ${g.version}`);
  if (!Array.isArray(g.party) || g.party.length === 0) throw new Error('save has no party');
  for (const c of g.party.concat(g.box || [])) {
    if (!Number.isInteger(c.level) || c.level < 1 || c.level > 30) throw new Error('bad level in save');
    if (!Number.isInteger(c.hp) || !Number.isInteger(c.maxHp) || c.hp < 0 || c.hp > c.maxHp) throw new Error('bad hp in save');
  }
  if (!g.rng || typeof g.rng !== 'object') throw new Error('save has no random state');
  if (!Array.isArray(g.map) || !Number.isInteger(g.x) || !Number.isInteger(g.y)) throw new Error('save has no position');
  return g;
}
