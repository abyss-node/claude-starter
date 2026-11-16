// How a demo's held-out checks call the workspace's code without letting it into their own process. A module
// imported by the checks shares node:assert, Math and every other global with them and can replace any of
// them: a module that set assert.equal and assert.ok to no-ops and returned constants once passed every check.
// So the checks never import the workspace. outcomes() starts a new Node process (probe-child.mjs), which
// imports the module and makes the calls, and hands back only what each call returned or threw. Whatever the
// workspace's code does there, all it can change is those answers, and a right answer is the work itself.
//
// That process runs under Node's permission model: it may read the workspace, which check.py has copied into
// a folder of its own, and the two probe files, and nothing else. It cannot write, start processes or
// workers, or read the kit, so a module that only re-exported the kit's reference/ solution, which once
// passed every check, now fails to load. Node documents the model as a seat belt for code you trust, not a
// sandbox against code that sets out to escape it, so this raises the cost of a cheat; it does not rule
// every one out (demos/MEASURING.md).
//
// Answers cross as v8 serialization, not JSON: JSON turns NaN into null, and Math.abs(null - 0) is 0, so a
// NaN where 0 is expected would pass a closeness check.
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { inspect } from 'node:util';
import v8 from 'node:v8';

export const MARK = 'demo-probe-answer:';
const CHILD = fileURLToPath(new URL('./probe-child.mjs', import.meta.url));
const PROBE = fileURLToPath(import.meta.url); // probe-child.mjs imports MARK from here
const TIMEOUT_MS = 30000;
const MAX_OUTPUT = 64 * 1024 * 1024;

/** `fn(arg, ...)`, for a failure message. */
export function describe([fn, ...args]) {
  return `${fn}(${args.map((a) => (Object.is(a, -0) ? '-0' : String(a))).join(', ')})`;
}

function firstError(stderr) {
  const lines = String(stderr || '').split('\n').map((l) => l.trim()).filter(Boolean);
  return lines.find((l) => /^\w*Error\b/.test(l)) || lines[0] || '';
}

const show = (v) => inspect(v, { breakLength: Infinity, maxArrayLength: 10, depth: 2 });

function isText(x) {
  return typeof x === 'string';
}

// The answer comes from the workspace's process, so its shape is checked here rather than trusted.
function normalise(o) {
  if (o && typeof o === 'object' && o.ok === true && 'value' in o) return { ok: true, value: o.value };
  const e = o && typeof o === 'object' && o.ok === false && o.error && typeof o.error === 'object' ? o.error : null;
  if (e && isText(e.name) && isText(e.message) && typeof e.range === 'boolean') {
    return { ok: false, error: { name: e.name, message: e.message, range: e.range } };
  }
  return { ok: false, error: { name: 'Error', message: 'the answer for this call is malformed', range: false } };
}

/**
 * Make `calls` ([name, ...args] each) on the workspace module `module` (a path relative to the workspace, with
 * forward slashes) in a process of its own. Returns, per call, { ok: true, value } or
 * { ok: false, error: { name, message, range } }, where range says whether it threw a RangeError. Throws when
 * the module does not load or the process gives no answer.
 */
export function outcomes(module, calls) {
  const ws = process.env.DEMO_WORKSPACE;
  if (!ws) throw new Error('DEMO_WORKSPACE is not set: run these through demos/check.py');
  // A raw Windows path is not an import specifier (ERR_UNSUPPORTED_ESM_URL_SCHEME), hence the file URL.
  const href = pathToFileURL(path.join(ws, ...module.split('/'))).href;
  const env = { ...process.env };
  delete env.NODE_OPTIONS;
  delete env.NODE_TEST_CONTEXT; // set by node --test for this process; the child is not a test file
  const flags = ['--permission', ...[path.resolve(ws), CHILD, PROBE].map((p) => `--allow-fs-read=${p}`)];
  const run = spawnSync(process.execPath, [...flags, CHILD, href, v8.serialize(calls).toString('base64')], {
    cwd: ws, env, encoding: 'utf8', timeout: TIMEOUT_MS, maxBuffer: MAX_OUTPUT, windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (run.error) {
    const why = run.error.code === 'ETIMEDOUT' ? `gave no answer within ${TIMEOUT_MS / 1000} seconds` : run.error.message;
    throw new Error(`${module}: ${why}`);
  }
  const line = String(run.stdout).split('\n').reverse().find((l) => l.startsWith(MARK));
  if (!line) {
    const why = firstError(run.stderr) || `its process exited (${run.status ?? run.signal}) without an answer`;
    throw new Error(`${module}: ${why}`);
  }
  let answer;
  try {
    answer = v8.deserialize(Buffer.from(line.slice(MARK.length), 'base64'));
  } catch (e) {
    throw new Error(`${module}: an answer that cannot be read (${e.message})`);
  }
  if (answer && typeof answer === 'object' && isText(answer.loadError)) {
    throw new Error(`${module} did not load: ${answer.loadError}`);
  }
  if (!answer || !Array.isArray(answer.results) || answer.results.length !== calls.length) {
    throw new Error(`${module}: the answer does not hold one result per call`);
  }
  return answer.results.map(normalise);
}

/** What each call returned; throws, naming the call, when one of them threw instead. */
export function values(module, calls) {
  return outcomes(module, calls).map((o, i) => {
    if (o.ok) return o.value;
    throw new Error(`${describe(calls[i])} threw ${o.error.name}: ${o.error.message}`);
  });
}

/** Each call that did not throw a RangeError, said as what it did instead. Empty when every call refused. */
export function notRefused(module, calls) {
  return outcomes(module, calls).flatMap((o, i) => {
    if (o.ok) return [`${describe(calls[i])} returned ${show(o.value)}`];
    return o.error.range ? [] : [`${describe(calls[i])} threw ${o.error.name}, not a RangeError`];
  });
}
