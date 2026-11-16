// The computer opponent for solo mode. A pure function of the world: it reads
// the world and returns one input, and keeps no state of its own, so the same
// world always gives the same answer. Nothing here calls Math.random or a clock.

// Tuned by hand against an idle opponent and a fleeing one: it wins every match
// against the first and a good share, not all, against the second. It aims at
// where the other top is now, not where it is going, which is what keeps it beatable.
const TUNE = {
  safe: 0.75, // fraction of the rim this top keeps inside of, now and a moment ahead
  coast: 0.15, // seconds of travel at the current speed used for that look-ahead
  stage: 2, // how many contact distances inside the target it lines up before charging
  damp: 1.2, // how hard it brakes while lining up
  gain: 2, // how hard it pulls towards the lining-up point
};

const unit = (x, y) => {
  const d = Math.hypot(x, y);
  return d > 1e-9 ? [x / d, y / d] : [0, 0];
};
const clamp1 = (v) => (v < -1 ? -1 : v > 1 ? 1 : v);

// Input for top `index`: get inside the nearest other top on the line from the
// centre through it, then drive outward through it.
export function aiInput(world, index) {
  const me = world.tops && world.tops[index];
  if (!me || me.status !== 'in') return { x: 0, y: 0 };

  let foe = null;
  let best = Infinity;
  world.tops.forEach((t, i) => {
    if (i === index || t.status !== 'in') return;
    const d = Math.hypot(t.x - me.x, t.y - me.y);
    if (d < best) { best = d; foe = t; }
  });
  if (!foe) return { x: 0, y: 0 };

  const R = world.config.arenaRadius;
  const px = me.x + me.vx * TUNE.coast;
  const py = me.y + me.vy * TUNE.coast;
  if (Math.hypot(me.x, me.y) > TUNE.safe * R || Math.hypot(px, py) > TUNE.safe * R) {
    const [cx, cy] = unit(-px, -py);
    return { x: clamp1(cx), y: clamp1(cy) };
  }

  const tx = foe.x;
  const ty = foe.y;
  const [ux, uy] = unit(tx, ty);
  const reach = me.radius + foe.radius;
  const along = (tx - me.x) * ux + (ty - me.y) * uy;
  const across = -(tx - me.x) * uy + (ty - me.y) * ux;
  let dx;
  let dy;
  if (along > 0.4 * reach && Math.abs(across) < 1.6 * reach) {
    dx = tx + ux * reach - me.x;
    dy = ty + uy * reach - me.y;
  } else {
    const gx = tx - ux * (reach * TUNE.stage);
    const gy = ty - uy * (reach * TUNE.stage);
    dx = (gx - me.x) * TUNE.gain - me.vx * TUNE.damp;
    dy = (gy - me.y) * TUNE.gain - me.vy * TUNE.damp;
  }
  const [ix, iy] = unit(dx, dy);
  return { x: clamp1(ix), y: clamp1(iy) };
}
