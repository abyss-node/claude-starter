import { test } from 'node:test';
import assert from 'node:assert/strict';
import { notPlain, stable } from './helpers.mjs';
import { ask } from './ask.mjs';

test('Graded 16: new game, talking, ignored inputs in every mode, battles ending, blackout, items, and purity', () => {
  const o = ask('./sc-game.mjs', 'loop');

  // newGame: every field, copies not aliases, plain data
  const g0 = o.g0.game;
  assert.deepEqual(g0.player, { map: 'town', x: 4, y: 3, facing: 'up' });
  assert.deepEqual(g0.flags, {});
  assert.deepEqual(g0.inventory, { tag: 1 });
  assert.deepEqual(g0.party, [o.g0.pup5]);
  assert.equal(o.g0.rng, o.g0.expectedRng);
  assert.equal(g0.mode, 'world');
  assert.equal(g0.dialogue, null);
  assert.equal(g0.battle, null);
  assert.equal(notPlain(o.g0.kinds), null);
  assert.deepEqual(o.startInventoryAfter, { tag: 1 }, 'the content is not shared with the game');
  assert.notEqual(o.seeds[0], o.seeds[1], 'the seed matters');
  assert.equal(o.ended.fresh, false);
  assert.equal(o.ended.set, true);
  assert.equal(o.ended.falseFlag, false);
  assert.deepEqual(o.ended.notTrue, [false, false, false, false, false], 'only true sets a flag');

  // step is pure: a new game back, the one given untouched (frozen in the scenario), and the result is plain data
  assert.equal(o.pure.length, 9);
  for (const { input, newObject, kinds } of o.pure) {
    assert.equal(newObject, true, `${input}: a new object`);
    assert.equal(notPlain(kinds), null, `${input}: plain data`);
  }

  // inputs a mode does not take change nothing, in the world, in a conversation, in a battle, with items refused
  assert.ok(o.same.length > 100);
  for (const { why, before, after } of o.same) assert.equal(after, before, why);

  // movement: turning, walking, and a wall
  assert.deepEqual(o.moves, [
    { map: 'town', x: 3, y: 3, facing: 'left' },
    { map: 'town', x: 3, y: 2, facing: 'up' },
    { map: 'town', x: 3, y: 1, facing: 'up' },
  ]);
  assert.equal(o.turnChanges, true, 'turning is a change');
  assert.deepEqual(o.wallStop, { map: 'town', x: 3, y: 1, facing: 'up' });

  // talking: only to an npc on the tile faced
  assert.equal(o.talk.mode, 'dialogue');
  assert.deepEqual(o.talk.dialogue, { tree: 'sage', view: { node: 'hi', text: 'Hello', choices: ['Open the way', 'Just passing'], ended: false, battle: null } });
  assert.deepEqual(o.talk.player, o.freshPlayer);
  // the first node's own effects apply when the talk starts
  assert.equal(o.chiefAfterWin.mode, 'dialogue');
  assert.equal(o.chiefAfterWin.flags.the_end, true, 'entering the node set the flag');
  assert.equal(o.chiefAfterWin.dialogue.tree, 'chief');
  assert.equal(o.chiefAfterWin.dialogue.view.node, 'thanks');
  // a tree whose start has no match: nothing happens
  assert.equal(o.noStart.after, o.noStart.before);

  // in a conversation: the sage's first node has two choices
  assert.equal(o.bye.mode, 'dialogue');
  assert.deepEqual(o.bye.view, { node: 'bye', text: 'Bye', choices: [], ended: false, battle: null });
  assert.equal(o.byeOut.mode, 'world');
  assert.equal(o.byeOut.dialogue, null);
  assert.equal(o.byeOut.flags, '{}');
  assert.deepEqual(o.open.flags, { asked: true, pass: true });
  assert.deepEqual(o.open.inventory, { tag: 1, salve: 2 });
  assert.equal(o.open.dialogue.view.node, 'open');
  assert.deepEqual(o.open.player, o.freshPlayer, 'while talking the player does not walk');
  assert.equal(o.finished.mode, 'world');
  assert.equal(o.finished.dialogue, null);
  assert.deepEqual(o.finished.inventory, { tag: 1, salve: 2 });
  assert.equal(o.again, 'done', 'talking again after the flag: the other start entry');

  // a conversation that ends in a battle: one draw for the battle's seed
  assert.equal(o.fightTalk.node, 'fight');
  assert.equal(o.fightTalk.mode, 'dialogue');
  const f = o.battleStart.game;
  assert.equal(f.mode, 'battle');
  assert.equal(f.dialogue, null);
  assert.equal(f.battle.wild, false);
  assert.equal(f.battle.over, false);
  assert.equal(f.battle.turn, 0);
  assert.deepEqual(f.battle.enemyParty, [o.battleStart.rockling6]);
  assert.deepEqual(f.battle.playerParty, f.party);
  assert.equal(f.battle.winFlag, 'chief_beaten');
  assert.equal(stable(f.battle.rng), o.battleStart.expectedRng, 'the battle is seeded from the one draw');
  assert.equal(stable(f.rng), o.battleStart.oneDraw, 'exactly one draw');
  assert.equal(notPlain(o.battleStart.kinds), null);

  // winning with two jabs: the chief hits back once, the flag is set, hp carries over
  const { one, win } = o;
  assert.equal(one.mode, 'battle');
  assert.equal(one.battle.turn, 1);
  assert.equal(one.battle.enemyParty[0].hp, 52 - 31);
  assert.equal(one.battle.playerParty[0].hp, 35 - 21);
  assert.equal(one.party[0].hp, 35, 'the party only changes when the battle is over');
  assert.equal(win.mode, 'world');
  assert.equal(win.battle, null);
  assert.equal(win.flags.chief_beaten, true);
  assert.equal(win.party[0].hp, 14, 'the damage taken stays');
  assert.equal(win.party[0].maxHp, 35);
  assert.deepEqual(win.player, { map: 'keep', x: 3, y: 2, facing: 'right' });
  assert.deepEqual(win.inventory, { tag: 1 });
  // flare is move 1: one hit finishes it before the chief can act
  assert.equal(o.quick.mode, 'world');
  assert.equal(o.quick.party[0].hp, 35);
  assert.equal(o.quick.flags.chief_beaten, true);
  // the talk afterwards ends the game
  assert.equal(o.end.flag, true);
  assert.equal(o.end.ended, true);
  assert.equal(o.end.mode, 'world');

  // losing: a blackout back at the start, the party healed, flags and items kept
  assert.equal(o.beforeBlackout, 'battle');
  assert.equal(o.lost.mode, 'world');
  assert.equal(o.lost.battle, null);
  assert.deepEqual(o.lost.player, { map: 'town', x: 4, y: 3, facing: 'up' });
  assert.equal(o.lost.party[0].hp, 35, 'healed at the start');
  assert.deepEqual(o.lost.flags, { pass: true }, 'no win flag, nothing else lost');
  assert.deepEqual(o.lost.inventory, { tag: 1, salve: 3 });
  // with a second creature standing, the battle goes on instead
  assert.equal(o.mid.mode, 'battle');
  assert.equal(o.mid.battle.playerParty[0].hp, 0);
  assert.equal(o.mid.player.map, 'keep');

  // a wild battle: running leaves it with hp kept, winning sets no flag
  assert.equal(o.enc, 'battle');
  assert.equal(o.ran.mode, 'world');
  assert.equal(o.ran.battle, null);
  assert.equal(o.ran.hp, 20);
  assert.deepEqual(o.ran.player, { map: 'wild', x: 1, y: 1, facing: 'up' });
  assert.equal(o.ran.rng, o.ran.encRng, 'running does not draw');
  assert.deepEqual(o.ran.flags, {});
  assert.equal(o.killed.mode, 'world');
  assert.deepEqual(o.killed.flags, {}, 'a wild win has no flag');
  assert.equal(o.killed.hp, 20);

  // items from the world: heal, revive, and refusals (the refusals are in the list of unchanged games above)
  assert.equal(o.heal.hp, 25);
  assert.deepEqual(o.heal.inventory, { tag: 1, salve: 1, spark: 1 });
  assert.equal(o.revive.hp, Math.floor(o.revive.maxHp / 2));
  assert.deepEqual(o.revive.inventory, { tag: 1, salve: 2 });
  assert.equal(o.busyMode, 'dialogue');

  // determinism: the same seed and inputs, the same game; the clocks were off the whole time
  assert.equal(o.determinism[0], o.determinism[1]);
});
