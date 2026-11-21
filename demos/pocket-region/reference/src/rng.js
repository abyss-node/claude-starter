// Seeded random numbers. The state is plain data, so it travels with a save.

export function makeRng(seed) {
  return { s: Number(seed) >>> 0 };
}

// Draws one float in [0, 1) and advances the state in place (mulberry32).
export function rngNext(rng) {
  rng.s = (rng.s + 0x6d2b79f5) >>> 0;
  let t = rng.s;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
