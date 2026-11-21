import { createBattle, resolveTurn } from './battle.js';

// FNV-1a, 32 bits, over the UTF-8 bytes of JSON.stringify(log); 8 lowercase hex digits.
export function hashLog(log) {
  const bytes = new TextEncoder().encode(JSON.stringify(log));
  let h = 0x811c9dc5;
  for (const b of bytes) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

export function replayBattle(config, history) {
  const battle = createBattle(config);
  for (const choices of history) resolveTurn(battle, choices);
  return battle;
}
