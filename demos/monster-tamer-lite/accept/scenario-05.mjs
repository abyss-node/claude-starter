// Item 5: Stats and damage. Runs beside the workspace (demos/probe.mjs, scenario()) and returns what calcStat,
// calcMaxHp, makeCreature and calcDamage gave for the inputs below; 05-stats-damage.test.mjs works out the right
// answers from the same inputs and compares.
import { engineOf, mv, mon, testRng, deepFreeze, objectIds, TYPE_NAMES } from './fixtures.mjs';

export const STAT_CALLS = [[50, 10], [63, 7], [45, 30], [1, 1], [150, 30]];
export const HP_CALLS = [[50, 10], [63, 7], [100, 30], [10, 1]];
export const ODD_LEVELS = [0, -4, 99, 7.9];

export const species = (moveIds) => ({ id: 'fx-species', name: 'Fx Species', type: 'moss', base: { hp: 50, atk: 40, def: 30, spd: 20 }, baseXp: 60, catchRate: 33, moves: [moveIds[0], moveIds[1]], extra: 'ignored' });

const attacker = (o = {}) => mon({ type: 'moss', level: 10, stats: { atk: 30 }, ...o });
const defender = (o = {}) => mon({ type: 'spark', stats: { def: 30 }, ...o });

// [attacker, defender, move]
export const FIXED = () => [
  [attacker(), defender(), mv({ type: 'cinder', power: 40 })],
  [attacker(), defender(), mv({ type: 'moss', power: 40 })],
  [attacker(), defender({ type: 'cinder' }), mv({ type: 'tide', power: 40 })],
  [attacker(), defender({ type: 'tide' }), mv({ type: 'cinder', power: 40 })],
  [attacker({ type: 'tide' }), defender({ type: 'cinder' }), mv({ type: 'tide', power: 40 })],
  [attacker({ type: 'cinder' }), defender({ type: 'tide' }), mv({ type: 'cinder', power: 40 })],
  [attacker({ type: 'spark' }), defender({ type: 'stone' }), mv({ type: 'spark', power: 150 })],
  [attacker(), defender({ type: 'stone' }), mv({ type: 'spark', power: 150 })],
  [attacker(), defender({ type: 'cinder' }), mv({ type: 'tide', power: 0 })],
  [attacker({ level: 1, stats: { atk: 5 } }), defender({ stats: { def: 200 } }), mv({ type: 'cinder', power: 5 })],
  [attacker({ level: 1, stats: { atk: 5 } }), defender({ type: 'tide', stats: { def: 200 } }), mv({ type: 'cinder', power: 5 })],
  [attacker({ level: 1 }), defender(), mv({ type: 'cinder', power: 40 })],
  [attacker({ level: 30 }), defender(), mv({ type: 'cinder', power: 40 })],
  [attacker({ stats: { atk: 60 } }), defender({ stats: { def: 20 } }), mv({ type: 'cinder', power: 30 })],
  [attacker({ stats: { atk: 20 } }), defender({ stats: { def: 60 } }), mv({ type: 'cinder', power: 30 })],
  [attacker({ stats: { atk: 30, def: 1, spd: 1 } }), defender({ stats: { atk: 1, def: 30, spd: 99 } }), mv({ type: 'cinder', power: 40 })],
];

// Many random cases, the same in every process.
export function randomCases() {
  const rnd = testRng(2024);
  const pick = (n) => Math.floor(rnd() * n);
  return Array.from({ length: 600 }, () => {
    const a = attacker({ type: TYPE_NAMES[pick(5)], level: 1 + pick(30), stats: { atk: 5 + pick(200) } });
    const d = defender({ type: TYPE_NAMES[pick(5)], stats: { def: 5 + pick(200) } });
    const m = mv({ type: TYPE_NAMES[pick(5)], power: pick(151) });
    return [a, d, m];
  });
}

export async function run({ load }) {
  const { data, rules } = await engineOf(load);
  const { calcStat, calcMaxHp, calcDamage, makeCreature, MAX_LEVEL } = rules;
  const out = { MAX_LEVEL };
  out.stat = STAT_CALLS.map(([b, l]) => calcStat(b, l));
  out.maxHp = HP_CALLS.map(([b, l]) => calcMaxHp(b, l));

  const moveIds = Object.keys(data.MOVES);
  out.moveIds = moveIds.slice(0, 2);
  out.moves = out.moveIds.map((m) => structuredClone(data.MOVES[m]));
  const sp = species(moveIds);
  const c = makeCreature(sp, 5);
  out.creature = structuredClone(c);
  const id = objectIds();
  out.moveIds2 = [id(c.moves[0]), id(data.MOVES[moveIds[0]])];
  c.moves[0].power = 999;
  c.base.hp = 1;
  out.afterEdit = { movePower: data.MOVES[moveIds[0]].power, speciesHp: sp.base.hp };
  out.oddLevels = ODD_LEVELS.map((l) => makeCreature(sp, l).level);
  out.xpAt30 = makeCreature(sp, 30).xp;
  out.xpAt1 = makeCreature(sp, 1).xp;
  const l30 = makeCreature(sp, 30);
  out.l30 = { maxHp: l30.maxHp, stats: structuredClone(l30.stats) };

  out.fixed = FIXED().map(([a, d, m]) => calcDamage(deepFreeze(a), deepFreeze(d), deepFreeze(m)));
  out.random = randomCases().map(([a, d, m]) => {
    const got = calcDamage(a, d, m);
    return [got, structuredClone([a, d, m])];
  });
  return out;
}
