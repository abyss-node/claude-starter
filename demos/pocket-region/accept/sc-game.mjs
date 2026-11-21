// Scenarios for checks 16 to 19 (the game loop, the shipped world, the shipped walkthrough, the scripted
// playthrough). Run by demos/probe.mjs in a process of its own beside the workspace's code; they return what the
// code did, never a verdict.
import { stable, clone, deepFreeze, play, kinds } from './helpers.mjs';
import { fixture } from './fixture.mjs';

// ---- 16: the game loop ---------------------------------------------------------------------------------------
export async function loop({ load, withoutClocks }) {
  const { newGame, step, isEnded } = await load('src/game.js');
  const { makeRng, rngNext } = await load('src/rng.js');
  const { makeCreature } = await load('src/battle.js');
  const c = fixture();
  const fresh = (seed = 21) => newGame(c, seed);
  const o = { same: [] };
  const same = (game, input, why) => o.same.push({ why: why || `${JSON.stringify(input)} changes nothing`, before: stable(game), after: stable(step(c, game, input)) });
  const at = (game, map, x, y, facing) => { const g = structuredClone(game); g.player = { map, x, y, facing }; return g; };
  const ATTACK = (g) => at(g, 'keep', 3, 2, 'right');
  const NONSENSE = ['', 'jump', 'UP', 'Up', ' up', 'up ', 'choose:', 'choose:x', 'choose:-1', 'move:', 'move:x', 'use:', 'use:salve', 'use::0', 'use:salve:x', 'use:salve:-1', 42, null, undefined, true, ['up'], { x: 1 }];

  await withoutClocks(async () => {
    // newGame
    const g0 = fresh();
    o.g0 = { game: clone(g0), kinds: kinds(g0, 'game'), rng: stable(g0.rng), expectedRng: stable(makeRng(21)), pup5: makeCreature(c, 'pup', 5) };
    g0.inventory.tag = 9;
    g0.party[0].hp = 1;
    o.startInventoryAfter = clone(c.start.inventory);
    o.seeds = [stable(fresh(22).rng), stable(fresh(21).rng)];
    const done = fresh();
    o.ended = { fresh: isEnded(c, fresh()) };
    done.flags.the_end = true;
    o.ended.set = isEnded(c, done);
    done.flags = { the_end: false, other: true };
    o.ended.falseFlag = isEnded(c, done);
    o.ended.notTrue = [1, 'yes', {}, [], 'true'].map((v) => { done.flags = { the_end: v }; return isEnded(c, done); });

    // step is pure and plain
    const frozen = deepFreeze(fresh());
    o.pure = ['up', 'left', 'action', 'right', 'run', 'choose:0', 'move:0', 'use:salve:0', 'nonsense'].map((input) => {
      const out = step(c, frozen, input);
      return { input, newObject: out !== frozen, kinds: kinds(out, 'game') };
    });

    // in the world, things that mean nothing change nothing
    for (const input of [...NONSENSE, 'choose:0', 'move:0', 'run', 'use:salve:0', 'use:tag:0', 'use:ghost:0', 'use:salve:9']) same(fresh(), input);

    // movement
    let g = step(c, fresh(), 'left');
    const moves = [g.player];
    g = step(c, g, 'up');
    moves.push(g.player);
    g = play(c, step, g, ['up', 'up', 'up']);
    moves.push(g.player);
    o.moves = moves;
    o.turnChanges = stable(step(c, g, 'left')) !== stable(g);
    o.wallStop = step(c, g, 'up').player;

    // talking
    same(at(fresh(), 'town', 3, 3, 'left'), 'action', 'nobody there');
    same(at(fresh(), 'town', 4, 4, 'down'), 'action', 'nobody there either');
    same(at(fresh(), 'town', 3, 3, 'up'), 'action', 'the sage is diagonal, not faced');
    same(at(fresh(), 'town', 4, 4, 'up'), 'action', 'the sage is two tiles away');
    same(at(fresh(), 'town', 4, 3, 'left'), 'action', 'the sage is above, but the player faces left');
    same(at(fresh(), 'town', 4, 3, 'down'), 'action', 'the sage is above, but the player faces down');
    o.talk = step(c, fresh(), 'action');
    o.freshPlayer = fresh().player;
    const won = ATTACK(fresh());
    won.flags.chief_beaten = true;
    o.chiefAfterWin = step(c, won, 'action');
    const c2 = fixture();
    c2.trees.sage.start = [{ if: 'never', node: 'hi' }];
    const nothing = newGame(c2, 1);
    o.noStart = { before: stable(nothing), after: stable(step(c2, nothing, 'action')) };

    // in a conversation
    const talk = step(c, fresh(), 'action');
    for (const input of [...NONSENSE, 'up', 'down', 'left', 'right', 'move:0', 'run', 'use:salve:0', 'action', 'choose:2', 'choose:3', 'choose:9']) same(talk, input, `in a conversation with choices, ${JSON.stringify(input)}`);
    const bye = step(c, talk, 'choose:1');
    o.bye = { mode: bye.mode, view: bye.dialogue.view };
    for (const input of ['up', 'choose:0', 'choose:1', 'move:0', 'run', 'use:salve:0', 'left']) same(bye, input, `in a conversation without choices, ${JSON.stringify(input)}`);
    const out = step(c, bye, 'action');
    o.byeOut = { mode: out.mode, dialogue: out.dialogue, flags: stable(out.flags) };
    const open = step(c, talk, 'choose:0');
    o.open = open;
    const finished = step(c, open, 'action');
    o.finished = finished;
    o.again = step(c, finished, 'action').dialogue.view.node;

    // a conversation that ends in a battle
    let f = step(c, ATTACK(fresh(5)), 'action');
    o.fightTalk = { node: f.dialogue.view.node, mode: f.mode };
    const h = JSON.parse(JSON.stringify(f.rng));
    const seed = Math.floor(rngNext(h) * 4294967296);
    f = step(c, f, 'action');
    o.battleStart = {
      game: f, expectedRng: stable(makeRng(seed)), oneDraw: stable(h), kinds: kinds(f, 'game'),
      rockling6: makeCreature(c, 'rockling', 6),
    };

    // in a battle: only moves and running count
    for (const input of [...NONSENSE, 'up', 'down', 'left', 'right', 'action', 'choose:0', 'use:salve:0', 'move:2', 'move:9', 'run']) same(f, input, `in a battle, ${JSON.stringify(input)}`);

    // winning with two jabs
    const one = step(c, f, 'move:0');
    o.one = one;
    const win = step(c, one, 'move:0');
    o.win = win;
    o.quick = step(c, f, 'move:1');
    const end = play(c, step, win, ['action', 'action']);
    o.end = { flag: end.flags.the_end, ended: isEnded(c, end), mode: end.mode };

    // losing: a blackout
    const weak = ATTACK(fresh(5));
    weak.flags.pass = true;
    weak.inventory = { tag: 1, salve: 3 };
    weak.party[0].hp = 1;
    const fl = play(c, step, weak, ['action', 'action']);
    o.beforeBlackout = fl.mode;
    o.lost = step(c, fl, 'move:0');
    const pair = structuredClone(weak);
    pair.party.push(makeCreature(c, 'sprig', 5));
    const fl2 = play(c, step, pair, ['action', 'action']);
    o.mid = step(c, fl2, 'move:0');

    // a wild battle
    const wc = fixture();
    wc.maps.wild.encounterRate = 100;
    wc.maps.wild.encounters = [{ species: 'pool', minLevel: 1, maxLevel: 1, weight: 1 }];
    const wg = newGame(wc, 8);
    wg.player = { map: 'wild', x: 1, y: 2, facing: 'up' };
    wg.party[0].hp = 20;
    const enc = step(wc, wg, 'up');
    o.enc = enc.mode;
    const ran = step(wc, enc, 'run');
    o.ran = { mode: ran.mode, battle: ran.battle, hp: ran.party[0].hp, player: ran.player, rng: stable(ran.rng), encRng: stable(enc.rng), flags: ran.flags };
    const killed = step(wc, enc, 'move:1');
    o.killed = { mode: killed.mode, flags: killed.flags, hp: killed.party[0].hp };

    // items from the world
    const hurt = fresh();
    hurt.inventory = { tag: 1, salve: 2, spark: 1 };
    hurt.party = [makeCreature(c, 'pup', 5), makeCreature(c, 'sprig', 5)];
    hurt.party[0].hp = 10;
    hurt.party[1].hp = 0;
    const u1 = step(c, hurt, 'use:salve:0');
    o.heal = { hp: u1.party[0].hp, inventory: u1.inventory };
    same(hurt, 'use:salve:1', 'a fallen creature cannot be healed');
    same(hurt, 'use:salve:2', 'no such party member');
    same(hurt, 'use:tag:0', 'a key item cannot be used');
    same(hurt, 'use:spark:0', 'a living creature cannot be revived');
    const u2 = step(c, hurt, 'use:spark:1');
    o.revive = { hp: u2.party[1].hp, maxHp: u2.party[1].maxHp, inventory: u2.inventory };
    const busy = step(c, hurt, 'action');
    o.busyMode = busy.mode;
    same(busy, 'use:salve:0', 'while talking');
    same(play(c, step, structuredClone(ATTACK(hurt)), ['action', 'action']), 'use:salve:0', 'in a battle');

    // determinism
    const script = ['action', 'choose:0', 'action', 'right', 'right', 'right', 'right', 'down', 'up', 'left', 'action', 'right'];
    o.determinism = [stable(play(c, step, fresh(3), script)), stable(play(c, step, fresh(3), script))];
  });
  return o;
}

// ---- 17: the shipped world -----------------------------------------------------------------------------------
export async function content({ load }) {
  const { CONTENT } = await load('src/content.js');
  let copy = null;
  try { copy = structuredClone(CONTENT); } catch { /* the kinds say why */ }
  return { kinds: kinds(CONTENT, 'CONTENT'), content: copy };
}

// ---- 18: the shipped walkthrough -----------------------------------------------------------------------------
export async function walkthrough({ load, withoutClocks }) {
  const { CONTENT: C } = await load('src/content.js');
  const { newGame, step, isEnded } = await load('src/game.js');
  const { saveGame, loadGame } = await load('src/save.js');
  const w = C.walkthrough;
  const o = { given: w && typeof w === 'object' ? { seed: w.seed, inputs: w.inputs } : null, ran: false };
  const usable = w && typeof w === 'object' && Number.isInteger(w.seed) && Array.isArray(w.inputs)
    && w.inputs.length >= 1 && w.inputs.length <= 20000 && w.inputs.every((i) => typeof i === 'string');
  if (!usable) return o;

  const dirs = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  const gateAt = (mapId, x, y) => Object.hasOwn(C.maps, mapId) && (C.maps[mapId].gates || []).some((g) => g.x === x && g.y === y);

  await withoutClocks(async () => {
    const run = (inputs, from) => {
      let g = from || newGame(C, w.seed);
      const trace = { modes: new Set(), maps: new Set(), gates: new Set(), endedAt: -1 };
      inputs.forEach((input, n) => {
        const before = g;
        g = step(C, g, input);
        trace.modes.add(g.mode);
        trace.maps.add(g.player.map);
        // a gate is passed when a step in the world onto a gate tile moves the player (a gate tile may also be a
        // warp tile, where the player is sent on at once and is never seen standing on it)
        if (before.mode === 'world' && Object.hasOwn(dirs, input)) {
          const [dx, dy] = dirs[input];
          const p = before.player;
          const moved = g.player.map !== p.map || g.player.x !== p.x || g.player.y !== p.y;
          if (moved && gateAt(p.map, p.x + dx, p.y + dy)) trace.gates.add(`${p.map},${p.x + dx},${p.y + dy}`);
        }
        if (trace.endedAt < 0 && isEnded(C, g)) trace.endedAt = n;
      });
      return { g, trace };
    };
    const summary = (r) => ({
      ended: isEnded(C, r.g), endFlag: r.g.flags[C.endFlag], mode: r.g.mode, partyLength: r.g.party.length,
      modes: [...r.trace.modes], maps: [...r.trace.maps], gates: [...r.trace.gates], endedAt: r.trace.endedAt, stable: stable(r.g),
    });
    o.ran = true;
    o.endFlagName = C.endFlag;
    o.startEnded = isEnded(C, newGame(C, w.seed));
    const a = run(w.inputs);
    o.first = summary(a);
    o.second = summary(run(w.inputs));
    o.resumed = [0.25, 0.5, 0.9].map((frac) => {
      const cut = Math.floor(w.inputs.length * frac);
      const first = run(w.inputs.slice(0, cut)).g;
      const resumed = run(w.inputs.slice(cut), loadGame(saveGame(first))).g;
      return { cut, stable: stable(resumed) };
    });
  });
  return o;
}

// ---- 19: a scripted playthrough ------------------------------------------------------------------------------
export async function playthrough({ load, withoutClocks }, inputs, seeds) {
  const { newGame, step, isEnded } = await load('src/game.js');
  const { saveGame, loadGame } = await load('src/save.js');
  const c = deepFreeze(fixture());
  const o = {};
  await withoutClocks(async () => {
    o.runs = seeds.map((seed) => {
      let g = newGame(c, seed);
      const states = [];
      for (const input of inputs) {
        g = step(c, g, input);
        states.push(g);
      }
      return { seed, states, endedAfter20: isEnded(c, states[19]), endedAtEnd: isEnded(c, g) };
    });
    const direct = inputs.reduce((g, i) => step(c, g, i), newGame(c, 77));
    const again = inputs.reduce((g, i) => step(c, g, i), newGame(c, 77));
    const reloaded = inputs.reduce((g, i) => step(c, loadGame(saveGame(g)), i), newGame(c, 77));
    o.seed77 = { direct: stable(direct), again: stable(again), reloaded: stable(reloaded) };
  });
  return o;
}
