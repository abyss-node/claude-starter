import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe, counted, assertUnchanged } from './helpers.mjs';
import { SW, core } from './fixtures.mjs';
import { HIDDEN_SEEDS } from './scenario-15.mjs';

const each = (list, why) => counted(list, why.length, why.join('; ')).forEach((u, i) => assertUnchanged(u, why[i]));

test('Graded 15: Two players, one screen', () => {
  const o = observe('./scenario-15.mjs');

  // The stages, in order.
  {
    const s = o.stages;
    assert.equal(s.configAfter, s.configBefore, 'createDuel must not change its config');
    let { duel: d, view } = s.created;
    assert.equal(d.stage, 'handoff');
    assert.equal(d.who, 0);
    assert.deepEqual(d.queue, [0, 1]);
    assert.deepEqual(d.picks, [null, null]);
    assert.deepEqual(d.turnLog, []);
    assert.equal(d.battle.phase, 'choose');
    assert.equal(view.stage, 'handoff');
    assert.equal(view.who, 0);
    each(s.coverPicks, ['a pick during the cover screen', 'a pick by the other player during the cover screen']);
    ({ duel: d, view } = s.firstPick);
    assert.equal(d.stage, 'pick');
    assert.equal(d.who, 0);
    assert.deepEqual(view.actions, s.firstPick.legal);
    assert.equal(view.who, 0);
    each(s.firstBad, ['continuing from a pick', 'the wrong player picks', 'an illegal action', 'a snare outside a wild battle', 'a switch to the active creature']);
    d = s.picked.duel;
    assert.equal(d.stage, 'handoff');
    assert.equal(d.who, 1);
    assert.equal(s.picked.battle, s.picked.battleBefore, 'nothing is resolved after only one pick');
    each(s.secondCover, ['the first player picks twice', 'the second player picks during their cover screen']);
    ({ duel: d, view } = s.secondPick);
    assert.equal(d.stage, 'pick');
    assert.equal(d.who, 1);
    assert.deepEqual(view.actions, s.secondPick.legal);
    each(s.secondBad, ['the first player picks again in the second player turn', 'an illegal action by the second player']);
    ({ duel: d, view } = s.result);
    assert.equal(d.stage, 'result');
    assert.equal(d.who, null);
    assert.deepEqual(d.picks, [null, null], 'the picks are cleared once used');
    assert.equal(d.battle.turn, 2);
    assert.equal(d.battle.history.length, 1, 'resolved exactly once');
    // exactly the two picks
    assert.equal(s.result.battle, s.result.direct, 'the battle equals resolveTurn on the two picks');
    assert.deepEqual(d.turnLog, s.result.directLog);
    assert.deepEqual(view.log, s.result.directLog);
    assert.equal(view.stage, 'result');
    assertUnchanged(s.resultPick, 'a pick in the result stage');
    d = s.next.duel;
    assert.equal(d.stage, 'handoff');
    assert.equal(d.who, 0);
    assert.deepEqual(d.queue, [0, 1]);
    assert.deepEqual(d.picks, [null, null]);
  }

  // The first player's choice is invisible in everything shown before the turn resolves.
  counted(o.hidden, HIDDEN_SEEDS.length, 'duels tried with every first pick').forEach(({ choices, views }, i) => {
    const seed = HIDDEN_SEEDS[i];
    assert.ok(choices.length >= 5);
    counted(views, choices.length, `seed ${seed}: one run per first pick`);
    const ref = counted(views[0], 4, `seed ${seed}: views before the result`);
    views.slice(1).forEach((got, k) => {
      counted(got, 4, `seed ${seed}: views before the result`);
      got.forEach((view, j) => assert.equal(view, ref[j], `seed ${seed}: view ${j} before the result depends on the first pick ${JSON.stringify(choices[k + 1])}`));
    });
    assert.ok(JSON.parse(ref[3]).stage === 'pick' && JSON.parse(ref[3]).who === 1);
    assert.ok(JSON.parse(ref[2]).stage === 'handoff' && JSON.parse(ref[2]).who === 1);
  });

  // The replacement phase: only the side that needs to choose is asked.
  {
    const r = o.replace;
    assert.equal(r.result.duel.stage, 'result');
    assert.equal(r.result.duel.battle.phase, 'replace');
    assert.equal(r.asked.duel.stage, 'handoff');
    assert.equal(r.asked.duel.who, 1, 'only the side that must replace is asked');
    assert.deepEqual(r.asked.duel.queue, [1]);
    assert.deepEqual(r.picking.view.actions, [{ kind: 'switch', to: 1 }]);
    assertUnchanged(r.otherPicks, 'the other player picks during a replacement');
    assert.equal(r.replaced.duel.stage, 'result', 'one pick is enough');
    assert.equal(r.replaced.duel.battle.phase, 'choose');
    assert.deepEqual(core(r.replaced.duel.turnLog), [{ type: 'switch', side: 1, to: 1 }]);
    assert.equal(r.next.duel.who, 0);
    assert.deepEqual(r.next.duel.queue, [0, 1]);
  }
  // Both sides must replace: asked in turn, and the first choice stays hidden.
  {
    const { one, two, done } = o.bothReplace;
    for (const s of [one, two]) {
      assert.equal(s.asked.duel.battle.phase, 'replace');
      assert.deepEqual(s.asked.duel.battle.pending, [true, true]);
      assert.deepEqual(s.queued.duel.queue, [0, 1]);
      assert.equal(s.oneIn.duel.stage, 'handoff');
      assert.equal(s.oneIn.duel.who, 1);
      assert.equal(s.oneIn.duel.battle.phase, 'replace', 'not resolved until both have picked');
      assert.deepEqual(s.last.view.actions, [SW(1), SW(2)]);
    }
    counted(one.views, 4, 'views during a double replacement');
    assert.deepEqual(one.views, two.views, 'the first replacement choice shows nowhere before the second is made');
    assert.equal(done.duel.stage, 'result');
    assert.deepEqual(done.duel.turnLog.map((e) => [e.type, e.side, e.to]), [['switch', 0, 1], ['switch', 1, 2]]);
    assert.equal(done.duel.battle.phase, 'choose');
  }

  // To the end: stage over, who null, nothing left to continue.
  {
    const e = o.end;
    assert.equal(e.result.duel.battle.phase, 'over');
    assert.equal(e.result.duel.stage, 'result');
    assert.equal(e.over.duel.stage, 'over');
    assert.equal(e.over.duel.who, null);
    assert.equal(e.over.view.stage, 'over');
    assert.ok(Array.isArray(e.over.view.log));
    assertUnchanged(e.more, 'continuing a finished duel');
    assertUnchanged(e.pick, 'picking in a finished duel');
  }
});
