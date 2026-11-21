// Item 12: XP and levelling. Runs beside the workspace (demos/probe.mjs, scenario()) and returns what xpForLevel,
// levelForXp, xpReward and gainXp gave, and the creatures gainXp left; 12-xp-levels.test.mjs holds them to the brief.
import { engineOf, clone, mon } from './fixtures.mjs';

export const CURVE = { 1: 0, 2: 12, 3: 36, 4: 72, 5: 120, 6: 180, 10: 540, 14: 1092, 15: 1260, 20: 2280, 29: 4872, 30: 5220 };
export const LEVEL_FOR = [[0, 1], [11, 1], [12, 2], [35, 2], [36, 3], [1091, 13], [1092, 14], [5219, 29], [5220, 30], [99999, 30]];
export const REWARDS = [[{ baseXp: 60, level: 5 }, 60], [{ baseXp: 50, level: 7 }, 70], [{ baseXp: 45, level: 3 }, 27], [{ baseXp: 62, level: 7 }, 86], [{ baseXp: 20, level: 1 }, 4], [{ baseXp: 3, level: 1 }, 1], [{ baseXp: 150, level: 30 }, 900]];
export const SMALL = [0, 5, 54];
export const BAD_AMOUNTS = [0.9, 5.9, -5, NaN, '10', undefined, null, {}];

const copy = (v) => structuredClone(v);

export async function run({ load }) {
  const { data, rules } = await engineOf(load);
  const { xpForLevel, levelForXp, xpReward, gainXp, makeCreature, MAX_LEVEL } = rules;
  const out = { MAX_LEVEL };
  out.curve = Object.keys(CURVE).map((level) => xpForLevel(Number(level)));
  out.levelFor = LEVEL_FOR.map(([xp]) => levelForXp(xp));
  out.roundTrip = Array.from({ length: 30 }, (_, i) => {
    const level = i + 1;
    return [levelForXp(xpForLevel(level)), levelForXp(xpForLevel(level) - 1)];
  });
  out.rewards = REWARDS.map(([c]) => xpReward(c));

  const moveIds = Object.keys(data.MOVES);
  const species = { id: 'fx', name: 'Fx', type: 'moss', base: { hp: 50, atk: 40, def: 30, spd: 20 }, baseXp: 60, catchRate: 33, moves: [moveIds[0], moveIds[1]] };
  const fresh = (level = 5) => makeCreature(species, level);

  out.small = SMALL.map((amount) => {
    const c = fresh();
    const before = clone(c);
    const gained = gainXp(c, amount);
    return { gained, before, after: copy(c) };
  });
  out.bad = BAD_AMOUNTS.map((amount) => {
    const c = fresh();
    const before = clone(c);
    const gained = gainXp(c, amount);
    return { gained, before, after: copy(c) };
  });
  {
    const c = fresh();
    const g1 = gainXp(c, 55);
    const at175 = copy(c);
    const g2 = gainXp(c, 5);
    out.oneLevel = { gained: [g1, g2], at175, after: copy(c) };
  }
  {
    const c = fresh();
    c.hp = 10;
    out.hurt = { gained: gainXp(c, 60), after: copy(c) };
  }
  {
    const c = fresh();
    const gained = gainXp(c, 1000);
    const d = fresh();
    d.hp = 1;
    gainXp(d, 1000);
    const made = makeCreature(species, 14);
    out.several = { gained, after: copy(c), hurtHp: d.hp, made: { stats: copy(made.stats), maxHp: made.maxHp } };
  }
  {
    const c = fresh();
    c.hp = 0;
    out.fainted = { gained: gainXp(c, 1000), after: copy(c) };
  }
  {
    const c = fresh();
    const g1 = gainXp(c, 1e9);
    const capped = copy(c);
    const g2 = gainXp(c, 500);
    const e = makeCreature(species, 29);
    const g3 = gainXp(e, 400);
    out.cap = { gained: [g1, g2, g3], capped, after: copy(c), from29: copy(e) };
  }
  {
    const c = mon({ level: 5, xp: 120, maxHp: 31, hp: 31, base: { hp: 50, atk: 100, def: 100, spd: 100 }, stats: { atk: 1, def: 1, spd: 1 } });
    gainXp(c, 60);
    out.fromBase = { stats: copy(c.stats), maxHp: c.maxHp };
  }
  return out;
}
