import { makeRng, rngNext } from './rng.js';
import { tileAt, hasFlag } from './map.js';
import { DIRS, movePlayer } from './movement.js';
import { startDialogue, advanceDialogue } from './dialogue.js';
import { startBattle, takeTurn, makeCreature } from './battle.js';
import { useItem } from './inventory.js';

export function newGame(content, seed) {
  const s = content.start;
  return {
    player: { map: s.map, x: s.x, y: s.y, facing: s.facing },
    flags: {},
    inventory: { ...(s.inventory || {}) },
    party: s.party.map((p) => makeCreature(content, p.species, p.level)),
    rng: makeRng(seed),
    mode: 'world',
    dialogue: null,
    battle: null,
  };
}

export function isEnded(content, game) {
  return hasFlag(game.flags, content.endFlag);
}

function beginBattle(content, g, enemyParty, wild, winFlag) {
  const seed = Math.floor(rngNext(g.rng) * 4294967296);
  g.battle = startBattle(content, g.party, enemyParty, seed, { wild });
  g.battle.winFlag = winFlag;
  g.mode = 'battle';
}

function wildEncounter(content, g) {
  const map = content.maps[g.player.map];
  const a = rngNext(g.rng);
  const list = map.encounters || [];
  if (!(a * 100 < (map.encounterRate ?? 0)) || list.length === 0) return;
  const total = list.reduce((n, e) => n + e.weight, 0);
  const t = rngNext(g.rng) * total;
  let acc = 0;
  let pick = list[list.length - 1];
  for (const e of list) {
    acc += e.weight;
    if (t < acc) { pick = e; break; }
  }
  const lv = pick.minLevel + Math.floor(rngNext(g.rng) * (pick.maxLevel - pick.minLevel + 1));
  beginBattle(content, g, [makeCreature(content, pick.species, lv)], true, null);
}

function finishBattle(content, g) {
  const b = g.battle;
  g.party = b.playerParty;
  if (b.winner === 'player' && b.winFlag) g.flags[b.winFlag] = true;
  if (b.winner === 'enemy') {
    const s = content.start;
    g.player = { map: s.map, x: s.x, y: s.y, facing: s.facing };
    for (const c of g.party) c.hp = c.maxHp;
  }
  g.battle = null;
  g.mode = 'world';
}

function afterDialogue(content, g, r) {
  g.flags = r.game.flags;
  g.inventory = r.game.inventory;
  if (r.view.ended) {
    g.dialogue = null;
    g.mode = 'world';
    if (r.view.battle) {
      const spec = r.view.battle;
      const enemies = spec.party.map((p) => makeCreature(content, p.species, p.level));
      beginBattle(content, g, enemies, false, spec.win ?? null);
    }
  } else {
    g.dialogue = { tree: g.dialogue.tree, view: r.view };
  }
}

export function step(content, game, input) {
  const g = structuredClone(game);
  if (typeof input !== 'string') return g;
  if (g.mode === 'world') {
    if (Object.hasOwn(DIRS, input)) {
      const r = movePlayer(content, g.flags, g.player, input);
      g.player = r.player;
      if (r.moved && !r.warped && tileAt(content.maps[g.player.map], g.player.x, g.player.y) === ',') {
        wildEncounter(content, g);
      }
    } else if (input === 'action') {
      const map = content.maps[g.player.map];
      const [dx, dy] = DIRS[g.player.facing];
      const npc = (map.npcs || []).find((n) => n.x === g.player.x + dx && n.y === g.player.y + dy);
      if (npc) {
        const r = startDialogue(content.trees[npc.tree], g);
        g.flags = r.game.flags;
        g.inventory = r.game.inventory;
        if (!r.view.ended) {
          g.mode = 'dialogue';
          g.dialogue = { tree: npc.tree, view: r.view };
        }
      }
    } else {
      const m = /^use:([^:]+):(\d+)$/.exec(input);
      if (m) {
        const r = useItem(content, g.inventory, g.party, m[1], Number(m[2]));
        if (r.ok) { g.inventory = r.inventory; g.party = r.party; }
      }
    }
  } else if (g.mode === 'dialogue') {
    const tree = content.trees[g.dialogue.tree];
    const view = g.dialogue.view;
    if (input === 'action' && view.choices.length === 0) {
      afterDialogue(content, g, advanceDialogue(tree, g, view));
    } else {
      const m = /^choose:(\d+)$/.exec(input);
      if (m && Number(m[1]) < view.choices.length) {
        afterDialogue(content, g, advanceDialogue(tree, g, view, Number(m[1])));
      }
    }
  } else if (g.mode === 'battle') {
    let action = null;
    const m = /^move:(\d+)$/.exec(input);
    if (m) {
      const me = g.battle.playerParty.find((c) => c.hp > 0);
      if (Number(m[1]) < me.moves.length) action = { type: 'move', slot: Number(m[1]) };
    } else if (input === 'run') action = { type: 'run' };
    if (action) {
      const winFlag = g.battle.winFlag;
      g.battle = takeTurn(content, g.battle, action);
      g.battle.winFlag = winFlag;
      if (g.battle.over) finishBattle(content, g);
    }
  }
  return g;
}
