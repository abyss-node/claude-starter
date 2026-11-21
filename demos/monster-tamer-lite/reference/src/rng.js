// Seeded random numbers. The state is a plain object so it travels inside saves and battles.

function toU32(seed) {
  const n = Number(seed);
  return Number.isFinite(n) ? Math.floor(n) >>> 0 : 0;
}

export function createRng(seed) {
  return { s: toU32(seed) };
}

// Advances the state in place and returns a float in [0, 1).
export function nextFloat(rng) {
  rng.s = (rng.s + 0x6d2b79f5) >>> 0;
  let t = rng.s;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
