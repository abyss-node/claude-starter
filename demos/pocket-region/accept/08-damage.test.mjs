import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { ask } from './ask.mjs';

// species, level, maxHp, atk, def, spd (the brief's formulas worked by hand for the fixture's species)
const STATS = [
  ['pup', 1, 15, 10, 9, 8],
  ['pup', 5, 35, 30, 25, 20],
  ['pup', 8, 50, 45, 37, 29],
  ['pup', 100, 510, 505, 405, 305],
  ['pool', 4, 34, 23, 25, 15],
  ['rockling', 6, 52, 8, 41, 8],
];

// attacker type, attack, defender type, defence, move type, power, damage, why
const DAMAGE = [
  ['ember', 50, 'moss', 40, 'plain', 40, 52, 'neutral, no same-type bonus: 40*50/40=50, +2'],
  ['plain', 50, 'moss', 40, 'plain', 40, 78, 'same-type bonus: 52*3/2'],
  ['ember', 50, 'moss', 40, 'ember', 40, 156, 'same type and super effective: 52 -> 78 -> 156'],
  ['plain', 50, 'brine', 40, 'ember', 40, 26, 'resisted: brine beats ember, 52/2'],
  ['ember', 50, 'ember', 40, 'moss', 40, 26, 'resisted: ember beats moss'],
  ['plain', 50, 'ember', 40, 'brine', 40, 104, 'super effective: brine beats ember, 52*2'],
  ['plain', 50, 'moss', 40, 'brine', 40, 26, 'moss beats brine, so a brine move into moss is resisted'],
  ['plain', 50, 'brine', 40, 'moss', 40, 104, 'moss into brine is super effective'],
  ['plain', 50, 'plain', 40, 'ember', 40, 52, 'ember into plain is neutral'],
  ['moss', 50, 'ember', 40, 'plain', 40, 52, 'plain into anything is neutral'],
  ['ember', 50, 'plain', 40, 'moss', 40, 52, 'moss into plain is neutral'],
  ['ember', 33, 'plain', 40, 'plain', 45, 39, 'rounding: 45*33/40 = 37 (floored), +2 = 39'],
  ['plain', 33, 'plain', 40, 'plain', 45, 58, 'floor(39*3/2)'],
  ['ember', 33, 'ember', 40, 'moss', 45, 19, 'floor(39/2)'],
  ['moss', 33, 'ember', 40, 'moss', 45, 29, 'same-type first (58), then resisted: floor(58/2), not floor(39/2)*3/2'],
  ['moss', 33, 'brine', 40, 'moss', 45, 116, 'same-type 58, then x2'],
  ['ember', 7, 'plain', 10, 'plain', 14, 11, 'the division floors before the +2: floor(98/10)=9, +2'],
  ['ember', 1, 'plain', 200, 'plain', 10, 2, 'floor(10/200)=0, +2'],
  ['plain', 99, 'plain', 1, 'plain', 0, 0, 'power 0 does no damage, whatever the rest'],
  ['ember', 99, 'moss', 1, 'ember', 0, 0, 'power 0 does no damage, whatever the rest'],
];

test('Graded 8: makeCreature gives the exact stats and copies its moves; damage is exact for the same-type bonus, types, floors and power 0', () => {
  const c = fixture();
  const seen = ask('./sc-battle.mjs', 'stats', STATS.map(([id, level]) => [id, level]));
  STATS.forEach(([id, level, maxHp, atk, def, spd], i) => {
    const m = seen.made[i];
    const sp = c.species[id];
    assert.deepEqual(
      { species: m.species, name: m.name, type: m.type, level: m.level, hp: m.hp, maxHp: m.maxHp, atk: m.atk, def: m.def, spd: m.spd, moves: m.moves },
      { species: id, name: sp.name, type: sp.type, level, hp: maxHp, maxHp, atk, def, spd, moves: sp.moves },
      `${id} at level ${level}`,
    );
  });
  assert.equal(seen.sameArray, false, 'the move list is a copy');
  assert.equal(seen.pushed, true, 'the copy can be changed');
  assert.deepEqual(seen.speciesMoves, ['jab', 'flare'], 'changing the copy leaves the species alone');

  // damage(attacker, defender, move) = floor(power * atk / def) + 2, then x3/2 (floored) when the move's type is
  // the attacker's type, then x2 when the move's type beats the defender's, or /2 (floored) when the defender's
  // type beats the move's (ember beats moss, moss beats brine, brine beats ember; plain beats and loses to nothing)
  const d = ask('./sc-battle.mjs', 'damages', DAMAGE.map((row) => row.slice(0, 6)));
  DAMAGE.forEach(([, , , , , , want, why], i) => assert.equal(d.values[i], want, why));
  assert.equal(d.frozenInputs, 63, 'floor(1200/30)+2 = 42, same type: 63, with frozen inputs');
});
