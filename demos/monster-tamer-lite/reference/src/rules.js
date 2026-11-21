import { TYPE_CHART, MOVES } from './data.js';

export const MAX_LEVEL = 30;

export function typeMultiplier(attackType, defendType) {
  const row = TYPE_CHART[attackType];
  const v = row && row[defendType];
  if (typeof v !== 'number') throw new Error(`unknown type pair ${attackType} -> ${defendType}`);
  return v;
}

export function calcStat(base, level) {
  return Math.floor((base * level) / 25) + 5;
}

export function calcMaxHp(base, level) {
  return Math.floor((base * level) / 15) + level + 10;
}

// Whole-number maths: the floor of the exact value power*atk*(level+10)/(def*30), times the type and bonus multipliers.
export function calcDamage(attacker, defender, move) {
  if (!(move.power > 0)) return 0;
  const typePct = Math.round(typeMultiplier(move.type, defender.type) * 100);
  if (typePct === 0) return 0;
  const stabPct = move.type === attacker.type ? 150 : 100;
  const num = move.power * attacker.stats.atk * (attacker.level + 10) * typePct * stabPct;
  const den = defender.stats.def * 30 * 100 * 100;
  return Math.max(1, Math.floor(num / den));
}

export function effectiveSpeed(creature) {
  const spd = creature.stats.spd;
  return creature.status && creature.status.kind === 'chill' ? Math.floor(spd / 2) : spd;
}

export function xpForLevel(level) {
  return 6 * level * (level - 1);
}

export function levelForXp(xp) {
  let level = 1;
  while (level < MAX_LEVEL && xp >= xpForLevel(level + 1)) level++;
  return level;
}

export function xpReward(foe) {
  return Math.max(1, Math.floor((foe.baseXp * foe.level) / 5));
}

export function catchChance(creature) {
  const hpPart = Math.floor((creature.catchRate * (3 * creature.maxHp - 2 * creature.hp)) / (3 * creature.maxHp));
  const bonus = creature.status ? 10 : 0;
  return Math.min(95, Math.max(1, hpPart + bonus));
}

// Draws exactly one number from rand.
export function attemptCatch(creature, rand) {
  return rand() * 100 < catchChance(creature);
}

function restat(c) {
  c.stats = { atk: calcStat(c.base.atk, c.level), def: calcStat(c.base.def, c.level), spd: calcStat(c.base.spd, c.level) };
  c.maxHp = calcMaxHp(c.base.hp, c.level);
}

export function makeCreature(species, level) {
  const lv = Math.min(MAX_LEVEL, Math.max(1, Math.floor(Number(level) || 1)));
  const c = {
    species: species.id,
    name: species.name,
    type: species.type,
    level: lv,
    xp: xpForLevel(lv),
    hp: 0,
    maxHp: 0,
    base: { ...species.base },
    stats: { atk: 0, def: 0, spd: 0 },
    baseXp: species.baseXp,
    catchRate: species.catchRate,
    moves: species.moves.map((id) => {
      const m = MOVES[id];
      if (!m) throw new Error(`unknown move ${id}`);
      return JSON.parse(JSON.stringify(m));
    }),
    status: null,
  };
  restat(c);
  c.hp = c.maxHp;
  return c;
}

// Returns the number of levels gained. Mutates the creature.
export function gainXp(creature, amount) {
  const add = Number.isInteger(amount) && amount > 0 ? amount : 0;
  creature.xp = Math.min(xpForLevel(MAX_LEVEL), creature.xp + add);
  let gained = 0;
  while (creature.level < MAX_LEVEL && creature.xp >= xpForLevel(creature.level + 1)) {
    creature.level += 1;
    gained += 1;
    const oldMax = creature.maxHp;
    restat(creature);
    if (creature.hp > 0) creature.hp += creature.maxHp - oldMax;
  }
  return gained;
}
