// Item 8: Status effects and their durations. Runs beside the workspace (demos/probe.mjs, scenario()) and plays the short battles below,
// returning the logs, hit points, statuses and random states they left at each point named; 08-status.test.mjs
// holds them to the brief.
import { engineOf, J, mv, mon, idle, config, MV, SW, ofType } from './fixtures.mjs';

export const SCORCH_AMOUNTS = [[80, 10], [30, 3], [7, 1], [9, 1], [15, 1], [16, 2], [100, 12], [1, 1]];
export const DAZE_SEEDS = 8;

const calm = (o = {}) => mon({ maxHp: 80, stats: { spd: 30 }, moves: [idle()], ...o });
const applying = (kind) => mv({ id: `apply-${kind}`, power: 0, accuracy: 100, status: { kind, chance: 100 } });
const copy = (v) => structuredClone(v);

export async function run({ load }) {
  const { battle: B, rng, data } = await engineOf(load);
  const { createBattle, resolveTurn } = B;
  const turn = (b, a = MV(0), c = MV(0)) => resolveTurn(b, [a, c]);
  const out = { STATUS_TURNS: copy(data.STATUS_TURNS) };

  // scorch from a preset status, five turns.
  {
    const b = createBattle(config(calm(), calm({ status: { kind: 'scorch', turns: 3 } })));
    const foe = b.sides[1].team[0];
    const hps = [];
    const cured = [];
    for (let t = 1; t <= 5; t++) {
      turn(b);
      hps.push(foe.hp);
      cured.push(ofType(b.log, 'cured').length);
    }
    out.preset = { hps, cured, status: copy(foe.status), log: copy(b.log), ownHp: b.sides[0].team[0].hp };
  }
  // the amount, one turn each
  out.amounts = SCORCH_AMOUNTS.map(([maxHp]) => {
    const b = createBattle(config(calm({ maxHp }), calm({ maxHp, status: { kind: 'scorch', turns: 3 } })));
    turn(b);
    return { log: copy(b.log), hp: b.sides[1].team[0].hp };
  });
  // both sides burn
  {
    const b = createBattle(config(calm({ status: { kind: 'scorch', turns: 2 } }), calm({ status: { kind: 'scorch', turns: 3 } })));
    turn(b);
    out.bothBurn = { log: copy(b.log), statuses: [copy(b.sides[0].team[0].status), copy(b.sides[1].team[0].status)] };
  }
  // scorch fells a creature
  {
    const b = createBattle(config(calm(), [calm({ hp: 5, status: { kind: 'scorch', turns: 3 } }), calm()]));
    turn(b);
    out.felled = { foe: copy(b.sides[1].team[0]), log: copy(b.log), phase: b.phase };
  }
  // scorch applied by a move
  out.applied = [20, 40].map((foeSpd) => {
    const b = createBattle(config(calm({ moves: [applying('scorch'), idle()] }), calm({ stats: { spd: foeSpd } })));
    const foe = b.sides[1].team[0];
    turn(b, MV(0), MV(0));
    const first = { hp: foe.hp, status: copy(foe.status), log: copy(b.log) };
    turn(b, MV(1), MV(0));
    turn(b, MV(1), MV(0));
    const third = { hp: foe.hp, status: copy(foe.status) };
    turn(b, MV(1), MV(0));
    return { first, third, fourth: { hp: foe.hp }, log: copy(b.log) };
  });

  // daze on a slower foe
  out.dazeSlow = [];
  {
    const hit = mv({ id: 'hit', power: 10, accuracy: 50 });
    for (let seed = 0; seed < DAZE_SEEDS; seed++) {
      const b = createBattle(config(calm({ stats: { spd: 40 }, moves: [applying('daze'), idle()] }), calm({ stats: { spd: 30 }, moves: [hit] }), { seed }));
      turn(b, MV(0), MV(0));
      const t1 = { log: copy(b.log), status: copy(b.sides[1].team[0].status) };
      turn(b, MV(1), MV(0));
      const t2 = { log: copy(b.log), status: copy(b.sides[1].team[0].status), rng: J(b.rng), start: J(rng.createRng(seed)), ownHp: b.sides[0].team[0].hp };
      turn(b, MV(1), MV(0));
      out.dazeSlow.push({ t1, t2, t3: { log: copy(b.log) } });
    }
  }
  // daze on a faster foe
  {
    const hit = mv({ id: 'hit', power: 10, accuracy: 100 });
    const b = createBattle(config(calm({ stats: { spd: 30 }, moves: [applying('daze'), idle()] }), calm({ stats: { spd: 50 }, moves: [hit] })));
    turn(b, MV(0), MV(0));
    const t1 = { log: copy(b.log), status: copy(b.sides[1].team[0].status) };
    turn(b, MV(1), MV(0));
    const t2 = { log: copy(b.log), status: copy(b.sides[1].team[0].status) };
    turn(b, MV(1), MV(0));
    out.dazeFast = { t1, t2, t3: { log: copy(b.log) } };
  }
  // chill, four turns
  {
    const moves = [];
    const b2 = createBattle(config(calm({ stats: { spd: 30 }, moves: [applying('chill'), idle()] }), calm({ stats: { spd: 40 }, moves: [mv({ id: 'hit', power: 10, accuracy: 100 })] })));
    for (let t = 1; t <= 4; t++) {
      const before = b2.log.length;
      turn(b2, MV(t === 1 ? 0 : 1), MV(0));
      moves.push(b2.log.slice(before).filter((e) => e.type === 'move').map((e) => e.side));
    }
    out.chill = { moves, status: copy(b2.sides[1].team[0].status), log: copy(b2.log) };
  }
  // at most one status
  {
    const b = createBattle(config(calm({ moves: [applying('scorch'), idle()] }), calm({ status: { kind: 'daze', turns: 2 } })));
    turn(b);
    out.oneStatus = { log: copy(b.log), foe: copy(b.sides[1].team[0]) };
  }
  // a benched creature's status
  {
    const burnt = calm({ name: 'Benched', hp: 50, status: { kind: 'scorch', turns: 3 } });
    const b = createBattle(config([calm(), burnt], calm()));
    for (let t = 0; t < 3; t++) turn(b);
    const benched = { originalHp: burnt.hp, bench: copy(b.sides[0].team[1]) };
    resolveTurn(b, [SW(1), MV(0)]);
    out.bench = { ...benched, inPlay: copy(b.sides[0].team[1]) };
  }
  // fainting by a move
  {
    const killer = mv({ id: 'killer', power: 120, accuracy: 100 });
    const b = createBattle(config(calm({ stats: { spd: 40 }, moves: [killer] }), [calm({ hp: 1, status: { kind: 'daze', turns: 2 } }), calm()]));
    turn(b);
    out.faintByMove = copy(b.sides[1].team[0]);
  }
  return out;
}
