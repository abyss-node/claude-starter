// Item 15: Two players, one screen. Runs beside the workspace (demos/probe.mjs, scenario()) and steps the duels
// below, returning the duel and its view at each point named and what each refused call did;
// 15-duel.test.mjs holds them to the brief.
import { engineOf, J, mv, mon, idle, config, MV, SW, thrown } from './fixtures.mjs';

export const HIDDEN_SEEDS = [1, 2, 3, 9];

const swing = (id, power = 20) => mv({ id, power, accuracy: 100 });
const team = (spd, tag) => [
  mon({ name: `${tag}1`, maxHp: 200, stats: { spd }, moves: [swing(`${tag}a`), swing(`${tag}b`, 30), swing(`${tag}c`, 25)] }),
  mon({ name: `${tag}2`, maxHp: 200, stats: { spd: spd + 3 }, moves: [swing(`${tag}d`), swing(`${tag}e`, 35)] }),
  mon({ name: `${tag}3`, maxHp: 200, stats: { spd: spd - 3 }, moves: [swing(`${tag}f`)] }),
];
const cfg = (seed = 1) => config(team(40, 'L'), team(30, 'R'), { seed });
const copy = (v) => structuredClone(v);
const refused = (d, fn) => { const before = J(d); const call = thrown(fn); return { before, call, after: J(d) }; };

export async function run({ load }) {
  const { duel: D, battle: B } = await engineOf(load);
  const { createDuel, duelContinue, duelPick, duelView } = D;
  const { createBattle, resolveTurn, legalActions } = B;
  const at = (d) => ({ duel: copy(d), view: copy(duelView(d)) });
  const out = {};

  // The stages, in order.
  {
    const config0 = cfg(4);
    const frozen = J(config0);
    const d = createDuel(config0);
    const s = { configBefore: frozen, configAfter: J(config0), created: at(d) };
    s.coverPicks = [refused(d, () => duelPick(d, 0, MV(0))), refused(d, () => duelPick(d, 1, MV(0)))];
    duelContinue(d);
    s.firstPick = { ...at(d), legal: copy(legalActions(d.battle, 0)) };
    s.firstBad = [
      refused(d, () => duelContinue(d)), refused(d, () => duelPick(d, 1, MV(0))), refused(d, () => duelPick(d, 0, MV(9))),
      refused(d, () => duelPick(d, 0, { kind: 'snare' })), refused(d, () => duelPick(d, 0, SW(0))),
    ];
    const beforeBattle = J(d.battle);
    duelPick(d, 0, MV(1));
    s.picked = { ...at(d), battleBefore: beforeBattle, battle: J(d.battle) };
    s.secondCover = [refused(d, () => duelPick(d, 0, MV(0))), refused(d, () => duelPick(d, 1, MV(0)))];
    duelContinue(d);
    s.secondPick = { ...at(d), legal: copy(legalActions(d.battle, 1)) };
    s.secondBad = [refused(d, () => duelPick(d, 0, MV(0))), refused(d, () => duelPick(d, 1, MV(7)))];
    duelPick(d, 1, MV(0));
    const direct = createBattle(cfg(4));
    resolveTurn(direct, [MV(1), MV(0)]);
    s.result = { ...at(d), battle: J(d.battle), direct: J(direct), directLog: copy(direct.log) };
    s.resultPick = refused(d, () => duelPick(d, 0, MV(0)));
    duelContinue(d);
    s.next = at(d);
    out.stages = s;
  }

  // The first player's choice, against everything shown before the turn resolves.
  const stagesBefore = (seed, a0) => {
    const d = createDuel(cfg(seed));
    const views = [J(duelView(d))];
    duelContinue(d);
    views.push(J(duelView(d)));
    duelPick(d, 0, a0);
    views.push(J(duelView(d)));
    duelContinue(d);
    views.push(J(duelView(d)));
    return views;
  };
  out.hidden = HIDDEN_SEEDS.map((seed) => {
    const choices = legalActions(createDuel(cfg(seed)).battle, 0);
    return { choices: copy(choices), views: choices.map((a0) => stagesBefore(seed, a0)) };
  });

  // The replacement phase.
  {
    const killer = mv({ id: 'killer', power: 120, accuracy: 100 });
    const d = createDuel(config(
      mon({ name: 'Hunter', stats: { spd: 40 }, moves: [killer] }),
      [mon({ name: 'Weak', hp: 1, stats: { spd: 30 } }), mon({ name: 'Back' })],
      { seed: 2 },
    ));
    duelContinue(d);
    duelPick(d, 0, MV(0));
    duelContinue(d);
    duelPick(d, 1, MV(0));
    const result = at(d);
    duelContinue(d);
    const asked = at(d);
    duelContinue(d);
    const picking = at(d);
    const otherPicks = refused(d, () => duelPick(d, 0, MV(0)));
    duelPick(d, 1, SW(1));
    const replaced = at(d);
    duelContinue(d);
    out.replace = { result, asked, picking, otherPicks, replaced, next: at(d) };
  }
  // Both sides must replace.
  {
    const burning = (name) => mon({ name, hp: 3, stats: { spd: 30 }, moves: [idle()], status: { kind: 'scorch', turns: 3 } });
    const replacements = (tag) => [mon({ name: `${tag}x`, moves: [idle()] }), mon({ name: `${tag}y`, moves: [idle()] })];
    const play = (firstPick) => {
      const d = createDuel(config([burning('A'), ...replacements('a')], [burning('B'), ...replacements('b')], { seed: 6 }));
      duelContinue(d); duelPick(d, 0, MV(0));
      duelContinue(d); duelPick(d, 1, MV(0));
      const asked = at(d);
      duelContinue(d);
      const queued = at(d);
      const views = [J(duelView(d))];
      duelContinue(d);
      views.push(J(duelView(d)));
      duelPick(d, 0, firstPick);
      views.push(J(duelView(d)));
      const oneIn = at(d);
      duelContinue(d);
      views.push(J(duelView(d)));
      return { d, seen: { asked, queued, views, oneIn, last: at(d) } };
    };
    const one = play(SW(1));
    const two = play(SW(2));
    duelPick(one.d, 1, SW(2));
    out.bothReplace = { one: one.seen, two: two.seen, done: at(one.d) };
  }

  // To the end.
  {
    const killer = mv({ id: 'killer', power: 120, accuracy: 100 });
    const d = createDuel(config(mon({ stats: { spd: 40 }, moves: [killer] }), mon({ hp: 1, stats: { spd: 30 } }), { seed: 2 }));
    duelContinue(d); duelPick(d, 0, MV(0));
    duelContinue(d); duelPick(d, 1, MV(0));
    const result = at(d);
    duelContinue(d);
    out.end = { result, over: at(d), more: refused(d, () => duelContinue(d)), pick: refused(d, () => duelPick(d, 0, MV(0))) };
  }
  return out;
}
