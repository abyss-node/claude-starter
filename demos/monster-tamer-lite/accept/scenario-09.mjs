// Item 9: A fainted creature cannot act. Runs beside the workspace (demos/probe.mjs, scenario()) and plays the
// battles below, returning the battles (and legal actions) at each point named and what each refused call did;
// 09-fainted.test.mjs holds them to the brief.
import { engineOf, J, mv, mon, idle, config, MV, SW, thrown } from './fixtures.mjs';

export const TIE_SEEDS = 30;
const killer = () => mv({ id: 'killer', power: 120, accuracy: 100 });
const swing = () => mv({ id: 'swing', power: 20, accuracy: 100 });
const burning = () => mon({ hp: 3, moves: [idle()], status: { kind: 'scorch', turns: 3 } });
const copy = (v) => structuredClone(v);
// A call that should be refused: the battle as text before and after it, and what it threw.
const refused = (b, fn) => { const before = J(b); const call = thrown(fn); return { before, call, after: J(b) }; };

export async function run({ load }) {
  const { battle: B } = await engineOf(load);
  const { createBattle, resolveTurn, legalActions } = B;
  const legal = (b) => [copy(legalActions(b, 0)), copy(legalActions(b, 1))];
  const out = {};

  {
    const b = createBattle(config(mon({ stats: { spd: 40 }, moves: [killer()] }), mon({ hp: 1, stats: { spd: 30 }, moves: [swing()] }), { seed: 9 }));
    resolveTurn(b, [MV(0), MV(0)]);
    out.fasterFells = {
      battle: copy(b), legal: legal(b),
      again: refused(b, () => resolveTurn(b, [MV(0), MV(0)])),
      nulls: refused(b, () => resolveTurn(b, [null, null])),
    };
  }
  {
    const b = createBattle(config(mon({ hp: 1, stats: { spd: 20 }, moves: [swing()] }), mon({ stats: { spd: 40 }, moves: [killer()] }), { seed: 9 }));
    resolveTurn(b, [MV(0), MV(0)]);
    out.otherWay = copy(b);
  }
  out.ties = [];
  for (let seed = 0; seed < TIE_SEEDS; seed++) {
    const b = createBattle(config(mon({ hp: 1, stats: { spd: 30 }, moves: [killer()] }), mon({ hp: 1, stats: { spd: 30 }, moves: [killer()] }), { seed }));
    resolveTurn(b, [MV(0), MV(0)]);
    out.ties.push({ log: copy(b.log), winner: b.winner });
  }
  {
    const b = createBattle(config(burning(), burning()));
    resolveTurn(b, [MV(0), MV(0)]);
    out.draw = copy(b);
  }
  {
    const b = createBattle(config(mon({ stats: { spd: 40 }, moves: [killer()] }), [mon({ hp: 1 }), mon({ hp: 0 })], { seed: 3 }));
    resolveTurn(b, [MV(0), MV(0)]);
    out.benchFainted = { phase: b.phase, winner: b.winner };
  }

  // Replacement.
  {
    const fallen = mon({ name: 'Fallen', hp: 1, stats: { spd: 30 }, moves: [swing()] });
    const gone = mon({ name: 'Out', hp: 0 });
    const spare = mon({ name: 'Spare', stats: { spd: 30 }, moves: [swing()] });
    const b = createBattle(config([mon({ name: 'Hunter', stats: { spd: 40 }, moves: [killer()] }), mon({ name: 'Bench' })], [fallen, gone, spare], { seed: 5 }));
    resolveTurn(b, [MV(0), MV(0)]);
    const asked = { battle: copy(b), legal: legal(b) };
    const bad = [[MV(0), null], [null, MV(0)], [null, SW(1)], [null, SW(0)], [null, null], [SW(1), SW(2)]].map((choices) => refused(b, () => resolveTurn(b, choices)));
    const logLength = b.log.length;
    const state = J(b.rng);
    resolveTurn(b, [null, SW(2)]);
    const replaced = { battle: copy(b), newEntries: copy(b.log.slice(logLength)), rngBefore: state, rng: J(b.rng) };
    resolveTurn(b, [MV(0), MV(0)]);
    out.replace = { asked, bad, replaced, next: copy(b) };
  }
  {
    const b = createBattle(config([burning(), mon()], [burning(), mon()]));
    resolveTurn(b, [MV(0), MV(0)]);
    const asked = { battle: copy(b), legal: legal(b), oneOfTwo: refused(b, () => resolveTurn(b, [SW(1), null])) };
    const at = b.log.length;
    resolveTurn(b, [SW(1), SW(1)]);
    out.bothReplace = { asked, newEntries: copy(b.log.slice(at)), phase: b.phase };
  }
  {
    const b = createBattle(config(burning(), [burning(), mon()]));
    resolveTurn(b, [MV(0), MV(0)]);
    out.nothingLeft = { phase: b.phase, winner: b.winner };
  }
  {
    const b = createBattle(config([mon({ hp: 0 }), mon({ hp: 0 }), mon({ name: 'Third' })], mon()));
    out.start = {
      active: b.sides[0].active, name: b.sides[0].team[2].name, legal: copy(legalActions(b, 0)),
      noneLeft: thrown(() => createBattle(config([mon({ hp: 0 }), mon({ hp: 0 })], mon()))),
      noneRight: thrown(() => createBattle(config(mon(), [mon({ hp: 0 })]))),
    };
  }
  return out;
}
