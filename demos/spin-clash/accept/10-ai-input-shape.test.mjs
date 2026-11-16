import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clone } from './helpers.mjs';
import { ask } from './ask.mjs';

const valid = (out) => out && typeof out === 'object' && Number.isFinite(out.x) && Number.isFinite(out.y)
  && Math.abs(out.x) <= 1 && Math.abs(out.y) <= 1;

test('Graded 10: the computer opponent returns a valid input and leaves the world alone', () => {
  const seen = ask('aiShape');

  assert.ok(seen.ticks.length > 0, 'setup: the match ended before the computer was asked anything');
  for (const { t, before, after, answer } of seen.ticks) {
    assert.equal(after, before, `aiInput changed the world on tick ${t} (it may only read it)`);
    assert.ok(answer && typeof answer === 'object', `tick ${t}: aiInput must return {x, y}, got ${JSON.stringify(answer)}`);
    for (const k of ['x', 'y']) {
      assert.ok(Number.isFinite(answer[k]) && Math.abs(answer[k]) <= 1, `tick ${t}: input ${k} must be a number from -1 to 1, got ${answer[k]}`);
    }
  }

  // Awkward layouts must still give finite answers: the foe exactly at the centre, the computer exactly at the
  // centre, both on one spot, and the foe on the rim.
  assert.equal(seen.awkward.length, 5, 'setup: five awkward layouts');
  for (const { label, before, after, answers } of seen.awkward) {
    answers.forEach((out, idx) => {
      assert.ok(valid(out), `${label}: aiInput for top ${idx} must be {x, y} of finite numbers from -1 to 1, got ${JSON.stringify(out)}`);
    });
    assert.equal(after, before, `${label}: aiInput changed the world`);
  }

  // Cases with nothing to chase must still answer, not throw.
  assert.equal(seen.doneWinner, 1, 'setup: Top A should have rung out on tick 1');
  assert.equal(seen.nothing.length, 3, 'setup: three cases with nothing to steer against');
  // The winner of a finished match has no other top in play, a top that is out is not steered, and a lone top
  // has no one to chase: each is {x: 0, y: 0} by the brief.
  for (const { label, answer } of seen.nothing) {
    assert.ok(valid(answer), `aiInput for ${label} must still return a valid {x, y}, got ${JSON.stringify(answer)}`);
    assert.deepEqual(clone(answer), { x: 0, y: 0 }, `aiInput for ${label} has nothing to steer against: expected {x: 0, y: 0}, got ${JSON.stringify(answer)}`);
  }
});
