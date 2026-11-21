import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertThrew, assertDistinct } from './helpers.mjs';
import { MAP_A, OPEN_WALK, EDGE_WALK, GRASS_SEEDS } from './scenario-13.mjs';

const still = { moved: false, encounter: false };
const moved = { moved: true, encounter: false };

test('Graded 13: The overworld', () => {
  const o = observe('./scenario-13.mjs');
  const { SPECIES, MAP, WILD_TABLE } = o.data;

  // createGame
  {
    const { game: g, rng5, mapIds, mapAfterEdit, starter, otherStarter, noStart, plain: d, plainMapIds } = o.create;
    assert.equal(g.version, 1);
    assert.equal(g.seed, 5);
    assert.deepEqual(g.rng, rng5);
    assert.deepEqual(g.map, MAP_A);
    assertDistinct(mapIds, 'the map is a copy');
    assert.deepEqual(mapAfterEdit, MAP_A, 'editing the options afterwards must not change the game');
    assert.deepEqual(g.start, { x: 1, y: 1 });
    assert.deepEqual([g.x, g.y], [1, 1]);
    assert.equal(g.steps, 0);
    assert.equal(g.snares, 5);
    assert.deepEqual(g.box, []);
    assert.equal(g.battle, null);
    assert.equal(g.party.length, 1);
    assert.equal(g.party[0].species, SPECIES[0].id);
    assert.equal(g.party[0].level, 5);
    assert.deepEqual(g.party[0], starter);
    assert.equal(otherStarter, SPECIES[2].id);
    assertThrew(noStart, 'a map without S');
    assert.equal(d.seed, 1);
    assert.deepEqual(d.map, MAP);
    const sy = MAP.findIndex((r) => r.includes('S'));
    assert.deepEqual([d.x, d.y], [MAP[sy].indexOf('S'), sy]);
    assert.deepEqual(d.start, { x: d.x, y: d.y });
    assertDistinct(plainMapIds, 'the default map is a copy of MAP');
  }

  // Directions, walls, the edge of the map, and no draws off the grass.
  {
    const { state, steps: s, rng } = o.open;
    counted(s, OPEN_WALK.length, 'steps on the open map');
    assert.deepEqual(s[0].result, moved);
    assert.deepEqual(s[0].at, [2, 1]);
    assert.deepEqual(s[1].result, still);
    assert.deepEqual(s[1].at, [2, 1]);
    assert.deepEqual(s[2].at, [3, 1]);
    assert.deepEqual(s[3].at, [3, 2]);
    assert.deepEqual(s[4].at, [2, 2], 'S is walkable');
    assert.deepEqual(s[5].at, [1, 2]);
    assert.equal(s[5].steps, 5);
    assert.deepEqual(s[6].result, still);
    assert.equal(s[6].steps, 5, 'a blocked step is not counted');
    assert.equal(rng, state, 'steps on path and S, and blocked steps, take no draw');
  }
  {
    const { state, steps: s, rng } = o.edge;
    counted(s, EDGE_WALK.length, 'steps on the edge map');
    assert.deepEqual(s[0].result, still);
    assert.deepEqual(s[1].result, still);
    assert.deepEqual(s[1].at, [0, 0]);
    assert.deepEqual(s[2].result, moved);
    assert.deepEqual(s[3].result, still);
    assert.deepEqual(s[4].result, moved);
    assert.deepEqual(s[5].result, still);
    assert.deepEqual(s[5].at, [1, 1]);
    assert.equal(s[5].steps, 2);
    assert.equal(rng, state);
  }

  // The healing spring: no draw, whole party restored, fainted creatures too.
  {
    const sp = o.spring;
    assert.equal(sp.beforeSpring, 3, 'not healed before the spring');
    assert.deepEqual(sp.result, moved);
    assert.deepEqual(sp.at, [3, 1]);
    counted(sp.party, 2, 'the party at the spring');
    for (const c of sp.party) { assert.equal(c.hp, c.maxHp); assert.equal(c.status, null); }
    assert.equal(sp.rng, sp.state, 'the spring takes no draw');
    assert.equal(sp.battle, null);
  }

  // Tall grass: one draw; an encounter exactly when it is below 0.25; then species, level and battle seed.
  const total = WILD_TABLE.reduce((n, e) => n + e.weight, 0);
  let encounters = 0;
  counted(o.grass, GRASS_SEEDS, 'grass steps').forEach((s, seed) => {
    const [r, r2, r3, r4] = s.draws;
    const want = r < 0.25;
    assert.deepEqual(s.at, [1, 2]);
    assert.equal(s.steps, 1);
    assert.deepEqual(s.result, { moved: true, encounter: want }, `seed ${seed}, draw ${r}`);
    if (!want) {
      assert.equal(s.battle, null);
      assert.equal(s.rng, s.states[0], 'one draw when no encounter happens');
      return;
    }
    encounters++;
    let acc = 0;
    let entry = WILD_TABLE[WILD_TABLE.length - 1];
    for (const e of WILD_TABLE) { acc += e.weight; if (r2 * total < acc) { entry = e; break; } }
    const level = entry.minLevel + Math.floor(r3 * (entry.maxLevel - entry.minLevel + 1));
    const b = s.battle;
    assert.ok(b, 'an encounter starts a battle');
    assert.equal(b.wild, true);
    assert.equal(b.snares, s.snares, 'the battle starts with the snares the game has');
    assert.equal(b.seed, Math.floor(r4 * 4294967296), `seed ${seed}: battle seed from the fourth draw`);
    assert.equal(b.phase, 'choose');
    assert.equal(b.sides.length, 2);
    assert.equal(b.sides[1].team.length, 1);
    const wildOne = b.sides[1].team[0];
    assert.equal(wildOne.species, entry.species, `seed ${seed}: species from the second draw ${r2}`);
    assert.equal(wildOne.level, level, `seed ${seed}: level from the third draw ${r3}`);
    assert.ok(level >= entry.minLevel && level <= entry.maxLevel);
    assert.deepEqual(wildOne, s.made);
    assert.equal(s.teamJson, s.partyJson);
    assertDistinct(s.teamIds, 'the battle holds its own copies');
    assert.equal(s.rng, s.states[3], `seed ${seed}: four draws for an encounter`);
    assertThrew(s.walkInBattle, 'no walking in a battle');
    assert.equal(s.rngAfter, s.states[3]);
    assert.deepEqual(s.atAfter, [1, 2]);
  });
  assert.ok(encounters > 70 && encounters < 135, `${encounters} encounters in ${GRASS_SEEDS} grass steps`);

  // The same seed and the same walk give the same encounters, on every kind of tile.
  const [a, again, other] = counted(o.long, 3, 'long walks');
  assert.equal(typeof a, 'string');
  assert.equal(again, a);
  assert.notEqual(other, a);
  assert.ok(JSON.parse(a)[1].length > 3, 'the long walk should meet several creatures');
});
