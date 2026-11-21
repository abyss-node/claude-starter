// Draws one visual state on a 2D canvas, procedurally. No images, no fonts. Not graded.

import { PATTERN_COUNT } from './synth.js';

const TAU = Math.PI * 2;

// Pulls a hue toward warm (30) or cool (210) by up to 35% along the shorter arc.
function tint(hue, warmth) {
  if (!warmth) return hue;
  const goal = warmth > 0 ? 30 : 210;
  const delta = ((((goal - hue) % 360) + 540) % 360) - 180;
  return (((hue + delta * 0.35 * Math.abs(warmth)) % 360) + 360) % 360;
}

export function createRenderer(canvas) {
  const ctx = canvas.getContext('2d');
  let driftX = 0;
  let lastTime = null;

  function color(hue, sat, light, alpha = 1) {
    return `hsla(${hue.toFixed(1)}, ${sat}%, ${light}%, ${alpha})`;
  }

  const patterns = [
    // 0 concentric rings
    (c, s) => {
      for (let i = 0; i < c.rings; i++) {
        const r = ((i + 1) / c.rings) * c.reach;
        ctx.strokeStyle = c.ink(i * 24);
        ctx.lineWidth = 2 + c.pulse * 6;
        ctx.beginPath();
        ctx.arc(0, 0, r, 0, TAU);
        ctx.stroke();
      }
    },
    // 1 spokes
    (c) => {
      const n = 6 + c.rings;
      for (let i = 0; i < n; i++) {
        const a = (i / n) * TAU;
        ctx.strokeStyle = c.ink(i * 10);
        ctx.lineWidth = 3 + c.pulse * 8;
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * c.reach * 0.1, Math.sin(a) * c.reach * 0.1);
        ctx.lineTo(Math.cos(a) * c.reach, Math.sin(a) * c.reach);
        ctx.stroke();
      }
    },
    // 2 polar checker blocks
    (c) => {
      const rings = Math.max(3, c.rings);
      const wedges = 8 + rings;
      for (let i = 0; i < rings; i++) {
        for (let j = 0; j < wedges; j++) {
          if ((i + j) % 2) continue;
          const r0 = (i / rings) * c.reach;
          const r1 = ((i + 1) / rings) * c.reach;
          const a0 = (j / wedges) * TAU;
          const a1 = ((j + 1) / wedges) * TAU;
          ctx.fillStyle = c.ink(i * 18 + j * 4, 0.8);
          ctx.beginPath();
          ctx.arc(0, 0, r1, a0, a1);
          ctx.arc(0, 0, r0, a1, a0, true);
          ctx.closePath();
          ctx.fill();
        }
      }
    },
    // 3 spiral
    (c) => {
      ctx.lineWidth = 2 + c.pulse * 6;
      ctx.beginPath();
      const turns = 3 + c.rings / 4;
      for (let t = 0; t <= 1; t += 0.004) {
        const a = t * turns * TAU;
        const r = t * c.reach;
        ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r);
      }
      ctx.strokeStyle = c.ink(0);
      ctx.stroke();
    },
    // 4 nested squares
    (c) => {
      for (let i = 0; i < c.rings; i++) {
        const half = ((i + 1) / c.rings) * c.reach * 0.75;
        ctx.save();
        ctx.rotate(i * 0.12);
        ctx.strokeStyle = c.ink(i * 20);
        ctx.lineWidth = 2 + c.pulse * 5;
        ctx.strokeRect(-half, -half, half * 2, half * 2);
        ctx.restore();
      }
    },
    // 5 dot lattice
    (c) => {
      const n = 3 + Math.round(c.rings / 2);
      const step = (c.reach * 1.6) / n;
      for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
          ctx.fillStyle = c.ink((i + j) * 14, 0.9);
          ctx.beginPath();
          ctx.arc((i - (n - 1) / 2) * step, (j - (n - 1) / 2) * step, step * (0.18 + 0.25 * c.pulse), 0, TAU);
          ctx.fill();
        }
      }
    },
  ];
  if (patterns.length !== PATTERN_COUNT) throw new Error('render.js needs one drawing per pattern');

  return function draw(state) {
    const w = canvas.width;
    const h = canvas.height;
    const dt = lastTime === null ? 0 : Math.max(0, state.time - lastTime);
    lastTime = state.time;
    driftX += state.drift * 120 * dt;
    driftX = Math.max(-w * 0.3, Math.min(w * 0.3, driftX * (1 - 0.4 * dt)));

    const base = tint(state.hue, state.warmth);
    const lightness = 8 + state.brightness * 55;
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = color((base + 180) % 360, 55, Math.max(2, lightness * 0.18), 0.35);
    ctx.fillRect(0, 0, w, h);

    ctx.save();
    ctx.translate(w / 2 + driftX, h / 2);
    ctx.rotate(state.phase * 0.5);
    const scale = state.zoom * (1 + 0.12 * state.pulse);
    ctx.scale(scale, scale);
    const c = {
      rings: 4 + Math.round(state.detail * 14),
      reach: Math.min(w, h) * 0.45,
      pulse: state.pulse,
      ink: (offset, alpha = 1) => color((base + offset) % 360, 85, lightness, alpha),
    };
    ctx.globalCompositeOperation = 'lighter';
    patterns[state.pattern](c, state);
    ctx.restore();
  };
}
