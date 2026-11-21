// Scenarios for Synesthesia's held-out checks. Each runs in a Node process of its own beside the workspace
// (demos/probe.mjs, scenario()), given { load } to reach a workspace module by its path there, and answers with
// plain data: what the workspace's functions returned or did, never a verdict. The tests compare the answers with
// what the brief says. Sounds are rebuilt here from a description (signals.mjs) so that large frames never travel
// on a command line. Nothing here is imported by the tests themselves.

import { framesOf, oneFrame } from './signals.mjs';

const errorOf = (e) => ({ name: String(e?.name), message: String(e?.message), range: e instanceof RangeError });

// ---------------------------------------------------------------- calls with frames made here

function expand(arg, mod) {
  if (arg && typeof arg === 'object' && !Array.isArray(arg)) {
    if ('$frame' in arg) return oneFrame(arg.$frame);
    if ('$call' in arg) {
      const [name, ...rest] = arg.$call;
      return mod[name](...rest.map((a) => expand(a, mod)));
    }
  }
  return arg;
}

// For each call [name, ...args] on the module `file`: { ok: true, value } or { ok: false, error }. An argument
// { $frame: <sound description> } is the first frame of that sound; { $call: [name, ...args] } is the answer of
// another function of the same module, so estimateMode(chroma(frame)) is one call.
export async function apply({ load }, file, calls) {
  const mod = await load(file);
  return calls.map(([name, ...args]) => {
    if (typeof mod[name] !== 'function') return { ok: false, error: { name: 'TypeError', message: `${file} exports no function ${name}`, range: false } };
    try {
      return { ok: true, value: structuredClone(mod[name](...args.map((a) => expand(a, mod)))) };
    } catch (e) {
      return { ok: false, error: errorOf(e) };
    }
  });
}

// ---------------------------------------------------------------- the layout

// What each module exports, and the constants the brief fixes.
export async function layout({ load }, files) {
  const out = {};
  for (const file of files) {
    try {
      const mod = await load(file);
      out[file] = { names: Object.keys(mod) };
    } catch (e) {
      out[file] = { error: `${e?.name}: ${e?.message}` };
    }
  }
  const safety = await load('src/safety.js');
  const synth = await load('src/synth.js');
  return {
    modules: out,
    constants: {
      MAX_FLASHES_PER_SECOND: safety.MAX_FLASHES_PER_SECOND,
      MAX_BRIGHTNESS_SLEW: safety.MAX_BRIGHTNESS_SLEW,
      MAX_ZOOM_SLEW: safety.MAX_ZOOM_SLEW,
      MAX_HUE_SLEW: safety.MAX_HUE_SLEW,
      PATTERN_COUNT: synth.PATTERN_COUNT,
    },
  };
}

// ---------------------------------------------------------------- capture, presets, the limiter, the warning

// detectSupport on environments made here, with real functions in them.
export async function support({ load }) {
  const { detectSupport } = await load('src/capture.js');
  const fn = () => {};
  const envs = [
    {},
    { navigator: {} },
    { navigator: { mediaDevices: { getUserMedia: fn } } },
    { navigator: { mediaDevices: { getDisplayMedia: fn } } },
    { navigator: { mediaDevices: { getUserMedia: fn, getDisplayMedia: fn } }, MediaRecorder: fn },
    { MediaRecorder: fn },
    { navigator: { mediaDevices: { getUserMedia: 'yes' } } },
    { navigator: null },
  ];
  return envs.map((env) => {
    try {
      const s = detectSupport(env);
      return { ok: true, value: { mic: s.mic, display: s.display, file: s.file, record: s.record } };
    } catch (e) {
      return { ok: false, error: errorOf(e) };
    }
  });
}

// PRESETS as plain data.
export async function presets({ load }) {
  const { PRESETS } = await load('src/palette.js');
  return Object.fromEntries(Object.entries(PRESETS).map(([name, p]) => [name, { label: p.label, hues: Array.from(p.hues) }]));
}

// For each list of times: what a fresh limiter's allow(time) answered, in order.
export async function limiters({ load }, sequences) {
  const { createFlashLimiter } = await load('src/safety.js');
  return sequences.map((times) => {
    const lim = createFlashLimiter();
    return times.map((t) => lim.allow(t));
  });
}

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
  };
}

const settle = (fn) => {
  try {
    return { ok: true, value: fn() };
  } catch (e) {
    return { ok: false, error: errorOf(e) };
  }
};

// The first-run warning on storages made here.
export async function warnings({ load }) {
  const { shouldShowWarning, acknowledgeWarning, WARNING_KEY, WARNING_TEXT } = await load('src/safety.js');
  const fresh = fakeStorage();
  const run = {
    key: WARNING_KEY,
    text: WARNING_TEXT,
    first: settle(() => shouldShowWarning(fresh)),
    again: settle(() => shouldShowWarning(fresh)),
    acknowledged: settle(() => acknowledgeWarning(fresh)),
    after: settle(() => shouldShowWarning(fresh)),
    stored: fresh.data[WARNING_KEY],
    earlierVisit: settle(() => shouldShowWarning(fakeStorage({ [WARNING_KEY]: 'yes' }))),
    otherKey: settle(() => shouldShowWarning(fakeStorage({ somethingElse: 'yes' }))),
    otherValues: ['no', '', '1', 'true', 'YES'].map((v) => settle(() => shouldShowWarning(fakeStorage({ [WARNING_KEY]: v })))),
    noStorage: [undefined, null, {}, 5].map((none) => ({ show: settle(() => shouldShowWarning(none)), ack: settle(() => acknowledgeWarning(none)) })),
  };
  const broken = {
    getItem() { throw new Error('blocked'); },
    setItem() { throw new Error('blocked'); },
  };
  run.broken = { show: settle(() => shouldShowWarning(broken)), ack: settle(() => acknowledgeWarning(broken)) };
  return run;
}

// ---------------------------------------------------------------- running a synth

/**
 * Each job { frames | steps, opts, ambient, hash }: a synth made with createSynth(opts) (no argument when `opts`
 * is missing), run over the sound `frames`, or over `steps` in order:
 *   { push: <sound>, after? }   push its frames; with `after`, their times are moved to start `after` seconds
 *                                past the last frame pushed so far
 *   { setPreset: name }         call setPreset and note whether it threw
 *   { setLimiter: on }
 *   { read: label }             note the synth's preset, limiter and state getter
 * `ambient` runs the job with the clocks taken away (the probe's withoutClocks: Math.random, Date.now and
 * performance.now throw); `hash` adds stateHash of each state.
 * Answers { states, segments, hashes?, ops, reads, createError? } or { error }. States are copies taken the moment
 * each push returned.
 */
export async function runs({ load, withoutClocks }, jobs) {
  const { createSynth, stateHash } = await load('src/synth.js');
  return jobs.map((job) => {
    const body = () => {
      const out = { states: [], segments: [], ops: [], reads: [] };
      if (job.hash) out.hashes = [];
      let synth;
      try {
        synth = job.opts === undefined ? createSynth() : createSynth(job.opts);
      } catch (e) {
        out.createError = errorOf(e);
        return out;
      }
      let lastTime = 0;
      for (const step of job.steps ?? [{ push: job.frames }]) {
        if (step.push) {
          let frames = framesOf(step.push);
          if (step.after !== undefined) {
            const by = lastTime + step.after;
            frames = frames.map((f) => ({ ...f, time: f.time + by }));
          }
          const from = out.states.length;
          for (const f of frames) {
            const s = synth.push(f);
            if (job.hash) out.hashes.push(stateHash(s));
            out.states.push(structuredClone(s));
          }
          out.segments.push([from, out.states.length]);
          if (frames.length) lastTime = frames.at(-1).time;
        } else if ('setPreset' in step) {
          try {
            synth.setPreset(step.setPreset);
            out.ops.push({ op: 'setPreset', threw: null });
          } catch (e) {
            out.ops.push({ op: 'setPreset', threw: errorOf(e) });
          }
        } else if ('setLimiter' in step) {
          synth.setLimiter(step.setLimiter);
          out.ops.push({ op: 'setLimiter', threw: null });
        } else if (step.read) {
          out.reads.push({ label: step.read, preset: synth.preset, limiter: synth.limiter, state: structuredClone(synth.state) });
        }
      }
      return out;
    };
    try {
      return job.ambient ? withoutClocks(body) : body();
    } catch (e) {
      return { error: `${e?.name}: ${e?.message}` };
    }
  });
}

// ---------------------------------------------------------------- determinism

// For each seed: twice the first `count` numbers of createRng(seed), with the clocks taken away.
export async function rngStreams({ load, withoutClocks }, seeds, count) {
  const { createRng } = await load('src/synth.js');
  return seeds.map((seed) => {
    try {
      return withoutClocks(() => {
        const stream = () => {
          const r = createRng(seed);
          return Array.from({ length: count }, () => r());
        };
        return { seed, a: stream(), b: stream() };
      });
    } catch (e) {
      return { seed, error: `${e?.name}: ${e?.message}` };
    }
  });
}

// stateHash of one state of a run, of copies of it with the keys in another order, and with each field changed.
export async function hashProbes({ load }, sound, seed) {
  const { createSynth, stateHash } = await load('src/synth.js');
  const synth = createSynth({ seed });
  const states = framesOf(sound).map((f) => synth.push(f));
  const s = states[states.length >> 1];
  const changed = {};
  for (const key of Object.keys(s)) {
    const v = s[key];
    changed[key] = stateHash({ ...s, [key]: typeof v === 'number' ? v + 0.01 : typeof v === 'boolean' ? !v : v === null ? 0 : `${v}x` });
  }
  return {
    state: structuredClone(s),
    hash: stateHash(s),
    copy: stateHash({ ...s }),
    reversed: stateHash(Object.fromEntries(Object.entries(s).reverse())),
    changed,
    tiny: stateHash({ ...s, hue: s.hue + 0.0001 }),
  };
}

// Whether each push gives a state of its own that nothing changes afterwards, and whether edits to returned
// states or to a copy of the state getter reach the synth.
export async function ownership({ load }, sound) {
  const { createSynth, stateHash } = await load('src/synth.js');
  const frames = framesOf(sound).slice(0, 200);
  const synth = createSynth({ seed: 5 });
  const states = [];
  const atReturn = [];
  for (const f of frames) {
    const s = synth.push(f);
    states.push(s);
    atReturn.push(stateHash(s));
  }
  const later = states.map(stateHash);
  const a = createSynth({ seed: 5 });
  const b = createSynth({ seed: 5 });
  const pairs = [];
  frames.slice(0, 80).forEach((f, i) => {
    const sa = a.push(f);
    const sb = b.push(f);
    pairs.push([structuredClone(sa), structuredClone(sb)]);
    if (i === 0) sa.flashes = 9999;
    if (i === 1) sa.pattern = -3;
    if (i === 2) sa.hue = -50;
  });
  const copy = a.state;
  copy.hue = -1;
  return { distinct: new Set(states).size, count: states.length, atReturn, later, pairs, hueAfterCopyEdit: a.state.hue };
}
