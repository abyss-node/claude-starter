// Scenarios for Next Word's held-out checks. Each runs in a Node process of its own beside the workspace
// (demos/probe.mjs, scenario()), given { load } to reach a workspace module by its path there, and answers with
// plain data: what the workspace's functions returned, never a verdict. The tests compare the answers with what
// the brief says. Nothing here is imported by the tests themselves.

const train = (lm, text, order) => (order === undefined ? lm.train(text) : lm.train(text, order));

// For each job { text, order?, context, alsoTokenized? }: the answer of nextDistribution(train(text, order), context),
// and, with alsoTokenized, the answer for tokenize(context) as an array.
export async function dists({ load }, jobs) {
  const lm = await load('src/lm.js');
  return jobs.map((job) => {
    const model = train(lm, job.text, job.order);
    const dist = lm.nextDistribution(model, job.context);
    if (!job.alsoTokenized) return { dist };
    return { dist, viaTokens: lm.nextDistribution(model, lm.tokenize(job.context)) };
  });
}

// What the story is and what a model trained on it says after "the".
export async function story({ load }) {
  const { CORPUS } = await load('src/corpus.js');
  const lm = await load('src/lm.js');
  const isText = typeof CORPUS === 'string';
  return {
    type: typeof CORPUS,
    length: isText ? CORPUS.length : null,
    tokenCount: isText ? lm.tokenize(CORPUS).length : null,
    afterThe: isText ? lm.nextDistribution(lm.train(CORPUS), 'the') : null,
  };
}

// For each job { entries | corpusContext, settings, noSettings?, mutateResult? }: applySettings on a list, the list
// before the call, the list after it (and after the caller changed the result, with mutateResult), and the result.
export async function applied({ load }, jobs) {
  const { applySettings } = await load('src/sampling.js');
  const lm = jobs.some((j) => j.corpusContext !== undefined) ? await load('src/lm.js') : null;
  const corpus = lm ? (await load('src/corpus.js')).CORPUS : null;
  return jobs.map((job) => {
    const input = job.corpusContext === undefined
      ? job.entries
      : lm.nextDistribution(lm.train(corpus), job.corpusContext).entries;
    const before = structuredClone(input);
    const out = job.noSettings ? applySettings(input) : applySettings(input, job.settings);
    const result = structuredClone(out);
    if (job.mutateResult) {
      out.reverse();
      out.pop();
      out.push({ token: 'zzz', p: 1 });
    }
    return { before, after: structuredClone(input), out: result };
  });
}

// For each job { entries | corpusContext, temperature: [...], topK: [...], topP: [...] }: applySettings under every
// combination, with the list before and after.
export async function appliedGrid({ load }, jobs) {
  const { applySettings } = await load('src/sampling.js');
  const lm = jobs.some((j) => j.corpusContext !== undefined) ? await load('src/lm.js') : null;
  const corpus = lm ? (await load('src/corpus.js')).CORPUS : null;
  return jobs.map((job) => {
    const input = job.corpusContext === undefined
      ? job.entries
      : lm.nextDistribution(lm.train(corpus), job.corpusContext).entries;
    const before = structuredClone(input);
    const cells = [];
    for (const temperature of job.temperature) {
      for (const topK of job.topK) {
        for (const topP of job.topP) {
          cells.push({ temperature, topK, topP, out: structuredClone(applySettings(input, { temperature, topK, topP })) });
        }
      }
    }
    return { before, after: structuredClone(input), cells };
  });
}

// For each job { seed, draws, twin? }: the first `draws` numbers of createRng(seed). With twin, two generators of
// the same seed are made first and drawn from in turn: { a, b }.
export async function rngs({ load }, jobs) {
  const { createRng } = await load('src/sampling.js');
  return jobs.map((job) => {
    const a = createRng(job.seed);
    if (!job.twin) return { a: Array.from({ length: job.draws }, () => a()) };
    const b = createRng(job.seed);
    const out = { a: [], b: [] };
    for (let i = 0; i < job.draws; i++) {
      out.a.push(a());
      out.b.push(b());
    }
    return out;
  });
}

// For each job { entries, r, times? }: sampleToken `times` times (once by default) with a generator that always gives
// r and counts its calls: the tokens it returned and the number of draws. With { entries, seed, count } instead:
// how often each token came up in `count` draws from createRng(seed).
export async function sampled({ load }, jobs) {
  const { sampleToken, createRng } = await load('src/sampling.js');
  return jobs.map((job) => {
    if (job.seed !== undefined) {
      const rng = createRng(job.seed);
      const counts = {};
      for (let i = 0; i < job.count; i++) {
        const t = sampleToken(job.entries, rng);
        counts[t] = (counts[t] ?? 0) + 1;
      }
      return { counts };
    }
    let calls = 0;
    const rng = () => {
      calls += 1;
      return job.r;
    };
    const tokens = [];
    for (let i = 0; i < (job.times ?? 1); i++) tokens.push(sampleToken(job.entries, rng));
    return { tokens, calls };
  });
}

// For each spec { text | corpus, order?, runs: [{ prompt, opts, typedSeed?, kinds }] }: one model, and per run the
// answers named in kinds:
//   gen     generate(model, prompt, opts)
//   hand    the loop the brief describes, run by hand with createRng, nextDistribution, applySettings, sampleToken
//   greedy  the first entry of nextDistribution, `greedyLength` times, each appended to the context
//   top2    the first two tokens of nextDistribution at each step of what generate wrote
//   vocab   tokenize(CORPUS)
// typedSeed is a text for parseSeed, whose answer becomes opts.seed.
export async function generated({ load }, specs) {
  const lm = await load('src/lm.js');
  const sampling = await load('src/sampling.js');
  const needsCorpus = specs.some((s) => s.corpus);
  const needsSeed = specs.some((s) => s.runs.some((r) => r.typedSeed !== undefined));
  const corpus = needsCorpus ? (await load('src/corpus.js')).CORPUS : null;
  const seedModule = needsSeed ? await load('src/seed.js') : null;
  return specs.map((spec) => {
    const model = train(lm, spec.corpus ? corpus : spec.text, spec.order);
    return spec.runs.map((run) => {
      const opts = run.opts === undefined ? undefined : { ...run.opts };
      if (run.typedSeed !== undefined) opts.seed = seedModule.parseSeed(run.typedSeed);
      const out = {};
      let generatedTokens = null;
      for (const kind of run.kinds) {
        if (kind === 'gen') {
          generatedTokens = sampling.generate(model, run.prompt, opts);
          out.gen = generatedTokens;
        } else if (kind === 'hand') {
          out.hand = byHand(lm, sampling, model, run.prompt, opts);
        } else if (kind === 'greedy') {
          const context = lm.tokenize(run.prompt);
          out.greedy = [];
          for (let i = 0; i < run.greedyLength; i++) {
            const token = lm.nextDistribution(model, context).entries[0].token;
            out.greedy.push(token);
            context.push(token);
          }
        } else if (kind === 'top2') {
          const context = lm.tokenize(run.prompt);
          out.top2 = generatedTokens.map((token) => {
            const top = lm.nextDistribution(model, context).entries.slice(0, 2).map((e) => e.token);
            context.push(token);
            return top;
          });
        } else if (kind === 'vocab') {
          out.vocab = lm.tokenize(corpus);
        }
      }
      return out;
    });
  });
}

function byHand(lm, sampling, model, prompt, { length, seed, temperature, topK, topP }) {
  const rng = sampling.createRng(seed);
  const context = lm.tokenize(prompt);
  const out = [];
  for (let i = 0; i < length; i++) {
    const kept = sampling.applySettings(lm.nextDistribution(model, context).entries, { temperature, topK, topP });
    if (kept.length === 0) break;
    const token = sampling.sampleToken(kept, rng);
    out.push(token);
    context.push(token);
  }
  return out;
}

// For each draw r: newSeed with a generator that always gives r and counts its calls.
export async function newSeedsFrom({ load }, draws) {
  const { newSeed } = await load('src/seed.js');
  return draws.map((r) => {
    let calls = 0;
    const value = newSeed(() => {
      calls += 1;
      return r;
    });
    return { value, calls };
  });
}

// `count` calls of newSeed with no argument, and what parseSeed makes of each one written as text.
export async function randomSeeds({ load }, count) {
  const { newSeed, parseSeed } = await load('src/seed.js');
  const seeds = [];
  const parsed = [];
  for (let i = 0; i < count; i++) {
    const s = newSeed();
    seeds.push(s);
    parsed.push(parseSeed(String(s)));
  }
  return { seeds, parsed };
}

// `count` seeds from newSeed(createRng(rngSeed)), each written as text, read by parseSeed and given to generate
// twice on a model trained on the story: [{ seed, parsed, a, b }].
export async function newSeedsDrive({ load }, { rngSeed, count, prompt, opts }) {
  const lm = await load('src/lm.js');
  const sampling = await load('src/sampling.js');
  const { newSeed, parseSeed } = await load('src/seed.js');
  const { CORPUS } = await load('src/corpus.js');
  const model = lm.train(CORPUS);
  const rng = sampling.createRng(rngSeed);
  const out = [];
  for (let i = 0; i < count; i++) {
    const seed = newSeed(rng);
    const parsed = parseSeed(String(seed));
    out.push({
      seed,
      parsed,
      a: sampling.generate(model, prompt, { ...opts, seed: parsed }),
      b: sampling.generate(model, prompt, { ...opts, seed: parsed }),
    });
  }
  return out;
}
