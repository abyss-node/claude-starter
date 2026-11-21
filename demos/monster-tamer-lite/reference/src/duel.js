import { createBattle, legalActions, isLegalAction, resolveTurn, activeOf } from './battle.js';

const pickers = (battle) => [0, 1].filter((side) => legalActions(battle, side).length > 0);

export function createDuel(config) {
  const battle = createBattle(config);
  const queue = pickers(battle);
  return { battle, stage: 'handoff', who: queue[0], queue, picks: [null, null], turnLog: [] };
}

export function duelContinue(duel) {
  if (duel.stage === 'handoff') {
    duel.stage = 'pick';
  } else if (duel.stage === 'result') {
    if (duel.battle.phase === 'over') {
      duel.stage = 'over';
      duel.who = null;
    } else {
      duel.queue = pickers(duel.battle);
      duel.picks = [null, null];
      duel.who = duel.queue[0];
      duel.stage = 'handoff';
    }
  } else {
    throw new Error(`cannot continue from stage ${duel.stage}`);
  }
  return duel;
}

export function duelPick(duel, who, action) {
  if (duel.stage !== 'pick') throw new Error(`nobody is picking in stage ${duel.stage}`);
  if (who !== duel.who) throw new Error(`it is not player ${who + 1}'s pick`);
  if (!isLegalAction(duel.battle, who, action)) throw new Error('that action is not legal');
  duel.picks[who] = JSON.parse(JSON.stringify(action));
  duel.queue.shift();
  if (duel.queue.length > 0) {
    duel.who = duel.queue[0];
    duel.stage = 'handoff';
  } else {
    const before = duel.battle.log.length;
    resolveTurn(duel.battle, duel.picks);
    duel.turnLog = duel.battle.log.slice(before);
    duel.picks = [null, null];
    duel.who = null;
    duel.stage = 'result';
  }
  return duel;
}

function teams(battle) {
  return battle.sides.map((s, side) => ({
    name: s.name,
    creatures: s.team.map((c, i) => ({
      name: c.name, type: c.type, level: c.level, hp: c.hp, maxHp: c.maxHp,
      status: c.status ? c.status.kind : null, active: i === s.active,
    })),
  }));
}

// Everything a screen may show right now. Before the turn resolves it never depends on what anyone has chosen.
export function duelView(duel) {
  const b = duel.battle;
  const base = { stage: duel.stage, turn: b.turn, names: b.sides.map((s) => s.name) };
  if (duel.stage === 'handoff') return { ...base, who: duel.who };
  if (duel.stage === 'pick') {
    return {
      ...base, who: duel.who, teams: teams(b), actions: legalActions(b, duel.who),
      picked: duel.picks.map((p) => p !== null),
    };
  }
  if (duel.stage === 'result') return { ...base, teams: teams(b), log: duel.turnLog };
  return { ...base, teams: teams(b), log: duel.turnLog, winner: b.winner };
}

export { activeOf };
