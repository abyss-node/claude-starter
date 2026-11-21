// Item 13: The overworld. Runs beside the workspace (demos/probe.mjs, scenario()) and returns the games createGame
// made, what each walk returned and the game after it, with the workspace's own draws from the same seed;
// 13-overworld.test.mjs works out what should have happened and compares.
import { engineOf, probeOf, J, thrown, objectIds } from './fixtures.mjs';

export const MAP_A = ['#####', '#S.+#', '#"""#', '#####'];
export const MAP_OPEN = ['#####', '#...#', '#.S.#', '#...#', '#####'];
export const MAP_EDGE = ['S.', '..'];
export const LONG_MAP = ['#########', '#S."""+.#', '#.""""".#', '#########'];
export const GRASS_SEEDS = 400;
export const OPEN_WALK = 'nnesww' + 'w';
export const EDGE_WALK = 'nwees' + 's';

const copy = (v) => structuredClone(v);
const at = (g) => [g.x, g.y];

export async function run({ load }) {
  const { game: G, data, rules, rng } = await engineOf(load);
  const { createGame, walk } = G;
  const makeProbe = probeOf(load);
  const fresh = (seed, map) => createGame(seed, { map });
  const out = { data: { SPECIES: copy(data.SPECIES), MAP: copy(data.MAP), WILD_TABLE: copy(data.WILD_TABLE) } };

  // createGame
  {
    const options = { map: MAP_A.slice() };
    const g = createGame(5, options);
    const made = copy(g);
    const id = objectIds();
    const mapIds = [id(g.map), id(options.map)];
    options.map[1] = 'XXXXX';
    const d = createGame();
    out.create = {
      game: made, rng5: copy(rng.createRng(5)), mapIds, mapAfterEdit: copy(g.map),
      starter: copy(rules.makeCreature(data.SPECIES[0], 5)),
      otherStarter: createGame(1, { map: MAP_A, starter: data.SPECIES[2].id }).party[0].species,
      noStart: thrown(() => createGame(1, { map: ['###', '#.#', '###'] })),
      plain: copy(d), plainMapIds: [id(d.map), id(data.MAP)],
    };
  }

  // Directions, walls, the edge of the map.
  for (const [name, map, path] of [['open', MAP_OPEN, OPEN_WALK], ['edge', MAP_EDGE, EDGE_WALK]]) {
    const g = fresh(3, map);
    const state = J(g.rng);
    const steps = [...path].map((dir) => ({ result: copy(walk(g, dir)), at: at(g), steps: g.steps }));
    out[name] = { state, steps, rng: J(g.rng) };
  }

  // The healing spring.
  {
    const g = fresh(4, MAP_A);
    g.party.push(rules.makeCreature(data.SPECIES[1], 8));
    g.party[0].hp = 3;
    g.party[0].status = { kind: 'daze', turns: 2 };
    g.party[1].hp = 0;
    g.party[1].status = { kind: 'scorch', turns: 1 };
    const state = J(g.rng);
    walk(g, 'e');
    const beforeSpring = g.party[0].hp;
    const result = copy(walk(g, 'e'));
    out.spring = { state, beforeSpring, result, at: at(g), party: copy(g.party), rng: J(g.rng), battle: copy(g.battle) };
  }

  // Tall grass.
  out.grass = [];
  for (let seed = 0; seed < GRASS_SEEDS; seed++) {
    const g = fresh(seed, MAP_A);
    g.snares = 1 + (seed % 4);
    const p = await makeProbe(seed);
    const draws = [];
    const states = [];
    for (let i = 0; i < 4; i++) { draws.push(p.draw()); states.push(p.state()); }
    const result = copy(walk(g, 's'));
    const seen = { draws, states, result, at: at(g), steps: g.steps, snares: g.snares, rng: J(g.rng), battle: copy(g.battle) };
    if (g.battle) {
      const b = g.battle;
      const wild = b.sides && b.sides[1] && b.sides[1].team && b.sides[1].team[0];
      const sp = wild && data.SPECIES.find((s) => s.id === wild.species);
      seen.made = sp ? copy(rules.makeCreature(sp, wild.level)) : null;
      seen.partyJson = J(g.party);
      seen.teamJson = J(b.sides[0].team);
      const id = objectIds();
      seen.teamIds = [id(b.sides[0].team[0]), id(g.party[0])];
      seen.walkInBattle = thrown(() => walk(g, 'e'));
      seen.rngAfter = J(g.rng);
      seen.atAfter = at(g);
    }
    out.grass.push(seen);
  }

  // A long walk, twice from one seed and once from the next.
  const play = (seed) => {
    const g = fresh(seed, LONG_MAP);
    const path = 'eeeessnnwwwsseeeennwwwwssee';
    const trail = [];
    for (let round = 0; round < 6; round++) {
      for (const d of path) {
        const r = walk(g, d);
        if (r.encounter) { trail.push([g.steps, g.battle.sides[1].team[0].species, g.battle.sides[1].team[0].level, g.battle.seed]); g.battle = null; }
      }
    }
    return J([g, trail]);
  };
  out.long = [play(31), play(31), play(32)];
  return out;
}
