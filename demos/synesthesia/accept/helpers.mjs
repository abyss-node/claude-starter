// Shared by the held-out tests. The workspace's code is never imported here: it runs in processes of its own
// (demos/probe.mjs: values(), outcomes() for calls with plain arguments, scenario() over scenarios.mjs for the
// rest), and these helpers only build the inputs and compare what came back. Every sound is made by signals.mjs.

import { readFile } from 'node:fs/promises';
import { isAbsolute, join, resolve } from 'node:path';
import { scenario } from '../../probe.mjs';

export { notRefused, outcomes, values } from '../../probe.mjs';

const SCENARIOS = new URL('./scenarios.mjs', import.meta.url);

// Runs the scenario `name` of scenarios.mjs beside the workspace and returns its answer.
export function ask(name, ...args) {
  return scenario(SCENARIOS, name, args, { timeoutMs: 50000 });
}

// Synth runs, in one process for all the jobs given; a job already run by an earlier test of the same file is
// not run again. A job is { frames | steps, opts, ambient, hash }: see scenarios.mjs.
const MEMO = new Map();
const keyOf = (job) => JSON.stringify(job, (_k, v) => (v === undefined ? '__undefined__' : v));
export function runs(...jobs) {
  const fresh = jobs.filter((job) => !MEMO.has(keyOf(job)));
  if (fresh.length) {
    const answers = ask('runs', fresh);
    fresh.forEach((job, i) => MEMO.set(keyOf(job), answers[i]));
  }
  return jobs.map((job) => MEMO.get(keyOf(job)));
}

// What each call [name, ...args] on the workspace module `file` returned, in one process; frames made there from
// a sound description, as scenarios.mjs says. Throws, naming the call, when one threw.
export function call(file, calls) {
  return ask('apply', file, calls).map((o, i) => {
    if (o.ok) return o.value;
    throw new Error(`${calls[i][0]} threw ${o.error.name}: ${o.error.message}`);
  });
}

// The same, as { ok, value | error } for each call, for a check that expects some to throw.
export function callOutcomes(file, calls) {
  return ask('apply', file, calls);
}

// The states of one job, failing with the job's own message when the synth threw.
export function statesOf(result) {
  if (result.error) throw new Error(result.error);
  return result.states;
}

export function workspace() {
  const ws = process.env.DEMO_WORKSPACE;
  if (!ws) throw new Error('DEMO_WORKSPACE is not set');
  return isAbsolute(ws) ? ws : resolve(ws);
}

export function readWorkspaceFile(rel) {
  return readFile(join(workspace(), rel), 'utf8');
}

export function close(actual, expected, tol, msg) {
  if (!(Math.abs(actual - expected) <= tol)) {
    throw new Error(`${msg ?? 'value'}: expected ${expected} within ${tol}, got ${actual}`);
  }
}

export function hueDistance(a, b) {
  const d = Math.abs((((a - b) % 360) + 360) % 360);
  return Math.min(d, 360 - d);
}

// Times at which a counter of the states went up (once per step of the counter).
export function flashTimes(states, field = 'flashes') {
  const out = [];
  let prev = 0;
  for (const s of states) {
    for (let n = prev; n < s[field]; n++) out.push(s.time);
    prev = s[field];
  }
  return out;
}

// True when any four consecutive events fit inside one second (the cap is three per second).
export function fourWithinASecond(times) {
  for (let i = 0; i + 3 < times.length; i++) if (times[i + 3] - times[i] < 1 - 1e-6) return true;
  return false;
}

export function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// The visible flash is the pulse jumping up and the pattern switching. Both may happen only on a frame
// where the flash counter went up; on every other frame the pattern holds and the pulse only fades.
export function checkVisibleOnlyOnFlash(states, assert) {
  for (let i = 1; i < states.length; i++) {
    const s = states[i];
    const p = states[i - 1];
    if (s.flashes === p.flashes) {
      assert.ok(s.pulse <= p.pulse + 1e-12, `pulse rose from ${p.pulse} to ${s.pulse} at ${s.time.toFixed(3)} s on a frame with no flash (a refused onset must not show)`);
      assert.equal(s.pattern, p.pattern, `pattern switched from ${p.pattern} to ${s.pattern} at ${s.time.toFixed(3)} s on a frame with no flash (a refused onset must not show)`);
    }
  }
}
