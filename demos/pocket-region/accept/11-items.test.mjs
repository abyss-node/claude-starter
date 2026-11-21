import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './ask.mjs';

test('Graded 11: counts, adding and removing; heal and revive apply once; every failure changes nothing and gives its reason', () => {
  const o = ask('./sc-battle.mjs', 'items');

  // counts
  assert.deepEqual(o.counts, [2, 0, 0], 'a name every object inherits is not an item');
  assert.deepEqual(o.adds, [{ salve: 3, tag: 1 }, { salve: 7, tag: 1 }, { salve: 2, tag: 1, spark: 2 }]);
  assert.deepEqual(o.removes.removedOne, { salve: 1, tag: 1 });
  assert.deepEqual(o.removes.removedTwo, { tag: 1 }, 'a count of 0 leaves no key at all');
  assert.equal(o.removes.tagKey, false);
  for (const { id, n, error } of o.shortfalls) assert.equal(error, 'RangeError', `removing ${n} of ${id}`);
  assert.deepEqual(o.invAfter, { salve: 2, tag: 1 });

  // heal: adds the amount (15) to the target, up to its maximum, uses one item
  let r = o.heal1;
  assert.equal(r.ok, true);
  assert.equal(r.reason, null);
  assert.deepEqual(r.inventory, { salve: 1 });
  assert.deepEqual(r.party.map((m) => m.hp), [10, 20], 'only the target is healed');
  r = o.heal2.r;
  assert.equal(r.party[0].hp, 30, 'healing stops at the maximum');
  assert.deepEqual(r.inventory, {}, 'the last one leaves the inventory');
  assert.equal(o.heal2.key, false);
  assert.equal(o.heal3.party[0].hp, 30, 'exactly to the maximum');
  assert.equal(o.heal4.party[0].hp, 16);
  assert.equal(o.heal4.party[0].maxHp, 100);

  // revive: a fallen creature comes back with half its maximum hp, rounded down, at least 1
  assert.equal(o.revive1.ok, true);
  assert.equal(o.revive1.party[0].hp, 15);
  assert.equal(o.revive1.party[1].hp, 9);
  assert.deepEqual(o.revive1.inventory, { spark: 1 });
  assert.equal(o.revive2.party[0].hp, 1, 'at least 1 hp');
  assert.equal(o.revive3.party[0].hp, 20);
  assert.deepEqual(o.revive3.inventory, {});

  // the effect happens once: three uses of two items, and the third finds none
  assert.deepEqual(o.threeUses.results.map((u) => u.ok), [true, true, false]);
  assert.equal(o.threeUses.results[2].reason, 'none');
  assert.equal(o.threeUses.hp, 31);

  // failures: ok false, a reason, and everything exactly as it was
  const REASONS = {
    'full hp': 'full', 'fainted target': 'fainted', 'revive a living creature': 'alive', 'key item': 'key',
    'none held': 'none', 'unknown item': 'none', 'inherited name': 'none',
    'target below range': 'bad-target', 'target past range': 'bad-target', 'target not whole': 'bad-target', 'target as text': 'bad-target',
    'none held beats a bad target': 'none', 'key beats a bad target': 'key', 'bad target on a full-hp creature': 'bad-target',
  };
  assert.deepEqual(o.failures.map((f) => f.name), Object.keys(REASONS));
  for (const f of o.failures) {
    assert.equal(f.ok, false, `${f.name}: not ok`);
    assert.equal(f.reason, REASONS[f.name], `${f.name}: reason`);
    assert.equal(f.after, f.before, `${f.name}: nothing changed, nothing used up`);
  }
});
