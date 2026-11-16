// Browser front end: sliders, keyboard, a fixed-timestep loop and the canvas.
// All game rules live in physics.js; this file only reads the world and draws it.
import { DT, LIMITS, createWorld, step } from './physics.js';
import { aiInput } from './ai.js';

const PRESETS = {
  Kestrel: { mass: 0.7, radius: 0.08, friction: 0.2 },
  'Old Ballast': { mass: 2.6, radius: 0.16, friction: 0.5 },
  Thistle: { mass: 1.2, radius: 0.11, friction: 0.9 },
  Lantern: { mass: 1.4, radius: 0.12, friction: 0.4 },
};
const COLORS = ['#e8a33d', '#4fb3a9'];
const KEYS = [
  { up: 'KeyW', down: 'KeyS', left: 'KeyA', right: 'KeyD' },
  { up: 'ArrowUp', down: 'ArrowDown', left: 'ArrowLeft', right: 'ArrowRight' },
];

const canvas = document.getElementById('arena');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');
const seedEl = document.getElementById('seed');
const startBtn = document.getElementById('start');
const replayBtn = document.getElementById('replay');
const modeEl = document.getElementById('mode');
const legendB = document.getElementById('legend-b');
const keysTwo = document.getElementById('keys-two');
const keysSolo = document.getElementById('keys-solo');
const held = new Set();

const picks = [0, 1].map((i) => buildPanel(document.querySelector(`[data-top="${i}"]`), i));

function buildPanel(root, index) {
  const names = Object.keys(PRESETS);
  const state = { name: names[index === 0 ? 0 : 1], ...PRESETS[names[index === 0 ? 0 : 1]] };
  const select = document.createElement('select');
  for (const n of names) select.append(new Option(n, n));
  select.value = state.name;
  root.append(select);
  const sliders = {};
  for (const key of ['mass', 'radius', 'friction']) {
    const [lo, hi] = LIMITS[key];
    const label = document.createElement('label');
    const input = Object.assign(document.createElement('input'), { type: 'range', min: lo, max: hi, step: (hi - lo) / 100 });
    const out = document.createElement('output');
    label.append(key, input, out);
    root.append(label);
    const sync = () => { state[key] = Number(input.value); out.textContent = state[key].toFixed(2); };
    input.addEventListener('input', sync);
    sliders[key] = { input, sync };
  }
  const load = () => {
    Object.assign(state, PRESETS[select.value], { name: select.value });
    for (const k of Object.keys(sliders)) { sliders[k].input.value = state[k]; sliders[k].sync(); }
  };
  select.addEventListener('change', load);
  load();
  return state;
}

let world = null;
let mode = 'idle'; // idle | live | replay
let log = [];
let playMode = 'two'; // the mode the current match started in; changing the select mid-match does not switch it
let replayFrom = null;
let acc = 0;
let last = 0;
const angles = [0, 0];

function newWorld() {
  return createWorld({
    seed: Number(seedEl.value) || 0,
    tops: picks.map((p) => ({ name: p.name, mass: p.mass, radius: p.radius, friction: p.friction })),
  });
}

const axes = (keys) => ({
  x: keys.reduce((n, k) => n + (held.has(k.right) ? 1 : 0) - (held.has(k.left) ? 1 : 0), 0),
  y: keys.reduce((n, k) => n + (held.has(k.down) ? 1 : 0) - (held.has(k.up) ? 1 : 0), 0),
});

// Two players: A on W A S D, B on the arrows. Solo: both key sets steer A, and
// B's input comes from the computer, read off the world like any other input.
// The row is recorded either way, so a replay never needs to call the AI.
function readInputs() {
  if (playMode === 'solo') return [axes(KEYS), aiInput(world, 1)];
  return KEYS.map((k) => axes([k]));
}

function showMode() {
  const solo = modeEl.value === 'solo';
  legendB.textContent = solo ? 'Top B (computer)' : 'Top B';
  keysSolo.hidden = !solo;
  keysTwo.hidden = solo;
}
modeEl.addEventListener('change', showMode);
showMode();

startBtn.addEventListener('click', () => {
  playMode = modeEl.value;
  world = newWorld();
  replayFrom = JSON.parse(JSON.stringify(world));
  log = [];
  mode = 'live';
  acc = 0;
  replayBtn.disabled = true;
  statusEl.textContent = 'Clash!';
});

replayBtn.addEventListener('click', () => {
  if (!replayFrom) return;
  world = JSON.parse(JSON.stringify(replayFrom));
  mode = 'replay';
  acc = 0;
  statusEl.textContent = 'Replaying the last match';
});

addEventListener('keydown', (e) => {
  if (KEYS.some((k) => Object.values(k).includes(e.code))) { held.add(e.code); e.preventDefault(); }
});
addEventListener('keyup', (e) => held.delete(e.code));
addEventListener('blur', () => held.clear());

function tick() {
  if (mode === 'live') {
    const row = readInputs();
    log.push(row);
    step(world, row);
  } else if (mode === 'replay') {
    step(world, log[world.tick] || null);
  }
  world.tops.forEach((t, i) => { angles[i] = (angles[i] + t.spin * DT) % (2 * Math.PI); });
  if (world.winner !== null && mode !== 'idle') {
    const w = world.winner;
    const why = w >= 0 ? world.tops.find((t, i) => i !== w && t.status !== 'in') : null;
    statusEl.textContent = w === -1
      ? `Draw on tick ${world.tick}: both tops are out.`
      : `${world.tops[w].name} wins on tick ${world.tick}${why ? ` (${why.name} ${why.status === 'ringout' ? 'rang out' : 'spun down'})` : ''}.`;
    mode = 'idle';
    replayBtn.disabled = false;
  }
}

function frame(now) {
  const elapsed = Math.min(0.25, (now - last) / 1000 || 0);
  last = now;
  if (world && mode !== 'idle') {
    acc += elapsed;
    while (acc >= DT && mode !== 'idle') { tick(); acc -= DT; }
  }
  draw();
  requestAnimationFrame(frame);
}

function draw() {
  const size = canvas.width;
  const R = world ? world.config.arenaRadius : 1;
  const scale = (size / 2 - 24) / R;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, size, size);
  ctx.translate(size / 2, size / 2);

  const bowl = ctx.createRadialGradient(0, 0, 0, 0, 0, R * scale);
  bowl.addColorStop(0, '#2b303b');
  bowl.addColorStop(1, '#171a21');
  ctx.fillStyle = bowl;
  ctx.beginPath(); ctx.arc(0, 0, R * scale, 0, 2 * Math.PI); ctx.fill();
  ctx.strokeStyle = '#596075'; ctx.lineWidth = 3; ctx.stroke();
  ctx.strokeStyle = 'rgba(255,255,255,0.05)'; ctx.lineWidth = 1;
  for (const f of [0.25, 0.5, 0.75]) { ctx.beginPath(); ctx.arc(0, 0, R * scale * f, 0, 2 * Math.PI); ctx.stroke(); }
  if (!world) return;

  world.tops.forEach((t, i) => {
    const x = t.x * scale;
    const y = t.y * scale;
    const r = t.radius * scale;
    ctx.globalAlpha = t.status === 'in' ? 1 : 0.35;
    ctx.fillStyle = COLORS[i % COLORS.length];
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
    ctx.strokeStyle = '#0d0f13'; ctx.lineWidth = Math.max(2, r * 0.18);
    for (let s = 0; s < 3; s++) {
      const a = angles[i] + (s * 2 * Math.PI) / 3;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(a) * r * 0.85, y + Math.sin(a) * r * 0.85); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // Spin meter under the bowl edge.
    const w = 160;
    const mx = -size / 2 + 16 + i * (w + 24);
    const my = size / 2 - 16;
    ctx.fillStyle = '#262a33'; ctx.fillRect(mx, my - 8, w, 8);
    ctx.fillStyle = COLORS[i % COLORS.length];
    ctx.fillRect(mx, my - 8, Math.min(1, t.spin / 60) * w, 8);
    ctx.fillStyle = '#e8e6df'; ctx.font = '13px system-ui';
    ctx.fillText(`${t.name} ${t.spin.toFixed(1)}`, mx, my - 14);
  });
}

requestAnimationFrame(frame);
