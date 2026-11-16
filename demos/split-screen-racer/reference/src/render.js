// Canvas drawing only. Reads race state, never changes it.

import { worldToScreen } from './camera.js';

const COLORS = ['#ffb000', '#36c6ff'];

function tracePath(ctx, pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
  ctx.closePath();
}

function drawTrack(ctx, track, nextGate) {
  const pts = track.centerline;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  tracePath(ctx, pts);
  ctx.strokeStyle = '#7a3b2e';
  ctx.lineWidth = track.width + 2 * track.verge + 14;
  ctx.stroke();
  ctx.strokeStyle = '#c9a86a';
  ctx.lineWidth = track.width + 2 * track.verge;
  ctx.stroke();
  ctx.strokeStyle = '#e8e8e8';
  ctx.lineWidth = track.width + 8;
  ctx.setLineDash([18, 18]);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.strokeStyle = '#3b3f46';
  ctx.lineWidth = track.width;
  ctx.stroke();
  ctx.strokeStyle = 'rgba(255,255,255,0.35)';
  ctx.lineWidth = 2;
  ctx.setLineDash([22, 26]);
  ctx.stroke();
  ctx.setLineDash([]);

  track.checkpoints.forEach((g, i) => {
    ctx.beginPath();
    ctx.moveTo(g.a.x, g.a.y);
    ctx.lineTo(g.b.x, g.b.y);
    if (i === 0) {
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 10;
      ctx.setLineDash([10, 10]);
      ctx.stroke();
      ctx.setLineDash([]);
    } else {
      ctx.strokeStyle = i === nextGate ? 'rgba(120,255,160,0.85)' : 'rgba(255,255,255,0.18)';
      ctx.lineWidth = i === nextGate ? 5 : 3;
      ctx.stroke();
    }
  });
}

function drawVehicle(ctx, p, color) {
  ctx.save();
  ctx.translate(p.x, p.y);
  ctx.rotate(p.heading);
  const s = p.spec;
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.fillRect(-s.length / 2 + 3, -s.breadth / 2 + 3, s.length, s.breadth);
  if (p.kind === 'bike') {
    ctx.fillStyle = '#222';
    ctx.fillRect(-s.length / 2, -2, s.length, 4);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.ellipse(-1, 0, s.length * 0.3, s.breadth * 0.55, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#f4f4f4';
    ctx.beginPath();
    ctx.arc(-3, 0, 4, 0, Math.PI * 2);
    ctx.fill();
  } else {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(-s.length / 2, -s.breadth / 2, s.length, s.breadth, 5);
    ctx.fill();
    ctx.fillStyle = 'rgba(20,30,50,0.85)';
    ctx.fillRect(2, -s.breadth / 2 + 3, 8, s.breadth - 6);
    ctx.fillRect(-12, -s.breadth / 2 + 4, 5, s.breadth - 8);
  }
  ctx.restore();
}

function ordinal(n) {
  return n === 1 ? '1st' : n === 2 ? '2nd' : `${n}th`;
}

function placeOf(race, i) {
  const score = (p, j) => (p.finished ? 1e9 - race.finishOrder.indexOf(j) : p.lap * 1000 + ((p.next - 1 + race.track.checkpoints.length) % race.track.checkpoints.length));
  const mine = score(race.players[i], i);
  return 1 + race.players.filter((p, j) => j !== i && score(p, j) > mine).length;
}

export function drawFrame(ctx, race, viewports, labels, banner) {
  const { width, height } = ctx.canvas;
  ctx.fillStyle = '#2f6b3a';
  ctx.fillRect(0, 0, width, height);
  viewports.forEach((vp, vi) => {
    const me = race.players[vi];
    ctx.save();
    ctx.beginPath();
    ctx.rect(vp.x, vp.y, vp.w, vp.h);
    ctx.clip();
    const origin = worldToScreen(vp, 0, 0);
    ctx.translate(origin.x, origin.y);
    ctx.scale(vp.scale, vp.scale);
    drawTrack(ctx, race.track, me.next);
    race.players.forEach((p, i) => drawVehicle(ctx, p, COLORS[i % COLORS.length]));
    ctx.restore();

    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(vp.x + 8, vp.y + 8, 210, 62);
    ctx.fillStyle = COLORS[vi % COLORS.length];
    ctx.font = 'bold 16px system-ui, sans-serif';
    ctx.fillText(labels[vi] ?? `P${vi + 1}`, vp.x + 16, vp.y + 28);
    ctx.fillStyle = '#fff';
    ctx.font = '14px system-ui, sans-serif';
    const lap = Math.min(me.lap + 1, race.laps);
    ctx.fillText(`Lap ${lap}/${race.laps}   ${ordinal(placeOf(race, vi))}`, vp.x + 16, vp.y + 48);
    ctx.fillText(`${Math.round(me.speed)} u/s   ${me.finished ? 'FINISHED' : ''}`, vp.x + 16, vp.y + 64);
  });
  if (viewports.length > 1) {
    const b = viewports[1];
    ctx.fillStyle = '#111';
    if (b.x > 0) ctx.fillRect(b.x - 2, 0, 4, height);
    else ctx.fillRect(0, b.y - 2, width, 4);
  }
  if (banner) {
    // Countdown digits and the result line only. A box sized to its text, never a full-width strip.
    ctx.font = 'bold 32px system-ui, sans-serif';
    const textW = ctx.measureText(banner).width;
    const w = Math.min(width - 16, Math.max(96, textW + 48));
    const h = 64;
    const cx = viewports.length === 1 ? viewports[0].x + viewports[0].w / 2 : width / 2;
    const cy = viewports.length === 1 ? viewports[0].y + viewports[0].h / 2 : height / 2;
    ctx.fillStyle = 'rgba(0,0,0,0.7)';
    ctx.beginPath();
    ctx.roundRect(cx - w / 2, cy - h / 2, w, h, 10);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.fillText(banner, cx, cy + 11);
    ctx.textAlign = 'start';
  }
}
