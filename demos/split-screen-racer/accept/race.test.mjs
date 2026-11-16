import { test } from 'node:test';
import assert from 'node:assert/strict';
import { scenario } from '../../probe.mjs';
import { assertFiniteAt, distToLoop } from './helpers.mjs';

const S = new URL('./scenarios.mjs', import.meta.url);
const run = (name, ...args) => scenario(S, name, args);

test('fixed timestep: DT is 1/TICK_HZ and stepRace advances one tick', () => {
  const d = run('raceBasics');
  assert.equal(d.TICK_HZ, 60, 'TICK_HZ must be 60');
  assert.ok(Math.abs(d.DT - 1 / 60) < 1e-12, 'DT must be 1/60');
  assert.equal(d.tick, 0);
  assert.equal(d.laps, 3, 'laps defaults to 3');
  assert.deepEqual(d.finishOrder, []);
  assert.deepEqual(d.kinds, ['car', 'bike']);
  for (const p of d.players) {
    assert.deepEqual(p, { lap: 0, next: 1, finished: false });
  }
  assert.equal(d.tickAfter, 1);
});

test('createRace: players start on the grid, with the documented fields and the given laps and track', () => {
  const d = run('raceCreated');
  assert.equal(d.laps, 2);
  assert.deepEqual(d.raceCenterline, d.givenCenterline, 'race.track must be the track that was passed in');
  assert.deepEqual(d.kinds, ['bike', 'car']);
  const spots = d.players.map((p) => d.grid.findIndex((g) => Math.hypot(g.x - p.x, g.y - p.y) < 1e-6 && Math.abs(g.heading - p.heading) < 1e-6));
  assert.ok(spots.every((i) => i >= 0), `players must start on grid poses; found grid indexes ${JSON.stringify(spots)}`);
  assert.notEqual(spots[0], spots[1], 'the two players must start on different grid poses');
  for (const p of d.players) {
    assert.equal(p.plainObject, true, 'each player must be a plain object, not an instance of a class');
    assert.equal(p.finishTick, null, 'finishTick starts as null');
    assert.equal(p.speed, 0, 'players start at rest');
    assert.deepEqual({ lap: p.lap, next: p.next, finished: p.finished }, { lap: 0, next: 1, finished: false });
  }
  assert.equal(d.solo.players, 1, 'a one-vehicle race has one player');
  assert.equal(d.solo.tickAfter, 1);
});

test('replay determinism: same seed and recorded inputs give the same hash and finish order', () => {
  const { recorded: a, replayed: b } = run('replayAi', 4242, 1, 12000);
  assert.equal(a.finishOrder.length, 2, `both AI players should finish 1 lap within 12000 ticks; finishOrder=${JSON.stringify(a.finishOrder)}`);
  assert.equal(b.hashType, 'string', 'hashRace must return a string');
  assert.deepEqual(b.hashes, a.hashes, 'replayed hashes diverged from the recorded run');
  assert.equal(b.finalHash, a.finalHash, 'final hash differs on replay');
  assert.deepEqual(b.finishOrder, a.finishOrder, 'finish order differs on replay');
  const ticks = a.finishTicks;
  assert.ok(ticks.every((t, k) => k === 0 || t >= ticks[k - 1]), `finishOrder ${JSON.stringify(a.finishOrder)} does not follow finishTick ${JSON.stringify(ticks)}`);
  assert.ok(new Set(a.hashes).size > a.hashes.length * 0.9, 'hashRace barely changes while the race runs');

  // Random inputs for both players on the fixed track replay identically too.
  const random = run('replayRandom', 9, 3000);
  assert.ok(random.first.length > 0, 'random-input replay produced no hashes');
  assert.deepEqual(random.second, random.first, 'random-input replay diverged');
});

test('hash changes when one input changes', () => {
  const d = run('hashAfterInputs');
  assert.notEqual(d.other, d.base, 'one different steer input left the hash unchanged');
  assert.notEqual(d.seeded, d.base, 'a different track left the hash unchanged');
});

// hashRace has to move with every piece of race state, one at a time, and come back when the state does.
test('hash changes with each piece of race state and returns when the state is restored', () => {
  const d = run('hashPerState');
  assert.equal(d.again, d.base, 'hashRace must give the same string twice for the same state');
  for (const { what, changed, restored } of d.changes) {
    assert.notEqual(changed, d.base, `changing ${what} left the hash unchanged`);
    assert.equal(restored, d.base, `after undoing the change to ${what} the hash did not come back`);
  }
});

test('no NaN or Infinity over 20k ticks of random inputs, and vehicles stay inside the walls', () => {
  const d = run('abuse', 5, 20000);
  const { track, players } = d;
  const limit = track.width / 2 + track.verge + 1;
  let closest = Infinity;
  const [a, b] = d.kinds;
  const minSep = 0.75 * (d.radii[a] + d.radii[b]);
  for (let t = 0; t < 20000; t++) {
    assertFiniteAt(d, t);
    if (t % 10 === 0) {
      for (const [i, p] of players.entries()) {
        const dist = distToLoop(track.centerline, p.x[t], p.y[t]).dist;
        assert.ok(dist <= limit, `tick ${t}: player ${i} is ${dist.toFixed(1)} from the centreline, past the wall at ${limit - 1}`);
      }
    }
    const sep = Math.hypot(players[0].x[t] - players[1].x[t], players[0].y[t] - players[1].y[t]);
    closest = Math.min(closest, sep);
    assert.ok(sep >= minSep, `tick ${t}: vehicles overlap (${sep.toFixed(1)} apart, radii sum ${(minSep / 0.75).toFixed(1)})`);
  }
  assert.equal(d.tick, 20000);
});

test('vehicles do not overlap after a collision, and the lighter one moves more', () => {
  // Overlap depth is a share of the combined radii: from a deep push (about 10%) to a shallow one (90%),
  // from several directions, so a collision that only fires once the overlap is deep, or only along one axis, fails.
  const cases = [
    { gap: Math.hypot(2, 1), angle: Math.atan2(1, 2) },
    { share: 0.3, angle: 2.4 },
    { share: 0.5, angle: -0.7 },
    { share: 0.65, angle: 1.2 },
    { share: 0.8, angle: -2.5 },
    { share: 0.9, angle: 0.3 },
  ];
  // Both seatings are tried (car first, then bike first), so a push that favours one player number fails one of them.
  const { sum, runs } = run('collisions', [['car', 'bike'], ['bike', 'car']], cases);
  for (const { kinds, angle, gap, before, after } of runs) {
    const share = gap / sum;
    const sep = Math.hypot(after[0].x - after[1].x, after[0].y - after[1].y);
    const where = `${kinds.join(' + ')}, placed ${gap.toFixed(2)} apart (${(share * 100).toFixed(0)}% of the radii sum ${sum}, angle ${angle.toFixed(2)})`;
    assert.ok(sep >= 0.95 * sum, `${where}: after one tick the vehicles are ${sep.toFixed(2)} apart; overlapping vehicles must be pushed apart within one tick`);
    const moved = after.map((p, i) => Math.hypot(p.x - before[i].x, p.y - before[i].y));
    const car = kinds.indexOf('car');
    const bike = kinds.indexOf('bike');
    assert.ok(moved[bike] > moved[car], `${where}: the bike (lighter) moved ${moved[bike].toFixed(2)}, the car ${moved[car].toFixed(2)}; the lighter vehicle should move more`);
  }
});

// Both vehicles steer at each other at full throttle, so they stay in contact for most of the run.
test('vehicles that keep ramming each other never overlap by more than a quarter of their radii', () => {
  for (const seed of [null, 5]) {
    const { track, runs } = run('ramming', seed, [['car', 'bike'], ['bike', 'car'], ['car', 'car']], 1200);
    const limit = track.width / 2 + track.verge + 1;
    for (const r of runs) {
      let touching = 0;
      for (let t = 0; t < 1200; t++) {
        assertFiniteAt(r, t);
        const sep = Math.hypot(r.players[0].x[t] - r.players[1].x[t], r.players[0].y[t] - r.players[1].y[t]);
        const label = `${track.name}, ${r.kinds.join(' + ')}, tick ${t}`;
        assert.ok(sep >= 0.75 * r.sum, `${label}: vehicles overlap too much (${sep.toFixed(1)} apart, radii sum ${r.sum}; at most a quarter may overlap)`);
        if (sep <= 1.1 * r.sum) touching += 1;
        if (t % 10 === 0) {
          for (const [i, p] of r.players.entries()) {
            const d = distToLoop(track.centerline, p.x[t], p.y[t]).dist;
            assert.ok(d <= limit, `${label}: player ${i} is ${d.toFixed(1)} from the centreline, past the wall at ${limit - 1}`);
          }
        }
      }
      assert.ok(touching >= 100, `${track.name}, ${r.kinds.join(' + ')}: the vehicles were in contact on only ${touching} of 1200 ticks, so the overlap check was not really tested`);
    }
  }
});

function assertFinishedOnLastLap(who, o) {
  assert.equal(o.lap, o.laps, `player ${who} finished with lap ${o.lap}; with laps = ${o.laps} the race ends for a player when its lap count reaches ${o.laps}`);
  assert.equal(o.lapTick, o.tick, `player ${who}'s lap count reached ${o.laps} on tick ${o.lapTick}, but it was only marked finished on tick ${o.tick}`);
  assert.equal(o.finishTick, o.lapTick, `player ${who} completed its final lap on tick ${o.lapTick}, but finishTick is ${o.finishTick}`);
}

test('finish order follows who finished first, not player index, and a race ends on its last lap', () => {
  // Each order is tried, so listing by player number fails one of them and reversing fails the other.
  // The second order runs two laps, so ending a race after the first lap fails there and ending it a lap late fails the first.
  for (const [order, laps] of [[[1, 0], 1], [[0, 1], 2]]) {
    const d = run('finishOrderRun', order, laps);
    const [first, second] = order;
    assert.ok(d.first.finished, `player ${first} driven by the AI did not finish ${laps} lap(s) in 12000 ticks`);
    assertFinishedOnLastLap(first, d.first);
    assert.equal(d.first.idleFinished, false, 'the idle player cannot have finished');
    assert.deepEqual(d.first.finishOrder, [first], `only player ${first} has finished; finishOrder=${JSON.stringify(d.first.finishOrder)}`);
    assert.ok(d.second.finished, `player ${second} driven by the AI did not finish ${laps} lap(s) in 12000 more ticks`);
    assertFinishedOnLastLap(second, d.second);
    assert.ok(d.secondFinishTick > d.firstFinishTick, 'the second finisher has the later finishTick');
    assert.deepEqual(d.finishOrder, order, `player ${first} finished on tick ${d.firstFinishTick} and player ${second} on tick ${d.secondFinishTick}; finishOrder=${JSON.stringify(d.finishOrder)}`);
  }
});

// Each player is moved to its spot on the track carrying its full road speed, and held there every tick, so only
// the surface under it can change its speed (scenarios.mjs holdRuns).
test('off track slows both in a race, the bike more: stepRace uses the surface under each vehicle', () => {
  for (const seed of [null, 2024]) {
    const runs = [];
    for (const kind of ['car', 'bike']) {
      runs.push({ kinds: [kind], placements: ['road'], ticks: 120 }, { kinds: [kind], placements: ['verge'], ticks: 300 });
    }
    const d = run('holdRuns', seed, runs);
    const ratio = {};
    ['car', 'bike'].forEach((kind, k) => {
      const [road, verge] = [d.runs[2 * k], d.runs[2 * k + 1]];
      assert.ok(!road.noSpot && !verge.noSpot, `${d.name}: no point found at the distance wanted from the centreline`);
      const [rp, vp] = [road.players[0], verge.players[0]];
      const kept = rp.speeds[rp.speeds.length - 1] / rp.entry;
      assert.ok(kept >= 0.95, `${d.name}: the ${kind} on the road at full throttle fell to ${(kept * 100).toFixed(0)}% of its road speed`);
      const slowed = vp.speeds.findIndex((s) => s < 0.9 * vp.entry);
      assert.ok(slowed >= 0 && slowed < 120, `${d.name}: the ${kind} on the verge (${verge.offs[0].toFixed(0)} from the centreline) at full throttle kept ${((vp.speeds[119] / vp.entry) * 100).toFixed(0)}% of its road speed after 2 s; it must fall below 90%`);
      ratio[kind] = vp.speeds[vp.speeds.length - 1] / vp.entry;
    });
    assert.ok(ratio.bike < ratio.car, `${d.name}: after 5 s on the verge the bike keeps ${(ratio.bike * 100).toFixed(0)}% of its road speed and the car ${(ratio.car * 100).toFixed(0)}%; the bike should lose more`);
  }
});

// Each player gets the surface under its own wheels: one holds the road, the other the verge, in both seatings.
test('off track slows both in a race: each player gets the surface under itself, in either seating', () => {
  for (const seed of [null, 2024]) {
    const runs = [];
    for (const kinds of [['car', 'car'], ['car', 'bike'], ['bike', 'car'], ['bike', 'bike']]) {
      for (const vergeIdx of [0, 1]) {
        const placements = ['road', 'road'];
        placements[vergeIdx] = 'verge';
        runs.push({ kinds, placements, ticks: 120 });
      }
    }
    const d = run('holdRuns', seed, runs);
    d.runs.forEach((r) => {
      assert.ok(!r.noSpot, `${d.name}: no point found at the distance wanted from the centreline`);
      const vergeIdx = r.placements.indexOf('verge');
      const roadIdx = 1 - vergeIdx;
      const road = r.players[roadIdx];
      const side = r.players[vergeIdx];
      const where = `${d.name}, ${r.kinds.join(' + ')}, player ${vergeIdx} on the verge and player ${roadIdx} on the road`;
      const kept = road.speeds[119] / road.entry;
      assert.ok(kept >= 0.95, `${where}: the player on the road fell to ${(kept * 100).toFixed(0)}% of its road speed; each player must get the surface under itself`);
      const slowed = side.speeds.findIndex((v) => v < 0.9 * side.entry);
      assert.ok(slowed >= 0 && slowed < 120, `${where}: the player on the verge kept ${((side.speeds[119] / side.entry) * 100).toFixed(0)}% of its road speed after 2 s; it must fall below 90%`);
    });
  }
});

test('solo AI completes a lap within the tick bound on the fixed track and seeded tracks (car and bike)', () => {
  for (const seed of [null, 3, 11, 42]) {
    const d = run('soloLaps', seed);
    for (const r of d.runs) {
      assert.ok(r.finished, `${d.name}: AI ${r.kind} did not finish a lap within ${r.bound} ticks (lap ${r.lap}, next ${r.next})`);
      assert.deepEqual(r.finishOrder, [0]);
      assertFinishedOnLastLap(0, r);
    }
  }
});
