// Scenarios for the first seven Pocket Region checks (layout, tiles, movement, warps, dialogue, the gated door).
// Each function is run by demos/probe.mjs in a process of its own beside the workspace's code, which it reaches
// through the `load` it is given: it makes the calls and returns what it saw, as plain data. It never judges:
// the numbered test files hold every assert.
import { stable, deepFreeze, mapOf, contentOf, play, TILE_FLAGS, tilesMap } from './helpers.mjs';
import { fixture } from './fixture.mjs';

// ---- 1: layout -----------------------------------------------------------------------------------------------
export async function layout({ load }, expected, contentKeys) {
  const files = {};
  for (const [file, names] of Object.entries(expected)) {
    try {
      const mod = await load(file);
      files[file] = { loaded: true, types: Object.fromEntries(names.map((n) => [n, n in mod ? typeof mod[n] : null])) };
    } catch (e) {
      files[file] = { loaded: false, error: String(e && e.message).split('\n')[0] };
    }
  }
  let content = { type: 'missing', has: {} };
  try {
    const { CONTENT } = await load('src/content.js');
    const isObject = CONTENT !== null && typeof CONTENT === 'object';
    content = { type: typeof CONTENT, has: Object.fromEntries(contentKeys.map((k) => [k, isObject && k in CONTENT])) };
  } catch { /* the files entry says why */ }
  return { documentType: typeof globalThis.document, files, content };
}

// ---- 2: tiles ------------------------------------------------------------------------------------------------
export async function tiles({ load }) {
  const { tileAt, blockedReason, canEnter } = await load('src/map.js');
  const m = deepFreeze(tilesMap());
  const out = { tile: {}, reason: {}, can: {}, odd: {} };
  for (let y = -2; y <= 4; y++) {
    for (let x = -2; x <= 5; x++) {
      out.tile[`${x},${y}`] = tileAt(m, x, y);
      for (const flags of TILE_FLAGS) {
        out.reason[`${x},${y},${stable(flags)}`] = blockedReason(m, x, y, flags);
        out.can[`${x},${y},${stable(flags)}`] = canEnter(m, x, y, flags);
      }
    }
  }
  out.odd = { halfX: tileAt(m, 0.5, 0), halfY: tileAt(m, 1, 1.5), far: tileAt(m, 100, 100) };
  const bare = { id: 'x', name: 'X', width: 2, height: 1, rows: ['..'] };
  out.bare = blockedReason(bare, 1, 0, {});
  return out;
}

// ---- 3: movement ---------------------------------------------------------------------------------------------
export async function movement({ load }) {
  const { movePlayer } = await load('src/movement.js');
  const m = mapOf(['.....', '.#.~.', '..T..', '.....', '.....'], {
    npcs: [{ id: 'n', x: 4, y: 3, tree: 't' }],
    gates: [{ x: 1, y: 4, flag: 'g' }],
  });
  const content = deepFreeze(contentOf([m]));
  const at = (x, y, facing = 'down') => deepFreeze({ map: 'm', x, y, facing });
  const flags = deepFreeze({});

  const openContent = deepFreeze(contentOf([mapOf(['...', '...', '...'])]));
  const dirs = {};
  for (const dir of ['up', 'down', 'left', 'right']) {
    const p = at(1, 1, 'up');
    const r = movePlayer(openContent, flags, p, dir);
    dirs[dir] = { r, newObject: r.player !== p };
  }
  const cases = [
    ['wall', at(0, 1), 'right'],
    ['water', at(3, 0), 'down'],
    ['tree', at(2, 3), 'up'],
    ['left edge', at(0, 0), 'left'],
    ['top edge', at(0, 0), 'up'],
    ['right edge', at(4, 0), 'right'],
    ['bottom edge', at(4, 4), 'down'],
    ['npc', at(3, 3), 'right'],
    ['gate', at(0, 4), 'right'],
  ];
  const blocked = cases.map(([name, p, dir]) => ({ name, p: JSON.parse(JSON.stringify(p)), dir, r: movePlayer(content, flags, p, dir) }));
  const open = movePlayer(content, { g: true }, at(0, 4), 'right');
  let p = at(0, 0, 'down');
  for (const d of ['down', 'down', 'down', 'right', 'right']) p = movePlayer(content, flags, p, d).player;
  return { dirs, blocked, open, chain: p };
}

// ---- 4: warps ------------------------------------------------------------------------------------------------
export async function warps({ load }) {
  const { movePlayer } = await load('src/movement.js');
  const a = mapOf(['.....', '.....', '.....'], {
    id: 'a',
    warps: [
      { x: 4, y: 1, to: 'b', tx: 2, ty: 0, facing: 'up' },
      { x: 2, y: 2, to: 'b', tx: 0, ty: 1 },
      { x: 0, y: 0, to: 'b', tx: 1, ty: 1, facing: 'left' },
    ],
    gates: [{ x: 2, y: 2, flag: 'door' }],
  });
  const b = mapOf(['...', '...'], {
    id: 'b',
    warps: [
      { x: 1, y: 1, to: 'c', tx: 0, ty: 0, facing: 'down' },
      { x: 2, y: 0, to: 'a', tx: 3, ty: 1, facing: 'left' },
    ],
  });
  const c = mapOf(['..'], { id: 'c' });
  const content = deepFreeze(contentOf([a, b, c]));
  const none = deepFreeze({});
  const P = (map, x, y, facing = 'down') => deepFreeze({ map, x, y, facing });
  const out = {};

  out.plain = movePlayer(content, none, P('a', 3, 1, 'right'), 'right');
  out.ownFacing = movePlayer(content, none, P('a', 0, 1, 'down'), 'up');
  out.keepsDirection = [[[2, 1], 'down'], [[1, 2], 'right'], [[3, 2], 'left']].map(([from, dir]) => ({
    dir, r: movePlayer(content, { door: true }, P('a', from[0], from[1], 'up'), dir),
  }));
  out.landsOnWarp1 = movePlayer(content, none, P('a', 4, 2, 'down'), 'up');
  out.landsOnWarp2 = movePlayer(content, none, P('a', 1, 0, 'right'), 'left');
  out.behindGate = movePlayer(content, none, P('a', 2, 1, 'up'), 'down');
  out.leaving = movePlayer(content, none, P('b', 1, 1, 'up'), 'left');
  out.sharesColumnOrRow = movePlayer(content, none, P('b', 0, 0, 'up'), 'right');
  out.there = movePlayer(content, none, P('b', 1, 0, 'up'), 'right');
  out.andBack = movePlayer(content, none, out.there.player, 'right');
  out.byCoordinates = movePlayer(content, none, P('b', 1, 0, 'up'), 'down');
  out.ownMapOnly = movePlayer(content, none, P('c', 0, 0, 'up'), 'right');
  return out;
}

// ---- 5: dialogue ---------------------------------------------------------------------------------------------
export async function dialogue({ load }) {
  const { startDialogue, advanceDialogue } = await load('src/dialogue.js');
  const tree = deepFreeze({
    start: 'a',
    nodes: {
      a: { text: 'Welcome', set: ['met'], give: [{ item: 'salve' }, { item: 'spark', count: 3 }],
        choices: [{ text: 'Ask', next: 'ask', set: ['asked'] }, { text: 'Leave', next: null, set: ['left'] }, { text: 'Skip', next: 'end' }],
        next: 'end' },
      ask: { text: 'Question?', next: 'more' },
      more: { text: 'More', give: [{ item: 'salve', count: 2 }], next: 'ask2' },
      ask2: { text: 'Again?', choices: [{ text: 'Back', next: 'a' }, { text: 'Done', next: 'end' }] },
      end: { text: 'Bye', set: ['bye'] },
    },
  });
  const game = deepFreeze({ flags: { old: true }, inventory: { salve: 1 }, keep: { me: 1 }, mode: 'dialogue' });
  const o = {};
  const r = startDialogue(tree, game);
  o.start = { r, newObject: r.game !== game };
  o.a1 = advanceDialogue(tree, r.game, r.view, 0);
  o.a2 = advanceDialogue(tree, o.a1.game, o.a1.view);
  o.a2b = advanceDialogue(tree, o.a1.game, o.a1.view, 5);
  o.a3 = advanceDialogue(tree, o.a2.game, o.a2.view);
  o.back = advanceDialogue(tree, o.a3.game, o.a3.view, 0);
  o.leave = advanceDialogue(tree, r.game, r.view, 1);
  o.skip = advanceDialogue(tree, r.game, r.view, 2);
  o.fin = advanceDialogue(tree, o.skip.game, o.skip.view);
  o.again = advanceDialogue(tree, o.fin.game, o.fin.view);
  o.againGameStable = stable(o.again.game);
  o.finGameStable = stable(o.fin.game);
  o.bad = [-1, 3, 7, 1.5, undefined, '0', null, NaN].map((choice) => {
    try {
      advanceDialogue(tree, r.game, r.view, choice);
      return { choice: String(choice), threw: null };
    } catch (e) {
      return { choice: String(choice), threw: e instanceof RangeError ? 'RangeError' : 'other' };
    }
  });
  return o;
}

// ---- 6: dialogue conditions ----------------------------------------------------------------------------------
export async function conditions({ load }) {
  const { startDialogue, advanceDialogue } = await load('src/dialogue.js');
  const G = (flags = {}, inventory = {}) => deepFreeze({ flags, inventory });
  const o = {};

  const t1 = deepFreeze({
    start: [{ if: 'a', ifNot: 'b', node: 'ab' }, { if: 'a', node: 'a' }, { ifNot: 'c', node: 'notc' }, { node: 'rest' }],
    nodes: { ab: { text: 'AB' }, a: { text: 'A' }, notc: { text: 'NOTC' }, rest: { text: 'REST' } },
  });
  o.t1 = [{ a: true }, { a: true, b: true }, { b: true }, { b: true, c: true }, {}].map((flags) => startDialogue(t1, G(flags)).view.node);

  const t2 = deepFreeze({ start: [{ if: 'a', node: 'a' }], nodes: { a: { text: 'A', set: ['x'] } } });
  const none = startDialogue(t2, G({ z: true }, { salve: 1 }));
  o.none = { view: none.view, game: stable(none.game), given: stable(G({ z: true }, { salve: 1 })) };

  const t3 = deepFreeze({
    start: [{ if: 'toString', node: 'inherited' }, { if: 'f', node: 'f' }, { node: 'plain' }],
    nodes: { inherited: { text: 'I' }, f: { text: 'F' }, plain: { text: 'P' } },
  });
  o.t3 = [{}, { f: false }, { toString: true }].map((flags) => startDialogue(t3, G(flags)).view.node);
  const t3b = deepFreeze({ start: [{ ifNot: 'constructor', node: 'free' }, { node: 'blocked' }], nodes: { free: { text: 'F' }, blocked: { text: 'B' } } });
  o.t3b = [{}, { constructor: true }].map((flags) => startDialogue(t3b, G(flags)).view.node);

  const t4 = deepFreeze({
    start: 'q',
    nodes: {
      q: { text: 'Q', choices: [
        { text: 'one', next: 'n1' },
        { text: 'needs-key', if: 'key', next: 'nk' },
        { text: 'not-seen', ifNot: 'seen', next: 'ns' },
        { text: 'both', if: 'key', ifNot: 'seen', next: 'nb' },
        { text: 'last', next: 'nl' },
      ] },
      n1: { text: 'N1' }, nk: { text: 'NK' }, ns: { text: 'NS' }, nb: { text: 'NB' }, nl: { text: 'NL' },
    },
  });
  o.t4texts = [{}, { key: true }, { key: true, seen: true }, { seen: true }].map((flags) => startDialogue(t4, G(flags)).view.choices);
  const s = startDialogue(t4, G({ seen: true }));
  o.t4index1 = advanceDialogue(t4, s.game, s.view, 1).view.node;
  try { advanceDialogue(t4, s.game, s.view, 2); o.t4index2 = null; } catch (e) { o.t4index2 = e instanceof RangeError ? 'RangeError' : 'other'; }
  const s2 = startDialogue(t4, G({ key: true }));
  o.t4index3 = advanceDialogue(t4, s2.game, s2.view, 3).view.node;

  const t5 = deepFreeze({
    start: 'x',
    nodes: {
      x: { text: 'X', set: ['f'], choices: [{ text: 'shown', if: 'f', next: 'ok' }, { text: 'hidden', ifNot: 'f', next: 'ok' }] },
      ok: { text: 'ok' },
    },
  });
  o.t5 = startDialogue(t5, G()).view.choices;

  const t6 = deepFreeze({
    start: 'x',
    nodes: { x: { text: 'X', choices: [{ text: 'no', if: 'never', next: 'y' }], next: 'y' }, y: { text: 'Y' } },
  });
  const h = startDialogue(t6, G());
  o.t6 = { choices: h.view.choices, next: advanceDialogue(t6, h.game, h.view).view.node };
  const t6b = deepFreeze({ start: 'x', nodes: { x: { text: 'X', choices: [{ text: 'no', if: 'never', next: 'y' }] }, y: { text: 'Y' } } });
  const h2 = startDialogue(t6b, G());
  o.t6bEnded = advanceDialogue(t6b, h2.game, h2.view).view.ended;

  const spec = { party: [{ species: 'rockling', level: 6 }], win: 'beaten' };
  const t7 = deepFreeze({
    start: 'fight',
    nodes: { fight: { text: 'Fight!', set: ['dared'], battle: spec, next: 'after' }, after: { text: 'After' } },
  });
  const b = startDialogue(t7, G());
  const done = advanceDialogue(t7, b.game, b.view);
  o.t7 = { b, done };
  const t8 = deepFreeze({
    start: 'x',
    nodes: { x: { text: 'X', battle: spec, choices: [{ text: 'go', next: 'y' }] }, y: { text: 'Y' } },
  });
  const c = startDialogue(t8, G());
  o.t8 = advanceDialogue(t8, c.game, c.view, 0).view;
  const t9 = deepFreeze({ start: 'x', nodes: { x: { text: 'X' } } });
  const e = startDialogue(t9, G());
  o.t9 = advanceDialogue(t9, e.game, e.view).view.battle;
  return o;
}

// ---- 7: the gated door ---------------------------------------------------------------------------------------
export async function gatedDoor({ load }) {
  const { newGame, step } = await load('src/game.js');
  const c = fixture();
  const start = newGame(c, 1);
  const toGate = ['right', 'right'];
  const o = {};

  const g = play(c, step, start, [...toGate, 'right', 'right', 'right']);
  o.blocked = g;
  const wrong = structuredClone(g);
  wrong.flags.asked = true;
  wrong.flags.other = true;
  o.wrongFlag = play(c, step, wrong, ['right']);
  o.falseFlag = play(c, step, { ...wrong, flags: { pass: false } }, ['right']);

  o.talk = play(c, step, start, ['action']);
  o.otherChoice = play(c, step, o.talk, ['choose:1']);
  const t = play(c, step, start, ['action', 'choose:1', 'action']);
  o.justPassing = t;
  o.justPassingWalk = play(c, step, t, [...toGate, 'right', 'right']);

  o.openedAtChoice = play(c, step, start, ['action', 'choose:0']);
  const opened = play(c, step, o.openedAtChoice, ['action']);
  o.opened = opened;
  o.through = play(c, step, opened, [...toGate, 'right']);
  o.out = play(c, step, o.through, ['right']);

  const direct = structuredClone(start);
  direct.flags.pass = true;
  o.direct = play(c, step, direct, [...toGate, 'right']);

  o.home = play(c, step, o.out, ['left']);
  o.homeAgain = play(c, step, o.home, ['right']);
  o.closedGateStable = { after: stable(step(c, g, 'right')), before: stable(g) };
  return o;
}
