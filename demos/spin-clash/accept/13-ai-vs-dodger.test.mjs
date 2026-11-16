import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

const SEEDS = 20;
const TICK_BOUND = 1800; // 30 seconds of game time

test('Graded 13: the computer opponent does not always beat a dodging opponent', () => {
  const matches = ask('soloWinners', 'dodger', SEEDS, TICK_BOUND);
  assert.equal(matches.length, SEEDS, 'setup: one match per seed');
  const outcomes = matches.map(({ winner }) => (winner === null ? '-' : winner === -1 ? 'D' : winner === 1 ? 'W' : 'L'));
  const wins = matches.filter(({ winner }) => winner === 1).length;
  assert.ok(wins < SEEDS,
    `Top B (the computer) won all ${SEEDS} seeded matches against the dodging Top A within ${TICK_BOUND} ticks; a beatable opponent must fail at least once. Per seed 1..${SEEDS}: ${outcomes.join('')}`);
});
