// Tracks: one hand-made loop and a seeded generator. Pure data, no DOM.

import { closestOnLoop, loopLength, segmentsIntersectStrict, smoothLoop, tangentAt, TAU } from './geom.js';
import { mulberry32 } from './rng.js';

export const ROAD_WIDTH = 90;
export const VERGE = 60;
const SPACING = 20;

// Hand-made "Hollow Reach": a long back straight, a kink, and a tight double-apex hook.
const HOLLOW_REACH = [
  { x: -900, y: -420 },
  { x: -200, y: -520 },
  { x: 500, y: -520 },
  { x: 1050, y: -380 },
  { x: 1250, y: -60 },
  { x: 1120, y: 300 },
  { x: 760, y: 420 },
  { x: 420, y: 260 },
  { x: 100, y: 180 },
  { x: -120, y: 420 },
  { x: -380, y: 640 },
  { x: -820, y: 600 },
  { x: -1120, y: 300 },
  { x: -1160, y: -120 },
];

export function buildTrack(name, ctrl, checkpointCount = 8) {
  const centerline = smoothLoop(ctrl, SPACING);
  const n = centerline.length;
  const gateHalf = ROAD_WIDTH / 2 + VERGE;
  const checkpoints = [];
  for (let k = 0; k < checkpointCount; k++) {
    const i = Math.round((k * n) / checkpointCount) % n;
    const p = centerline[i];
    const t = tangentAt(centerline, i);
    const nx = -t.y;
    const ny = t.x;
    checkpoints.push({
      a: { x: p.x + nx * gateHalf, y: p.y + ny * gateHalf },
      b: { x: p.x - nx * gateHalf, y: p.y - ny * gateHalf },
    });
  }
  // Two start slots side by side, a little behind the start line.
  const back = centerline[(n - 3) % n];
  const t = tangentAt(centerline, n - 3);
  const heading = Math.atan2(t.y, t.x);
  const side = ROAD_WIDTH / 4;
  const grid = [
    { x: back.x - t.y * side, y: back.y + t.x * side, heading },
    { x: back.x + t.y * side, y: back.y - t.x * side, heading },
  ];
  return { name, width: ROAD_WIDTH, verge: VERGE, centerline, checkpoints, grid, length: loopLength(centerline) };
}

// No proper self-crossings, and parts of the loop that are far apart along the road
// stay at least road + both verges apart, so walls never merge two stretches.
export function isValidTrack(track) {
  const pts = track.centerline;
  const n = pts.length;
  for (let i = 0; i < n; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % n];
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue;
      if (segmentsIntersectStrict(a, b, pts[j], pts[(j + 1) % n])) return false;
    }
  }
  const cum = [0];
  for (let i = 1; i < n; i++) cum.push(cum[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y));
  const total = track.length;
  const minGap = track.width + 2 * track.verge + 10;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const along = Math.min(cum[j] - cum[i], total - (cum[j] - cum[i]));
      if (along < 4 * track.width) continue;
      if (Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y) < minGap) return false;
    }
  }
  return true;
}

export function fixedTrack({ checkpoints = 8 } = {}) {
  return buildTrack('Hollow Reach', HOLLOW_REACH, checkpoints);
}

// Integer seeds 0..2^32-1 feed the generator as they are. Any other seed (negative, past 2^32, not an integer)
// is hashed to a 32-bit key first: truncating it with >>> 0 would make 2^32 + 5, -2^32 + 5 and 5 the same track.
function seedKey(seed) {
  if (Number.isInteger(seed) && seed >= 0 && seed < 2 ** 32) return seed;
  const text = `seed:${String(seed)}`;
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function generateTrack(seed, { checkpoints = 8 } = {}) {
  const key = seedKey(seed);
  for (let attempt = 0; attempt < 200; attempt++) {
    const rand = mulberry32(key ^ Math.imul(attempt + 1, 0x9e3779b9));
    const count = 9 + Math.floor(rand() * 5);
    const base = 850 + rand() * 250;
    const ctrl = [];
    for (let k = 0; k < count; k++) {
      const ang = (k / count) * TAU + (rand() - 0.5) * (TAU / count) * 0.5;
      const r = base * (0.6 + rand() * 0.7);
      ctrl.push({ x: Math.cos(ang) * r * 1.25, y: Math.sin(ang) * r });
    }
    const track = buildTrack(`Seed ${seed}`, ctrl, checkpoints);
    if (isValidTrack(track)) return track;
  }
  // Every seed tried so far succeeds well before this; an ellipse is the safe floor.
  const ctrl = [];
  for (let k = 0; k < 12; k++) ctrl.push({ x: Math.cos((k / 12) * TAU) * 1200, y: Math.sin((k / 12) * TAU) * 800 });
  return buildTrack(`Seed ${seed}`, ctrl, checkpoints);
}

export function surfaceAt(track, x, y) {
  const d = closestOnLoop(track.centerline, x, y).dist;
  if (d <= track.width / 2) return 'road';
  if (d <= track.width / 2 + track.verge) return 'off';
  return 'wall';
}
