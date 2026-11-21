import { legalActions, activeOf } from './battle.js';
import { calcDamage } from './rules.js';
import { nextFloat } from './rng.js';

// Reads the battle, never changes it. Its two draws come from a copy of the battle's random state,
// moved on by one draw per turn played so that it does not repeat itself while the state stands still.
export function chooseAction(battle, side) {
  const legal = legalActions(battle, side);
  if (legal.length === 0) return null;
  const probe = JSON.parse(JSON.stringify(battle.rng));
  for (let i = 0; i < battle.turn; i++) nextFloat(probe);
  const explore = nextFloat(probe) < 0.15;
  const draw = nextFloat(probe);
  const options = legal.filter((a) => a.kind !== 'snare');
  const moves = options.filter((a) => a.kind === 'move');
  if (explore || moves.length === 0) return options[Math.floor(draw * options.length)];
  const me = activeOf(battle, side);
  const foe = activeOf(battle, 1 - side);
  const score = (a) => (calcDamage(me, foe, me.moves[a.slot]) * me.moves[a.slot].accuracy) / 100;
  const best = Math.max(...moves.map(score));
  const top = moves.filter((a) => score(a) === best);
  return top[Math.floor(draw * top.length)];
}
