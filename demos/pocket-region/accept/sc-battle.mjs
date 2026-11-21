// Scenarios for checks 8 to 11 (stats and damage, turn order, battle flow, items). Run by demos/probe.mjs in a
// process of its own beside the workspace's code; they return what the code did, never a verdict.
import { stable, deepFreeze, attempt } from './helpers.mjs';
import { fixture, mon } from './fixture.mjs';

// ---- 8: stats and damage -------------------------------------------------------------------------------------
export async function stats({ load }, cases) {
  const { makeCreature } = await load('src/battle.js');
  const c = fixture();
  deepFreeze(c);
  const made = cases.map(([id, level]) => makeCreature(c, id, level));
  const m5 = makeCreature(c, 'pup', 5);
  const sameArray = m5.moves === c.species.pup.moves;
  const pushed = attempt(() => m5.moves.push('x'));
  return { made, sameArray, pushed: pushed.ok, speciesMoves: JSON.parse(JSON.stringify(c.species.pup.moves)) };
}

export async function damages({ load }, cases) {
  const { damage } = await load('src/battle.js');
  const mv = (type, power) => ({ id: 'm', name: 'M', type, power, accuracy: 100 });
  const values = cases.map(([atkType, atk, defType, def, moveType, power]) => damage(mon({ type: atkType, atk }), mon({ type: defType, def }), mv(moveType, power)));
  const a = deepFreeze(mon());
  const d = deepFreeze(mon());
  const frozenInputs = damage(a, d, deepFreeze(mv('plain', 40)));
  return { values, frozenInputs };
}

// ---- 9: turn order and chance --------------------------------------------------------------------------------
export async function turnOrder({ load }) {
  const { startBattle, takeTurn } = await load('src/battle.js');
  const { makeRng, rngNext } = await load('src/rng.js');
  const c = fixture();
  deepFreeze(c);
  const run = (p, e, seed = 1, slot = 0) => {
    const b = deepFreeze(startBattle(c, [p], [e], seed));
    return takeTurn(c, b, { type: 'move', slot });
  };
  const actors = (b) => b.log.map((l) => l.actor).join(',');
  const advanced = (seed, n) => { const r = makeRng(seed); for (let i = 0; i < n; i++) rngNext(r); return stable(r); };
  const o = {};

  o.order = [
    run(mon({ spd: 30 }), mon({ spd: 20, species: 'pool', type: 'brine' })),
    run(mon({ spd: 20 }), mon({ spd: 30, species: 'pool', type: 'brine' })),
    run(mon({ spd: 25 }), mon({ spd: 25, species: 'pool', type: 'brine' })),
    run(mon({ spd: 99, moves: ['jab'] }), mon({ spd: 1, moves: ['fast'] })),
    run(mon({ spd: 1, moves: ['fast'] }), mon({ spd: 99, moves: ['jab'] })),
    run(mon({ spd: 5, moves: ['fast'] }), mon({ spd: 9, moves: ['fast'] })),
  ].map(actors);

  o.logged = run(mon({ spd: 30, hp: 100, maxHp: 100, atk: 30, def: 30 }), mon({ spd: 20, hp: 100, maxHp: 100, atk: 40, def: 30 }));

  const strong = mon({ spd: 30, atk: 200, hp: 30 });
  const weak = mon({ spd: 20, hp: 5, maxHp: 5 });
  const b1 = run(strong, weak, 3);
  o.playerKnocksOut = { log: b1.log, playerHp: b1.playerParty[0].hp, enemyHp: b1.enemyParty[0].hp, rng: stable(b1.rng), oneDraw: advanced(3, 1) };
  const b2 = run(mon({ spd: 20, hp: 5, maxHp: 5 }), mon({ spd: 30, atk: 200, hp: 30 }), 3);
  o.enemyKnocksOut = { actors: b2.log.map((l) => l.actor), playerHp: b2.playerParty[0].hp, enemyHp: b2.enemyParty[0].hp, rng: stable(b2.rng), oneDraw: advanced(3, 1) };

  o.draws = [1, 2, 3, 5, 8, 13].map((seed) => {
    const out = run(mon({ spd: 30, hp: 100, maxHp: 100, moves: ['jab'] }), mon({ spd: 20, hp: 100, maxHp: 100 }), seed);
    return { seed, rng: stable(out.rng), twoDraws: advanced(seed, 2) };
  });

  o.wobbly = [];
  for (let seed = 1; seed <= 40; seed++) {
    const out = run(mon({ spd: 30, hp: 200, maxHp: 200, moves: ['wobbly'] }), mon({ spd: 20, hp: 200, maxHp: 200, moves: ['wobbly'] }), seed);
    const r = makeRng(seed);
    const first = rngNext(r);
    const second = rngNext(r);
    o.wobbly.push({ seed, first, second, log: out.log, enemyHp: out.enemyParty[0].hp });
  }
  o.sure = [];
  for (let seed = 1; seed <= 30; seed++) {
    const out = run(mon({ hp: 500, maxHp: 500 }), mon({ hp: 500, maxHp: 500 }), seed);
    o.sure.push({ seed, hits: out.log.map((l) => l.hit) });
  }
  const dud = run(mon({ moves: ['dud'] }), mon());
  o.dud = { first: dud.log[0], enemyHp: dud.enemyParty[0].hp };

  const start = deepFreeze(startBattle(c, [mon({ hp: 900, maxHp: 900 })], [mon({ hp: 900, maxHp: 900 })], 4));
  let t = start;
  o.turns = [];
  for (let i = 1; i <= 3; i++) {
    t = takeTurn(c, t, { type: 'move', slot: 0 });
    o.turns.push({ i, turn: t.turn, logTurns: t.log.slice(-2).map((l) => l.turn), logLength: t.log.length });
  }
  o.startTurn = start.turn;
  o.startLogLength = start.log.length;
  return o;
}

// ---- 10: battle flow -----------------------------------------------------------------------------------------
export async function flow({ load }) {
  const { startBattle, takeTurn, activeIndex, enemyChoose } = await load('src/battle.js');
  const { makeRng } = await load('src/rng.js');
  const c = fixture();
  deepFreeze(c);
  const turn = (b, slot = 0) => takeTurn(c, deepFreeze(b), { type: 'move', slot });
  const o = {};

  o.active = [
    activeIndex([mon(), mon()]),
    activeIndex([mon({ hp: 0 }), mon(), mon()]),
    activeIndex([mon({ hp: 0 }), mon({ hp: 0 }), mon({ hp: 1 })]),
    activeIndex([mon({ hp: 0 }), mon({ hp: 0 })]),
    activeIndex([]),
  ];

  const pp = [mon({ name: 'A' })];
  const ep = [mon({ name: 'B' })];
  let b = startBattle(c, pp, ep, 77);
  const sameParty = b.playerParty === pp;
  const sameCreature = b.playerParty[0] === pp[0];
  pp[0].hp = 1;
  o.start = {
    battle: b, sameParty, sameCreature, afterChange: b.playerParty[0].hp, rng: stable(b.rng), expectedRng: stable(makeRng(77)),
    wildTrue: startBattle(c, [mon()], [mon()], 1, { wild: true }).wild,
    wildFalse: startBattle(c, [mon()], [mon()], 1, { wild: false }).wild,
  };

  b = startBattle(c, [mon({ atk: 200, spd: 30 })], [mon({ hp: 10, maxHp: 10 })], 1);
  const won = turn(b);
  const after = turn(won);
  o.won = { won, after: stable(after), wonStable: stable(won), sameObject: after === won, slot9: stable(turn(won, 9)) };
  b = startBattle(c, [mon({ hp: 10, maxHp: 10, spd: 1 })], [mon({ atk: 200 })], 1);
  o.lost = turn(b);

  const two = [mon({ name: 'first', hp: 5, maxHp: 5, spd: 1 }), mon({ name: 'second', moves: ['vine'], type: 'moss', spd: 1 })];
  b = startBattle(c, two, [mon({ atk: 200, spd: 50, moves: ['jab'] })], 9);
  o.t1 = turn(b);
  o.t2 = turn(o.t1);
  const eTwo = [mon({ hp: 10, maxHp: 10, spd: 1 }), mon({ name: 'second', spd: 1 })];
  b = startBattle(c, [mon({ atk: 200, spd: 99 })], eTwo, 5);
  o.e1 = turn(b);
  o.e2 = turn(o.e1);
  o.e3 = turn(turn(turn(o.e2)));

  const frozen = deepFreeze(startBattle(c, [mon()], [mon()], 3));
  const f1 = takeTurn(c, frozen, { type: 'move', slot: 0 });
  o.frozen = { turn: frozen.turn, newObject: f1 !== frozen };

  o.slots = [1, -1, 2.5, undefined, '0'].map((slot) => {
    const r = attempt(() => takeTurn(c, startBattle(c, [mon()], [mon()], 1), { type: 'move', slot }));
    return { slot: String(slot), error: r.ok ? null : r.error };
  });
  const m2 = mon({ moves: ['jab', 'fast'] });
  const s1 = takeTurn(c, startBattle(c, [m2], [mon()], 1), { type: 'move', slot: 1 });
  o.ownSlot = s1.log.find((l) => l.actor === 'player').move;

  const wild = startBattle(c, [mon()], [mon()], 12, { wild: true });
  const ran = takeTurn(c, deepFreeze(wild), { type: 'run' });
  o.ran = { ran, rng: stable(ran.rng), wildRng: stable(wild.rng) };
  const trainer = startBattle(c, [mon()], [mon()], 12);
  const stuck = takeTurn(c, deepFreeze(trainer), { type: 'run' });
  o.stuck = { after: stable(stuck), before: stable(trainer) };

  const foe = mon({ type: 'ember' });
  const pick = (enemy, player = foe) => enemyChoose(c, startBattle(c, [player], [enemy], 1));
  o.picks = [
    pick(mon({ type: 'plain', moves: ['jab', 'rinse'] })),
    pick(mon({ type: 'plain', moves: ['rinse', 'jab'] })),
    pick(mon({ type: 'plain', moves: ['jab', 'jab'] })),
    pick(mon({ type: 'plain', moves: ['jab', 'wobbly', 'fast'] })),
    pick(mon({ type: 'plain', moves: ['dud', 'fast', 'jab'] })),
    pick(mon({ type: 'moss', moves: ['jab', 'vine'] }), mon({ type: 'brine' })),
    pick(mon({ type: 'plain', moves: ['vine', 'jab'] }), mon({ type: 'brine' })),
  ];
  const pl = [mon({ hp: 0, type: 'plain' }), mon({ type: 'ember' })];
  o.activePlayer = enemyChoose(c, startBattle(c, pl, [mon({ type: 'plain', moves: ['jab', 'rinse'] })], 1));
  const en = [mon({ hp: 0, moves: ['jab', 'rinse'] }), mon({ type: 'plain', moves: ['rinse', 'jab'] })];
  o.activeEnemy = enemyChoose(c, startBattle(c, [foe], en, 1));
  return o;
}

// ---- 11: items -----------------------------------------------------------------------------------------------
export async function items({ load }) {
  const { countOf, addItem, removeItem, useItem } = await load('src/inventory.js');
  const c = fixture();
  deepFreeze(c);
  const o = {};

  const inv = deepFreeze({ salve: 2, tag: 1 });
  o.counts = [countOf(inv, 'salve'), countOf(inv, 'spark'), countOf(inv, 'toString')];
  o.adds = [addItem(inv, 'salve'), addItem(inv, 'salve', 5), addItem(inv, 'spark', 2)];
  const removedOne = removeItem(inv, 'salve');
  const removedTwo = removeItem(inv, 'salve', 2);
  const removedTag = removeItem(inv, 'tag');
  o.removes = { removedOne, removedTwo, tagKey: Object.hasOwn(removedTag, 'tag') };
  o.shortfalls = [['salve', 3], ['spark', 1], ['toString', 1]].map(([id, n]) => {
    const r = attempt(() => removeItem(inv, id, n));
    return { id, n, error: r.ok ? null : r.error };
  });
  o.invAfter = JSON.parse(JSON.stringify(inv));

  const party = (...hps) => hps.map(([hp, maxHp]) => mon({ hp, maxHp }));
  const P = (...a) => deepFreeze(party(...a));
  const use = (i, p, id, idx) => useItem(c, deepFreeze(i), p, id, idx);

  o.heal1 = use({ salve: 2 }, P([10, 30], [5, 30]), 'salve', 1);
  const heal2 = use({ salve: 1 }, P([20, 30]), 'salve', 0);
  o.heal2 = { r: heal2, key: Object.hasOwn(heal2.inventory, 'salve') };
  o.heal3 = use({ salve: 1 }, P([15, 30]), 'salve', 0);
  o.heal4 = use({ salve: 1 }, P([1, 100]), 'salve', 0);

  o.revive1 = use({ spark: 2 }, P([0, 31], [9, 20]), 'spark', 0);
  o.revive2 = use({ spark: 1 }, P([0, 1]), 'spark', 0);
  o.revive3 = use({ spark: 1 }, P([0, 40]), 'spark', 0);

  let inv3 = { salve: 2 };
  let pt = party([1, 100]);
  const results = [];
  for (let i = 0; i < 3; i++) {
    const u = useItem(c, inv3, pt, 'salve', 0);
    results.push({ ok: u.ok, reason: u.reason });
    if (u.ok) { inv3 = u.inventory; pt = u.party; }
  }
  o.threeUses = { results, hp: pt[0].hp };

  const fails = [
    ['full hp', { salve: 1 }, party([30, 30]), 'salve', 0],
    ['fainted target', { salve: 1 }, party([0, 30]), 'salve', 0],
    ['revive a living creature', { spark: 1 }, party([5, 30]), 'spark', 0],
    ['key item', { tag: 1 }, party([5, 30]), 'tag', 0],
    ['none held', {}, party([5, 30]), 'salve', 0],
    ['unknown item', { ghost: 1 }, party([5, 30]), 'ghost', 0],
    ['inherited name', {}, party([5, 30]), 'toString', 0],
    ['target below range', { salve: 1 }, party([5, 30]), 'salve', -1],
    ['target past range', { salve: 1 }, party([5, 30]), 'salve', 1],
    ['target not whole', { salve: 1 }, party([5, 30]), 'salve', 0.5],
    ['target as text', { salve: 1 }, party([5, 30]), 'salve', '0'],
    ['none held beats a bad target', {}, party([5, 30]), 'salve', 9],
    ['key beats a bad target', { tag: 1 }, party([5, 30]), 'tag', 9],
    ['bad target on a full-hp creature', { salve: 1 }, party([30, 30]), 'salve', 3],
  ];
  o.failures = fails.map(([name, i, p, id, idx]) => {
    const before = stable({ i, p });
    const u = useItem(c, deepFreeze(i), deepFreeze(p), id, idx);
    return { name, ok: u.ok, reason: u.reason, before, after: stable({ i: u.inventory, p: u.party }) };
  });
  return o;
}
