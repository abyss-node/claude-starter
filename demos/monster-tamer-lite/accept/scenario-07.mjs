// Item 7: Accuracy and the draw order. Runs beside the workspace (demos/probe.mjs, scenario()) and returns, for each
// battle below, its log, the random state after the turn and the workspace's own draws from the same seed (with the
// state after each); 07-accuracy-draws.test.mjs works out what should have happened and compares.
import { engineOf, probeOf, J, mv, mon, config, MV, SNARE } from './fixtures.mjs';

const fighter = (spd, moves, o = {}) => mon({ maxHp: 600, stats: { spd }, moves, ...o });

// What one battle left, with `n` draws of the workspace's generator from its seed (and the state after each).
async function oneTurn(B, makeProbe, seed, cfg, choices, n) {
  const p = await makeProbe(seed);
  const draws = [];
  const states = [p.state()];
  for (let i = 0; i < n; i++) { draws.push(p.draw()); states.push(p.state()); }
  const b = B.createBattle(cfg);
  B.resolveTurn(b, choices);
  return { draws, states, log: structuredClone(b.log), rng: J(b.rng), foe: structuredClone(b.sides[1].team[0]) };
}

export const RUNS = {
  sure: [20, (seed) => { const m = mv({ power: 10, accuracy: 100, status: { kind: 'chill', chance: 100 } }); return config(fighter(40, [m]), fighter(30, [m]), { seed }); }],
  half: [60, (seed) => { const m = mv({ power: 10, accuracy: 50 }); return config(fighter(40, [m]), fighter(30, [m]), { seed }); }],
  statusAfterHit: [80, (seed) => config(fighter(40, [mv({ power: 10, accuracy: 70, status: { kind: 'daze', chance: 40 } })]), fighter(30, [mv({ power: 10, accuracy: 100 })]), { seed })],
  fells: [40, (seed) => config(fighter(40, [mv({ power: 90, accuracy: 90, status: { kind: 'scorch', chance: 50 } })]), fighter(30, [mv()], { hp: 1 }), { seed })],
  hasStatus: [20, (seed) => config(fighter(40, [mv({ power: 10, accuracy: 100, status: { kind: 'chill', chance: 50 } })]), fighter(30, [mv({ power: 0 })], { status: { kind: 'scorch', turns: 3 } }), { seed })],
  miss: [40, (seed) => config(fighter(40, [mv({ power: 90, accuracy: 1, status: { kind: 'scorch', chance: 100 } })]), fighter(30, [mv({ power: 0 })]), { seed })],
  statusMove: [40, (seed) => config(fighter(40, [mv({ power: 0, accuracy: 50, status: { kind: 'daze', chance: 100 } })]), fighter(30, [mv({ power: 0 })]), { seed })],
  snare: [60, (seed) => config(fighter(30, [mv()]), fighter(30, [mv({ power: 10, accuracy: 60 })], { catchRate: 1 }), { seed, wild: true, snares: 1 }), [SNARE, MV(0)]],
  tie: [60, (seed) => { const m = mv({ power: 10, accuracy: 50 }); return config(fighter(30, [m]), fighter(30, [m]), { seed }); }],
};

export async function run({ load }) {
  const { battle: B } = await engineOf(load);
  const makeProbe = probeOf(load);
  const out = {};
  for (const [name, [seeds, cfg, choices]] of Object.entries(RUNS)) {
    out[name] = [];
    for (let seed = 0; seed < seeds; seed++) out[name].push(await oneTurn(B, makeProbe, seed, cfg(seed), choices || [MV(0), MV(0)], 3));
  }
  return out;
}
