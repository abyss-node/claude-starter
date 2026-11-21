import { makeRng, rngNext } from './rng.js';

export const BEATS = { ember: 'moss', moss: 'brine', brine: 'ember' };

export function makeCreature(content, speciesId, level) {
  const s = content.species[speciesId];
  const maxHp = Math.floor((s.hp * level) / 10) + level + 10;
  const stat = (b) => Math.floor((b * level) / 10) + 5;
  return {
    species: speciesId, name: s.name, type: s.type, level,
    hp: maxHp, maxHp, atk: stat(s.atk), def: stat(s.def), spd: stat(s.spd),
    moves: [...s.moves],
  };
}

export function damage(attacker, defender, move) {
  if (move.power <= 0) return 0;
  let d = Math.floor((move.power * attacker.atk) / defender.def) + 2;
  if (move.type === attacker.type) d = Math.floor((d * 3) / 2);
  if (BEATS[move.type] === defender.type) d *= 2;
  else if (BEATS[defender.type] === move.type) d = Math.floor(d / 2);
  return Math.max(1, d);
}

export function activeIndex(party) {
  return party.findIndex((c) => c.hp > 0);
}

export function startBattle(content, playerParty, enemyParty, seed, options = {}) {
  return {
    playerParty: structuredClone(playerParty),
    enemyParty: structuredClone(enemyParty),
    turn: 0, over: false, winner: null, wild: Boolean(options.wild),
    rng: makeRng(seed), log: [],
  };
}

export function enemyChoose(content, battle) {
  const me = battle.enemyParty[activeIndex(battle.enemyParty)];
  const foe = battle.playerParty[activeIndex(battle.playerParty)];
  let best = 0;
  let bestDmg = -1;
  me.moves.forEach((id, slot) => {
    const dmg = damage(me, foe, content.moves[id]);
    if (dmg > bestDmg) { best = slot; bestDmg = dmg; }
  });
  return best;
}

export function takeTurn(content, battle, action) {
  const b = structuredClone(battle);
  if (b.over) return b;
  if (action.type === 'run') {
    if (!b.wild) return b;
    b.turn += 1;
    b.over = true;
    b.winner = 'fled';
    b.log.push({ turn: b.turn, actor: 'player', action: 'run' });
    return b;
  }
  const pi = activeIndex(b.playerParty);
  const ei = activeIndex(b.enemyParty);
  const pc = b.playerParty[pi];
  const ec = b.enemyParty[ei];
  if (!Number.isInteger(action.slot) || action.slot < 0 || action.slot >= pc.moves.length) {
    throw new RangeError(`no move slot ${String(action.slot)}`);
  }
  const pm = content.moves[pc.moves[action.slot]];
  const em = content.moves[ec.moves[enemyChoose(content, b)]];
  b.turn += 1;
  const sides = [
    { actor: 'player', mon: pc, move: pm, party: b.playerParty, foes: b.enemyParty },
    { actor: 'enemy', mon: ec, move: em, party: b.enemyParty, foes: b.playerParty },
  ];
  const pri = (s) => s.move.priority ?? 0;
  sides.sort((a, c) => {
    if (pri(a) !== pri(c)) return pri(c) - pri(a);
    if (a.mon.spd !== c.mon.spd) return c.mon.spd - a.mon.spd;
    return a.actor === 'player' ? -1 : 1;
  });
  for (const s of sides) {
    if (s.mon.hp <= 0) continue;
    const target = s.foes[activeIndex(s.foes)];
    const r = rngNext(b.rng);
    const hit = r * 100 < s.move.accuracy;
    const dmg = hit ? damage(s.mon, target, s.move) : 0;
    target.hp = Math.max(0, target.hp - dmg);
    b.log.push({ turn: b.turn, actor: s.actor, move: s.move.id, hit, damage: dmg, targetHp: target.hp });
  }
  if (activeIndex(b.enemyParty) === -1) { b.over = true; b.winner = 'player'; }
  else if (activeIndex(b.playerParty) === -1) { b.over = true; b.winner = 'enemy'; }
  return b;
}
