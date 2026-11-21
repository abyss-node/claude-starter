// Drawing only. Everything is shapes on a canvas; nothing here is graded.
import { SPECIES } from './data.js';

const TILE = 32;
const TYPE_HUE = { cinder: 20, tide: 200, moss: 115, spark: 55, stone: 30 };

function hueOf(c) {
  const s = SPECIES.find((x) => x.id === c.species);
  return s && s.hue !== undefined ? s.hue : TYPE_HUE[c.type] || 0;
}

export function drawCreature(ctx, c, cx, cy, size, flip) {
  const h = hueOf(c);
  const dir = flip ? -1 : 1;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(dir, 1);
  ctx.fillStyle = `hsl(${h} 65% 55%)`;
  ctx.beginPath();
  ctx.ellipse(0, 0, size * 0.5, size * 0.4, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = `hsl(${h} 70% 38%)`;
  ctx.beginPath();
  ctx.ellipse(-size * 0.1, size * 0.18, size * 0.32, size * 0.16, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.beginPath();
  ctx.arc(size * 0.2, -size * 0.1, size * 0.1, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#111';
  ctx.beginPath();
  ctx.arc(size * 0.23, -size * 0.1, size * 0.045, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = `hsl(${h} 80% 70%)`;
  ctx.beginPath();
  if (c.type === 'cinder') { ctx.moveTo(-size * 0.1, -size * 0.38); ctx.lineTo(0, -size * 0.75); ctx.lineTo(size * 0.1, -size * 0.38); }
  else if (c.type === 'tide') { ctx.moveTo(-size * 0.4, -size * 0.1); ctx.lineTo(-size * 0.75, -size * 0.35); ctx.lineTo(-size * 0.5, size * 0.1); }
  else if (c.type === 'moss') { ctx.ellipse(0, -size * 0.5, size * 0.08, size * 0.18, 0.4, 0, Math.PI * 2); }
  else if (c.type === 'spark') { ctx.moveTo(-size * 0.1, -size * 0.4); ctx.lineTo(size * 0.05, -size * 0.55); ctx.lineTo(-size * 0.02, -size * 0.55); ctx.lineTo(size * 0.12, -size * 0.75); ctx.lineTo(-size * 0.05, -size * 0.5); ctx.lineTo(size * 0.02, -size * 0.5); }
  else { ctx.rect(-size * 0.3, -size * 0.5, size * 0.12, size * 0.14); ctx.rect(0, -size * 0.52, size * 0.12, size * 0.16); }
  ctx.fill();
  ctx.restore();
}

export function drawMap(ctx, game) {
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  game.map.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const t = row[x];
      ctx.fillStyle = t === '#' ? '#39414f' : t === '"' ? '#2d6a3a' : t === '+' ? '#2a5f8f' : '#6b5a3c';
      ctx.fillRect(x * TILE, y * TILE, TILE, TILE);
      if (t === '"') { ctx.strokeStyle = '#4f9a5c'; ctx.beginPath(); ctx.moveTo(x * TILE + 8, y * TILE + 24); ctx.lineTo(x * TILE + 12, y * TILE + 10); ctx.moveTo(x * TILE + 20, y * TILE + 26); ctx.lineTo(x * TILE + 24, y * TILE + 12); ctx.stroke(); }
      if (t === '+') { ctx.fillStyle = '#bfe3ff'; ctx.fillRect(x * TILE + 12, y * TILE + 6, 8, 20); ctx.fillRect(x * TILE + 6, y * TILE + 12, 20, 8); }
    }
  });
  ctx.fillStyle = '#f0a030';
  ctx.beginPath();
  ctx.arc(game.x * TILE + TILE / 2, game.y * TILE + TILE / 2, 10, 0, Math.PI * 2);
  ctx.fill();
}

function bar(ctx, x, y, w, c) {
  ctx.fillStyle = '#000';
  ctx.fillRect(x, y, w, 10);
  ctx.fillStyle = c.hp / c.maxHp > 0.5 ? '#4cc16a' : c.hp / c.maxHp > 0.2 ? '#e6c23a' : '#d94c4c';
  ctx.fillRect(x + 1, y + 1, Math.max(0, (w - 2) * (c.hp / c.maxHp)), 8);
  ctx.fillStyle = '#e8ecf1';
  ctx.font = '12px system-ui';
  ctx.fillText(`${c.name} Lv${c.level}${c.status ? ' [' + c.status.kind + ']' : ''}  ${c.hp}/${c.maxHp}`, x, y - 4);
}

export function drawBattle(ctx, battle) {
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  const [me, foe] = battle.sides.map((s) => s.team[s.active]);
  ctx.fillStyle = '#1b2430';
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  if (foe.hp > 0) drawCreature(ctx, foe, 350, 90, 90, true);
  if (me.hp > 0) drawCreature(ctx, me, 130, 200, 110, false);
  bar(ctx, 20, 28, 200, foe);
  bar(ctx, 260, 250, 200, me);
}

export function drawBlank(ctx, text) {
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.fillStyle = '#fff';
  ctx.font = '20px system-ui';
  ctx.textAlign = 'center';
  ctx.fillText(text, ctx.canvas.width / 2, ctx.canvas.height / 2);
  ctx.textAlign = 'start';
}
