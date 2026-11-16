// Small 2D helpers shared by the track, the race and the AI. No DOM.

export const TAU = Math.PI * 2;

export function wrapAngle(a) {
  return a - TAU * Math.floor((a + Math.PI) / TAU);
}

function orient(ax, ay, bx, by, cx, cy) {
  return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

// True when segment p1-p2 and segment p3-p4 cross. Touching at an end point counts
// on one side only (half-open), so a path that ends exactly on a gate and the next
// path that starts there count the crossing once.
export function segmentsCross(p1, p2, p3, p4) {
  const d1 = orient(p3.x, p3.y, p4.x, p4.y, p1.x, p1.y);
  const d2 = orient(p3.x, p3.y, p4.x, p4.y, p2.x, p2.y);
  const d3 = orient(p1.x, p1.y, p2.x, p2.y, p3.x, p3.y);
  const d4 = orient(p1.x, p1.y, p2.x, p2.y, p4.x, p4.y);
  const s1 = d1 > 0 ? 1 : d1 < 0 ? -1 : 0;
  const s2 = d2 > 0 ? 1 : d2 < 0 ? -1 : 0;
  if (s1 === 0 && s2 === 0) return false; // collinear: moving along a gate is not crossing it
  if (s1 === s2 || s2 === 0) return false; // ending on the gate waits for the next segment
  return d3 * d4 < 0 || (d3 === 0) !== (d4 === 0);
}

// Proper crossing only, for self-intersection checks.
export function segmentsIntersectStrict(p1, p2, p3, p4) {
  const d1 = orient(p3.x, p3.y, p4.x, p4.y, p1.x, p1.y);
  const d2 = orient(p3.x, p3.y, p4.x, p4.y, p2.x, p2.y);
  const d3 = orient(p1.x, p1.y, p2.x, p2.y, p3.x, p3.y);
  const d4 = orient(p1.x, p1.y, p2.x, p2.y, p4.x, p4.y);
  return d1 * d2 < 0 && d3 * d4 < 0;
}

// Nearest point on a closed polyline. Returns the segment index, the point, and the distance.
export function closestOnLoop(points, x, y) {
  const n = points.length;
  let best = Infinity;
  let bi = 0;
  let bx = points[0].x;
  let by = points[0].y;
  let bt = 0;
  for (let i = 0; i < n; i++) {
    const a = points[i];
    const b = points[(i + 1) % n];
    const ex = b.x - a.x;
    const ey = b.y - a.y;
    const len2 = ex * ex + ey * ey;
    let t = len2 > 0 ? ((x - a.x) * ex + (y - a.y) * ey) / len2 : 0;
    if (t < 0) t = 0;
    else if (t > 1) t = 1;
    const px = a.x + ex * t;
    const py = a.y + ey * t;
    const d2 = (x - px) * (x - px) + (y - py) * (y - py);
    if (d2 < best) {
      best = d2;
      bi = i;
      bx = px;
      by = py;
      bt = t;
    }
  }
  return { index: bi, t: bt, x: bx, y: by, dist: Math.sqrt(best) };
}

export function loopLength(points) {
  let s = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    s += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return s;
}

// Closed Catmull-Rom spline through control points, then resampled to even spacing.
export function smoothLoop(ctrl, spacing) {
  const n = ctrl.length;
  const dense = [];
  for (let i = 0; i < n; i++) {
    const p0 = ctrl[(i - 1 + n) % n];
    const p1 = ctrl[i];
    const p2 = ctrl[(i + 1) % n];
    const p3 = ctrl[(i + 2) % n];
    const steps = 24;
    for (let s = 0; s < steps; s++) {
      const t = s / steps;
      const t2 = t * t;
      const t3 = t2 * t;
      dense.push({
        x: 0.5 * (2 * p1.x + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3),
        y: 0.5 * (2 * p1.y + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3),
      });
    }
  }
  const total = loopLength(dense);
  const count = Math.max(32, Math.round(total / spacing));
  const step = total / count;
  const out = [];
  let seg = 0;
  let segStart = 0;
  let segLen = Math.hypot(dense[1].x - dense[0].x, dense[1].y - dense[0].y);
  for (let k = 0; k < count; k++) {
    const target = k * step;
    while (segStart + segLen < target && seg < dense.length - 1) {
      segStart += segLen;
      seg++;
      const a = dense[seg];
      const b = dense[(seg + 1) % dense.length];
      segLen = Math.hypot(b.x - a.x, b.y - a.y);
    }
    const a = dense[seg];
    const b = dense[(seg + 1) % dense.length];
    const t = segLen > 0 ? (target - segStart) / segLen : 0;
    out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
  }
  return out;
}

export function tangentAt(points, i) {
  const n = points.length;
  const a = points[(i - 1 + n) % n];
  const b = points[(i + 1) % n];
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const l = Math.hypot(dx, dy) || 1;
  return { x: dx / l, y: dy / l };
}
