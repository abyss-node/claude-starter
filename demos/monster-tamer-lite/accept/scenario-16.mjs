// Item 16: The computer opponent. Runs beside the workspace (demos/probe.mjs, scenario()) and asks chooseAction at
// every position of many battles, returning its answers (asked again, of a copy and of a fresh battle), the legal
// actions there and a digest of the battle before and after asking; 16-ai.test.mjs holds them to the brief.
import { engineOf, J, clone, mv, mon, idle, config, MV, testRng, fnv1a, randTeam } from './fixtures.mjs';

export const RANDOM_SEEDS = 60;
export const EQUAL_SEEDS = 80;
export const AI_SEEDS = 40;
const digest = (v) => fnv1a(J(v));
const copy = (v) => structuredClone(v);

export async function run({ load }) {
  const { battle: B, ai } = await engineOf(load);
  const { createBattle, resolveTurn, legalActions } = B;
  const { chooseAction } = ai;
  const out = {};

  // Every position of many random battles.
  out.positions = [];
  out.overAnswers = [];
  for (let seed = 1; seed <= RANDOM_SEEDS; seed++) {
    const rnd = testRng(seed * 7);
    const wild = rnd() < 0.5;
    const cfg = config(randTeam(rnd, 2 + (seed % 2), 'L'), randTeam(rnd, 2, 'R'), { seed, wild, snares: wild ? 2 : 0 });
    const b = createBattle(cfg);
    for (let turn = 0; turn < 80; turn++) {
      const choices = [];
      for (const side of [0, 1]) {
        const before = digest(b);
        const a = chooseAction(b, side);
        const seen = { seed, side, phase: b.phase, before, after: digest(b), a: copy(a), legal: copy(legalActions(b, side)) };
        out.positions.push(seen);
        if (seen.legal.length === 0) { choices.push(null); continue; }
        seen.again = J(chooseAction(b, side));
        seen.ofCopy = J(chooseAction(clone(b), side));
        seen.ofFresh = J(chooseAction(createBattle(cfg).phase === b.phase && b.turn === 1 ? createBattle(cfg) : clone(b), side));
        // the human side picks at random (own generator), the computer side uses the AI
        const legal = legalActions(b, side);
        choices.push(side === 0 && rnd() < 0.5 ? legal[Math.floor(rnd() * legal.length)] : a);
      }
      if (b.phase === 'over') {
        out.overAnswers.push([copy(chooseAction(b, 0)), copy(chooseAction(b, 1))]);
        break;
      }
      resolveTurn(b, choices);
    }
  }

  // Forced choices.
  {
    const b = createBattle(config(mon({ moves: [idle()] }), mon({ moves: [idle()] })));
    const s = createBattle(config([mon({ hp: 1, moves: [mv({ power: 90 })], stats: { spd: 1 } }), mon({ moves: [idle()] })], mon({ moves: [mv({ power: 90 })], stats: { spd: 99 } }), { seed: 3 }));
    const only = copy(chooseAction(b, 0));
    resolveTurn(s, [MV(0), MV(0)]);
    out.forced = { only, phase: s.phase, notAsked: copy(chooseAction(s, 1)), replace: copy(chooseAction(s, 0)) };
  }

  // Equally good moves.
  {
    const equal = () => mon({ moves: [mv({ id: 'm1', power: 40 }), mv({ id: 'm2', power: 40 }), mv({ id: 'm3', power: 40 })] });
    out.equal = [];
    for (let seed = 1; seed <= EQUAL_SEEDS; seed++) {
      const b = createBattle(config(equal(), equal(), { seed }));
      const a = J(chooseAction(b, 0));
      out.equal.push({ a, again: J(chooseAction(b, 0)), other: J(chooseAction(createBattle(config(equal(), equal(), { seed })), 0)) });
    }
  }

  // Two battles asked in turn.
  {
    const mk = (seed) => createBattle(config(randTeam(testRng(seed), 3, 'L'), randTeam(testRng(seed + 1), 3, 'R'), { seed }));
    const x = mk(5);
    const y = mk(6);
    const solo = [J(chooseAction(x, 0)), J(chooseAction(x, 1))];
    const soloY = [J(chooseAction(y, 0)), J(chooseAction(y, 1))];
    const mixed = [J(chooseAction(mk(5), 0)), J(chooseAction(mk(6), 0)), J(chooseAction(mk(5), 1)), J(chooseAction(mk(6), 1))];
    out.turnAbout = { solo, soloY, mixed };
  }

  // Whole computer-against-computer battles, each played twice.
  out.whole = [];
  for (let seed = 0; seed < AI_SEEDS; seed++) {
    const play = () => {
      const r = testRng(seed + 100);
      const b = createBattle(config(randTeam(r, 3, 'L'), randTeam(r, 3, 'R'), { seed }));
      for (let i = 0; i < 600 && b.phase !== 'over'; i++) {
        resolveTurn(b, [0, 1].map((side) => chooseAction(b, side)));
      }
      return { phase: b.phase, winner: b.winner, log: digest(b.log) };
    };
    out.whole.push([play(), play()]);
  }
  return out;
}
