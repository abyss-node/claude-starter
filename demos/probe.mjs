// How a demo's held-out checks call the workspace's code without letting it into their own process. A module
// imported by the checks shares node:assert, Math and every other global with them and can replace any of
// them: a module that set assert.equal and assert.ok to no-ops and returned constants once passed every check.
// So the checks never import the workspace. outcomes() starts a new Node process (probe-child.mjs), which
// imports the module and makes the calls, and hands back only what each call returned or threw, on a line that
// carries a key the workspace's code cannot learn. Whatever that code does there, all it can change is those
// answers, and a right answer is the work itself.
//
// That process runs under Node's permission model: it may read the workspace, which check.py has copied into
// a folder of its own, and the two probe files; a scenario's process (below) may also read the scenario's
// module and the modules of accept/ it imports (scenarioReads). Nothing else of the kit: it cannot write,
// start processes or workers, or read reference/, so a module that only re-exported the kit's reference/
// solution, which once passed every check, now fails to load. Its command line names the probe files, so the
// workspace's code can learn where the kit is; it cannot read it. Node documents the model as a seat belt for
// code you trust, not a sandbox against code that sets out to escape it, so this raises the cost of a cheat;
// it does not rule every one out (demos/MEASURING.md).
//
// Answers cross as v8 serialization, not JSON: JSON turns NaN into null, and Math.abs(null - 0) is 0, so a
// NaN where 0 is expected would pass a closeness check.
//
// A check that needs more than calls with plain arguments (a simulation stepped ten thousand times, an object
// frozen before it is handed over, a callback) runs a scenario: a function exported by a module in the demo's
// accept/ folder, which the same kind of process imports beside the workspace and runs there (scenario()). It
// returns observations, plain data, and the asserts stay here. A scenario shares that process with the
// workspace's code. Before that code loads, probe-child.mjs freezes the built-ins and what the kit's modules
// there export, takes away Node's heap snapshots and promise hooks, and holds the clocks, so it cannot change how
// a scenario looks (workspaces once changed Number.prototype.toFixed, Object.getPrototypeOf, Math.random or a
// scenario's own table of seeds, and hid a real bug each time). What it can still change is its own values as they are read: a getter or a Proxy
// of its own runs when the scenario reads it. So a scenario returns what it saw, the values themselves, never a
// verdict such as `true` for "it was pure" nor text it made of them: the test formats, classifies and compares.
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
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

function workspaceDir() {
  const ws = process.env.DEMO_WORKSPACE;
  if (!ws) throw new Error('DEMO_WORKSPACE is not set: run these through demos/check.py');
  return path.resolve(ws);
}

// The key the answer line must carry, new for each process: the child reads it from stdin before any workspace
// module loads, and the workspace's code, which can print lines of its own, cannot learn it.
const answerKey = () => randomBytes(16).toString('hex');

// Start probe-child.mjs under the permission model, reading the copy, the probe files and `alsoRead`, with
// `args`, and return its one answer. `what` names it in a message.
function ask(what, args, alsoRead, timeoutMs) {
  const ws = workspaceDir();
  const env = { ...process.env };
  delete env.NODE_OPTIONS;
  delete env.NODE_TEST_CONTEXT; // set by node --test for this process; the child is not a test file
  delete env.DEMO_RESULT_TOKEN; // only the runner's own result lines carry it
  const flags = ['--permission', ...[ws, CHILD, PROBE, ...alsoRead].map((p) => `--allow-fs-read=${p}`)];
  const timeout = timeoutMs || TIMEOUT_MS;
  const key = answerKey();
  const head = `${MARK}${key}:`;
  const run = spawnSync(process.execPath, [...flags, CHILD, ...args], {
    cwd: ws, env, encoding: 'utf8', timeout, maxBuffer: MAX_OUTPUT, windowsHide: true,
    input: key, stdio: ['pipe', 'pipe', 'pipe'],
  });
  if (run.error) {
    const why = run.error.code === 'ETIMEDOUT' ? `gave no answer within ${timeout / 1000} seconds` : run.error.message;
    throw new Error(`${what}: ${why}`);
  }
  const line = String(run.stdout).split('\n').find((l) => l.startsWith(head));
  if (!line) {
    const why = firstError(run.stderr) || `its process exited (${run.status ?? run.signal}) without an answer`;
    throw new Error(`${what}: ${why}`);
  }
  try {
    return v8.deserialize(Buffer.from(line.slice(head.length), 'base64'));
  } catch (e) {
    throw new Error(`${what}: an answer that cannot be read (${e.message})`);
  }
}

// The static imports of a module: `import ... from '<spec>'`, `import '<spec>'` and `export ... from '<spec>'`,
// read once comments are gone.
const IMPORT_SPEC = /(?:^|[\s;}])(?:import|export)\s*(?:[\w$\s{},*]*?\bfrom\s*)?(['"])([^'"\n]+)\1/g;
const withoutComments = (src) => src.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(^|[^:\\'"`])\/\/.*$/gm, '$1');
const READS = new Map();

/**
 * The files of the kit a scenario's process may read besides the probe files: the scenario module `file` (an
 * absolute path) and every module of its folder it imports, followed through their static imports. Granting the
 * folder instead let the workspace's code read all of accept/, mutants/ included, whose find strings quote the
 * reference solution, since a folder's grant covers everything below it. So an import is followed only to a .mjs
 * module of the scenario's own folder outside mutants/, or to a probe file; anything else throws, before any
 * process starts, naming the import. An import missed here is not granted, so it fails to load (the permission
 * model denies it) rather than widening what can be read.
 */
export function scenarioReads(file) {
  if (READS.has(file)) return READS.get(file);
  const root = path.dirname(file);
  const reads = [];
  const todo = [[file, null, null]];
  while (todo.length) {
    const [f, from, spec] = todo.pop();
    if (reads.includes(f)) continue;
    const where = path.relative(root, f);
    const inside = where !== '' && !where.startsWith('..') && !path.isAbsolute(where);
    if (!inside || where.split(path.sep).includes('mutants') || path.extname(f) !== '.mjs') {
      const which = from === null ? `the scenario module ${f} is not a .mjs file, and`
        : `${path.relative(root, from)} imports ${spec}, which a scenario's process may not read:`;
      throw new Error(`${which} a scenario reaches the kit only through .mjs modules of its own folder outside `
        + 'mutants/ (demos/AUTHORING.md)');
    }
    let source;
    try {
      if (!statSync(f).isFile()) throw new Error('not a file');
      source = readFileSync(f, 'utf8');
    } catch (e) {
      throw new Error(from === null ? `cannot read the scenario module ${f}: ${e.message}`
        : `${path.relative(root, from)} imports ${spec}, which cannot be read: ${e.message}`);
    }
    reads.push(f);
    for (const [, , s] of withoutComments(source).matchAll(IMPORT_SPEC)) {
      if (!s.startsWith('./') && !s.startsWith('../')) continue;   // a node: builtin
      const target = path.resolve(path.dirname(f), s);
      if (target !== PROBE && target !== CHILD) todo.push([target, f, s]);
    }
  }
  READS.set(file, reads);
  return reads;
}

/**
 * Run the function `name`, exported by the scenario module `file` (a file URL or path of a module in the demo's
 * accept/ folder), in a process of its own beside the workspace: `fn({ load, withoutClocks }, ...args)`, where
 * `await load('src/x.js')` imports a workspace module and `withoutClocks(fn)` runs fn with Math.random, Date.now and
 * performance.now throwing (probe-child.mjs). Returns what it returned (awaited), which must be plain data;
 * throws, saying why, when it threw, a workspace module did not load or the process gave no answer. The
 * process may read the copy, the probe files and the files scenarioReads names, and nothing else: whatever a
 * scenario imports, the workspace's code there can read, and import, too. Options: timeoutMs (default 30000).
 */
export function scenario(file, name, args = [], { timeoutMs } = {}) {
  const scenarioPath = String(file).startsWith('file:') ? fileURLToPath(file) : path.resolve(String(file));
  const wsHref = pathToFileURL(workspaceDir() + path.sep).href;
  const what = `scenario ${name}`;
  let reads;
  try {
    reads = scenarioReads(scenarioPath);
  } catch (e) {
    throw new Error(`${what} did not run: ${e.message}`);
  }
  // The kit's modules among what it may read: probe-child.mjs freezes what each exports.
  const modules = reads.filter((f) => path.extname(f) === '.mjs').map((f) => pathToFileURL(f).href);
  const answer = ask(what, ['--scenario', pathToFileURL(scenarioPath).href, name, wsHref,
    v8.serialize(args).toString('base64'), v8.serialize(modules).toString('base64')], reads, timeoutMs);
  if (answer && typeof answer === 'object' && isText(answer.loadError)) {
    throw new Error(`${what} did not run: ${answer.loadError}`);
  }
  const results = answer && Array.isArray(answer.results) ? answer.results : [];
  const o = normalise(results[0]);
  if (results.length !== 1) throw new Error(`${what}: the answer does not hold one result`);
  if (!o.ok) throw new Error(`${what} threw ${o.error.name}: ${o.error.message}`);
  return o.value;
}

/**
 * Make `calls` ([name, ...args] each) on the workspace module `module` (a path relative to the workspace, with
 * forward slashes) in a process of its own. Returns, per call, { ok: true, value } or
 * { ok: false, error: { name, message, range } }, where range says whether it threw a RangeError. Throws when
 * the module does not load or the process gives no answer. Options: timeoutMs (default 30000).
 */
export function outcomes(module, calls, { timeoutMs } = {}) {
  // A raw Windows path is not an import specifier (ERR_UNSUPPORTED_ESM_URL_SCHEME), hence the file URL.
  const href = pathToFileURL(path.join(workspaceDir(), ...module.split('/'))).href;
  const answer = ask(module, [href, v8.serialize(calls).toString('base64')], [], timeoutMs);
  return checked(module, calls, answer);
}

function checked(module, calls, answer) {
  if (answer && typeof answer === 'object' && isText(answer.loadError)) {
    throw new Error(`${module} did not load: ${answer.loadError}`);
  }
  if (!answer || !Array.isArray(answer.results) || answer.results.length !== calls.length) {
    throw new Error(`${module}: the answer does not hold one result per call`);
  }
  return answer.results.map(normalise);
}

/** What each call returned; throws, naming the call, when one of them threw instead. */
export function values(module, calls, options = {}) {
  return outcomes(module, calls, options).map((o, i) => {
    if (o.ok) return o.value;
    throw new Error(`${describe(calls[i])} threw ${o.error.name}: ${o.error.message}`);
  });
}

/** Each call that did not throw a RangeError, said as what it did instead. Empty when every call refused. */
export function notRefused(module, calls, options = {}) {
  return outcomes(module, calls, options).flatMap((o, i) => {
    if (o.ok) return [`${describe(calls[i])} returned ${show(o.value)}`];
    return o.error.range ? [] : [`${describe(calls[i])} threw ${o.error.name}, not a RangeError`];
  });
}
