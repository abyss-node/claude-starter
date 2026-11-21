import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { notPlain } from './helpers.mjs';
import { ask } from './ask.mjs';

// The kit's own list of names the demos must not use (demos/denylist.txt), matched as the launcher matches it: no
// case, no accents, plurals allowed, and spaces, hyphens, underscores, dots and apostrophes between letters ignored.
// It is read from the kit, so no franchise name is written in these files.
const SEPARATORS = String.raw`[\s\-_.'’]*`;
const fold = (text) => text.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
const DENY = readFileSync(new URL('../../denylist.txt', import.meta.url), 'utf8').split('\n')
  .map((line) => line.split('#')[0].trim())
  .filter(Boolean)
  .map((term) => {
    const letters = fold(term).match(/[a-z0-9]+/g) || [];
    return { term, rx: new RegExp(`(?<![a-z0-9])${letters.join(SEPARATORS)}(?:e?s)?(?![a-z0-9])`) };
  });
const LEGAL_TILES = new Set(['.', ',', '#', '~', 'T']);

test('Graded 17: the shipped world is plain data with three towns and a route, original, and every reference resolves', () => {
  const seen = ask('./sc-game.mjs', 'content');
  assert.equal(notPlain(seen.kinds), null);
  assert.ok(seen.content, 'CONTENT could not be copied out of its module');
  const C = seen.content;
  const ids = Object.keys(C.maps);
  assert.ok(ids.length >= 4, `at least three towns and one route (got ${ids.length} maps)`);
  assert.ok(typeof C.title === 'string' && C.title.length > 0);

  const flagsSet = new Set();
  const flagsRead = new Set();
  const itemsUsed = new Set();
  const speciesUsed = new Set();
  for (const [key, m] of Object.entries(C.maps)) {
    assert.equal(m.id, key, `map ${key}: id matches its key`);
    assert.ok(typeof m.name === 'string' && m.name.length > 0, `${key}: has a name`);
    assert.ok(Array.isArray(m.rows), `${key}: rows is a list`);
    assert.equal(m.rows.length, m.height, `${key}: height is the number of rows`);
    for (const row of m.rows) {
      assert.equal(typeof row, 'string');
      assert.equal(row.length, m.width, `${key}: every row is ${m.width} wide`);
      for (const ch of row) assert.ok(LEGAL_TILES.has(ch), `${key}: tile ${JSON.stringify(ch)} is not one of . , # ~ T`);
    }
  }
  const tile = (m, x, y) => C.maps[m].rows[y]?.[x];
  const walkable = (m, x, y) => tile(m, x, y) === '.' || tile(m, x, y) === ',';
  const npcIds = new Set();
  let gates = 0;
  let routes = 0;
  const graph = new Map(ids.map((i) => [i, new Set()]));
  for (const [key, m] of Object.entries(C.maps)) {
    for (const w of m.warps || []) {
      assert.ok(walkable(key, w.x, w.y), `${key}: warp tile (${w.x},${w.y}) must be floor or grass`);
      assert.ok(C.maps[w.to], `${key}: warp to unknown map ${w.to}`);
      assert.ok(walkable(w.to, w.tx, w.ty), `${key}: warp lands on (${w.tx},${w.ty}) of ${w.to}, which is not walkable`);
      assert.ok(!(C.maps[w.to].npcs || []).some((n) => n.x === w.tx && n.y === w.ty), `${key}: warp lands on an npc`);
      if (w.facing !== undefined) assert.ok(['up', 'down', 'left', 'right'].includes(w.facing));
      graph.get(key).add(w.to);
    }
    for (const g of m.gates || []) {
      gates++;
      assert.ok(walkable(key, g.x, g.y), `${key}: gate (${g.x},${g.y}) must sit on a walkable tile`);
      assert.equal(typeof g.flag, 'string');
      flagsRead.add(g.flag);
    }
    for (const n of m.npcs || []) {
      assert.ok(walkable(key, n.x, n.y), `${key}: npc ${n.id} stands on a tile that blocks`);
      assert.ok(C.trees[n.tree], `${key}: npc ${n.id} has no tree ${n.tree}`);
      assert.ok(!npcIds.has(n.id), `npc id ${n.id} is used twice`);
      npcIds.add(n.id);
    }
    if ((m.encounters || []).length > 0) {
      routes++;
      assert.ok(m.encounterRate > 0 && m.encounterRate <= 100, `${key}: encounter rate`);
      assert.ok(m.rows.some((r) => r.includes(',')), `${key}: has encounters but no tall grass`);
      for (const e of m.encounters) {
        assert.ok(C.species[e.species], `${key}: encounter species ${e.species}`);
        assert.ok(Number.isInteger(e.minLevel) && Number.isInteger(e.maxLevel) && e.minLevel >= 1 && e.minLevel <= e.maxLevel && e.maxLevel <= 100);
        assert.ok(e.weight > 0);
        speciesUsed.add(e.species);
      }
    }
  }
  assert.ok(routes >= 1, 'a route with tall grass and wild creatures');
  assert.ok(ids.filter((i) => (C.maps[i].encounters || []).length === 0 && (C.maps[i].npcs || []).length > 0).length >= 3, 'at least three towns (maps with no encounters) with people in them');
  assert.ok(gates >= 1, 'at least one gated door');
  assert.ok(npcIds.size >= 4, 'at least four people to talk to');

  // the start
  const s = C.start;
  assert.ok(C.maps[s.map] && walkable(s.map, s.x, s.y), 'the start tile is walkable');
  assert.ok(['up', 'down', 'left', 'right'].includes(s.facing));
  assert.ok(Array.isArray(s.party) && s.party.length >= 1);
  for (const p of s.party) { assert.ok(C.species[p.species]); speciesUsed.add(p.species); assert.ok(Number.isInteger(p.level) && p.level >= 1); }
  for (const [item, n] of Object.entries(s.inventory || {})) { assert.ok(C.items[item], `start item ${item}`); assert.ok(Number.isInteger(n) && n > 0); }

  // every map can be reached from the start by warps
  const reached = new Set([s.map]);
  const queue = [s.map];
  while (queue.length) for (const next of graph.get(queue.shift())) if (!reached.has(next)) { reached.add(next); queue.push(next); }
  assert.deepEqual([...reached].sort(), [...ids].sort(), 'every map is reachable from the start');

  // dialogue trees
  const treeIds = Object.keys(C.trees);
  assert.ok(treeIds.length >= 4);
  let branching = 0;
  for (const [tid, tree] of Object.entries(C.trees)) {
    const node = (id, where) => assert.ok(typeof id === 'string' && tree.nodes[id], `tree ${tid}: ${where} names the missing node ${id}`);
    if (typeof tree.start === 'string') node(tree.start, 'start');
    else {
      assert.ok(Array.isArray(tree.start) && tree.start.length > 0, `tree ${tid}: start`);
      for (const e of tree.start) { node(e.node, 'a start entry'); for (const f of [e.if, e.ifNot]) if (f !== undefined) flagsRead.add(f); }
    }
    for (const [nid, n] of Object.entries(tree.nodes)) {
      assert.ok(typeof n.text === 'string' && n.text.length > 0, `tree ${tid}.${nid}: text`);
      for (const f of n.set || []) flagsSet.add(f);
      for (const g of n.give || []) { assert.ok(C.items[g.item], `tree ${tid}.${nid}: gives unknown item ${g.item}`); itemsUsed.add(g.item); }
      if (n.next !== null && n.next !== undefined) node(n.next, `${nid}.next`);
      if (n.battle) {
        assert.ok(Array.isArray(n.battle.party) && n.battle.party.length > 0);
        for (const p of n.battle.party) { assert.ok(C.species[p.species], `${tid}.${nid}: battle species`); speciesUsed.add(p.species); }
        if (n.battle.win !== undefined) flagsSet.add(n.battle.win);
      }
      if ((n.choices || []).length >= 2) branching++;
      for (const ch of n.choices || []) {
        assert.ok(typeof ch.text === 'string' && ch.text.length > 0);
        if (ch.next !== null && ch.next !== undefined) node(ch.next, `a choice of ${nid}`);
        for (const f of ch.set || []) flagsSet.add(f);
        for (const f of [ch.if, ch.ifNot]) if (f !== undefined) flagsRead.add(f);
      }
    }
  }
  assert.ok(branching >= 2, 'at least two places where the player chooses');
  for (const f of flagsRead) assert.ok(flagsSet.has(f), `the flag ${f} is read but nothing sets it`);
  assert.ok(flagsSet.has(C.endFlag), 'something sets the ending flag');
  assert.equal(typeof C.endFlag, 'string');
  for (const m of Object.values(C.maps)) for (const g of m.gates || []) assert.ok(flagsSet.has(g.flag), `gate flag ${g.flag} is never set`);

  // creatures, moves, items
  const types = new Set(['ember', 'moss', 'brine', 'plain']);
  assert.ok(Object.keys(C.species).length >= 4, 'at least four creatures');
  assert.ok(Object.keys(C.moves).length >= 4, 'at least four moves');
  for (const [id, sp] of Object.entries(C.species)) {
    assert.equal(sp.id, id);
    assert.ok(types.has(sp.type), `${id}: type ${sp.type}`);
    for (const k of ['hp', 'atk', 'def', 'spd']) assert.ok(Number.isInteger(sp[k]) && sp[k] >= 1, `${id}.${k}`);
    assert.ok(sp.moves.length >= 1 && sp.moves.length <= 4);
    for (const mv of sp.moves) assert.ok(C.moves[mv], `${id}: unknown move ${mv}`);
  }
  for (const [id, mv] of Object.entries(C.moves)) {
    assert.equal(mv.id, id);
    assert.ok(types.has(mv.type), `${id}: type`);
    assert.ok(Number.isInteger(mv.power) && mv.power >= 0 && mv.accuracy > 0 && mv.accuracy <= 100);
  }
  for (const [id, it] of Object.entries(C.items)) {
    assert.equal(it.id, id);
    assert.ok(['heal', 'revive', 'key'].includes(it.kind), `${id}: kind`);
    if (it.kind === 'heal') assert.ok(it.amount > 0);
  }
  assert.ok(Object.values(C.items).some((i) => i.kind === 'heal'), 'at least one healing item');

  // original names only
  const text = fold(JSON.stringify(C));
  assert.ok(DENY.length > 20, 'the list of names was read from the kit');
  for (const { term, rx } of DENY) assert.ok(!rx.test(text), `"${term}" belongs to an existing franchise; use your own names`);
});
