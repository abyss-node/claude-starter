// Browser glue: setup form, fixed-timestep loop, split-screen drawing.

import { aiInput } from './ai.js';
import { splitViewports } from './camera.js';
import { listen, pressed, readInput } from './input.js';
import { createRace, DT, stepRace } from './race.js';
import { drawFrame } from './render.js';
import { fixedTrack, generateTrack } from './track.js';

const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
const form = document.getElementById('setup');
listen(window);

let session = null;

function fit() {
  canvas.width = Math.max(320, Math.floor(window.innerWidth));
  canvas.height = Math.max(240, Math.floor(window.innerHeight - form.offsetHeight));
}
window.addEventListener('resize', fit);
fit();

function start(e) {
  e?.preventDefault();
  const data = new FormData(form);
  const solo = data.get('mode') === 'solo';
  const seed = Number.parseInt(String(data.get('seed')), 10) || 0;
  const track = data.get('track') === 'fixed' ? fixedTrack() : generateTrack(seed);
  const kinds = [String(data.get('p1')), String(data.get('p2'))];
  const race = createRace({ track, vehicles: kinds, laps: Number(data.get('laps')) || 3 });
  session = {
    race,
    solo,
    layout: String(data.get('layout')),
    labels: solo ? ['You', 'Rival (AI)'] : ['P1  WASD', 'P2  Arrows'],
    countdown: 3,
    acc: 0,
    last: performance.now(),
  };
  form.querySelector('button')?.blur();
  fit();
}
form.addEventListener('submit', start);

function frame(now) {
  requestAnimationFrame(frame);
  if (!session) {
    ctx.fillStyle = '#1d2a22';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#e8e8e8';
    ctx.font = '20px system-ui, sans-serif';
    ctx.fillText('Pick a mode and vehicles above, then Start.', 24, 48);
    return;
  }
  if (pressed('Escape')) {
    session = null;
    return;
  }
  const s = session;
  const elapsed = Math.min(0.25, (now - s.last) / 1000);
  s.last = now;
  if (s.countdown > 0) {
    s.countdown -= elapsed;
  } else {
    s.acc += elapsed;
    while (s.acc >= DT) {
      const inputs = s.race.players.map((_, i) => (s.solo && i === 1 ? aiInput(s.race, 1) : readInput(i, s.solo)));
      stepRace(s.race, inputs);
      s.acc -= DT;
    }
  }
  const p = s.race.players;
  const targets = s.solo ? [p[0]] : [p[0], p[1]];
  const scale = Math.max(0.35, Math.min(1, Math.min(canvas.width, canvas.height) / (s.solo ? 700 : 520)));
  const vps = splitViewports(canvas.width, canvas.height, targets, { layout: s.layout, scale });
  let banner = '';
  if (s.countdown > 0) banner = String(Math.ceil(s.countdown));
  else if (s.race.finishOrder.length === p.length || (s.solo && p[0].finished)) {
    const w = s.race.finishOrder[0];
    banner = `${s.solo && w === 0 ? 'You win' : `${s.labels[w]} wins`}  -  Esc for the menu`;
  }
  drawFrame(ctx, s.race, vps, s.labels, banner);
}
requestAnimationFrame(frame);
