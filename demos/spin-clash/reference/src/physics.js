// Spin Clash physics: tops in a bowl, advanced on a fixed timestep.
// The world is plain data (numbers, strings, arrays), so it can be copied with
// JSON and stepped on any machine with the same result. No Math.random, no clock.

export const DT = 1 / 60;

export const LIMITS = {
  mass: [0.5, 3],
  radius: [0.05, 0.2],
  friction: [0, 1],
};

export const DEFAULTS = {
  arenaRadius: 1,
  slope: 1.2,
  steer: 2.5,
  minSpin: 4,
  friction: true,
};

const BASE_SPIN_DECAY = 0.6; // rad/s lost every second, whatever the top's friction
const SPIN_DECAY_PER_FRICTION = 1.4;
const SPIN_DRAG = 0.01; // proportional spin loss per second
const BASE_DRAG = 0.05; // linear velocity damping per second
const DRAG_PER_FRICTION = 0.5;
const RESTITUTION_WITH_FRICTION = 0.9;
const MAX_TOPS = 8;

const ROSTER = ['Kestrel', 'Old Ballast', 'Thistle', 'Lantern', 'Wren', 'Copperhull', 'Nettle', 'Quill'];

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const num = (v, fallback) => (finite(v) ? v : fallback);

// mulberry32: one uint32 of state, so it lives in the world as a plain number.
function nextRandom(world) {
  let t = (world.rng + 0x6d2b79f5) >>> 0;
  world.rng = t;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

export function inertia(top) {
  return 0.5 * top.mass * top.radius * top.radius;
}

export function createWorld(config = {}) {
  const seed = num(config.seed, 1) >>> 0;
  const settings = {
    arenaRadius: Math.max(0.1, num(config.arenaRadius, DEFAULTS.arenaRadius)),
    slope: Math.max(0, num(config.slope, DEFAULTS.slope)),
    steer: Math.max(0, num(config.steer, DEFAULTS.steer)),
    minSpin: Math.max(0, num(config.minSpin, DEFAULTS.minSpin)),
    friction: config.friction !== false,
  };
  const world = { seed, tick: 0, rng: seed, winner: null, config: settings, tops: [] };

  const specs = Array.isArray(config.tops) && config.tops.length > 0
    ? config.tops.slice(0, MAX_TOPS)
    : [{}, {}];
  const R = settings.arenaRadius;
  const baseAngle = nextRandom(world) * 2 * Math.PI;

  specs.forEach((raw, i) => {
    const spec = raw && typeof raw === 'object' ? raw : {};
    const angle = baseAngle + (i * 2 * Math.PI) / specs.length;
    const dist = R * (0.45 + 0.15 * nextRandom(world));
    const orbit = 0.2 + 0.3 * nextRandom(world);
    const spinJitter = nextRandom(world);
    world.tops.push({
      name: typeof spec.name === 'string' && spec.name ? spec.name : ROSTER[i % ROSTER.length],
      mass: clamp(num(spec.mass, 1), ...LIMITS.mass),
      radius: clamp(num(spec.radius, 0.1), ...LIMITS.radius),
      friction: clamp(num(spec.friction, 0.4), ...LIMITS.friction),
      x: num(spec.x, Math.cos(angle) * dist),
      y: num(spec.y, Math.sin(angle) * dist),
      vx: num(spec.vx, -Math.sin(angle) * orbit),
      vy: num(spec.vy, Math.cos(angle) * orbit),
      spin: Math.max(0, num(spec.spin, 40 + 20 * spinJitter)),
      status: 'in',
    });
  });
  return world;
}

// Resolve one contact between tops i and j. Returns true when an impulse was applied.
export function collide(world, i, j) {
  const a = world.tops[i];
  const b = world.tops[j];
  let nx = b.x - a.x;
  let ny = b.y - a.y;
  const d = Math.hypot(nx, ny);
  const reach = a.radius + b.radius;
  if (d >= reach) return false;
  if (d > 1e-9) {
    nx /= d;
    ny /= d;
  } else {
    nx = 1; // coincident centres: push apart along +x, deterministically
    ny = 0;
  }

  const ima = 1 / a.mass;
  const imb = 1 / b.mass;
  // Separate the overlap, split by inverse mass (moves positions only).
  const push = (reach - d) / (ima + imb);
  a.x -= nx * push * ima;
  a.y -= ny * push * ima;
  b.x += nx * push * imb;
  b.y += ny * push * imb;

  const vn = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
  if (vn >= 0) return false; // already separating

  const e = world.config.friction ? RESTITUTION_WITH_FRICTION : 1;
  const jn = (-(1 + e) * vn) / (ima + imb);
  a.vx -= jn * ima * nx;
  a.vy -= jn * ima * ny;
  b.vx += jn * imb * nx;
  b.vy += jn * imb * ny;

  if (world.config.friction) {
    // Both tops spin the same way, so their rims rub against each other at the
    // contact. Coulomb friction turns some spin into a sideways shove. The impulse
    // is capped so it never reverses the slip and never drives a spin below zero:
    // spin is only ever lost, and the contact never creates energy.
    const tx = -ny;
    const ty = nx;
    const Ia = inertia(a);
    const Ib = inertia(b);
    const slip = (a.vx - b.vx) * tx + (a.vy - b.vy) * ty + a.spin * a.radius + b.spin * b.radius;
    if (slip > 0) {
      const K = ima + imb + (a.radius * a.radius) / Ia + (b.radius * b.radius) / Ib;
      const mu = (a.friction + b.friction) / 2;
      const jt = Math.min(mu * jn, slip / K, (a.spin * Ia) / a.radius, (b.spin * Ib) / b.radius);
      if (jt > 0) {
        a.vx -= jt * ima * tx;
        a.vy -= jt * ima * ty;
        b.vx += jt * imb * tx;
        b.vy += jt * imb * ty;
        a.spin = Math.max(0, a.spin - (jt * a.radius) / Ia);
        b.spin = Math.max(0, b.spin - (jt * b.radius) / Ib);
      }
    }
  }
  return true;
}

function readInput(inputs, i) {
  const inp = Array.isArray(inputs) ? inputs[i] : null;
  if (!inp || typeof inp !== 'object') return [0, 0];
  return [clamp(num(inp.x, 0), -1, 1), clamp(num(inp.y, 0), -1, 1)];
}

export function step(world, inputs) {
  const { slope, steer, friction, arenaRadius, minSpin } = world.config;
  const tops = world.tops;

  tops.forEach((top, i) => {
    if (top.status !== 'in') return;
    const [ix, iy] = readInput(inputs, i);
    let ax = -slope * top.x + steer * ix;
    let ay = -slope * top.y + steer * iy;
    if (friction) {
      const drag = BASE_DRAG + DRAG_PER_FRICTION * top.friction;
      ax -= drag * top.vx;
      ay -= drag * top.vy;
      const loss = (BASE_SPIN_DECAY + SPIN_DECAY_PER_FRICTION * top.friction + SPIN_DRAG * top.spin) * DT;
      top.spin = Math.max(0, top.spin - loss);
    }
    // Semi-implicit Euler: velocity first, then position with the new velocity.
    top.vx += ax * DT;
    top.vy += ay * DT;
    top.x += top.vx * DT;
    top.y += top.vy * DT;
  });

  for (let i = 0; i < tops.length; i++) {
    if (tops[i].status !== 'in') continue;
    for (let j = i + 1; j < tops.length; j++) {
      if (tops[j].status !== 'in') continue;
      collide(world, i, j);
    }
  }

  for (const top of tops) {
    if (top.status !== 'in') continue;
    if (Math.hypot(top.x, top.y) > arenaRadius) top.status = 'ringout';
    else if (top.spin <= minSpin) top.status = 'spundown';
  }

  world.tick += 1;
  if (world.winner === null && tops.length >= 2) {
    const alive = [];
    tops.forEach((t, i) => { if (t.status === 'in') alive.push(i); });
    if (alive.length <= 1) world.winner = alive.length === 1 ? alive[0] : -1;
  }
  return world;
}
