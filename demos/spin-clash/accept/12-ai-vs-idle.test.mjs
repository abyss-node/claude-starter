import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

const SEEDS = 20;
const TICK_BOUND = 900; // 15 seconds of game time
const NEEDED = 12;

test('Graded 12: the computer opponent beats an idle opponent in most matches within 900 ticks', () => {
  const matches = ask('soloWinners', 'idle', SEEDS, TICK_BOUND);
  assert.equal(matches.length, SEEDS, 'setup: one match per seed');
  const outcomes = matches.map(({ winner }) => (winner === null ? '-' : winner === -1 ? 'D' : winner === 1 ? 'W' : 'L'));
  const wins = matches.filter(({ winner }) => winner === 1).length;
  assert.ok(wins >= NEEDED,
    `Top B (the computer) won ${wins} of ${SEEDS} seeded matches against an idle Top A within ${TICK_BOUND} ticks; it needs ${NEEDED}. Per seed 1..${SEEDS}: ${outcomes.join('')} (W won, L lost, D draw, - nobody yet)`);
});
