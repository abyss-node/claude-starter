// Shared by the held-out tests and by their scenarios. It holds the grader's own geometry and nothing that
// touches the workspace, so a workspace cannot pass by agreeing with itself: the workspace's code runs in
// processes of its own (../../probe.mjs) and what comes back is checked with the functions below.

// The grader's own PRNG for random inputs (mulberry32).
export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function distToLoop(points, x, y) {
  let best = Infinity;
  let bi = 0;
  const n = points.length;
  for (let i = 0; i < n; i++) {
    const a = points[i];
    const b = points[(i + 1) % n];
    const ex = b.x - a.x;
    const ey = b.y - a.y;
    const l2 = ex * ex + ey * ey;
    let t = l2 > 0 ? ((x - a.x) * ex + (y - a.y) * ey) / l2 : 0;
    t = Math.max(0, Math.min(1, t));
    const dx = x - (a.x + ex * t);
    const dy = y - (a.y + ey * t);
    const d = dx * dx + dy * dy;
    if (d < best) {
      best = d;
      bi = i;
    }
  }
  return { dist: Math.sqrt(best), index: bi };
}

function orient(a, b, c) {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

export function properCross(p1, p2, p3, p4) {
  return orient(p3, p4, p1) * orient(p3, p4, p2) < 0 && orient(p1, p2, p3) * orient(p1, p2, p4) < 0;
}

export function cumulative(points) {
  const cum = [0];
  for (let i = 1; i < points.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y));
  }
  const last = points[points.length - 1];
  const total = cum[cum.length - 1] + Math.hypot(points[0].x - last.x, points[0].y - last.y);
  return { cum, total };
}

export function tangent(points, i) {
  const n = points.length;
  const at = (k) => points[((k % n) + n) % n];
  const a = at(i - 1);
  const b = at(i + 1);
  const l = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  return { x: (b.x - a.x) / l, y: (b.y - a.y) / l };
}

// Throws with a reason if the track is not a usable closed loop.
export function assertValidLoop(track, label) {
  const pts = track.centerline;
  const fail = (why) => {
    throw new Error(`${label}: ${why}`);
  };
  if (!Array.isArray(pts) || pts.length < 32 || pts.length > 5000) fail(`centerline needs 32..5000 points, has ${pts?.length}`);
  if (!(track.width > 0) || !(track.verge > 0)) fail('width and verge must be positive numbers');
  for (const p of pts) if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) fail('centerline has a non-finite point');
  const n = pts.length;
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % n];
    const l = Math.hypot(b.x - a.x, b.y - a.y);
    if (!(l > 1e-6)) fail(`segment ${i} has zero length (duplicate point, or first point repeated at the end)`);
    sum += l;
  }
  const closing = Math.hypot(pts[0].x - pts[n - 1].x, pts[0].y - pts[n - 1].y);
  if (closing > 4 * (sum / n)) fail(`the closing segment is ${closing.toFixed(1)} long, the loop does not close smoothly`);
  for (let i = 0; i < n; i++) {
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue;
      if (properCross(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n])) fail(`centerline crosses itself (segments ${i} and ${j})`);
    }
  }
  const { cum, total } = cumulative(pts);
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const along = Math.min(cum[j] - cum[i], total - (cum[j] - cum[i]));
      if (along <= 3 * track.width) continue;
      const d = Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y);
      if (d < track.width) fail(`road overlaps itself: points ${i} and ${j} are ${d.toFixed(1)} apart but ${along.toFixed(0)} apart along the road`);
    }
  }
}

export function inputsAt(r, wild) {
  if (wild && r() < 0.05) {
    const odd = [NaN, Infinity, -Infinity, 5, -5, undefined];
    return { throttle: odd[Math.floor(r() * odd.length)], brake: odd[Math.floor(r() * odd.length)], steer: odd[Math.floor(r() * odd.length)] };
  }
  return { throttle: r() < 0.8 ? r() : 0, brake: r() < 0.15 ? r() : 0, steer: r() * 2 - 1 };
}

// Turn radius of a path sampled one point per tick: arc length over the angle turned.
export function arcRadius(pts) {
  let arc = 0;
  let turned = 0;
  let prev = null;
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i].x - pts[i - 1].x;
    const dy = pts[i].y - pts[i - 1].y;
    arc += Math.hypot(dx, dy);
    const ang = Math.atan2(dy, dx);
    if (prev !== null) {
      let d = ang - prev;
      while (d > Math.PI) d -= 2 * Math.PI;
      while (d < -Math.PI) d += 2 * Math.PI;
      turned += d;
    }
    prev = ang;
  }
  return arc / Math.max(1e-9, Math.abs(turned));
}

export function totalLength(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    s += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return s;
}

export function wrapAngle(a) {
  return Math.atan2(Math.sin(a), Math.cos(a));
}

// A recorded run (a scenario's `players`, per-tick arrays, and its `nonFinite` list): the numbers of tick t.
export function assertFiniteAt(run, t) {
  for (const bad of run.nonFinite) {
    if (bad.tick === t) throw new Error(`tick ${t}: player ${bad.player} field ${bad.field} is ${bad.value}`);
  }
  run.players.forEach((p, i) => {
    for (const f of ['x', 'y', 'heading', 'speed']) {
      if (!Number.isFinite(p[f][t])) throw new Error(`tick ${t}: player ${i} ${f} is ${p[f][t]}`);
    }
    if (!(p.speed[t] >= 0)) throw new Error(`tick ${t}: player ${i} speed is ${p.speed[t]}; it is a magnitude, never below 0`);
  });
}
