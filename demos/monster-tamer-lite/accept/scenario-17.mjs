// Item 17: Replay. Runs beside the workspace (demos/probe.mjs, scenario()) and returns what hashLog gave for the logs
// below, and for many played battles the battle as text (as a digest) next to what replayBattle made of its history
// and of each prefix named; 17-replay.test.mjs works out the right hashes and compares.
import { engineOf, J, clone, config, testRng, fnv1a, deepFreeze, randTeam } from './fixtures.mjs';

export const KNOWN = [[], [{ type: 'turn', n: 1 }], ['é'], ['日本'], ['😀'], ['x'], [1], [null]];
export function randomLogs() {
  const rnd0 = testRng(5);
  return Array.from({ length: 60 }, (_, i) => Array.from({ length: i % 7 }, () => ({ type: 'x', n: Math.floor(rnd0() * 1e6), s: String.fromCharCode(97 + Math.floor(rnd0() * 26)) + (rnd0() < 0.2 ? 'ü' : '') })));
}
export const KINDS = ['wild-random', 'plain-random', 'ai-vs-ai'];
export const SEEDS = 14;
const digest = (v) => fnv1a(J(v));

export async function run({ load }) {
  const { replay, battle: B, ai } = await engineOf(load);
  const { hashLog, replayBattle } = replay;
  const { createBattle, resolveTurn, legalActions } = B;
  const out = {};
  out.known = KNOWN.map((log) => hashLog(log));
  out.random = randomLogs().map((log) => hashLog(log));
  out.differ = [hashLog([{ a: 1 }]), hashLog([{ a: 2 }])];

  out.battles = [];
  for (const kind of KINDS) {
    for (let seed = 1; seed <= SEEDS; seed++) {
      const rnd = testRng(seed * 31 + kind.length);
      const wild = kind === 'wild-random';
      const cfg = config(randTeam(rnd, 3, 'L'), randTeam(rnd, 3, 'R'), { seed, wild, snares: wild ? 3 : 0 });
      const frozenCfg = deepFreeze(clone(cfg));
      const live = createBattle(frozenCfg);
      const snapshots = [digest(live)];
      for (let i = 0; i < 300 && live.phase !== 'over'; i++) {
        const choices = [0, 1].map((side) => {
          const legal = legalActions(live, side);
          if (legal.length === 0) return null;
          if (kind === 'ai-vs-ai' || side === 1) return ai.chooseAction(live, side);
          return legal[Math.floor(rnd() * legal.length)];
        });
        resolveTurn(live, choices);
        snapshots.push(digest(live));
      }
      const history = live.history;
      const historyBefore = J(history);
      const again = replayBattle(frozenCfg, history);
      const prefixes = [...new Set([0, 1, Math.floor(history.length / 2), history.length - 1])].map((k) => [k, digest(replayBattle(cfg, history.slice(0, k)))]);
      out.battles.push({
        kind, seed, phase: live.phase, snares: live.snares, live: digest(live), snapshots,
        again: digest(again), againHash: hashLog(again.log), liveHash: hashLog(live.log),
        historyBefore, historyAfter: J(history), ofCopies: digest(replayBattle(clone(cfg), clone(history))),
        historyLength: history.length, prefixes,
      });
    }
  }

  {
    const rnd = testRng(77);
    const l = randTeam(rnd, 3, 'L');
    const r = randTeam(rnd, 3, 'R');
    out.bySeed = [];
    for (let seed = 1; seed <= 12; seed++) {
      const b = createBattle(config(l, r, { seed }));
      for (let i = 0; i < 400 && b.phase !== 'over'; i++) resolveTurn(b, [0, 1].map((s) => ai.chooseAction(b, s)));
      out.bySeed.push(hashLog(b.log));
    }
  }
  {
    const rnd = testRng(78);
    const cfg = config(randTeam(rnd, 3, 'L'), randTeam(rnd, 3, 'R'), { seed: 11 });
    const b = createBattle(cfg);
    for (let i = 0; i < 400 && b.phase !== 'over'; i++) resolveTurn(b, [0, 1].map((s) => ai.chooseAction(b, s)));
    out.again = { live: digest(b), replayed: digest(replayBattle(cfg, b.history)), emptyLog: structuredClone(replayBattle({ ...cfg, seed: 11 }, []).log) };
  }
  return out;
}
