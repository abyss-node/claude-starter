// The one file in the kit that imports a workspace's code. probe.mjs starts it in a Node process of its own,
// under Node's permission model, reading only the copy of the workspace and the two probe files, and for a
// scenario its module and the modules of accept/ it imports (probe.mjs, scenarioReads):
//   node --permission --allow-fs-read=... probe-child.mjs <file URL of the module> <the calls, v8, base64>
//   node --permission --allow-fs-read=... probe-child.mjs --scenario <scenario URL> <export> <workspace URL> <args>
// It imports the module, makes each call, and prints one line: MARK, then { results } or { loadError },
// v8-serialized and base64. The checks trust nothing here, so nothing here guards against the module.
import v8 from 'node:v8';
import { MARK } from './probe.mjs';

const write = process.stdout.write.bind(process.stdout);
const exit = process.exit.bind(process);

function text(get) {
  try {
    return String(get());
  } catch {
    return '(unreadable)';
  }
}

// A denial by the permission model says which access it refused and the flag the probe did not give, the same on
// every Node: newer releases name the flag in the message, but 22.13, the floor, says only "Access to this API
// has been restricted", and a FAIL that does not say the permission model refused it reads as a broken module.
const FLAGS = { FileSystemRead: '--allow-fs-read', FileSystemWrite: '--allow-fs-write',
  ChildProcess: '--allow-child-process', WorkerThreads: '--allow-worker' };

function messageOf(e) {
  const message = text(() => e.message);
  if (text(() => e.code) !== 'ERR_ACCESS_DENIED') return message;
  const permission = text(() => e.permission);
  const what = e.resource === undefined ? '' : ` of ${text(() => e.resource)}`;
  const flag = FLAGS[permission] ? `, which ${FLAGS[permission]} would allow` : '';
  return `${message.replace(/\.?\s*Use --allow-[\w-]+ to manage permissions\.?$/, '')}: the permission model `
    + `denied ${permission}${what}${flag}`;
}

function errorOf(e) {
  if (e === null || (typeof e !== 'object' && typeof e !== 'function')) {
    return { name: 'a thrown value', message: text(() => e), range: false };
  }
  return { name: text(() => e.name), message: messageOf(e), range: e instanceof RangeError };
}

function call(mod, [fn, ...args]) {
  if (typeof mod[fn] !== 'function') {
    return { ok: false, error: { name: 'TypeError', message: `the module exports no function ${fn}`, range: false } };
  }
  let value;
  try {
    value = mod[fn](...args);
  } catch (e) {
    return { ok: false, error: errorOf(e) };
  }
  try {
    v8.serialize(value);
  } catch (e) {
    const message = `it returned a value that cannot be copied out of its process (${text(() => e.message)})`;
    return { ok: false, error: { name: 'DataCloneError', message, range: false } };
  }
  return { ok: true, value };
}

// A scenario (probe.mjs's scenario()): --scenario <its file URL> <export> <workspace folder URL> <args, v8, base64>.
// Its function gets { load }, which imports a module of the workspace by its path there, then the args.
async function runScenario([scenarioHref, name, wsHref, request]) {
  const args = v8.deserialize(Buffer.from(request, 'base64'));
  const mod = await import(scenarioHref);
  if (typeof mod[name] !== 'function') {
    return { loadError: `TypeError: the scenario module exports no function ${name}` };
  }
  const load = (rel) => import(new URL(String(rel), wsHref).href);
  let value;
  try {
    value = await mod[name]({ load }, ...args);
  } catch (e) {
    return { results: [{ ok: false, error: errorOf(e) }] };
  }
  try {
    v8.serialize(value);
  } catch (e) {
    const message = `it returned a value that cannot be copied out of its process (${text(() => e.message)})`;
    return { results: [{ ok: false, error: { name: 'DataCloneError', message, range: false } }] };
  }
  return { results: [{ ok: true, value }] };
}

const argv = process.argv.slice(2);
let answer;
try {
  if (argv[0] === '--scenario') {
    answer = await runScenario(argv.slice(1));
  } else {
    const [href, request] = argv;
    const calls = v8.deserialize(Buffer.from(request, 'base64'));
    const mod = await import(href);
    answer = { results: calls.map((c) => call(mod, c)) };
  }
} catch (e) {
  answer = { loadError: `${text(() => e.name)}: ${messageOf(e)}` };
}
write(`\n${MARK}${v8.serialize(answer).toString('base64')}\n`, () => exit(0));
