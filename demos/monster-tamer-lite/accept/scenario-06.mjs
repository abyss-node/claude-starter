// Item 6: Speed order and the tie rule. Runs beside the workspace (demos/probe.mjs, scenario()) and returns, for
// each battle below, the order of the moves, the log's entry types and the random state, with the workspace's own
// draws from the same seed; 06-speed-order.test.mjs works out the right order and compares.
import { engineOf, probeOf, J, mv, mon, config, MV, SW, SNARE, types, ofType } from './fixtures.mjs';

export const SPEED_PAIRS = [[40, 30, 0], [30, 40, 1], [99, 1, 0], [2, 3, 1]];
export const TIE_SEEDS = 200;
export const SNARE_SEEDS = 60;

const hit = () => mv({ id: 'hit', power: 10, accuracy: 100 });
const fighter = (spd, o = {}) => mon({ maxHp: 600, stats: { spd }, moves: [hit()], ...o });
const order = (log) => ofType(log, 'move').map((e) => e.side);
const chill = (turns = 3) => ({ kind: 'chill', turns });

export async function run({ load }) {
  const { battle: B, rng, rules } = await engineOf(load);
  const { createBattle, resolveTurn } = B;
  const makeProbe = probeOf(load);
  const out = {};

  // Different speeds, many seeds.
  out.fixed = [];
  for (let seed = 1; seed <= 20; seed++) {
    for (const [s0, s1] of SPEED_PAIRS) {
      const b = createBattle(config(fighter(s0), fighter(s1), { seed }));
      resolveTurn(b, [MV(0), MV(0)]);
      out.fixed.push({ order: order(b.log), rng: J(b.rng), start: J(rng.createRng(seed)) });
    }
  }

  // Ties.
  out.ties = [];
  for (let seed = 0; seed < TIE_SEEDS; seed++) {
    const p = await makeProbe(seed);
    const r = p.draw();
    const b = createBattle(config(fighter(30), fighter(30), { seed }));
    resolveTurn(b, [MV(0), MV(0)]);
    out.ties.push({ r, after: p.state(), order: order(b.log), rng: J(b.rng) });
  }
  const one = (seed) => { const b = createBattle(config(fighter(30), fighter(30), { seed })); resolveTurn(b, [MV(0), MV(0)]); return J(b.log); };
  out.sameSeed = [one(77), one(77)];

  // Only one side moving.
  {
    const b = createBattle(config(fighter(30), [fighter(30), fighter(5)], { seed: 4 }));
    resolveTurn(b, [MV(0), SW(1)]);
    const b2 = createBattle(config([fighter(30), fighter(5)], fighter(30), { seed: 4 }));
    resolveTurn(b2, [SW(1), MV(0)]);
    out.lone = { rng: [J(b.rng), J(b2.rng)], start: J(rng.createRng(4)) };
  }

  // Chill.
  {
    out.speeds = [
      fighter(40), fighter(40, { status: chill() }), fighter(41, { status: chill() }), fighter(7, { status: chill() }),
      fighter(40, { status: { kind: 'scorch', turns: 3 } }), fighter(40, { status: { kind: 'daze', turns: 2 } }),
    ].map((c) => rules.effectiveSpeed(c));
    const b = createBattle(config(fighter(40, { status: chill() }), fighter(30), { seed: 3 }));
    resolveTurn(b, [MV(0), MV(0)]);
    const t = createBattle(config(fighter(41, { status: chill() }), fighter(20), { seed: 5 }));
    resolveTurn(t, [MV(0), MV(0)]);
    const u = createBattle(config(fighter(40, { status: { kind: 'scorch', turns: 3 } }), fighter(30), { seed: 3 }));
    resolveTurn(u, [MV(0), MV(0)]);
    out.chill = { chilledOrder: order(b.log), tieRng: J(t.rng), tieStart: J(rng.createRng(5)), scorchOrder: order(u.log) };
  }

  // Switches and moves.
  out.switches = [[10, 99], [99, 10]].map(([s0, s1]) => {
    const b = createBattle(config([fighter(s0), fighter(s0)], fighter(s1), { seed: 2 }));
    resolveTurn(b, [SW(1), MV(0)]);
    const c = createBattle(config(fighter(s0), [fighter(s1), fighter(s1)], { seed: 2 }));
    resolveTurn(c, [MV(0), SW(1)]);
    return [types(b.log), types(c.log)];
  });

  // The snare against a much faster foe, on every seed; the test keeps those where the snare fails.
  out.snares = [];
  for (let seed = 0; seed < SNARE_SEEDS; seed++) {
    const p = await makeProbe(seed);
    const r = p.draw();
    const b = createBattle(config(fighter(1), fighter(99, { catchRate: 1 }), { seed, wild: true, snares: 2 }));
    resolveTurn(b, [SNARE, MV(0)]);
    out.snares.push({ r, types: types(b.log) });
  }
  return out;
}
