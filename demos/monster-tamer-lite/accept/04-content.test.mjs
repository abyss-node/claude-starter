import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertPlain, kindsOf } from './helpers.mjs';
import { LEVELS } from './scenario-04.mjs';

test('Graded 4: The content', () => {
  const o = observe('./scenario-04.mjs');
  const { TYPES, STATUS_TURNS, MOVES, SPECIES, WILD_TABLE, MAP } = o;
  const id = /^[a-z][a-z0-9-]*$/;
  const whole = (n, lo, hi) => Number.isInteger(n) && n >= lo && n <= hi;

  assert.ok(Array.isArray(TYPES) && TYPES.length === 5, 'TYPES');
  assert.ok(STATUS_TURNS && typeof STATUS_TURNS === 'object', 'STATUS_TURNS');
  for (const what of ['MOVES', 'SPECIES', 'WILD_TABLE']) assertPlain(kindsOf(o[what], o.uncopied[what], what), what);
  const moveIds = Object.keys(MOVES);
  assert.ok(moveIds.length >= 8, 'a roster of 6 or more wants a real move list');
  const kindsInflicted = new Set();
  const names = new Set();
  const perType = Object.fromEntries(TYPES.map((t) => [t, 0]));
  for (const key of moveIds) {
    const m = MOVES[key];
    assert.match(key, id, `move id ${key}`);
    assert.equal(m.id, key, `MOVES.${key}.id`);
    assert.ok(typeof m.name === 'string' && m.name.length > 0, `MOVES.${key}.name`);
    assert.ok(!names.has(m.name.toLowerCase()), `two moves are called ${m.name}`);
    names.add(m.name.toLowerCase());
    assert.ok(TYPES.includes(m.type), `MOVES.${key}.type ${m.type}`);
    perType[m.type]++;
    assert.ok(whole(m.power, 0, 150), `MOVES.${key}.power ${m.power}`);
    assert.ok(whole(m.accuracy, 1, 100), `MOVES.${key}.accuracy ${m.accuracy}`);
    if (m.status !== null) {
      assert.ok(m.status && Object.keys(STATUS_TURNS).includes(m.status.kind), `MOVES.${key}.status.kind`);
      assert.ok(whole(m.status.chance, 1, 100), `MOVES.${key}.status.chance`);
      kindsInflicted.add(m.status.kind);
    }
  }
  for (const t of TYPES) assert.ok(perType[t] >= 2, `type ${t} has ${perType[t]} moves; each type needs at least two`);
  for (const kind of Object.keys(STATUS_TURNS)) assert.ok(kindsInflicted.has(kind), `no move inflicts ${kind}`);

  assert.ok(Array.isArray(SPECIES) && SPECIES.length >= 6 && SPECIES.length <= 8, `SPECIES has ${SPECIES && SPECIES.length} entries; the brief asks for 6 to 8`);
  counted(o.creatures, SPECIES.length, 'creatures made per species');
  const speciesIds = new Set();
  const speciesNames = new Set();
  const speciesTypes = new Set();
  SPECIES.forEach((s, si) => {
    assert.match(s.id, id, `species id ${s.id}`);
    assert.ok(!speciesIds.has(s.id), `species id ${s.id} twice`);
    speciesIds.add(s.id);
    assert.ok(typeof s.name === 'string' && s.name.trim().length > 0, `species ${s.id} name`);
    assert.ok(!speciesNames.has(s.name.toLowerCase()), `two species are called ${s.name}`);
    speciesNames.add(s.name.toLowerCase());
    assert.ok(TYPES.includes(s.type), `species ${s.id} type ${s.type}`);
    speciesTypes.add(s.type);
    for (const k of ['hp', 'atk', 'def', 'spd']) assert.ok(whole(s.base[k], 10, 150), `species ${s.id} base.${k} = ${s.base[k]}`);
    assert.ok(whole(s.baseXp, 20, 200), `species ${s.id} baseXp ${s.baseXp}`);
    assert.ok(whole(s.catchRate, 1, 100), `species ${s.id} catchRate ${s.catchRate}`);
    assert.ok(Array.isArray(s.moves) && s.moves.length >= 2 && s.moves.length <= 4, `species ${s.id} must have 2 to 4 moves`);
    for (const mid of s.moves) assert.ok(MOVES[mid], `species ${s.id} lists unknown move ${mid}`);
    counted(o.creatures[si], LEVELS.length, `creatures of ${s.id}`).forEach(({ creature: c, uncopied }, li) => {
      assert.equal(c.level, LEVELS[li]);
      assert.equal(c.species, s.id);
      assert.equal(c.hp, c.maxHp);
      assertPlain(kindsOf(c, uncopied, `creature ${s.id}`), `creature ${s.id}`);
    });
  });
  for (const t of TYPES) assert.ok(speciesTypes.has(t), `no species has the type ${t}`);

  assert.ok(Array.isArray(WILD_TABLE) && WILD_TABLE.length >= 1);
  for (const e of WILD_TABLE) {
    assert.ok(speciesIds.has(e.species), `WILD_TABLE names unknown species ${e.species}`);
    assert.ok(whole(e.weight, 1, 1e6), `weight ${e.weight}`);
    assert.ok(whole(e.minLevel, 1, 30) && whole(e.maxLevel, 1, 30) && e.minLevel <= e.maxLevel, `levels ${e.minLevel}-${e.maxLevel}`);
  }

  assert.ok(Array.isArray(MAP) && MAP.length >= 3 && MAP.every((r) => typeof r === 'string' && r.length === MAP[0].length), 'MAP rows must be equal-length strings');
  const w = MAP[0].length;
  const h = MAP.length;
  let start = null;
  const count = { S: 0, '"': 0, '+': 0 };
  MAP.forEach((row, y) => [...row].forEach((ch, x) => {
    assert.ok('#."+S'.includes(ch), `MAP has the character ${JSON.stringify(ch)} at ${x},${y}`);
    if (ch in count) count[ch]++;
    if (ch === 'S') start = { x, y };
    if (x === 0 || y === 0 || x === w - 1 || y === h - 1) assert.equal(ch, '#', `MAP is not walled at ${x},${y}`);
  }));
  assert.equal(count.S, 1, 'MAP needs exactly one S');
  assert.ok(count['"'] >= 1, 'MAP needs tall grass');
  assert.ok(count['+'] >= 1, 'MAP needs a healing spring');
  const seen = new Set([`${start.x},${start.y}`]);
  const queue = [start];
  while (queue.length) {
    const { x, y } = queue.shift();
    for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0]]) {
      const nx = x + dx;
      const ny = y + dy;
      if (MAP[ny] && MAP[ny][nx] && MAP[ny][nx] !== '#' && !seen.has(`${nx},${ny}`)) { seen.add(`${nx},${ny}`); queue.push({ x: nx, y: ny }); }
    }
  }
  const reach = (ch) => [...seen].some((k) => { const [x, y] = k.split(',').map(Number); return MAP[y][x] === ch; });
  assert.ok(reach('"'), 'no tall grass can be reached from S');
  assert.ok(reach('+'), 'no healing spring can be reached from S');
});
