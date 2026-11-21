// Item 14: After the battle. Runs beside the workspace (demos/probe.mjs, scenario()) and plays the battles below to
// their end, returning what endBattle returned, what it threw, and the game it left; 14-after-battle.test.mjs holds
// them to the brief.
import { engineOf, probeOf, J, clone, mv, mon, idle, MV, SNARE, ofType, thrown } from './fixtures.mjs';

export const MAP_A = ['#####', '#S.+#', '#"""#', '#####'];
export const PARTY_SIZES = [1, 5, 6];
export const CATCH_SEEDS = 50;

const killer = () => mv({ id: 'killer', power: 120, accuracy: 100 });
const wildFoe = (o = {}) => mon({ name: 'Wildling', level: 8, baseXp: 100, maxHp: 60, hp: 1, stats: { spd: 5 }, moves: [mv({ power: 20 })], ...o });
const copy = (v) => structuredClone(v);

export async function run({ load }) {
  const { game: G, battle: B, data, rules } = await engineOf(load);
  const { createGame, endBattle } = G;
  const { createBattle, resolveTurn } = B;
  const makeProbe = probeOf(load);
  const fx = { id: 'fx', name: 'Fx', type: 'moss', base: { hp: 50, atk: 40, def: 30, spd: 20 }, baseXp: 60, catchRate: 33, moves: Object.keys(data.MOVES).slice(0, 2) };
  const mine = (name, level = 5, o = {}) => {
    const c = rules.makeCreature({ ...fx, name }, level);
    c.moves = [killer()];
    c.stats.spd = 99;
    return Object.assign(c, o);
  };
  const newGame = (party, seed = 2) => {
    const g = createGame(seed, { map: MAP_A });
    g.party = party;
    return g;
  };
  const start = (g, foe, extra = {}) => {
    g.battle = createBattle({ seed: 3, wild: true, snares: g.snares, sides: [{ name: 'You', team: g.party }, { name: 'Wild', team: [foe] }], ...extra });
    return g.battle;
  };
  const out = {};

  // No battle, or an unfinished one.
  {
    const g = newGame([mine('A')]);
    const before = J(g);
    const none = thrown(() => endBattle(g));
    const afterNone = J(g);
    start(g, wildFoe());
    const mid = J(g);
    const unfinished = thrown(() => endBattle(g));
    out.notOver = { before, none, afterNone, mid, unfinished, afterUnfinished: J(g) };
  }

  // A win.
  {
    const g = newGame([mine('A'), mine('Down', 5, { hp: 0 }), mine('Bench', 5, { status: { kind: 'daze', turns: 2 } })]);
    g.snares = 4;
    const b = start(g, wildFoe());
    resolveTurn(b, [MV(0), MV(0)]);
    const over = { phase: b.phase, winner: b.winner };
    b.snares = 2;
    b.sides[0].team[0].status = { kind: 'scorch', turns: 1 };
    const expected = clone(b.sides[0].team).map((c) => {
      c.status = null;
      if (c.hp > 0) rules.gainXp(c, 160);
      return c;
    });
    const result = copy(endBattle(g));
    out.win = { over, expected, result, game: copy(g), again: thrown(() => endBattle(g)) };
  }

  // A catch.
  {
    const chance = rules.catchChance(wildFoe({ catchRate: 100, hp: 5, status: { kind: 'chill', turns: 2 } }));
    const draws = [];
    for (let s = 0; s < CATCH_SEEDS; s++) draws.push((await makeProbe(s)).draw());
    let seed = 0;
    while (seed < CATCH_SEEDS && !(draws[seed] * 100 < chance)) seed++;
    out.catchSeed = { chance, draws, seed };
    out.catches = PARTY_SIZES.map((partySize) => {
      const g = newGame(Array.from({ length: partySize }, (_, i) => mine(`P${i}`)));
      g.snares = 4;
      const foe = wildFoe({ name: 'Catchee', catchRate: 100, hp: 5, status: { kind: 'chill', turns: 2 }, stats: { spd: 5 } });
      const b = createBattle({ seed, wild: true, snares: g.snares, sides: [{ name: 'You', team: g.party }, { name: 'Wild', team: [foe] }] });
      g.battle = b;
      resolveTurn(b, [SNARE, MV(0)]);
      const caught = b.caught;
      const xps = b.sides[0].team.map((c) => c.xp);
      const result = copy(endBattle(g));
      return { caught, xps, result, game: copy(g) };
    });
  }

  // A loss, and a draw.
  out.lost = [false, true].map((draw) => {
    const a = mine('A', 5, { hp: 1, status: { kind: 'daze', turns: 2 } });
    a.stats.spd = 1;
    const down = mine('Down', 5, { hp: 0, status: { kind: 'scorch', turns: 1 } });
    const g = newGame([a, down]);
    g.x = 3;
    g.y = 1;
    g.steps = 9;
    const foe = draw ? wildFoe({ hp: 1, stats: { spd: 5 }, moves: [idle()], status: { kind: 'scorch', turns: 3 } }) : wildFoe({ hp: 60, stats: { spd: 99 }, moves: [killer()] });
    if (draw) { a.status = { kind: 'scorch', turns: 3 }; a.moves = [idle()]; }
    const b = start(g, foe);
    resolveTurn(b, [MV(0), MV(0)]);
    const over = { phase: b.phase, winner: b.winner, ends: ofType(b.log, 'end').length };
    const xps = b.sides[0].team.map((c) => c.xp);
    const result = copy(endBattle(g));
    return { over, xps, result, game: copy(g) };
  });
  return out;
}
