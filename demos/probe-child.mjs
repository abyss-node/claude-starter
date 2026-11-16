// The one file in the kit that imports a workspace's code. probe.mjs starts it in a Node process of its own,
// under Node's permission model, reading only the copy of the workspace and the two probe files:
//   node --permission --allow-fs-read=... probe-child.mjs <file URL of the module> <the calls, v8, base64>
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

function errorOf(e) {
  if (e === null || (typeof e !== 'object' && typeof e !== 'function')) {
    return { name: 'a thrown value', message: text(() => e), range: false };
  }
  return { name: text(() => e.name), message: text(() => e.message), range: e instanceof RangeError };
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

const [href, request] = process.argv.slice(2);
let answer;
try {
  const calls = v8.deserialize(Buffer.from(request, 'base64'));
  const mod = await import(href);
  answer = { results: calls.map((c) => call(mod, c)) };
} catch (e) {
  answer = { loadError: `${text(() => e.name)}: ${text(() => e.message)}` };
}
write(`\n${MARK}${v8.serialize(answer).toString('base64')}\n`, () => exit(0));
