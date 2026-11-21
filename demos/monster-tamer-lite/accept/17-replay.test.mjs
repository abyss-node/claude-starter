import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted } from './helpers.mjs';
import { fnv1a } from './fixtures.mjs';
import { KNOWN, randomLogs, KINDS, SEEDS } from './scenario-17.mjs';

const J = (v) => JSON.stringify(v);
const WANT = ['741638a5', 'd9ecb823', 'fa3c7d99', '7f74cc39', '3fa75718', '04684771', '7616c164', '5f74b2a2'];

test('Graded 17: Replay', () => {
  const o = observe('./scenario-17.mjs');

  // hashLog: FNV-1a over the UTF-8 bytes of JSON.stringify(log), 8 lowercase hex digits.
  counted(o.known, KNOWN.length, 'hashLog of the known logs').forEach((got, i) => {
    assert.equal(got, WANT[i], `hashLog(${J(KNOWN[i])})`);
    assert.equal(fnv1a(J(KNOWN[i])), WANT[i], 'the test oracle itself');
  });
  const logs = randomLogs();
  counted(o.random, logs.length, 'hashLog of random logs').forEach((got, i) => assert.equal(got, fnv1a(J(logs[i])), `hashLog(${J(logs[i])})`));
  assert.notEqual(o.differ[0], o.differ[1]);
  assert.match(o.known[0], /^[0-9a-f]{8}$/);

  // Play battles with random or computer choices, then replay the history.
  const hashes = new Set();
  const battles = counted(o.battles, KINDS.length * SEEDS, 'played battles');
  let n = 0;
  for (const kind of KINDS) {
    for (let seed = 1; seed <= SEEDS; seed++) {
      const b = battles[n++];
      assert.equal(b.kind, kind);
      assert.equal(b.seed, seed);
      assert.equal(b.phase, 'over', `${kind} seed ${seed} did not finish`);
      assert.equal(b.again, b.live, `${kind} seed ${seed}: replay differs from the live battle`);
      assert.equal(b.againHash, b.liveHash);
      assert.equal(b.historyAfter, b.historyBefore, 'replayBattle must not change the history it is given');
      assert.equal(b.ofCopies, b.live, 'a JSON copy of config and history replays the same');
      const len = b.historyLength;
      const wantK = [...new Set([0, 1, Math.floor(len / 2), len - 1])];
      assert.deepEqual(b.prefixes.map(([k]) => k), wantK);
      for (const [k, got] of b.prefixes) assert.equal(got, b.snapshots[k], `${kind} seed ${seed}: prefix of ${k} turns`);
      assert.equal(len, b.snapshots.length - 1, 'one history entry per resolved call');
      assert.equal(b.snapshots[b.snapshots.length - 1], b.live);
      if (kind === 'wild-random' && seed <= 3) assert.ok(b.snares <= 3);
      hashes.add(b.liveHash);
    }
  }
  assert.ok(hashes.size >= 20, `only ${hashes.size} different log hashes across 42 battles`);

  // Different seeds, same teams and choices policy: different logs somewhere.
  assert.ok(new Set(counted(o.bySeed, 12, 'battles by seed')).size >= 2, 'the seed does not change the battle at all');
  // Replaying the history from the same config reproduces the battle; an empty history replays to an empty log.
  assert.equal(o.again.replayed, o.again.live);
  assert.deepEqual(o.again.emptyLog, []);
});
