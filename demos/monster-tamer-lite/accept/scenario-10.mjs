// Item 10: Switching and legal actions. Runs beside the workspace (demos/probe.mjs, scenario()) and returns what
// legalActions and isLegalAction gave, what each refused resolveTurn did, and the battles the switches left;
// 10-switching-legal.test.mjs holds them to the brief.
import { engineOf, J, clone, mv, mon, idle, config, MV, SW, SNARE, thrown } from './fixtures.mjs';

const three = () => [mv({ id: 'a' }), mv({ id: 'b' }), mv({ id: 'c' })];
const team = () => [mon({ name: 'A', moves: three() }), mon({ name: 'B' }), mon({ name: 'C', hp: 0 }), mon({ name: 'D' })];
const copy = (v) => structuredClone(v);
const refused = (b, fn) => { const before = J(b); const call = thrown(fn); return { before, call, after: J(b) }; };

// [battle, side, action] asked of isLegalAction, by the name of the battle.
export const ASKED = [
  ['wild', 0, MV(3)], ['wild', 0, MV(-1)], ['wild', 0, SW(0)], ['wild', 0, SW(2)], ['wild', 0, SW(4)], ['wild', 0, { kind: 'dance' }],
  ['wild', 0, null], ['wild', 1, SNARE], ['tame', 0, SNARE], ['dry', 0, SNARE], ['wild', 0, { kind: 'move', slot: '0' }], ['wild', 0, SW(1)],
];
export const BAD = [
  [null, MV(0)], [MV(0), null], [null, null], [MV(5), MV(0)], [MV(0), MV(3)], [SW(0), MV(0)], [MV(0), SW(1 - 1)], [SW(2), MV(0)],
  [SW(9), MV(0)], [{ kind: 'dance' }, MV(0)], [MV(0), { kind: 'dance' }], [{}, MV(0)], [MV(0), SNARE], [undefined, MV(0)],
];

export async function run({ load }) {
  const { battle: B } = await engineOf(load);
  const { createBattle, resolveTurn, legalActions, isLegalAction } = B;
  const out = {};
  const battles = {
    wild: createBattle(config(team(), team(), { wild: true, snares: 2 })),
    tame: createBattle(config(team(), team(), { wild: false, snares: 2 })),
    dry: createBattle(config(team(), team(), { wild: true, snares: 0 })),
    lone: createBattle(config(mon({ moves: [mv()] }), mon(), { wild: true, snares: 1 })),
  };
  out.legal = Object.fromEntries(Object.entries(battles).map(([k, b]) => [k, [copy(legalActions(b, 0)), copy(legalActions(b, 1))]]));
  // Each listed action asked back, and the first with an extra property.
  out.listedAsked = Object.fromEntries(['wild', 'tame', 'dry'].map((k) => [k, [0, 1].map((side) => {
    const legal = legalActions(battles[k], side);
    return { each: legal.map((a) => isLegalAction(battles[k], side, a)), junk: isLegalAction(battles[k], side, { ...legal[0], junk: 1 }) };
  })]));
  out.asked = ASKED.map(([k, side, a]) => isLegalAction(battles[k], side, a));

  out.bad = BAD.map((choices) => {
    const b = createBattle(config(team(), team(), { wild: true, snares: 2, seed: 6 }));
    return refused(b, () => resolveTurn(b, choices));
  });
  out.badSnare = [refused(battles.tame, () => resolveTurn(battles.tame, [SNARE, MV(0)])), refused(battles.dry, () => resolveTurn(battles.dry, [SNARE, MV(0)]))];

  {
    const slow = mon({ name: 'Slow', stats: { spd: 10 }, moves: [mv({ id: 'x', power: 10 })] });
    const reserve = mon({ name: 'Reserve', stats: { spd: 10 }, moves: [mv({ id: 'y', power: 10 })] });
    const foe = mon({ name: 'Foe', stats: { spd: 99 }, moves: [mv({ id: 'f', power: 40 })] });
    const b = createBattle(config([slow, reserve], foe, { seed: 8 }));
    const choices = [SW(1), MV(0)];
    resolveTurn(b, choices);
    choices[0].to = 0;
    const first = copy(b);
    resolveTurn(b, [MV(0), MV(0)]);
    out.switchIn = { first, second: copy(b) };
  }
  {
    const b = createBattle(config([mon(), mon({ name: 'X' })], [mon(), mon({ name: 'Y' })]));
    resolveTurn(b, [SW(1), SW(1)]);
    out.bothSwitch = copy(b);
  }
  {
    const b = createBattle(config([mon({ moves: [mv(), mv()] }), mon({ moves: [mv(), mv(), mv(), mv()] })], mon()));
    resolveTurn(b, [SW(1), MV(0)]);
    out.afterSwitch = copy(legalActions(b, 0));
  }
  {
    const b = createBattle(config(mon({ moves: [idle()] }), mon({ moves: [idle()] })));
    out.failed = [];
    for (let i = 0; i < 4; i++) {
      out.failed.push(thrown(() => resolveTurn(b, [MV(7), MV(0)])));
      resolveTurn(b, [MV(0), MV(0)]);
    }
    out.longRun = { history: clone(b.history), historyLength: b.history.length, turn: b.turn };
  }
  return out;
}
