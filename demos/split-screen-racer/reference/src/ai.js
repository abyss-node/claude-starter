// A simple deterministic driver: chase a point ahead on the centreline, slow for bends.

import { closestOnLoop, wrapAngle } from './geom.js';

function curvatureRadius(pts, i, span) {
  const n = pts.length;
  const a = pts[(i - span + n) % n];
  const b = pts[i % n];
  const c = pts[(i + span) % n];
  const ab = Math.hypot(b.x - a.x, b.y - a.y);
  const bc = Math.hypot(c.x - b.x, c.y - b.y);
  const ca = Math.hypot(a.x - c.x, a.y - c.y);
  const cross = Math.abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x));
  if (cross < 1e-9) return Infinity;
  return (ab * bc * ca) / (2 * cross);
}

export function aiInput(race, index) {
  const p = race.players[index];
  const pts = race.track.centerline;
  const n = pts.length;
  const spacing = race.track.length ? race.track.length / n : 20;
  const near = closestOnLoop(pts, p.x, p.y);

  const lookahead = 50 + p.speed * 0.35;
  const k = Math.max(2, Math.round(lookahead / spacing));
  const target = pts[(near.index + k) % n];
  const err = wrapAngle(Math.atan2(target.y - p.y, target.x - p.x) - p.heading);
  const steer = Math.max(-1, Math.min(1, err * 2.2));

  // Slowest safe speed over the stretch we could still brake for.
  const spec = p.spec;
  const brakeDist = (p.speed * p.speed) / (2 * spec.brakeDecel) + 80;
  const steps = Math.max(3, Math.round(brakeDist / spacing));
  let desired = spec.topSpeed;
  for (let s = 1; s <= steps; s += 2) {
    const r = curvatureRadius(pts, near.index + s, 3);
    desired = Math.min(desired, 0.8 * r * spec.turnRate);
  }
  desired = Math.max(desired, 60);
  if (Math.abs(err) > 0.9) desired = Math.min(desired, 90);

  return {
    throttle: p.speed < desired ? 1 : 0,
    brake: p.speed > desired * 1.08 ? 1 : 0,
    steer,
  };
}
