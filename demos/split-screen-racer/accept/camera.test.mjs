// splitViewports and worldToScreen are pure functions; they are called in a process of their own (no DOM there either).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { values } from '../../probe.mjs';

// The page and main.js are read as text; the workspace's code is never loaded here.
const readWorkspaceFile = (rel) => readFile(join(process.env.DEMO_WORKSPACE, rel), 'utf8');
const cam = (calls) => values('src/camera.js', calls);

const SIZES = [
  [800, 600],
  [801, 601],
  [1280, 720],
  [333, 999],
];
const TARGETS = [
  { x: 120.5, y: -40.25 },
  { x: -900, y: 310 },
];

function overlap(a, b) {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

test('split viewports cover the canvas without overlap (side and stacked, odd sizes)', () => {
  const cases = [];
  for (const layout of ['side', 'stacked']) for (const [W, H] of SIZES) cases.push({ layout, W, H });
  const got = cam([
    ...cases.map(({ layout, W, H }) => ['splitViewports', W, H, TARGETS, { layout }]),
    ['splitViewports', 801, 601, TARGETS, { layout: 'side' }],
    ['splitViewports', 801, 601, TARGETS, { layout: 'side' }],
  ]);
  cases.forEach(({ layout, W, H }, k) => {
    const vps = got[k];
    assert.ok(Array.isArray(vps) && vps.length === 2, `${layout} ${W}x${H}: expected 2 viewports`);
    let area = 0;
    for (const v of vps) {
      for (const f of ['x', 'y', 'w', 'h']) assert.ok(Number.isInteger(v[f]), `${layout} ${W}x${H}: viewport ${f}=${v[f]} must be a whole pixel`);
      assert.ok(v.w > 0 && v.h > 0, `${layout} ${W}x${H}: empty viewport`);
      assert.ok(v.x >= 0 && v.y >= 0 && v.x + v.w <= W && v.y + v.h <= H, `${layout} ${W}x${H}: viewport leaves the canvas`);
      area += v.w * v.h;
    }
    assert.equal(overlap(vps[0], vps[1]), 0, `${layout} ${W}x${H}: viewports overlap`);
    assert.equal(area, W * H, `${layout} ${W}x${H}: viewports cover ${area} of ${W * H} pixels`);
    if (layout === 'side') assert.ok(vps.every((v) => v.h === H), 'side layout: both viewports are full height');
    else assert.ok(vps.every((v) => v.w === W), 'stacked layout: both viewports are full width');
  });
  assert.deepEqual(got[cases.length], got[cases.length + 1], 'same arguments must give the same viewports');
});

test('each viewport is centred on its own player', () => {
  const cases = [];
  for (const layout of ['side', 'stacked']) for (const scale of [1, 0.5, 1.75]) cases.push({ layout, scale });
  const all = cam(cases.map(({ layout, scale }) => ['splitViewports', 801, 601, TARGETS, { layout, scale }]));
  // Where each viewport sends its own player, a point 10 right and 4 up of it, and (viewport 0) the other player.
  const calls = [];
  all.forEach((vps) => {
    vps.forEach((v, i) => {
      calls.push(['worldToScreen', v, TARGETS[i].x, TARGETS[i].y]);
      calls.push(['worldToScreen', v, TARGETS[i].x + 10, TARGETS[i].y - 4]);
    });
    calls.push(['worldToScreen', vps[0], TARGETS[1].x, TARGETS[1].y]);
  });
  const mapped = cam(calls);
  let at = 0;
  cases.forEach(({ layout, scale }, k) => {
    const vps = all[k];
    vps.forEach((v, i) => {
      assert.ok(v.camX === TARGETS[i].x && v.camY === TARGETS[i].y, `${layout} x${scale}: viewport ${i} must report its player as the world point at its centre (camX, camY); got (${v.camX}, ${v.camY})`);
      assert.equal(v.scale, scale, `${layout} x${scale}: viewport ${i} reports scale ${v.scale}`);
      const c = mapped[at++];
      const cx = v.x + v.w / 2;
      const cy = v.y + v.h / 2;
      assert.ok(Math.abs(c.x - cx) < 1e-9 && Math.abs(c.y - cy) < 1e-9, `${layout} x${scale}: player ${i} maps to (${c.x}, ${c.y}), not its viewport centre (${cx}, ${cy})`);
      const d = mapped[at++];
      assert.ok(Math.abs(d.x - cx - 10 * scale) < 1e-9 && Math.abs(d.y - cy + 4 * scale) < 1e-9, `${layout} x${scale}: worldToScreen ignores the scale or flips an axis`);
    });
    const other = mapped[at++];
    assert.ok(Math.abs(other.x - (vps[0].x + vps[0].w / 2)) > 1, 'viewport 0 is not following player 0');
  });
});

// The setup screen lets a solo player pick either layout, so one target must give one full-canvas viewport whatever the layout says.
test('solo mode gets one full-canvas viewport in every layout (side, stacked, and no layout given)', () => {
  const options = [{ layout: 'side' }, { layout: 'stacked' }, {}, { layout: 'stacked', scale: 2 }, undefined];
  const cases = [];
  for (const opts of options) for (const [W, H] of SIZES) cases.push({ opts, W, H, label: `${JSON.stringify(opts)} ${W}x${H}` });
  const all = cam(cases.map(({ opts, W, H }) => (opts === undefined ? ['splitViewports', W, H, [TARGETS[0]]] : ['splitViewports', W, H, [TARGETS[0]], opts])));
  const mapped = cam(all.flatMap((vps) => [
    ['worldToScreen', vps[0], TARGETS[0].x, TARGETS[0].y],
    ['worldToScreen', vps[0], TARGETS[0].x + 10, TARGETS[0].y + 10],
  ]));
  cases.forEach(({ opts, W, H, label }, k) => {
    const vps = all[k];
    assert.equal(vps.length, 1, `${label}: one target must give one viewport, got ${vps.length}`);
    assert.deepEqual([vps[0].x, vps[0].y, vps[0].w, vps[0].h], [0, 0, W, H], `${label}: the solo viewport must be the whole canvas`);
    const scale = opts?.scale ?? 1;
    const c = mapped[2 * k];
    assert.ok(Math.abs(c.x - W / 2) < 1e-9 && Math.abs(c.y - H / 2) < 1e-9, `${label}: solo viewport is not centred on the player`);
    const d = mapped[2 * k + 1];
    assert.ok(Math.abs(d.x - W / 2 - 10 * scale) < 1e-9 && Math.abs(d.y - H / 2 - 10 * scale) < 1e-9, `${label}: solo worldToScreen ignores the scale`);
  });
});

// The page is read as text. Comments are dropped first, attributes may be quoted either way or not at all,
// and the script may sit at src/main.js, ./src/main.js or /src/main.js (any of them served from the workspace root).
function stripHtmlComments(html) {
  return html.replace(/<!--[\s\S]*?-->/g, '');
}

function attributes(tag) {
  const attrs = {};
  const re = /([^\s"'<>\/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  const inner = tag.replace(/^<\s*script/i, '').replace(/\/?>$/, '');
  for (const m of inner.matchAll(re)) attrs[m[1].toLowerCase()] = m[2] ?? m[3] ?? m[4] ?? '';
  return attrs;
}

function isMainModuleScript(html) {
  for (const m of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*>|<script\b[^>]*\/>/gi)) {
    const open = /^<script\b[^>]*>/i.exec(m[0])[0];
    const a = attributes(open);
    if (String(a.type ?? '').trim().toLowerCase() !== 'module') continue;
    if (a.src !== undefined) {
      const src = a.src.trim().split(/[?#]/)[0].replace(/^\.?\//, '');
      if (src === 'src/main.js') return true;
    } else if (/\bimport\s*(?:\(\s*)?['"`](?:\.\/|\/)src\/main\.js(?:[?#][^'"`]*)?['"`]/.test(m[1] ?? '')) {
      return true; // an inline module whose only job is to import the game
    }
  }
  return false;
}

function stripJsComments(js) {
  return js.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1');
}

test('index.html loads src/main.js as a module and has a canvas', async () => {
  const html = stripHtmlComments(await readWorkspaceFile('index.html'));
  assert.match(html, /<canvas\b/i, 'index.html has no <canvas>');
  assert.ok(isMainModuleScript(html), 'index.html must load src/main.js with type="module" (a <script type=module src=...> tag; quotes optional, ./ or / in front of src/ allowed)');
  const main = stripJsComments(await readWorkspaceFile('src/main.js'));
  assert.match(main, /(?:\bfrom\s*|\bimport\s*\(?\s*)(['"`])\.\/race\.js(?:[?#][^'"`]*)?\1/, 'src/main.js should drive the simulation from ./race.js (import ... from \'./race.js\')');
});
