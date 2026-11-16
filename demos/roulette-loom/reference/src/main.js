// The page: read the controls, trace the curve once, then let the pen draw it a few segments per frame while
// the rolling circle and the pen's arm move on a second canvas above the trail.
import { laps, trace } from './loom.js';

const SEGMENTS_PER_LAP = 360;
const trailCanvas = document.getElementById('trail');
const gearCanvas = document.getElementById('gear');
const trailPen = trailCanvas.getContext('2d');
const gearPen = gearCanvas.getContext('2d');
const inputs = Object.fromEntries(['R', 'r', 'd', 'speed'].map((id) => [id, document.getElementById(id)]));
const playButton = document.getElementById('play');
const statusLine = document.getElementById('status');

let shape = null;   // { R, r, d, points, scale }
let drawnUpTo = 0;  // index of the last point the pen has reached
let playing = true;

function colour(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function toCanvas(p) {
  const half = trailCanvas.width / 2;
  return [half + p.x * shape.scale, half - p.y * shape.scale];
}

function readShape() {
  const R = Number(inputs.R.value);
  inputs.r.max = String(R - 1);
  const r = Math.min(Number(inputs.r.value), R - 1);
  inputs.r.value = String(r);
  const d = Number(inputs.d.value);
  for (const id of ['R', 'r', 'd', 'speed']) document.getElementById(`${id}-out`).textContent = inputs[id].value;
  const turns = laps(R, r);
  const reach = Math.max(R, R - r + d);
  return { R, r, d, turns, points: trace(R, r, d, SEGMENTS_PER_LAP * turns), scale: (trailCanvas.width * 0.46) / reach };
}

function restart() {
  shape = readShape();
  drawnUpTo = 0;
  trailPen.clearRect(0, 0, trailCanvas.width, trailCanvas.height);
  trailPen.lineWidth = 2;
  trailPen.lineJoin = 'round';
  trailPen.strokeStyle = colour('--ink');
  statusLine.textContent = `The pen closes the curve after ${shape.turns} lap${shape.turns === 1 ? '' : 's'} of the ring.`;
}

function drawGear(index) {
  const { R, r, points } = shape;
  const end = 2 * Math.PI * shape.turns;
  const t = (end * index) / (points.length - 1);
  const centre = { x: (R - r) * Math.cos(t), y: (R - r) * Math.sin(t) };
  const [cx, cy] = toCanvas(centre);
  const [px, py] = toCanvas(points[index]);
  const [ox, oy] = toCanvas({ x: 0, y: 0 });
  gearPen.clearRect(0, 0, gearCanvas.width, gearCanvas.height);
  gearPen.lineWidth = 1.5;
  gearPen.strokeStyle = colour('--fg');
  gearPen.globalAlpha = 0.35;
  gearPen.beginPath();
  gearPen.arc(ox, oy, R * shape.scale, 0, 2 * Math.PI);
  gearPen.stroke();
  gearPen.globalAlpha = 0.8;
  gearPen.strokeStyle = colour('--gear');
  gearPen.beginPath();
  gearPen.arc(cx, cy, r * shape.scale, 0, 2 * Math.PI);
  gearPen.moveTo(cx, cy);
  gearPen.lineTo(px, py);
  gearPen.stroke();
  gearPen.globalAlpha = 1;
  gearPen.fillStyle = colour('--gear');
  gearPen.beginPath();
  gearPen.arc(px, py, 5, 0, 2 * Math.PI);
  gearPen.fill();
}

function frame() {
  const last = shape.points.length - 1;
  if (playing && drawnUpTo < last) {
    const next = Math.min(last, drawnUpTo + Number(inputs.speed.value));
    trailPen.beginPath();
    trailPen.moveTo(...toCanvas(shape.points[drawnUpTo]));
    for (let i = drawnUpTo + 1; i <= next; i++) trailPen.lineTo(...toCanvas(shape.points[i]));
    trailPen.stroke();
    drawnUpTo = next;
  }
  drawGear(drawnUpTo);
  requestAnimationFrame(frame);
}

for (const id of ['R', 'r', 'd']) inputs[id].addEventListener('input', restart);
inputs.speed.addEventListener('input', () => {
  document.getElementById('speed-out').textContent = inputs.speed.value;
});
playButton.addEventListener('click', () => {
  playing = !playing;
  playButton.textContent = playing ? 'Pause' : 'Play';
});

restart();
requestAnimationFrame(frame);
