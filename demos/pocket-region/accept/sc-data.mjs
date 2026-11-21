// Scenarios for checks 12 to 15 (the generator, canonical JSON, save and load, encounters). Run by
// demos/probe.mjs in a process of its own beside the workspace's code; they return what the code did, never a
// verdict.
import { stable, clone, deepFreeze, play, attempt, kinds } from './helpers.mjs';
import { fixture } from './fixture.mjs';

// ---- 12: the generator ---------------------------------------------------------------------------------------
export async function rng({ load }, seeds) {
  const { makeRng, rngNext } = await load('src/rng.js');
  const draw = (seed, n) => { const r = makeRng(seed); return Array.from({ length: n }, () => rngNext(r)); };
  const o = {};
  o.same = [draw(42, 200), draw(42, 200)];
  o.range = draw(7, 2000);
  o.ends = Object.fromEntries([0, 1, 4294967295].map((s) => [s, draw(s, 50)]));
  o.streams = seeds.map((s) => draw(s, 8));
  o.many = draw(5, 10000);

  const r = makeRng(99);
  for (let i = 0; i < 13; i++) rngNext(r);
  const copy = clone(r);
  o.copySame = stable(copy) === stable(r);
  o.carryOn = [Array.from({ length: 30 }, () => rngNext(r)), Array.from({ length: 30 }, () => rngNext(copy))];
  const s0 = stable(r);
  rngNext(r);
  o.advancedInPlace = stable(r) !== s0;
  o.seed5 = [JSON.stringify(makeRng(5)), JSON.stringify(clone(makeRng(5)))];
  o.kinds = kinds(makeRng(5), 'state');

  const x = makeRng(1);
  const y = makeRng(2);
  const xs = [];
  const ys = [];
  for (let i = 0; i < 40; i++) { xs.push(rngNext(x)); ys.push(rngNext(y)); }
  o.interleaved = { xs, ys, soloX: draw(1, 40), soloY: draw(2, 40) };
  const z = makeRng(3);
  rngNext(z);
  makeRng(3);
  o.undisturbed = { got: [rngNext(z), rngNext(z)], want: draw(3, 3).slice(1) };
  return o;
}

// ---- 13: canonical JSON --------------------------------------------------------------------------------------
export async function canonical({ load }, okValues, badValues) {
  const { canonicalJson } = await load('src/save.js');
  const o = {};
  o.ok = okValues.map((v) => canonicalJson(v));
  o.bad = badValues.map((v) => { const r = attempt(() => canonicalJson(v)); return r.ok ? null : r.error; });
  o.badBuilt = [
    ['a function', () => 1], ['a function in an object', { f() {} }], ['a symbol', Symbol('s')], ['a symbol in an array', [Symbol('s')]],
  ].map(([name, v]) => { const r = attempt(() => canonicalJson(v)); return { name, error: r.ok ? null : r.error }; });
  o.big = canonicalJson({ list: [1, { k: 'v w' }, []], o: { n: null }, s: 'a b' });
  const frozen = deepFreeze({ z: [1, 2, { y: 'q' }], a: false });
  o.frozen = { parsed: stable(JSON.parse(canonicalJson(frozen))), given: stable(frozen) };
  o.proto = canonicalJson(JSON.parse('{"b":1,"__proto__":2,"a":3}'));
  return o;
}

// ---- 14: save and load ---------------------------------------------------------------------------------------
export const TO_CHIEF = ['action', 'choose:0', 'action', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right', 'right'];
const MORE = ['right', 'action', 'choose:1', 'action', 'move:0', 'move:1', 'up', 'down', 'action', 'choose:0', 'run', 'left', 'action', 'action', 'move:0', 'right', 'use:salve:0', 'action', 'move:0', 'move:0', 'action', 'action', 'left', 'left'];

export async function saveLoad({ load, withoutClocks }) {
  const { newGame, step } = await load('src/game.js');
  const { saveGame, loadGame, canonicalJson } = await load('src/save.js');
  const c = fixture();
  const o = {};

  const world = play(c, step, newGame(c, 5), ['left', 'left', 'up']);
  const talking = play(c, step, newGame(c, 5), ['action']);
  const atChief = play(c, step, newGame(c, 5), TO_CHIEF);
  o.atChiefMap = atChief.player.map;
  const chat = play(c, step, atChief, ['action']);
  o.chatMode = chat.mode;
  const fighting = play(c, step, chat, ['action', 'move:0']);
  o.fightingMode = fighting.mode;
  const hurt = structuredClone(world);
  hurt.party[0].hp = 3;
  hurt.flags.zeta = true;
  hurt.flags.alpha = true;
  hurt.inventory = { tag: 1, salve: 4, spark: 2 };

  o.games = [['walking', world], ['in a conversation', talking], ['in a conversation with a choice made', chat], ['in a battle', fighting], ['edited', hurt]]
    .map(([name, g]) => {
      const frozen = deepFreeze(structuredClone(g));
      const text = saveGame(frozen);
      const back = loadGame(text);
      const backCanonical = canonicalJson(back);
      const again = saveGame(back);
      const second = loadGame(text);
      back.flags.mutated = true;
      back.party[0].hp = -1;
      back.player.x = 99;
      return {
        name, game: g, textType: typeof text, text, canonical: canonicalJson({ version: 1, game: g }), back: loadGame(text),
        backCanonical, again, secondStable: stable(second), gameStable: stable(g),
      };
    });

  const b = loadGame(saveGame(hurt));
  o.pieces = { b, hurt };

  const g1 = structuredClone(world);
  g1.flags = { b: true, a: true, c: true };
  const g2 = structuredClone(world);
  g2.flags = { c: true, a: true, b: true };
  o.order = [saveGame(g1), saveGame(g2)];

  await withoutClocks(async () => {
    o.carry = [['walking', world], ['talking', talking], ['fighting', fighting], ['edited', hurt]].map(([name, g]) => {
      let a = g;
      let l = loadGame(saveGame(g));
      const steps = MORE.map((input) => {
        a = step(c, a, input);
        l = step(c, l, input);
        return { input, original: stable(a), loaded: stable(l) };
      });
      return { name, steps };
    });
    const all = [...TO_CHIEF, 'action', 'action', 'move:0', 'move:0', 'action', 'action'];
    const straight = play(c, step, newGame(c, 3), all);
    o.cuts = { straight: stable(straight), resumed: [] };
    for (let cut = 0; cut <= all.length; cut += 3) {
      const first = play(c, step, newGame(c, 3), all.slice(0, cut));
      const resumed = play(c, step, loadGame(saveGame(first)), all.slice(cut));
      o.cuts.resumed.push({ cut, stable: stable(resumed) });
    }
  });

  const text = saveGame(world);
  const refusals = [
    ['a different version', () => loadGame(text.replace('{"game":', '{"foo":1,"game":').replace('"version":1', '"version":2'))],
    ['version 2', () => loadGame(canonicalJson({ version: 2, game: world }))],
    ['version as text', () => loadGame(canonicalJson({ version: '1', game: world }))],
    ['no version', () => loadGame(canonicalJson({ game: world }))],
    ['not JSON', () => loadGame('{not json')],
    ['empty', () => loadGame('')],
    ['nothing', () => loadGame(undefined)],
    ['an array', () => loadGame(canonicalJson([1, 2]))],
    ['no game', () => loadGame(canonicalJson({ version: 1 }))],
    ['a game that is not an object', () => loadGame(canonicalJson({ version: 1, game: 5 }))],
    ['null', () => loadGame('null')],
    ['a game with NaN', () => saveGame({ ...world, bad: NaN })],
  ];
  o.refusals = refusals.map(([name, fn]) => { const r = attempt(fn); return { name, error: r.ok ? null : r.error }; });
  return o;
}

// ---- 15: encounters ------------------------------------------------------------------------------------------
export async function encounters({ load, withoutClocks }) {
  const { newGame, step } = await load('src/game.js');
  const { makeRng, rngNext } = await load('src/rng.js');
  const { makeCreature } = await load('src/battle.js');

  const wildContent = (rate, list) => {
    const c = fixture();
    c.maps.wild.encounterRate = rate;
    c.maps.wild.encounters = list;
    return c;
  };
  const atWild = (c, seed) => {
    const g = newGame(c, seed);
    g.player = { map: 'wild', x: 1, y: 2, facing: 'up' };
    return g;
  };
  // draws made by hand from a copy of the generator's state: the first four values, and the state after one and
  // after four of them
  const replay = (rngState) => {
    const r = JSON.parse(JSON.stringify(rngState));
    const d = [rngNext(r)];
    const after1 = stable(r);
    for (let i = 0; i < 3; i++) d.push(rngNext(r));
    return { draws: d, after1, after4: stable(r) };
  };
  const o = {};

  await withoutClocks(async () => {
    {
      const c = wildContent(100, [{ species: 'pool', minLevel: 3, maxLevel: 3, weight: 1 }]);
      const g = atWild(c, 11);
      const h = replay(g.rng);
      const out = step(c, g, 'up');
      o.hundred = {
        g, out, ...h, enemy: makeCreature(c, 'pool', 3), battleRng: stable(makeRng(Math.floor(h.draws[3] * 4294967296))),
      };
    }
    {
      const c = wildContent(0, [{ species: 'pool', minLevel: 3, maxLevel: 3, weight: 1 }]);
      const g = atWild(c, 11);
      const h = replay(g.rng);
      o.zero = { out: step(c, g, 'up'), ...h };
    }
    o.mixed = [];
    for (let seed = 1; seed <= 80; seed++) {
      const c = wildContent(35, [
        { species: 'pool', minLevel: 2, maxLevel: 5, weight: 3 },
        { species: 'sprig', minLevel: 7, maxLevel: 7, weight: 1 },
      ]);
      const g = atWild(c, seed);
      const h = replay(g.rng);
      const out = step(c, g, 'up');
      const creatures = {};
      for (const level of [2, 3, 4, 5]) creatures[`pool,${level}`] = makeCreature(c, 'pool', level);
      creatures['sprig,7'] = makeCreature(c, 'sprig', 7);
      o.mixed.push({ seed, out, ...h, creatures, battleRng: stable(makeRng(Math.floor(h.draws[3] * 4294967296))) });
    }
    o.weights = [];
    for (let seed = 1; seed <= 30; seed++) {
      const c = wildContent(100, [
        { species: 'pool', minLevel: 1, maxLevel: 1, weight: 1 },
        { species: 'sprig', minLevel: 1, maxLevel: 1, weight: 2 },
        { species: 'rockling', minLevel: 1, maxLevel: 1, weight: 3 },
      ]);
      const g = atWild(c, seed);
      const h = replay(g.rng);
      const out = step(c, g, 'up');
      o.weights.push({ seed, draws: h.draws, mode: out.mode, species: out.battle ? out.battle.enemyParty[0].species : null });
    }
    {
      const c = wildContent(100, []);
      const g = atWild(c, 4);
      const h = replay(g.rng);
      const out = step(c, g, 'up');
      const c2 = fixture();
      delete c2.maps.wild.encounters;
      delete c2.maps.wild.encounterRate;
      const out2 = step(c2, atWild(c2, 4), 'up');
      o.noList = { mode: out.mode, rng: stable(out.rng), mode2: out2.mode, rng2: stable(out2.rng), after1: h.after1 };
    }
    {
      const c = wildContent(0, []);
      const g = atWild(c, 6);
      const h = replay(g.rng);
      const r = JSON.parse(JSON.stringify(g.rng));
      rngNext(r);
      rngNext(r);
      const out = step(c, step(c, g, 'up'), 'right');
      o.grassToGrass = { player: out.player, rng: stable(out.rng), twoDraws: stable(r), after1: h.after1 };
    }
    {
      const c = wildContent(100, [{ species: 'pool', minLevel: 3, maxLevel: 3, weight: 1 }]);
      const same = (why, g, input) => ({ why, before: stable(g.rng), after: stable(step(c, g, input).rng) });
      o.noDraw = [];
      const onFloor = atWild(c, 9);
      o.noDraw.push(same('a step along the floor row draws nothing', onFloor, 'right'));
      o.noDraw.push(same('a step onto a warp tile draws nothing', onFloor, 'left'));
      o.noDraw.push(same('action draws nothing', onFloor, 'action'));
      const wall = atWild(c, 9);
      wall.player = { map: 'wild', x: 1, y: 1, facing: 'up' };
      o.noDraw.push(same('walking into a wall draws nothing', wall, 'up'));
      o.noDraw.push(same('walking on the town floor draws nothing', newGame(c, 9), 'left'));
      c.maps.town.warps[0] = { x: 8, y: 3, to: 'wild', tx: 2, ty: 1, facing: 'right' };
      const gate = newGame(c, 9);
      gate.flags.pass = true;
      gate.player = { map: 'town', x: 7, y: 3, facing: 'right' };
      const out = step(c, gate, 'right');
      o.warpOntoGrass = { player: out.player, mode: out.mode, before: stable(gate.rng), after: stable(out.rng) };
      c.maps.wild.npcs = [{ id: 'n', x: 1, y: 1, tree: 'sage' }];
      o.noDraw.push(same('a blocked move onto grass draws nothing', atWild(c, 9), 'up'));
    }
  });
  return o;
}
