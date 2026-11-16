// Lap logic through the pure advanceProgress(track, progress, from, to).
// Paths are the grader's own polylines, walked one segment per call in a process of its own (scenarios.mjs), where
// every call gets frozen copies of the progress and both points: an advanceProgress that changes what it was given
// throws there, and the scenario hands the message back as `frozen`.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { scenario } from '../../probe.mjs';

const S = new URL('./scenarios.mjs', import.meta.url);
const run = (name, seed) => scenario(S, name, [seed]);

function notFrozen(res) {
  assert.equal(res.frozen, null, `advanceProgress must not change what it is given (${res.frozen})`);
  return res;
}

for (const [label, seed] of [['fixed track', null], ['seed 2024', 2024]]) {
  test(`a full lap through every checkpoint counts, two laps count two (${label})`, () => {
    const { one, two, part } = run('progressLaps', seed);
    notFrozen(one);
    assert.equal(one.lap, 1, `one lap round the centreline should give lap 1, got ${one.lap}`);
    assert.equal(one.next, 1, `after a lap the next checkpoint should be 1, got ${one.next}`);
    notFrozen(two);
    assert.equal(two.lap, 2, `two laps should give lap 2, got ${two.lap}`);
    notFrozen(part);
    assert.deepEqual({ lap: part.lap, next: part.next }, { lap: 0, next: 3 }, 'after passing gates 1 and 2 the next checkpoint should be 3');
  });

  test(`a shortcut to the finish line does not count (${label})`, () => {
    // Drive past gates 1 and 2, cut straight across to just before the line, cross it.
    const prog = notFrozen(run('progressShortcut', seed));
    assert.equal(prog.lap, 0, `crossing the line after skipping checkpoints counted a lap (lap ${prog.lap})`);
  });

  // Every gate in turn, the last one included: a lap that is missing only the checkpoint before the finish line is still no lap.
  test(`going round the outside of any one checkpoint does not count (${label})`, () => {
    const rounds = run('progressOutside', seed);
    assert.ok(rounds.length >= 4, `only ${rounds.length} gates were tried`);
    for (const prog of rounds) {
      notFrozen(prog);
      assert.equal(prog.lap, 0, `a lap that missed checkpoint ${prog.k} of ${prog.gates} counted (lap ${prog.lap})`);
      assert.equal(prog.next, prog.k, `progress should still wait for checkpoint ${prog.k}, got next=${prog.next}`);
    }
  });

  test(`driving the loop backwards does not count (${label})`, () => {
    const prog = notFrozen(run('progressBackwards', seed));
    assert.equal(prog.lap, 0, `a backwards lap counted (lap ${prog.lap})`);
  });
}
