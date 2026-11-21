// Item 2: Seeded random numbers. Runs beside the workspace (demos/probe.mjs, scenario()) and returns what the
// workspace's createRng and nextFloat gave, as the numbers themselves; 02-rng.test.mjs compares.
import { J, observed } from './fixtures.mjs';

export const SEEDS = [0, 1, 2, 3, 7, 8, 9, 15, 16, 255, 256, 65535, 65536, 65537, 65793, 1000000, 2147483647, 2147483648, 3000000000, 4294901760, 4294901761, 4294967291, 4294967292, 4294967293, 4294967294, 4294967295, 123456789];
export const N = 10000;

export async function run({ load }) {
  const { createRng, nextFloat } = await load('src/rng.js');
  const out = {};

  const r = createRng(42);
  out.state = structuredClone(r);
  out.stateJson = J(r);
  out.stateSeen = observed(r, 'the random state');
  out.draws = Array.from({ length: N }, () => nextFloat(r));

  const a = createRng(7);
  const b = createRng(7);
  out.sameSeed = Array.from({ length: 50 }, () => [nextFloat(a), nextFloat(b)]);

  const c = createRng(9);
  for (let i = 0; i < 5; i++) nextFloat(c);
  const copy = JSON.parse(J(c));
  out.copied = Array.from({ length: 25 }, () => [nextFloat(c), nextFloat(copy)]);

  const s = createRng(5);
  out.advancing = [J(s)];
  for (let i = 0; i < 5; i++) {
    nextFloat(s);
    out.advancing.push(J(s));
  }
  const again = createRng(5);
  out.twoInARow = [nextFloat(again), nextFloat(again)];

  out.streams = SEEDS.map((seed) => {
    const g = createRng(seed);
    return Array.from({ length: 6 }, () => nextFloat(g));
  });
  return out;
}
