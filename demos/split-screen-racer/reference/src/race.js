// The race: fixed-timestep simulation of 1-2 vehicles on a track. No DOM, no clock, no Math.random.

import { closestOnLoop, segmentsCross } from './geom.js';
import { createVehicle, DT, stepVehicle, TICK_HZ, VEHICLES } from './vehicles.js';

export { DT, TICK_HZ };

const RESTITUTION = 0.35;

// Pure: returns the new progress. Only the next expected gate can advance it, so
// checkpoints count strictly in order and a lap counts only on gate 0 after the rest.
export function advanceProgress(track, progress, from, to) {
  const n = track.checkpoints.length;
  const gate = track.checkpoints[progress.next];
  if (!segmentsCross(from, to, gate.a, gate.b)) return { lap: progress.lap, next: progress.next };
  if (progress.next === 0) return { lap: progress.lap + 1, next: 1 % n };
  return { lap: progress.lap, next: (progress.next + 1) % n };
}

export function createRace({ track, vehicles = ['car', 'bike'], laps = 3 }) {
  const players = vehicles.map((kind, i) => {
    const pose = track.grid[i % track.grid.length];
    const v = createVehicle(kind, pose);
    v.lap = 0;
    v.next = 1 % track.checkpoints.length;
    v.finished = false;
    v.finishTick = null;
    return v;
  });
  return { tick: 0, laps, track, players, finishOrder: [] };
}

function collide(a, b) {
  const ra = a.spec.radius;
  const rb = b.spec.radius;
  let dx = b.x - a.x;
  let dy = b.y - a.y;
  let d = Math.hypot(dx, dy);
  const min = ra + rb;
  if (d >= min) return;
  let nx = 1;
  let ny = 0;
  if (d > 1e-9) {
    nx = dx / d;
    ny = dy / d;
  } else {
    d = 0;
  }
  const ma = a.spec.mass;
  const mb = b.spec.mass;
  const overlap = min - d;
  const wa = mb / (ma + mb);
  const wb = ma / (ma + mb);
  a.x -= nx * overlap * wa;
  a.y -= ny * overlap * wa;
  b.x += nx * overlap * wb;
  b.y += ny * overlap * wb;
  const rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
  if (rel < 0) {
    const j = (-(1 + RESTITUTION) * rel) / (1 / ma + 1 / mb);
    a.vx -= (j / ma) * nx;
    a.vy -= (j / ma) * ny;
    b.vx += (j / mb) * nx;
    b.vy += (j / mb) * ny;
  }
}

function keepInside(track, v) {
  const c = closestOnLoop(track.centerline, v.x, v.y);
  const limit = track.width / 2 + track.verge - v.spec.radius;
  if (c.dist <= limit) return;
  const nx = (v.x - c.x) / c.dist;
  const ny = (v.y - c.y) / c.dist;
  v.x = c.x + nx * limit;
  v.y = c.y + ny * limit;
  const out = v.vx * nx + v.vy * ny;
  if (out > 0) {
    v.vx -= out * nx;
    v.vy -= out * ny;
  }
  v.vx *= 0.92;
  v.vy *= 0.92;
}

// Advances exactly one tick in place and returns the race.
export function stepRace(race, inputs = []) {
  const { track, players } = race;
  const from = players.map((p) => ({ x: p.x, y: p.y }));
  players.forEach((p, i) => {
    const input = p.finished ? { brake: 0.5 } : inputs[i] ?? {};
    const surface = closestOnLoop(track.centerline, p.x, p.y).dist <= track.width / 2 ? 'road' : 'off';
    stepVehicle(p, input, surface);
  });
  for (let i = 0; i < players.length; i++) {
    for (let j = i + 1; j < players.length; j++) collide(players[i], players[j]);
  }
  for (const p of players) {
    keepInside(track, p);
    p.speed = Math.hypot(p.vx, p.vy);
  }
  race.tick += 1;
  players.forEach((p, i) => {
    if (p.finished) return;
    const prog = advanceProgress(track, p, from[i], p);
    p.lap = prog.lap;
    p.next = prog.next;
    if (p.lap >= race.laps) {
      p.finished = true;
      p.finishTick = race.tick;
      race.finishOrder.push(i);
    }
  });
  return race;
}

// FNV-1a over every field that matters, at full float precision.
export function hashRace(race) {
  const parts = [race.tick, race.laps, race.finishOrder.join(',')];
  for (const p of race.players) {
    parts.push(p.kind, p.x, p.y, p.heading, p.vx, p.vy, p.lap, p.next, p.finished ? 1 : 0, p.finishTick ?? -1);
  }
  const text = parts.join('|');
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, '0') + ':' + text.length.toString(16);
}

export { VEHICLES };
