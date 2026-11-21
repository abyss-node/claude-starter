// Browser shell: draws the game on a canvas and feeds keys into the engine.
import { CONTENT } from './content.js';
import { newGame, step, isEnded } from './game.js';
import { saveGame, loadGame } from './save.js';

const TILE = 16;
const COLOURS = { '#': '#3b3f46', '.': '#6f9a4e', ',': '#3f7a3a', '~': '#2f5f9e', T: '#1f4a28' };
const canvas = document.getElementById('screen');
const ctx = canvas.getContext('2d');
let game = newGame(CONTENT, Date.now() % 1000000);
let message = '';

function draw() {
  ctx.fillStyle = '#0f150d';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (game.mode === 'battle') {
    const b = game.battle;
    const p = b.playerParty.find((c) => c.hp > 0) || b.playerParty[0];
    const e = b.enemyParty.find((c) => c.hp > 0) || b.enemyParty[0];
    ctx.fillStyle = '#d6e6c4';
    ctx.fillText(`${e.name} Lv${e.level}  HP ${e.hp}/${e.maxHp}`, 16, 40);
    ctx.fillText(`${p.name} Lv${p.level}  HP ${p.hp}/${p.maxHp}`, 16, 120);
    p.moves.forEach((m, i) => ctx.fillText(`${i + 1}. ${CONTENT.moves[m].name}`, 16, 160 + i * 14));
    return;
  }
  const map = CONTENT.maps[game.player.map];
  const ox = Math.floor(160 - game.player.x * TILE - TILE / 2);
  const oy = Math.floor(100 - game.player.y * TILE - TILE / 2);
  map.rows.forEach((row, y) => [...row].forEach((t, x) => {
    ctx.fillStyle = COLOURS[t] || '#000';
    ctx.fillRect(ox + x * TILE, oy + y * TILE, TILE, TILE);
  }));
  for (const n of map.npcs || []) {
    ctx.fillStyle = '#e0b84a';
    ctx.fillRect(ox + n.x * TILE + 3, oy + n.y * TILE + 3, 10, 10);
  }
  ctx.fillStyle = '#e8e8e8';
  ctx.fillRect(160 - 6, 100 - 6, 12, 12);
  ctx.fillStyle = '#d6e6c4';
  ctx.fillText(map.name, 8, 12);
  if (game.mode === 'dialogue') {
    ctx.fillStyle = '#10180d';
    ctx.fillRect(0, 170, 320, 70);
    ctx.fillStyle = '#d6e6c4';
    ctx.fillText(game.dialogue.view.text.slice(0, 52), 8, 186);
    game.dialogue.view.choices.forEach((c, i) => ctx.fillText(`${i + 1}. ${c}`, 8, 202 + i * 12));
  }
  if (isEnded(CONTENT, game)) ctx.fillText('The End', 130, 20);
  if (message) ctx.fillText(message, 8, 232);
}

// A small synthesized tune, no audio files.
let audio = null;
function blip(freq, at, len) {
  const o = audio.createOscillator();
  const g = audio.createGain();
  o.type = 'square';
  o.frequency.value = freq;
  g.gain.setValueAtTime(0.03, at);
  g.gain.exponentialRampToValueAtTime(0.0001, at + len);
  o.connect(g).connect(audio.destination);
  o.start(at);
  o.stop(at + len);
}
function toggleMusic() {
  if (audio) { audio.close(); audio = null; return; }
  audio = new AudioContext();
  const notes = [262, 330, 392, 330, 294, 349, 440, 349];
  for (let i = 0; i < 64; i++) blip(notes[i % notes.length] * (i % 16 < 8 ? 1 : 1.125), audio.currentTime + i * 0.25, 0.2);
}

const KEYS = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', z: 'action', Z: 'action', x: 'run' };
addEventListener('keydown', (ev) => {
  let input = KEYS[ev.key];
  if (/^[1-3]$/.test(ev.key)) input = game.mode === 'battle' ? `move:${Number(ev.key) - 1}` : `choose:${Number(ev.key) - 1}`;
  if (ev.key === 's') { localStorage.setItem('pocket-region', saveGame(game)); message = 'Saved.'; }
  else if (ev.key === 'l') {
    const text = localStorage.getItem('pocket-region');
    if (text) { game = loadGame(text); message = 'Loaded.'; }
  } else if (ev.key === 'm') toggleMusic();
  else if (input) { game = step(CONTENT, game, input); message = ''; }
  else return;
  ev.preventDefault();
  draw();
});
draw();
