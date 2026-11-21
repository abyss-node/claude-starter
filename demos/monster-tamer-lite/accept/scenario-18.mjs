// Item 18: Save and load. Runs beside the workspace (demos/probe.mjs, scenario()) and returns, for games in several
// states, the game, the text saveGame made, what loadGame made of it and how both play on; and what loadGame did
// with each bad save below. 18-save-load.test.mjs holds them to the brief.
import { engineOf, J, clone, thrown, objectIds, uncopied } from './fixtures.mjs';

export const MAP = ['#########', '#S"""""+#', '#.""""".#', '#########'];
const PATH = 'eeeessnnwwwsseeeennwwww';
export const CASES = ['a new game', 'after walking', 'mid battle', 'after a catch', 'a full party and a box'];

// Bad saves, each made from a good game (the one after a catch, out of its battle).
const BAD_TEXT = { 'not json': 'not json {', 'empty text': '', 'an array': '[]', 'null': 'null', 'a string': '"save"', 'a number': '42' };
const BAD_EDIT = {
  'version 2': (g) => { g.version = 2; },
  'version 0': (g) => { g.version = 0; },
  'version "1"': (g) => { g.version = '1'; },
  'no version': (g) => { delete g.version; },
  'no rng': (g) => { delete g.rng; },
  'rng null': (g) => { g.rng = null; },
  'rng a number': (g) => { g.rng = 7; },
  'no map': (g) => { delete g.map; },
  'map a string': (g) => { g.map = '#####'; },
  'x a string': (g) => { g.x = '3'; },
  'x fractional': (g) => { g.x = 1.5; },
  'x missing': (g) => { delete g.x; },
  'y null': (g) => { g.y = null; },
  'y fractional': (g) => { g.y = 0.5; },
  'no party': (g) => { delete g.party; },
  'empty party': (g) => { g.party = []; },
  'party not an array': (g) => { g.party = {}; },
  'level 0': (g) => { g.party[0].level = 0; },
  'level 31': (g) => { g.party[0].level = 31; },
  'level fractional': (g) => { g.party[0].level = 5.5; },
  'level a string': (g) => { g.party[0].level = '5'; },
  'hp negative': (g) => { g.party[0].hp = -1; },
  'hp above maxHp': (g) => { g.party[0].hp = g.party[0].maxHp + 1; },
  'hp fractional': (g) => { g.party[0].hp = 3.5; },
  'hp a string': (g) => { g.party[0].hp = '3'; },
  'second creature bad hp': (g) => { g.party[g.party.length - 1].hp = g.party[g.party.length - 1].maxHp + 5; },
  'box creature bad level': (g) => { g.box = [clone(g.party[0])]; g.box[0].level = 99; },
  'box creature bad hp': (g) => { g.box = [clone(g.party[0])]; g.box[0].hp = -4; },
};
export const BAD = [...Object.keys(BAD_TEXT), ...Object.keys(BAD_EDIT)];

const copy = (v) => structuredClone(v);

export async function run({ load }) {
  const { game: G, battle: B, data, rules, ai } = await engineOf(load);
  const { createGame, walk, endBattle, saveGame, loadGame } = G;
  const { resolveTurn, legalActions } = B;

  // Finish the battle in progress: snare when a snare is left (when asked), else the first move.
  const fight = (g, preferSnare) => {
    const b = g.battle;
    for (let i = 0; i < 200 && b.phase !== 'over'; i++) {
      const mine = legalActions(b, 0);
      const snare = mine.find((a) => a.kind === 'snare');
      const choices = [0, 1].map((side) => {
        if (legalActions(b, side).length === 0) return null;
        if (side === 0) return preferSnare && snare ? snare : mine[0];
        return ai.chooseAction(b, side);
      });
      resolveTurn(b, choices);
    }
    return endBattle(g);
  };
  // Walk the path over and over; fight whatever turns up.
  const wander = (g, rounds, preferSnare = false) => {
    const results = [];
    for (let r = 0; r < rounds; r++) {
      for (const d of PATH) {
        if (g.battle) results.push(fight(g, preferSnare).result);
        walk(g, d);
      }
    }
    return results;
  };

  const newGame = () => createGame(11, { map: MAP });
  const walked = () => { const g = newGame(); wander(g, 1); return g; };
  const midBattle = () => {
    for (let seed = 5; seed < 60; seed++) {
      const g = createGame(seed, { map: MAP });
      for (let i = 0; i < 400 && !g.battle; i++) for (const d of PATH) { if (g.battle) break; walk(g, d); }
      if (!g.battle) continue;
      const bt = g.battle;
      resolveTurn(bt, [legalActions(bt, 0)[0], ai.chooseAction(bt, 1)]);
      if (bt.phase !== 'over') return g;
    }
    throw new Error('no battle lasted past one turn');
  };
  const caught = () => {
    for (let seed = 1; seed < 30; seed++) {
      const g = createGame(seed, { map: MAP });
      g.snares = 40;
      g.party[0].level = 12;
      const r = wander(g, 4, true);
      if (r.includes('caught')) return g;
    }
    throw new Error('never caught anything; the encounter or catch rules are off');
  };
  const crowded = () => {
    const g = newGame();
    for (let i = 0; i < 5; i++) g.party.push(rules.makeCreature(data.SPECIES[i % data.SPECIES.length], 3 + i));
    for (let i = 0; i < 3; i++) g.box.push(rules.makeCreature(data.SPECIES[(i + 2) % data.SPECIES.length], 9 + i));
    g.party[2].hp = 4;
    g.party[3].status = { kind: 'chill', turns: 2 };
    g.snares = 1;
    return g;
  };
  const games = [newGame(), walked(), midBattle(), caught(), crowded()];
  const out = {};

  out.roundTrips = games.map((g) => {
    const text = saveGame(g);
    const back = loadGame(text);
    const id = objectIds();
    const seen = {
      textType: typeof text, text, game: copy(g), back: copy(back), resaved: saveGame(back),
      uncopied: [uncopied(g, 'game'), uncopied(back, 'game')],
      ids: [[id(back), id(g)], [id(back.party), id(g.party)], [id(back.party[0]), id(g.party[0])]],
    };
    back.party[0].hp = -999;
    seen.originalHpAfterEdit = g.party[0].hp;
    return seen;
  });

  // The loaded game carries on exactly like the original.
  out.playOn = games.map((g) => {
    const a = loadGame(saveGame(g));
    const b = loadGame(saveGame(g));
    if (a.battle) { fight(a, false); fight(b, false); }
    wander(a, 3);
    wander(b, 3);
    const c = clone(g);
    if (c.battle) fight(c, false);
    wander(c, 3);
    return { a: J(a), b: J(b), c: J(c), savedA: saveGame(a), savedC: saveGame(c) };
  });

  // Bad saves.
  const good = clone(games[3]);
  good.battle = null;
  const texts = { ...BAD_TEXT };
  for (const [label, edit] of Object.entries(BAD_EDIT)) { const g = clone(good); edit(g); texts[label] = JSON.stringify(g); }
  out.bad = BAD.map((label) => thrown(() => loadGame(texts[label])));

  // Edges that are valid.
  const edge = clone(good);
  edge.party[0].level = 30;
  edge.party[0].hp = edge.party[0].maxHp;
  edge.party.push({ ...clone(edge.party[0]), level: 1, hp: 0 });
  const edge2 = clone(good);
  edge2.party[0].level = 1;
  edge2.party[0].hp = 0;
  out.edges = [edge, edge2].map((e) => ({ game: copy(e), back: copy(loadGame(saveGame(e))) }));
  return out;
}
