import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

const label = (v) => (typeof v === 'object' ? JSON.stringify(v) : String(v));

test('Graded 16: step returns the world, and inputs steer the top they are for, are clamped to -1..1, and count as 0 unless a finite number', () => {
  // Every row of inputs this check tries, named, so one probe plays them all: Top A's x, y, vx and vy after 20
  // ticks of the same row, in a world where only the inputs act (two small tops far apart, a flat floor, no
  // friction).
  const rows = {
    idle: undefined,
    xPos: [{ x: 1, y: 0 }, null],
    xNeg: [{ x: -1, y: 0 }, null],
    yPos: [{ x: 0, y: 1 }, null],
    yNeg: [{ x: 0, y: -1 }, null],
    one: [{ x: 1, y: 1 }, null],
    x3: [{ x: 3, y: 1 }, null],
    huge: [{ x: 1e9, y: 7 }, null],
    negOne: [{ x: -1, y: -1 }, null],
    negX3: [{ x: -3, y: -1 }, null],
    xOneYNeg: [{ x: 1, y: -1 }, null],
    xOneYNeg50: [{ x: 1, y: -50 }, null],
    xOneY0: [{ x: 1, y: 0 }, null],
    x0Y1: [{ x: 0, y: 1 }, null],
    bothNull: [null, null],
    empty: [{}, null],
    infX: [{ x: Infinity, y: 1 }, null],
  };
  const ramp = [0.25, 0.5, 0.75, 1];
  ramp.forEach((v) => { rows[`ramp ${v}`] = [{ x: v, y: v }, null]; rows[`negRamp ${-v}`] = [{ x: -v, y: -v }, null]; });
  const badX = [NaN, Infinity, -Infinity, '1', 'left', true, null, undefined, [1], {}];
  const badY = [NaN, Infinity, -Infinity, '1', 'up', true, false, null, undefined, [1], {}];
  badX.forEach((bad, i) => { rows[`x bad ${i}`] = [{ x: bad, y: 0 }, null]; });
  badY.forEach((bad, i) => {
    rows[`y bad ${i}`] = [{ x: 0, y: bad }, null];
    rows[`y bad ${i} beside x`] = [{ x: 1, y: bad }, null];
    rows[`x bad ${i} beside y`] = [{ x: bad, y: 1 }, null];
  });
  const names = Object.keys(rows);
  const got = ask('steerRuns', names.map((n) => rows[n]));
  const run = Object.fromEntries(names.map((n, i) => [n, got[i]]));
  const same = (g, want, why) => assert.deepEqual(g.map((v) => Number(v.toFixed(12))), want.map((v) => Number(v.toFixed(12))), why);

  const seen = ask('steerWorld');

  // step changes the world in place and returns that same world.
  assert.ok(seen.sameAfterInputs, 'step must return the world it was given (the same object)');
  assert.equal(seen.tick1, 1, 'step advances the world it was given by one tick');
  assert.ok(seen.sameWithoutInputs, 'step without inputs must also return the world it was given');
  assert.equal(seen.tick2, 2);

  // Which top, and which way: a positive x pushes towards +x, a positive y towards +y.
  const vxPos = run.xPos[2];
  const vxNeg = run.xNeg[2];
  const vyPos = run.yPos[3];
  const vyNeg = run.yNeg[3];
  assert.ok(vxPos > 0 && vxNeg < 0, `input x 1 must push towards +x and -1 towards -x (vx ${vxPos} and ${vxNeg})`);
  assert.ok(vyPos > 0 && vyNeg < 0, `input y 1 must push towards +y and -1 towards -y (vy ${vyPos} and ${vyNeg})`);
  assert.ok(seen.pair[0].vx === 0 && seen.pair[0].x === -0.3, 'the second entry of inputs steers the second top only; the first top must not move');
  assert.ok(seen.pair[1].vx > 0, 'the second entry of inputs must push the second top');

  // Clamped to -1..1: a bigger value pushes exactly as hard as 1 does.
  same(run.x3, run.one, 'input x 3 must be clamped to 1');
  same(run.huge, run.one, 'input x 1e9 and y 7 must be clamped to 1');
  same(run.negX3, run.negOne, 'input x -3 must be clamped to -1');
  same(run.xOneYNeg50, run.xOneYNeg, 'input y -50 must be clamped to -1');

  // Between 0 and 1 a bigger input pushes harder, up to the full push at 1.
  for (let k = 1; k < ramp.length; k++) {
    const [, , vx, vy] = run[`ramp ${ramp[k]}`];
    const [, , px, py] = run[`ramp ${ramp[k - 1]}`];
    assert.ok(vx > px && vy > py, 'inputs between 0 and 1 must push harder the bigger they are (0.25, 0.5, 0.75, 1)');
  }
  for (let k = 1; k < ramp.length; k++) {
    const [, , vx, vy] = run[`negRamp ${-ramp[k]}`];
    const [, , px, py] = run[`negRamp ${-ramp[k - 1]}`];
    assert.ok(vx < px && vy < py, 'inputs between 0 and -1 must push harder the bigger they are');
  }

  // A missing entry is no input for that top: it does not borrow another top's.
  const [shortA, shortB] = seen.short;
  assert.ok(shortA.vx > 0 && shortB.vx === 0 && shortB.vy === 0 && shortB.x === 0.3, 'an inputs array with one entry steers the first top only; the second top must not move');
  const [, lonelyB] = seen.lonely;
  assert.ok(lonelyB.vx === 0 && lonelyB.vy === 0 && lonelyB.x === 0.3, 'inputs[0] steers top 0 and no other: top 1 must not move');
  const [holeyA] = seen.holey;
  assert.ok(holeyA.vx === 0 && holeyA.x === -0.3, 'an undefined first entry means no input for top 0');

  // The same inputs steer just as hard late in a match as early: no step number stops them.
  same([seen.aged[0].vx, seen.aged[0].vy], [seen.young[0].vx, seen.young[0].vy], 'inputs steer a top as hard on tick 1500 as on tick 1');
  assert.ok(seen.aged[0].vx > 0 && seen.aged[1].vx < 0, 'inputs must still steer on tick 1500');

  // Anything that is not a finite number counts as 0 (it does not become 1, or throw).
  badX.forEach((bad, i) => {
    same(run[`x bad ${i}`], run.idle, `an x of ${label(bad)} (not a finite number) must count as 0`);
  });
  // The same for y, on its own and beside a valid x.
  badY.forEach((bad, i) => {
    same(run[`y bad ${i}`], run.idle, `a y of ${label(bad)} (not a finite number) must count as 0`);
    same(run[`y bad ${i} beside x`], run.xOneY0, `a y of ${label(bad)} must count as 0 and must not stop a valid x from steering`);
    same(run[`x bad ${i} beside y`], run.x0Y1, `an x of ${label(bad)} must count as 0 and must not stop a valid y from steering`);
  });
  same(run.infX, run.x0Y1, 'an x of Infinity counts as 0 and must not stop a valid y from steering');
  same(run.bothNull, run.idle, 'null entries mean no input');
  same(run.empty, run.idle, 'an empty input object means no input');
});
