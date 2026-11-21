import { createRng, nextFloat } from './rng.js';
import { STATUS_TURNS } from './data.js';
import { calcDamage, effectiveSpeed, attemptCatch } from './rules.js';

const clone = (v) => JSON.parse(JSON.stringify(v));
const alive = (c) => c.hp > 0;

export function activeOf(battle, side) {
  const s = battle.sides[side];
  return s.team[s.active];
}

export function createBattle(config) {
  const sides = config.sides.map((s) => {
    const team = clone(s.team);
    const first = team.findIndex(alive);
    if (first === -1) throw new Error(`side ${s.name} has no creature that can fight`);
    return { name: String(s.name), team, active: first };
  });
  const seed = config.seed === undefined ? 1 : config.seed;
  return {
    seed,
    turn: 1,
    phase: 'choose',
    wild: !!config.wild,
    snares: config.snares === undefined ? 0 : config.snares,
    rng: createRng(seed),
    sides,
    pending: [false, false],
    winner: null,
    caught: false,
    log: [],
    history: [],
  };
}

export function legalActions(battle, side) {
  if (battle.phase === 'over') return [];
  const s = battle.sides[side];
  const switches = [];
  s.team.forEach((c, i) => {
    if (i !== s.active && alive(c)) switches.push({ kind: 'switch', to: i });
  });
  if (battle.phase === 'replace') return battle.pending[side] ? switches : [];
  const actions = [];
  s.team[s.active].moves.forEach((_, slot) => actions.push({ kind: 'move', slot }));
  actions.push(...switches);
  if (battle.wild && side === 0 && battle.snares > 0) actions.push({ kind: 'snare' });
  return actions;
}

function sameAction(a, b) {
  if (!a || !b || a.kind !== b.kind) return false;
  if (a.kind === 'move') return a.slot === b.slot;
  if (a.kind === 'switch') return a.to === b.to;
  return true;
}

export function isLegalAction(battle, side, action) {
  return legalActions(battle, side).some((a) => sameAction(a, action));
}

function normalise(action) {
  if (action === null || action === undefined) return null;
  if (action.kind === 'move') return { kind: 'move', slot: action.slot };
  if (action.kind === 'switch') return { kind: 'switch', to: action.to };
  if (action.kind === 'snare') return { kind: 'snare' };
  return { kind: action.kind };
}

function faint(battle, side) {
  const c = activeOf(battle, side);
  c.hp = 0;
  c.status = null;
  battle.log.push({ type: 'faint', side });
}

function doSwitch(battle, side, to) {
  battle.sides[side].active = to;
  battle.log.push({ type: 'switch', side, to });
}

function doMove(battle, side, slot) {
  const user = activeOf(battle, side);
  if (!alive(user)) return;
  if (user.status && user.status.kind === 'daze') {
    battle.log.push({ type: 'skip', side, reason: 'daze' });
    return;
  }
  const move = user.moves[slot];
  battle.log.push({ type: 'move', side, move: move.id });
  const foeSide = 1 - side;
  const foe = activeOf(battle, foeSide);
  if (move.accuracy < 100 && !(nextFloat(battle.rng) * 100 < move.accuracy)) {
    battle.log.push({ type: 'miss', side, move: move.id });
    return;
  }
  if (move.power > 0) {
    const amount = calcDamage(user, foe, move);
    foe.hp = Math.max(0, foe.hp - amount);
    battle.log.push({ type: 'damage', side: foeSide, amount, hp: foe.hp, cause: 'move' });
    if (foe.hp === 0) faint(battle, foeSide);
  }
  if (move.status && alive(foe) && foe.status === null) {
    if (move.status.chance >= 100 || nextFloat(battle.rng) * 100 < move.status.chance) {
      foe.status = { kind: move.status.kind, turns: STATUS_TURNS[move.status.kind] };
      battle.log.push({ type: 'status', side: foeSide, kind: move.status.kind });
    }
  }
}

function endOfTurn(battle) {
  for (const side of [0, 1]) {
    const c = activeOf(battle, side);
    if (alive(c) && c.status && c.status.kind === 'scorch') {
      const amount = Math.max(1, Math.floor(c.maxHp / 8));
      c.hp = Math.max(0, c.hp - amount);
      battle.log.push({ type: 'damage', side, amount, hp: c.hp, cause: 'scorch' });
      if (c.hp === 0) faint(battle, side);
    }
  }
  for (const side of [0, 1]) {
    const c = activeOf(battle, side);
    if (alive(c) && c.status) {
      c.status.turns -= 1;
      if (c.status.turns <= 0) {
        battle.log.push({ type: 'cured', side, kind: c.status.kind });
        c.status = null;
      }
    }
  }
}

function settle(battle) {
  const living = battle.sides.map((s) => s.team.some(alive));
  if (!living[0] || !living[1]) {
    battle.winner = living[0] ? 0 : living[1] ? 1 : -1;
    battle.phase = 'over';
    battle.pending = [false, false];
    battle.log.push({ type: 'end', winner: battle.winner });
    return;
  }
  battle.pending = [0, 1].map((side) => !alive(activeOf(battle, side)));
  battle.phase = battle.pending[0] || battle.pending[1] ? 'replace' : 'choose';
}

// Resolves one turn (phase 'choose') or one replacement (phase 'replace') in place and returns the battle.
export function resolveTurn(battle, choices) {
  if (battle.phase !== 'choose' && battle.phase !== 'replace') throw new Error(`cannot resolve a turn in phase ${battle.phase}`);
  const picks = [0, 1].map((side) => normalise(choices && choices[side]));
  for (const side of [0, 1]) {
    const legal = legalActions(battle, side);
    if (picks[side] === null) {
      if (legal.length > 0) throw new Error(`side ${side} must choose an action`);
    } else if (!legal.some((a) => sameAction(a, picks[side]))) {
      throw new Error(`side ${side} chose an action that is not legal`);
    }
  }
  battle.history.push(clone(picks));

  if (battle.phase === 'replace') {
    for (const side of [0, 1]) if (picks[side]) doSwitch(battle, side, picks[side].to);
    battle.pending = [false, false];
    battle.phase = 'choose';
    return battle;
  }

  battle.log.push({ type: 'turn', n: battle.turn });
  for (const side of [0, 1]) if (picks[side] && picks[side].kind === 'switch') doSwitch(battle, side, picks[side].to);

  if (picks[0] && picks[0].kind === 'snare') {
    battle.snares -= 1;
    const success = attemptCatch(activeOf(battle, 1), () => nextFloat(battle.rng));
    battle.log.push({ type: 'snare', side: 0, success });
    if (success) {
      battle.caught = true;
      battle.winner = 0;
      battle.phase = 'over';
      battle.log.push({ type: 'end', winner: 0 });
      return battle;
    }
  }

  const movers = [0, 1].filter((side) => picks[side] && picks[side].kind === 'move');
  let order = movers;
  if (movers.length === 2) {
    const s0 = effectiveSpeed(activeOf(battle, 0));
    const s1 = effectiveSpeed(activeOf(battle, 1));
    if (s0 > s1) order = [0, 1];
    else if (s1 > s0) order = [1, 0];
    else order = nextFloat(battle.rng) < 0.5 ? [0, 1] : [1, 0];
  }
  for (const side of order) doMove(battle, side, picks[side].slot);

  endOfTurn(battle);
  battle.turn += 1;
  settle(battle);
  return battle;
}
