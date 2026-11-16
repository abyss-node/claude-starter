// Seed handling for the page: read the seed box, and make a fresh random seed.

export const SEED_MIN = 1;
export const SEED_MAX = 999999;
const PARSE_MAX = 4294967295;

// The text of the seed box -> a whole number 0..4294967295, or null when the text is not one.
export function parseSeed(text) {
  const s = String(text ?? '').trim();
  if (!/^[0-9]+$/.test(s)) return null;
  const n = Number(s);
  return n <= PARSE_MAX ? n : null;
}

// One draw from rng (default Math.random) -> an integer from 1 to 999999 inclusive.
export function newSeed(rng = Math.random) {
  return SEED_MIN + Math.floor(rng() * SEED_MAX);
}
