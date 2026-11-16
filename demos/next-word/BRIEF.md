# Next Word: a tiny language model you can poke

**Tier:** S, browser. **Expected:** one session. **Needs:** Node 22 or newer and Python 3 (only to serve the page). No npm packages.

## What to build

A single web page that shows how a language model picks the next word.

You type a few words. A tiny model, counted from a short built-in story when the page loads, shows the words it thinks could come next as horizontal bars, one per word, longest first. Three sliders change how it chooses: **temperature**, **top-k** and **top-p**. A **seed** box you can type a number into, a **New random seed** button and a **Sample** button generate the next dozen words with the seed in the box, and the same seed with the same slider settings always writes the same words. The button fills the box with a fresh random seed, so you can always see which seed was used. When you type something the model has never seen, the page says so and shows what it falls back to.

The model is an n-gram counter, not a neural network: it counts which word followed which one or two words in the story. That is enough to show what the sliders do.

Write the story yourself (or use text you know is public domain). Keep it short: at least 200 tokens (words plus punctuation), under 20,000 characters. Repetition helps; a story where "the" is followed by several different words makes better bars.

## Layout

The logic lives in plain ES modules so it can be tested without a browser. These names are fixed, because a test you cannot see imports them:

```
index.html        the page
src/corpus.js     export const CORPUS   (the story, a string)
src/lm.js         tokenize, train, nextDistribution
src/sampling.js   applySettings, createRng, sampleToken, generate
src/seed.js       parseSeed, newSeed
package.json      already here; leave its "test" script alone
```

Serve it with `python -m http.server 8000` in this folder and open http://localhost:8000 (opening the file directly does not load modules).

### The model (`src/lm.js`)

- `tokenize(text)` returns an array of tokens. Lower-case the text. A token is a run of the letters a-z, the digits 0-9 and apostrophes, or one of the punctuation marks `. ! ? , ; :` on its own. Everything else (spaces, quotes, dashes, brackets, other letters) separates tokens and is dropped. `"Don't STOP!"` gives `["don't", "stop", "!"]`. Apostrophes count wherever they sit, so `'tis` and `dogs'` are one token each and a lone `'` between spaces is a token of its own.
- `train(text, order = 3)` returns a model. `order` n means the model looks at up to n-1 previous tokens, for any n (order 4 uses up to three, order 6 up to five); order 1 is plain word frequency; leaving `order` out means 3. The whole text is one stream of tokens: punctuation is a token, and counting runs straight across sentence ends.
- `nextDistribution(model, context)` takes a string (tokenized as above) or an array of tokens and returns `{ entries, usedContext }`. `entries` is an array of `{ token, p }`, probabilities from the counts, summing to 1. `usedContext` is the array of tokens it actually used.
- **Sort order, everywhere:** highest `p` first; equal `p` sorted by the token string in plain JavaScript `<` order, code unit by code unit (so `"."` comes before `"cat"`, and punctuation and digits tie-break as `! , . 0 : ; ?`). Not `localeCompare`, which orders punctuation differently.
- **Backoff rule:** use the longest ending of the context, at most order-1 tokens, that was followed by at least one token in the training text. If no ending was, fall back to the frequency of every token in the training text, with `usedContext` empty. A word seen only as the very last token was never followed by anything, so it counts as unseen. An empty model returns an empty `entries` list rather than throwing.

### The choosing (`src/sampling.js`)

- `applySettings(entries, { temperature = 1, topK = 0, topP = 1 })` returns a new list of the entries that survive, sorted as above, with probabilities summing to 1. It does not change its input. It drops entries with `p` of 0 or less first (they never appear in the result, whatever the other settings), and accepts input that does not sum to 1. Steps, in this order:
  1. **Temperature** T: each `p` becomes proportional to `p^(1/T)`. T = 1 changes nothing, below 1 sharpens, above 1 flattens. **T = 0 (or below) keeps only the first entry**, with p = 1.
  2. **Top-k:** keep the first k entries and renormalise. k = 0 means off; k at or above the number of entries keeps them all.
  3. **Top-p:** on the renormalised list from step 2, keep the shortest run from the top whose running total reaches p (a total within 1e-12 of p counts as reaching it: 0.3 + 0.3 + 0.3 reaches 0.9 even though floating point makes it 0.8999999999999999), then renormalise. Always keep at least one. p = 1 keeps all.
- `createRng(seed)` returns a function giving floats in [0, 1). The same seed gives the same stream; different seeds give different streams, and that holds for every whole number from 0 to 4294967295: 0 is not 1, 1 is not 8, 1 is not 65537, and the biggest seeds are not each other's twins. A generator that uses only part of the seed (the remainder after dividing by 7, the low 16 bits) fails. Any small seeded generator will do (mulberry32 is a common choice). Never `Math.random`.
- `sampleToken(entries, rng)` draws one number r = `rng()` and walks the list in order, returning the first token where r is below the running total. If rounding leaves none, it returns the last token.
- `generate(model, prompt, { length = 10, seed = 1, temperature, topK, topP })` makes one generator from the seed, then repeats `length` times: get the distribution for the context so far, apply all three settings with `applySettings`, pick a token with `sampleToken` using that same generator (one draw per token), append it. It returns the array of new tokens, stopping early only if the model has nothing to offer.

### The seed (`src/seed.js`)

Kept in a module of its own so node can test it without a browser.

- `parseSeed(text)` takes the text of the seed box. Spaces around it are ignored. If what is left is one or more digits 0-9 and the number is at most 4294967295, it returns that number (`"007"` gives 7). Anything else (empty, letters, a minus sign, a decimal point, too big) returns `null`.
- `newSeed(rng = Math.random)` draws one number r from `rng` and returns the integer `1 + Math.floor(r * 999999)`, so always a whole number from 1 to 999999 inclusive. This is the one place `Math.random` is fine, as the default source.
- A seed typed into the box, or made by `newSeed`, goes through `parseSeed` and then into `generate` as `seed`: the same seed gives the same text, and different seeds give different text.

### The page (`index.html`)

It loads the modules from `src/` with `<script type="module">` and has these elements, by id:

| id | what |
|---|---|
| `context` | the text box you type in |
| `temperature`, `topk`, `topp` | the three sliders (`<input type="range">`) |
| `seed` | the seed box |
| `newseed` | the New random seed `<button>` |
| `sample` | the Sample `<button>` |
| `bars` | where the bars go |

Show each slider's current value, and say which context the model used or that it backed off.

The seed box is a visible, editable `<input>` (a text-like type: text, number, search or tel, or no type at all; not hidden, read-only or disabled). **New random seed** puts `newSeed()` in the box, so the box always shows the seed in use. **Sample** reads the box with `parseSeed` and passes the result to `generate`; if the box does not hold a valid seed, the page says so and does not sample. The page imports `parseSeed` and `newSeed` from `src/seed.js`.

## Graded

A held-out check you cannot see grades this folder. Prose elsewhere in this brief describes the project and makes no extra promises: only the numbered contracts below are checked, and each is checked by at least one test.

1. **Tokenizing.** `tokenize` lower-cases, then makes a token of each run of the letters a-z, the digits 0-9 and apostrophes (letters and digits share a run: `b2b2`, `4th`, `90's` are one token each), or of each one of `. ! ? , ; :` on its own, even side by side (`Wait... what?!` gives `wait . . . what ? !`). Everything else separates tokens and is dropped: spaces, quotes, dashes, brackets, underscores, accented and other non-ASCII letters and digits, and a curly apostrophe (`snake_case` gives `snake`, `case`; `café` gives `caf`). Apostrophes stay in a token wherever they sit (`'tis`, `dogs'`, `'n'`), and a lone `'` between spaces is a token of its own. Empty text gives `[]`.
2. **Order.** `train(text, order)`: order n uses up to n-1 previous tokens, for any n (1 to 8 are tried); order 1 is plain word frequency; leaving `order` out means 3.
3. **Sentence ends.** Counting runs straight across them: a context may start with, contain or end with `.`, `!` or `?`, and is used whole when the text followed it (after `.` in `The cat sat. The cat ran. The dog sat. A cat sat!` come `the` 2/3 and `a` 1/3).
4. **The distribution.** `nextDistribution(model, context)` takes a string (tokenized as in 1, so case does not matter) or an array of tokens, and returns `{ entries, usedContext }`. Each entry is exactly `{ token, p }`, with `p` the count over the total, and the entries sum to 1. `usedContext` is the array of tokens used.
5. **Backoff.** The longest ending of the context, at most order-1 tokens, that was followed by at least one token wins. If none was, the entries are the frequency of every token in the training text and `usedContext` is `[]`. A token seen only as the very last one counts as unseen. An empty model gives an empty `entries` list, not an error.
6. **Sort order.** Everywhere (the entries of `nextDistribution`, the result of `applySettings`, the cut of top-k): highest `p` first; equal `p` by the token string in plain `<` order, code unit by code unit (`! , . 0 : ; ?`), not `localeCompare`.
7. **The story.** `CORPUS` is a string of at least 200 tokens and at most 20,000 characters, and a model trained on it knows more than one word after `the`.
8. **applySettings, shape.** It returns a new list (a different array from the input, even when nothing is dropped) and leaves its input untouched, even when the input is not in sort order or has ties. It drops entries with `p` of 0 or less first, whatever the other settings, accepts input that does not sum to 1, and returns `[]` for an empty list. For any non-empty input and any temperature (from 0 to 1000), top-k and top-p, the result keeps at least one entry, none is negative or NaN, and the `p` sum to 1 within 1e-9.
9. **Temperature.** 1 (or leaving it out) changes nothing; any other T reshapes each `p` to be proportional to `p^(1/T)`; **T = 0 or below, negative included, keeps only the first entry** with `p` 1 (on a tie, the first in sort order).
10. **Top-k.** Keeps the first k entries and renormalises, ties at the cut broken by the sort order, punctuation included. k = 0 is off; k at or above the number of entries keeps them all.
11. **Top-p.** Keeps the shortest run from the top whose running total reaches p, then renormalises. A total within 1e-12 of p reaches it (0.3 + 0.3 + 0.3 reaches 0.9; 0.5 does not reach 0.500001). At least one entry is always kept, so p = 0 keeps the first entry; p = 1 keeps all.
12. **Order of the steps.** Temperature, then top-k, then top-p on the renormalised result of top-k.
13. **The generator.** `createRng(seed)` gives floats in [0, 1), the same stream for the same seed, and a stream of its own for each of 27 seeds from 0 to 4294967295 (0 is not 1, 1 is not 8, 1 is not 65537, the biggest seeds are not each other's twins; a generator that uses only part of the seed fails).
14. **sampleToken.** Draws one number from the generator per call (also when there is one entry), walks the list in the order given without re-sorting it, and returns the first token where r is below the running total. If rounding, or a list that sums to less than 1, leaves none, it returns the last token. Over many draws the tokens land in proportion to their `p`.
15. **generate, the loop.** One generator from the seed for the whole run; for each of `length` steps one `nextDistribution`, one `applySettings` with all three settings, one `sampleToken` (one draw per token). The result equals that loop run by hand, and is the array of new tokens.
16. **generate, behaviour.** The same seed and settings give the same words and different seeds give different ones. Temperature 0 or below generates the greedy chain; top-k 1 or a top-p of 0.01 gives the greedy chain at any temperature; top-k 2 never leaves the top two at any step. An unknown prompt still generates words from the story; an empty model generates `[]` without an error.
17. **generate, defaults.** With an options object that leaves them out (or sets them to `undefined`): `length` 10, `seed` 1, `temperature` 1, `topK` 0, `topP` 1.
18. **parseSeed.** Spaces around the text are ignored. One or more digits 0-9 whose value is at most 4294967295 give that number, however many leading zeros (`"007"` and `"00000000007"` give 7). Anything else (empty, letters, `-5`, `+5`, `1.5`, `1e3`, `0x10`, `4 2`, a value above 4294967295) gives `null`.
19. **newSeed.** `newSeed(rng = Math.random)` draws exactly once from `rng` and returns a whole number from 1 to 999999 (a draw of 0 gives 1, one just under 1 gives 999999, a larger draw gives a larger seed). With no argument it varies, and the seed it returns parses back to itself through `parseSeed`.
20. **A typed seed drives sampling.** `parseSeed` then `generate`: the same typed seed gives the same text (spaces and leading zeros do not matter), and each of 27 different typed seeds (0, 1, 8, 65537 and the rest) writes a different text on a model with many choices at each step. Seeds from `newSeed` work with `generate` the same way.
21. **The page, elements.** `index.html` has elements with the ids `context`, `temperature`, `topk`, `topp`, `seed`, `newseed`, `sample` and `bars`; `temperature`, `topk` and `topp` are `<input type="range">`, `newseed` and `sample` are `<button>`. The ids are read from the tags themselves, so quoting style and attribute order do not matter (`<input value=7 id=seed>` is fine); comments and script bodies are not searched.
22. **The page, seed box.** `#seed` is an `<input>` of type text, number, search or tel (or no type), with no `readonly`, `disabled` or `hidden` attribute and no inline `display:none` or `visibility:hidden`.
23. **The page, modules.** `index.html` has a `<script type="module">` (quoted or not), references a module under `src/`, loads `src/seed.js`, and uses the names `parseSeed` and `newSeed`. A module is named by a quoted path or a script `src` attribute written `src/x.js`, `./src/x.js` or `/src/x.js` (the last works under `python -m http.server`); a mention inside an HTML comment does not count.
24. **Layout.** `src/corpus.js`, `src/lm.js`, `src/sampling.js`, `src/seed.js` and `index.html` exist, and the modules export the names given under Layout, so that Node can import them with no browser.

## Not graded

The brief describes these, or you might assume them, but the held-out check does not test them. They are yours to judge, in the browser or by reading.

- How the page looks or feels: layout, colours, dark mode; the bars being horizontal, one per word, longest first; showing each slider's current value; saying which context the model used or that it backed off; saying that it has never seen what you typed and showing the fallback.
- Whether anything is wired up: that the sliders, the text box and the buttons change the bars, that **New random seed** puts `newSeed()` in the seed box, that **Sample** reads the box with `parseSeed` and writes a dozen words, and that an invalid seed gets a message and no sample. The page tests read only the ids, the tags' own attributes and the imports.
- A seed box hidden by a stylesheet, a class or a script (only the tag's own attributes and inline `style` are read).
- The story: whether you wrote it yourself, whether it is public domain, whether it is repetitive enough to make good bars. Only its size and that it trains are checked.
- Working conditions: that `package.json`'s `test` script is left alone, that your own tests are under `tests/`, and the `python -m http.server` command.
- Inputs the brief does not define: `train` with an order that is not a whole number of at least 1; `tokenize`, `parseSeed` or `nextDistribution` given something other than text or an array; `sampleToken` on an empty list; `generate` called with no options object, or with a `length` of 0, below 0 or not a whole number.
- Whether `applySettings` hands back the input's own entry objects or copies of them: only that the returned list is a new array and the input is unchanged.
- The exact formula inside `newSeed`: the range, the single draw, the two ends and that a larger draw gives a larger seed are checked, so `Math.max(1, Math.ceil(r * 999999))`, which differs from `1 + Math.floor(r * 999999)` only where `r * 999999` is an exact whole number, passes.
- Which small seeded generator `createRng` uses (mulberry32, xorshift, an LCG), as long as items 13 and 20 hold; and that `generate` never calls `Math.random`, which shows only as a failed repeat.

## Your own tests

Write your own tests as you go, under `tests/`, and run them with `node --test tests/`. `npm test` runs the kit's held-out check; do not change that script.

<!-- for the person at the keyboard: start.py prints what follows and leaves it out of the workspace -->

## What to watch for

This demo exists to show the kit's chain working, not just to get a page built.

- **Your tests passing is not the check passing.** The held-out check was written by someone else against the rules above. If the agent says "done" on the strength of its own tests, ask whether the held-out check ran.
- **Grade it yourself** with the `demo check` line in step 5, not with `npm test`, which the agent can change. If the agent rewrites `test` in `package.json`, `npm test` can pass while that line still says `FAIL`. That line is feedback, not proof: the agent has a shell on this machine, as you do, and could tamper with the kit or the grade, so a measured run counts only after CI re-grades the committed folder (the kit's `demos/MEASURING.md`).
- **The verifier.** Before claiming done, the agent should hand the work to the verifier agent, which re-runs the check itself rather than trusting the summary. If it reports FAIL, that is the system working.
- **The checkpoint.** The commit should carry `Verified:` lines for what was actually run (with the PASS/FAIL count) and `Unverified:` lines for what was only reasoned about, such as "the bars look right". The commit guard rejects a commit without them.
- **Nothing outward without your yes.** No push, no repo creation, unless you say so.

## Try afterwards

1. Add an **order** slider (1 to 4) that retrains the model, and watch how often a short story leaves it only one choice at order 4.
2. Colour the bars by whether a word survived top-k and top-p, so you can see the cut move as you drag.
3. Paste in a different story and compare which words the model is confident about.
