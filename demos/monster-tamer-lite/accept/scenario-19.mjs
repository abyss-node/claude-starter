// Item 19: Plain data and determinism. Runs beside the workspace (demos/probe.mjs, scenario()) and returns a copy of
// a battle, a duel and a game at every stage, with what each copy cannot carry (fixtures.mjs uncopied); battles, duels and games as text (or a digest) where
// two runs should agree; what ran with the clocks and Math.random taken away; and labels of the objects a battle or
// game holds next to those it was given. 19-plain-determinism.test.mjs holds them to the brief.
import { engineOf, J, clone, config, testRng, fnv1a, deepFreeze, randTeam, observed, thrown, objectIds } from './fixtures.mjs';

export const MAP = ['#########', '#S"""""+#', '#.""""".#', '#########'];
const WALK = 'eeeessnnwwwsseeeennwwww';
const digest = (v) => fnv1a(J(v));

const mkCfg = (seed, wild = false) => {
  const rnd = testRng(seed * 13 + 1);
  return config(randTeam(rnd, 3, 'L'), randTeam(rnd, 3, 'R'), { seed, wild, snares: wild ? 3 : 0 });
};

export async function run({ load, withoutClocks }) {
  const m = await engineOf(load);
  const { battle: B, ai, duel: D, game: G, replay, data, rules } = m;
  const aiTurn = (b, mod = { B, ai }) => {
    mod.B.resolveTurn(b, [0, 1].map((s) => mod.ai.chooseAction(b, s)));
  };
  const finish = (b, mod) => { for (let i = 0; i < 500 && b.phase !== 'over'; i++) aiTurn(b, mod); return b; };
  const out = {};

  // A copy of a battle, a duel and a game at every stage.
  {
    const stages = [];
    const see = (v, label) => stages.push([label, observed(v, label)]);
    const b = B.createBattle(mkCfg(3, true));
    see(b, 'battle at the start');
    for (let i = 0; i < 6 && b.phase !== 'over'; i++) { aiTurn(b); see(b, `battle after turn ${i + 1}`); }
    finish(b);
    see(b, 'finished battle');
    const d = D.createDuel(mkCfg(4));
    see(d, 'duel at the start');
    see(D.duelView(d), 'duel view');
    for (let i = 0; i < 40 && d.stage !== 'over'; i++) {
      if (d.stage === 'pick') D.duelPick(d, d.who, ai.chooseAction(d.battle, d.who));
      else D.duelContinue(d);
      see(d, `duel stage ${d.stage}`);
      see(D.duelView(d), `duel view ${d.stage}`);
    }
    const g = G.createGame(5, { map: MAP });
    see(g, 'new game');
    for (let r = 0; r < 4; r++) for (const dir of WALK) {
      if (g.battle) { finish(g.battle); G.endBattle(g); see(g, 'game after a battle'); }
      G.walk(g, dir);
      if (g.battle) see(g, 'game in a battle');
    }
    see(g, 'game after walking');
    out.stages = stages;
  }

  // A JSON copy taken midway carries on exactly like the original.
  {
    const b = B.createBattle(mkCfg(8, true));
    for (let i = 0; i < 3; i++) aiTurn(b);
    const c = clone(b);
    finish(b);
    finish(c);
    const d = D.createDuel(mkCfg(9));
    D.duelContinue(d); D.duelPick(d, 0, B.legalActions(d.battle, 0)[1]);
    const e = clone(d);
    for (const x of [d, e]) {
      D.duelContinue(x);
      D.duelPick(x, 1, B.legalActions(x.battle, 1)[2]);
      D.duelContinue(x);
    }
    const g = G.createGame(6, { map: MAP });
    for (const dir of 'eeeeess') { if (g.battle) break; G.walk(g, dir); }
    const h = clone(g);
    for (const x of [g, h]) for (const dir of 'nneewwss') { if (x.battle) { finish(x.battle); G.endBattle(x); } G.walk(x, dir); }
    out.copies = {
      battle: [J(b), J(c)], duel: [J(d), J(e)], view: [J(D.duelView(d)), J(D.duelView(e))], game: [J(g), J(h)],
    };
  }

  // Two battles stepped turn about, alone, and with a fresh copy of the modules.
  {
    const alone = (seed, mod) => finish(mod.B.createBattle(mkCfg(seed)), mod);
    const base = { B, ai };
    const fresh = { B: await load('src/battle.js?fresh=1'), ai: await load('src/ai.js?fresh=1') };
    const turnAbout = [base, fresh].map((mod) => {
      const x = mod.B.createBattle(mkCfg(21));
      const y = mod.B.createBattle(mkCfg(22));
      for (let i = 0; i < 500 && (x.phase !== 'over' || y.phase !== 'over'); i++) {
        if (x.phase !== 'over') aiTurn(x, mod);
        if (y.phase !== 'over') aiTurn(y, mod);
      }
      return [digest(x), digest(y)];
    });
    const g1 = await load('src/game.js?fresh=1');
    const play = (mod) => { const g = mod.createGame(3, { map: MAP }); for (const d of WALK) { if (g.battle) g.battle = null; mod.walk(g, d); } return J(g); };
    out.alone = { x: digest(alone(21, base)), y: digest(alone(22, base)), turnAbout, games: [play(G), play(g1), play(G)] };
  }

  // Clocks and Math.random taken away (the probe's withoutClocks).
  {
    const seen = {};
    seen.call = thrown(() => withoutClocks(() => {
      const b = B.createBattle(mkCfg(31, true));
      finish(b);
      const cfg = mkCfg(32);
      const live = B.createBattle(cfg);
      finish(live);
      seen.replayed = [digest(replay.replayBattle(cfg, live.history)), digest(live)];
      replay.hashLog(live.log);
      const d = D.createDuel(mkCfg(33));
      for (let i = 0; i < 400 && d.stage !== 'over'; i++) {
        if (d.stage === 'pick') D.duelPick(d, d.who, ai.chooseAction(d.battle, d.who));
        else D.duelContinue(d);
        D.duelView(d);
      }
      const g = G.createGame(7, { map: MAP });
      for (let r = 0; r < 5; r++) for (const dir of WALK) {
        if (g.battle) { finish(g.battle); G.endBattle(g); }
        G.walk(g, dir);
      }
      G.loadGame(G.saveGame(g));
      rules.gainXp(rules.makeCreature(data.SPECIES[0], 3), 500);
      rules.catchChance(rules.makeCreature(data.SPECIES[0], 3));
      const r = m.rng.createRng(5);
      m.rng.nextFloat(r);
      seen.finished = 'all of it ran';
    }));
    out.clockless = seen;
  }

  // Inputs are left alone and nothing is shared with them.
  {
    const id = objectIds();
    const cfg = deepFreeze(clone(mkCfg(40, true)));
    const b = B.createBattle(cfg);
    const d = D.createDuel(cfg);
    const held = [b, d.battle].map((battle) => ({
      creatures: battle.sides.map((side, i) => side.team.map((c, j) => {
        const src = cfg.sides[i].team[j];
        return [[id(c), id(src)], [id(c.moves), id(src.moves)], [id(c.moves[0]), id(src.moves[0])], [id(c.stats), id(src.stats)], [id(c.base), id(src.base)]];
      })),
      team: [id(battle.sides[0].team), id(cfg.sides[0].team)],
    }));
    b.sides[0].team[0].hp = 1;
    b.sides[0].team[0].moves[0].power = 999;
    const cfgAfter = { hp: cfg.sides[0].team[0].hp, power: cfg.sides[0].team[0].moves[0].power };
    const again = thrown(() => finish(B.createBattle(cfg)));

    const options = deepFreeze({ map: MAP.slice(), starter: data.SPECIES[1].id });
    const g = G.createGame(2, options);
    const mapIds = [id(g.map), id(options.map)];
    const map = clone(g.map);
    g.map[1] = 'zzz';
    const optionsRow = options.map[1];
    const moveId = data.SPECIES[1].moves[0];
    const moveIds = [id(g.party[0].moves[0]), id(data.MOVES[moveId])];
    const powerBefore = data.MOVES[moveId].power;
    g.party[0].moves[0].power = 999;
    const frozenSpecies = deepFreeze(clone(data.SPECIES[0]));
    out.inputs = {
      held, cfgSizes: cfg.sides.map((s) => s.team.length), cfgAfter, again,
      mapIds, map, optionsRow, moveIds, powerBefore, powerAfter: data.MOVES[moveId].power,
      frozenSpecies: thrown(() => rules.makeCreature(frozenSpecies, 6)),
    };
  }
  return out;
}
