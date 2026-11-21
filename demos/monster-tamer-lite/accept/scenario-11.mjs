// Item 11: Catching. Runs beside the workspace (demos/probe.mjs, scenario()) and returns what catchChance and
// attemptCatch gave, and what each snare battle left, with the workspace's own draws from the same seed;
// 11-catching.test.mjs works out what should have happened and compares.
import { engineOf, probeOf, J, mv, mon, idle, config, MV, SNARE } from './fixtures.mjs';

const c = (o) => mon({ maxHp: 60, catchRate: 40, ...o });
export const CHANCES = [
  [c({ hp: 60 }), 13], [c({ hp: 30 }), 26], [c({ hp: 1 }), 39], [c({ hp: 60, status: { kind: 'daze', turns: 2 } }), 23],
  [c({ hp: 60, status: { kind: 'chill', turns: 2 } }), 23], [c({ hp: 60, status: { kind: 'scorch', turns: 2 } }), 23],
  [c({ hp: 1, status: { kind: 'scorch', turns: 2 } }), 49], [c({ catchRate: 77, maxHp: 45, hp: 17 }), 57],
  [c({ catchRate: 100, hp: 1 }), 95, 'capped at 95'], [c({ catchRate: 100, hp: 60 }), 33],
  [c({ catchRate: 100, hp: 1, status: { kind: 'daze', turns: 1 } }), 95], [c({ catchRate: 100, hp: 5 }), 94],
  [c({ catchRate: 100, hp: 5, status: { kind: 'daze', turns: 1 } }), 95, 'the cap holds after the bonus'],
  [c({ catchRate: 1, hp: 60 }), 1, 'at least 1'], [c({ catchRate: 2, hp: 60 }), 1],
  [c({ catchRate: 1, hp: 60, status: { kind: 'daze', turns: 1 } }), 10], [c({ catchRate: 50, maxHp: 90, hp: 30 }), 38],
];
// [creature, its chance]; each is tried with the draws below.
export const ATTEMPTS = [[c({ hp: 60 }), 13], [c({ hp: 60, status: { kind: 'daze', turns: 1 } }), 23], [c({ hp: 1 }), 39]];
export const attemptDraws = (chance) => [[0, true], [(chance - 0.5) / 100, true], [(chance + 0.5) / 100, false], [0.9999, false]];
export const N = 300;
export const STATUS_SEEDS = 200;

const hitter = () => mv({ id: 'hit', power: 10, accuracy: 100 });
const foe = (o = {}) => mon({ maxHp: 60, hp: 30, catchRate: 50, stats: { spd: 99 }, moves: [hitter()], ...o });
const copy = (v) => structuredClone(v);

export async function run({ load }) {
  const { battle: B, rules } = await engineOf(load);
  const { catchChance, attemptCatch } = rules;
  const { createBattle, resolveTurn } = B;
  const makeProbe = probeOf(load);
  const out = {};
  out.chances = CHANCES.map(([creature]) => catchChance(creature));
  out.attempts = ATTEMPTS.map(([creature, chance]) => attemptDraws(chance).map(([r]) => {
    const calls = [];
    const got = attemptCatch(creature, () => { calls.push(r); return r; });
    return { got, calls: calls.length };
  }));

  out.battles = [];
  for (let seed = 0; seed < N; seed++) {
    const f = foe();
    const chance = catchChance(f);
    const p = await makeProbe(seed);
    const r = p.draw();
    const b = createBattle(config(mon({ moves: [idle()] }), f, { seed, wild: true, snares: 3 }));
    resolveTurn(b, [SNARE, MV(0)]);
    out.battles.push({ chance, r, after: p.state(), rng: J(b.rng), battle: copy(b) });
  }

  const once = (seed) => {
    const b = createBattle(config(mon({ moves: [idle()] }), foe({ status: { kind: 'daze', turns: 2 } }), { seed, wild: true, snares: 1 }));
    resolveTurn(b, [SNARE, MV(0)]);
    return b;
  };
  out.withStatus = [];
  for (let seed = 0; seed < STATUS_SEEDS; seed++) {
    const p = await makeProbe(seed);
    const r = p.draw();
    const b = once(seed);
    out.withStatus.push({ r, caught: b.caught, log: J(b.log), again: J(once(seed).log) });
  }

  {
    const b = createBattle(config(mon({ moves: [idle()] }), foe({ catchRate: 1, hp: 60, moves: [idle()] }), { seed: 5, wild: true, snares: 2 }));
    const p = await makeProbe(5);
    const r = p.draw();
    resolveTurn(b, [SNARE, MV(0)]);
    const first = { snares: b.snares, caught: b.caught };
    resolveTurn(b, [MV(0), MV(0)]);
    out.runsOut = { r, first, snares: b.snares, log: copy(b.log) };
  }
  return out;
}
