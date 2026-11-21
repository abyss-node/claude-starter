// The one file in the kit that imports a workspace's code. probe.mjs starts it in a Node process of its own,
// under Node's permission model, reading only the copy of the workspace and the two probe files, and for a
// scenario its module and the modules of accept/ it imports (probe.mjs, scenarioReads):
//   node --permission --allow-fs-read=... probe-child.mjs <file URL of the module> <the calls, v8, base64>
//   node --permission --allow-fs-read=... probe-child.mjs --scenario <scenario URL> <export> <workspace URL> <args>
//     <the URLs of the kit's modules it imports>
// with this run's answer key on stdin. It imports the module, makes each call, and prints one line: MARK, the key,
// ':', then { results } or { loadError }, v8-serialized and base64.
//
// The workspace's code runs in this process, beside the kit's code that calls it and, for a scenario, beside the
// scenario that observes it. So before any workspace module loads, this file takes away what that code could
// otherwise change under them (harden, below):
// - The JavaScript built-ins and the globals of Node's that the kit's code here uses are frozen, as is each global
//   binding to them: assigning to Number.prototype.toFixed, Object.getPrototypeOf or Math.random, or defining
//   them anew, throws. A verifier's workspace once made every number it formatted unique, made class instances
//   look plain and kept Math.random from being taken away, each in 5 to 7 lines, and hid a real bug each time.
// - What the kit's own modules export in a scenario's process is frozen too (freezeExports): the workspace's code
//   can import each by the URL the scenario has, and gets the very module the scenario uses.
// - Taking the clocks away (a scenario's withoutClocks) is a switch held here: Math.random, Date.now and
//   performance.now are this file's own functions from before the freeze, which throw while the switch is on.
//   The workspace can neither replace them nor reach the switch.
// - The answer is serialized and written with functions taken before the freeze, and carries a key the parent
//   gave on stdin, read before any workspace module loads. A workspace that printed an answer line of its own,
//   after this file's, once had its line believed: the parent took the last line that began with MARK.
// - Node's ways of looking into this process are taken away (takeAway): all of node:v8 but its serializer and
//   its statistics, and node:async_hooks' createHook and executionAsyncResource, throw. A planted workspace read
//   the answer key out of v8.getHeapSnapshot() and printed an answer line of its own that the parent believed, in
//   9 lines; another hooked every promise made after it loaded (async_hooks.createHook, v8.promiseHooks) and
//   rewrote the record a scenario's helper resolved with before the scenario read it. The permission model
//   allows all of these.
// What is left to the workspace is its own values: a scenario reads what they hold, and a getter, a Proxy trap
// or a toJSON of the workspace's runs as the scenario reads it (demos/AUTHORING.md, "Node checks").
import asyncHooks from 'node:async_hooks';
import { readFileSync, writeSync } from 'node:fs';
import { syncBuiltinESMExports } from 'node:module';
import { types } from 'node:util';
import v8 from 'node:v8';
import { MARK } from './probe.mjs';

const KEY = readFileSync(0, 'utf8').trim();
const ARGV = process.argv.slice(2);
const exit = process.exit.bind(process);
const { serialize, deserialize } = v8;
const { apply, defineProperty, getOwnPropertyDescriptor, getPrototypeOf, ownKeys } = Reflect;
const { freeze } = Object;
const RealPromise = Promise;
const then = Promise.prototype.then;

// ---- the clocks, and the switch that takes them away ----

let clocksOff = 0;
let refused = [];

function refuse(name) {
  refused.push(name);
  throw new Error(`${name} was called while the checks had taken the clocks away: the code must take its time `
    + 'and randomness from its seed and its inputs');
}

function installClocks() {
  const realRandom = Math.random;
  const realNow = Date.now;
  const perf = globalThis.performance;
  const realPerfNow = perf.now;
  Math.random = function random() { if (clocksOff) refuse('Math.random'); return realRandom(); };
  Date.now = function now() { if (clocksOff) refuse('Date.now'); return realNow(); };
  const perfNow = function now() { if (clocksOff) refuse('performance.now'); return apply(realPerfNow, perf, []); };
  defineProperty(perf, 'now', { value: perfNow, writable: false, enumerable: true, configurable: false });
  defineProperty(globalThis, 'performance', { value: perf, writable: false, enumerable: true, configurable: false });
}

// Runs fn with Math.random, Date.now and performance.now throwing, and returns what it returns; for a promise, the
// clocks stay away until it settles. A clock the code reads in that time is refused even when the code catches
// the throw: withoutClocks then throws, naming it, once fn is done.
function withoutClocks(fn) {
  if (clocksOff === 0) refused = [];
  clocksOff += 1;
  const done = (value) => {
    clocksOff -= 1;
    if (clocksOff === 0 && refused.length) {
      const names = [...new Set(refused)].join(', ');
      throw new Error(`${names} was called while the checks had taken the clocks away (and the throw was caught)`);
    }
    return value;
  };
  let value;
  try {
    value = fn();
  } catch (e) {
    clocksOff -= 1;
    throw e;
  }
  if (value instanceof RealPromise) {
    return apply(then, value, [done, (e) => { clocksOff -= 1; throw e; }]);
  }
  return done(value);
}

// ---- the built-ins, frozen before any workspace module loads ----

// The globals of the language, where this Node has them.
const LANGUAGE = ['Object', 'Function', 'Array', 'Number', 'parseFloat', 'parseInt', 'Boolean', 'String', 'Symbol',
  'Date', 'Promise', 'RegExp', 'Error', 'AggregateError', 'EvalError', 'RangeError', 'ReferenceError', 'SyntaxError',
  'TypeError', 'URIError', 'SuppressedError', 'JSON', 'Math', 'Intl', 'ArrayBuffer', 'SharedArrayBuffer', 'Atomics',
  'DataView', 'Int8Array', 'Uint8Array', 'Uint8ClampedArray', 'Int16Array', 'Uint16Array', 'Int32Array',
  'Uint32Array', 'Float16Array', 'Float32Array', 'Float64Array', 'BigInt64Array', 'BigUint64Array', 'BigInt', 'Map',
  'Set', 'WeakMap', 'WeakSet', 'WeakRef', 'FinalizationRegistry', 'Proxy', 'Reflect', 'Iterator', 'DisposableStack',
  'AsyncDisposableStack', 'WebAssembly', 'decodeURI', 'decodeURIComponent', 'encodeURI', 'encodeURIComponent',
  'escape', 'unescape', 'eval', 'isFinite', 'isNaN'];
// Node's globals that scenarios and this file use: copies and digests, the load of a module by URL, the answer.
const HOST = ['structuredClone', 'TextEncoder', 'TextDecoder', 'URL', 'URLSearchParams', 'Buffer', 'queueMicrotask',
  'atob', 'btoa'];
// Built-ins no global names, reached from a value of their kind.
const HIDDEN = [
  () => getPrototypeOf(function* generator() {}),
  () => getPrototypeOf(async function asyncFunction() {}),
  () => getPrototypeOf(async function* asyncGenerator() {}),
  () => getPrototypeOf([][Symbol.iterator]()),
  () => getPrototypeOf(new Map()[Symbol.iterator]()),
  () => getPrototypeOf(new Set()[Symbol.iterator]()),
  () => getPrototypeOf(''[Symbol.iterator]()),
  () => getPrototypeOf(/(?:)/g[Symbol.matchAll]('')),
  () => getPrototypeOf([].values().map((x) => x)),
  () => getPrototypeOf(Iterator.from({ next: () => ({ done: true }) })),
  () => getPrototypeOf(new Intl.Segmenter().segment('')),
  () => getPrototypeOf(new Intl.Segmenter().segment('')[Symbol.iterator]()),
];
// Properties that ordinary code sets on objects derived from a built-in: `this.name = 'GameError'` in an Error
// class, `Foo.prototype.toString = ...`. On a frozen prototype that assignment throws (the "override mistake"), so
// each becomes a getter of the same value and a setter that defines the property on the derived object, and throws
// for the built-in itself. The same list as Node's own --frozen-intrinsics, less what would slow arrays and
// promises down (their `constructor` is watched by V8's fast paths).
const ERROR_KEYS = ['constructor', 'name', 'message', 'toString'];
const DERIVED = [[Object.prototype, ['constructor', 'toString', 'toLocaleString', 'valueOf']],
  [Function.prototype, ['toString']],
  ...['Error', 'AggregateError', 'EvalError', 'RangeError', 'ReferenceError', 'SyntaxError', 'TypeError', 'URIError',
    'SuppressedError'].filter((n) => typeof globalThis[n] === 'function').map((n) => [globalThis[n].prototype, ERROR_KEYS])];

function overridable(obj, key) {
  const d = getOwnPropertyDescriptor(obj, key);
  if (!d || !('value' in d) || !d.configurable) return;
  const { value } = d;
  defineProperty(obj, key, {
    get: { [key]() { return value; } }[key],
    set: { [key](v) {
      if (this === obj) throw new TypeError(`Cannot assign to read only property '${key}' of a built-in the checks froze`);
      defineProperty(this, key, { value: v, writable: true, enumerable: true, configurable: true });
    } }[key],
    enumerable: d.enumerable,
    configurable: false,
  });
}

const frozen = new Set([globalThis, process]);

// Freezes `from` and everything reachable from it through properties (values, getters, setters) and prototypes.
// `refuse(o)` names, for an object found on the way, why freezing it would not keep it unchanged, or says nothing.
function freezeFrom(from, refuse = () => null) {
  const todo = [];
  const keep = (v) => { if ((typeof v === 'object' && v !== null) || typeof v === 'function') todo.push(v); };
  keep(from);
  while (todo.length) {
    const o = todo.pop();
    if (frozen.has(o)) continue;
    const why = refuse(o);
    if (why) throw new TypeError(why);
    frozen.add(o);
    for (const key of ownKeys(o)) {
      const d = getOwnPropertyDescriptor(o, key);
      keep(d.value);
      keep(d.get);
      keep(d.set);
    }
    keep(getPrototypeOf(o));
    freeze(o);
  }
}

// What node:v8 and node:async_hooks keep: the serializer, which writes the answer, and what reads no value of
// this process (statistics, ids, AsyncLocalStorage). Everything else of them becomes a function that throws, or
// an object of such functions: a heap snapshot, a query or a profile reads every value here, the answer key among
// them; a promise hook is handed every promise made after it, with what each resolves to; a V8 flag changes how
// the engine runs the kit's code. Kept by name, so that what a newer Node adds is taken away too.
const KEPT = new Map([
  [v8, ['serialize', 'deserialize', 'Serializer', 'Deserializer', 'DefaultSerializer', 'DefaultDeserializer',
    'cachedDataVersionTag', 'getHeapStatistics', 'getHeapSpaceStatistics', 'getHeapCodeStatistics',
    'getCppHeapStatistics', 'isStringOneByteRepresentation']],
  [asyncHooks, ['AsyncLocalStorage', 'AsyncResource', 'executionAsyncId', 'triggerAsyncId', 'asyncWrapProviders']],
]);
const MODULE_NAMES = new Map([[v8, 'node:v8'], [asyncHooks, 'node:async_hooks']]);

function takenAway(what, value) {
  if (value !== null && typeof value === 'object') {
    const stand = {};
    for (const key of ownKeys(value)) if (typeof key === 'string') stand[key] = takenAway(`${what}.${key}`, value[key]);
    return freeze(stand);
  }
  return function refused() {
    throw new TypeError(`${what} was taken away by the checks: it looks into the process the workspace's code `
      + "shares with them (demos/AUTHORING.md, \"What a scenario's process freezes\")");
  };
}

function takeAway() {
  for (const [mod, kept] of KEPT) {
    for (const key of ownKeys(mod)) {
      if (typeof key !== 'string' || kept.includes(key)) continue;
      const d = getOwnPropertyDescriptor(mod, key);
      const value = takenAway(`${MODULE_NAMES.get(mod)} ${key}`, d.value);
      defineProperty(mod, key, { value, writable: false, enumerable: d.enumerable, configurable: false });
    }
  }
  // `import { getHeapSnapshot } from 'node:v8'` reads the module's named exports, which Node copied from it when
  // this file imported it; this copies them again, from what is left.
  syncBuiltinESMExports();
}

function harden() {
  takeAway();
  const roots = [v8, asyncHooks];   // node:v8 writes the answer; both hold what takeAway left
  for (const name of [...LANGUAGE, ...HOST, 'globalThis']) {
    const d = getOwnPropertyDescriptor(globalThis, name);
    if (!d) continue;
    const value = globalThis[name];
    defineProperty(globalThis, name, { value, writable: false, enumerable: d.enumerable, configurable: false });
    if (value !== globalThis) roots.push(value);
  }
  for (const reach of HIDDEN) {
    try { roots.push(reach()); } catch { /* not in this Node */ }
  }
  for (const [obj, keys] of DERIVED) for (const key of keys) overridable(obj, key);
  for (const root of roots) freezeFrom(root);
}

// What the kit's own modules in a scenario's process export, frozen too: the workspace's code can import each of
// them by its URL and gets the very module the scenario uses. A verifier's workspace once rewrote a scenario's
// table of seeds that way, in three lines, so that a seed collision it had went unseen. A value that freezing
// cannot keep unchanged (a Map, a Set, a Date, a typed array) is refused.
const UNFREEZABLE = [[types.isMap, 'a Map'], [types.isSet, 'a Set'], [types.isWeakMap, 'a WeakMap'],
  [types.isWeakSet, 'a WeakSet'], [types.isDate, 'a Date'], [types.isAnyArrayBuffer, 'an ArrayBuffer'],
  [types.isArrayBufferView, 'a typed array or DataView'], [types.isPromise, 'a promise'], [types.isProxy, 'a Proxy']];

function freezeExports(href, ns) {
  for (const name of ownKeys(ns)) {
    if (typeof name !== 'string') continue;
    freezeFrom(ns[name], (o) => {
      const hit = UNFREEZABLE.find(([is]) => is(o));
      return hit && `${href} exports ${name}, which holds ${hit[1]}: freezing cannot keep it from the workspace's `
        + "code, which shares a scenario's process, so a module a scenario imports exports none (demos/AUTHORING.md)";
    });
  }
}

installClocks();
harden();

// ---- the calls ----

// Writes the answer line. It is ASCII, so a byte written is a character written; fd 1 is non-blocking once
// anything in this process has used process.stdout as a pipe, hence the EAGAIN.
function send(answer) {
  let rest = `\n${MARK}${KEY}:${serialize(answer).toString('base64')}\n`;
  while (rest.length) {
    try {
      rest = rest.slice(writeSync(1, rest));
    } catch (e) {
      if (!e || e.code !== 'EAGAIN') throw e;
    }
  }
}

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

// A workspace module that the permission model kept from loading, as a scenario's load() rejects with it: its
// message says so and names the flag on every Node (messageOf), since a scenario that reports why a module did not
// load reports the message, and on 22.13 that said only "Access to this API has been restricted". Node rejects
// every import of a module that failed with the one error, so each is described once.
const described = new WeakSet();

function refusal(e) {
  if (text(() => e.code) !== 'ERR_ACCESS_DENIED' || described.has(e)) return e;
  const message = messageOf(e);
  try {
    e.message = message;
    described.add(e);
    return e;
  } catch {
    return new Error(message);
  }
}

function errorOf(e) {
  if (e === null || (typeof e !== 'object' && typeof e !== 'function')) {
    return { name: 'a thrown value', message: text(() => e), range: false };
  }
  return { name: text(() => e.name), message: messageOf(e), range: e instanceof RangeError };
}

function copiedOut(value) {
  try {
    serialize(value);
    return null;
  } catch (e) {
    const message = `it returned a value that cannot be copied out of its process (${text(() => e.message)})`;
    return { ok: false, error: { name: 'DataCloneError', message, range: false } };
  }
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
  return copiedOut(value) || { ok: true, value };
}

// A scenario (probe.mjs's scenario()): --scenario <its file URL> <export> <workspace folder URL> <args, v8, base64>
// <the file URLs of the kit's modules it imports, the scenario's own included, v8, base64>. Its function gets
// { load, withoutClocks }, then the args: load imports a module of the workspace by its path there (a module
// the permission model refused rejects with refusal's message), and withoutClocks(fn) runs fn with the clocks
// taken away (above).
async function runScenario([scenarioHref, name, wsHref, request, modules]) {
  const args = deserialize(Buffer.from(request, 'base64'));
  const mod = await import(scenarioHref);
  if (typeof mod[name] !== 'function') {
    return { loadError: `TypeError: the scenario module exports no function ${name}` };
  }
  for (const href of deserialize(Buffer.from(modules, 'base64'))) freezeExports(href, await import(href));
  const load = (rel) => apply(then, import(new URL(String(rel), wsHref).href), [undefined, (e) => {
    throw refusal(e);
  }]);
  let value;
  try {
    value = await mod[name](freeze({ load, withoutClocks }), ...args);
  } catch (e) {
    return { results: [{ ok: false, error: errorOf(e) }] };
  }
  return { results: [copiedOut(value) || { ok: true, value }] };
}

let answer;
try {
  if (ARGV[0] === '--scenario') {
    answer = await runScenario(ARGV.slice(1));
  } else {
    const [href, request] = ARGV;
    const calls = deserialize(Buffer.from(request, 'base64'));
    const mod = await import(href);
    answer = { results: calls.map((c) => call(mod, c)) };
  }
} catch (e) {
  answer = { loadError: `${text(() => e.name)}: ${messageOf(e)}` };
}
send(answer);
exit(0);
