import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join, posix } from 'node:path';
import { readWorkspaceFile, workspace } from './helpers.mjs';

// The page's opening tags, read the way a browser would: quotes keep a ">" inside a value from ending a tag,
// and comments and <script>/<style> bodies are not searched.
function openTags(html) {
  const text = html
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/(<(script|style)\b(?:"[^"]*"|'[^']*'|[^'">])*>)[\s\S]*?<\/\2\s*>/gi, '$1');
  return [...text.matchAll(/<[a-z][a-z0-9-]*\b(?:"[^"]*"|'[^']*'|[^'">])*>/gi)].map((m) => m[0]);
}

function attrsOf(tag) {
  const out = new Map();
  const body = tag.replace(/^<[a-z0-9-]+/i, '').replace(/\/?>$/, '');
  const re = /([^\s"'=<>\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  for (const m of body.matchAll(re)) out.set(m[1].toLowerCase(), m[2] ?? m[3] ?? m[4] ?? '');
  return out;
}

const tagWithId = (html, id) => openTags(html).find((tag) => attrsOf(tag).get('id') === id) ?? '';
const withoutComments = (html) => html.replace(/<!--[\s\S]*?-->/g, '');

function moduleScripts(html) {
  return openTags(withoutComments(html)).filter((tag) => /^<script\b/i.test(tag) && (attrsOf(tag).get('type') ?? '').trim().toLowerCase() === 'module');
}

// A specifier written in the page or in a module, as a path in the workspace: relative to `fromDir` (the folder of
// the file that wrote it; the root for index.html), or from the root when it starts with a slash, which is what
// the page's own server does. A query or a fragment is dropped; a URL or a bare name is not a file here.
function resolveSpec(spec, fromDir) {
  const s = spec.trim().replace(/[?#].*$/, '');
  if (!s || /^[a-z][a-z0-9+.-]*:/i.test(s) || s.startsWith('//')) return null;
  if (s.startsWith('/')) return posix.normalize(s.replace(/^\/+/, ''));
  if (s.startsWith('./') || s.startsWith('../')) return posix.normalize(posix.join(fromDir, s));
  return posix.normalize(posix.join(fromDir, s));
}

const IMPORT = /(?:from\s*|import\s*\(?\s*)["']([^"']+)["']/g;
const isScript = (rel) => rel.endsWith('.js') || rel.endsWith('.mjs');

// The text of every module the page loads, following imports of .js and .mjs files, so a name used in src/main.js
// (or src/main.mjs) counts.
async function pageGraph(html) {
  const page = withoutComments(html);
  const queue = [];
  for (const tag of moduleScripts(page)) {
    const src = resolveSpec(attrsOf(tag).get('src') ?? '', '.');
    if (src) queue.push(src);
  }
  for (const m of page.matchAll(/<script\b[^>]*type\s*=\s*["']?module["']?[^>]*>([\s\S]*?)<\/script>/gi)) {
    for (const imp of m[1].matchAll(IMPORT)) {
      const rel = resolveSpec(imp[1], '.');
      if (rel) queue.push(rel);
    }
  }
  const seen = new Set();
  const texts = new Map([['index.html', page]]);
  while (queue.length) {
    const rel = queue.shift();
    if (seen.has(rel) || !isScript(rel) || rel.startsWith('..')) continue;
    seen.add(rel);
    let src;
    try {
      src = await readFile(join(workspace(), rel), 'utf8');
    } catch {
      continue;
    }
    texts.set(rel, src);
    for (const imp of src.matchAll(IMPORT)) {
      const next = resolveSpec(imp[1], dirname(rel));
      if (next) queue.push(next);
    }
  }
  return { files: [...seen], texts };
}

test('item 21: index.html has the stage canvas, source buttons, file input, preset select and record button', async () => {
  const html = await readWorkspaceFile('index.html');
  const need = { stage: /^<canvas\b/i, 'source-mic': /^<button\b/i, 'source-tab': /^<button\b/i, 'source-file': /^<input\b/i, preset: /^<select\b/i, record: /^<button\b/i, 'warning-ok': /^<button\b/i };
  for (const [id, shape] of Object.entries(need)) {
    const tag = tagWithId(html, id);
    assert.ok(tag, `index.html has no element with id="${id}"`);
    assert.match(tag, shape, `#${id} has the wrong kind of tag: ${tag.slice(0, 40)}`);
  }
  assert.equal((attrsOf(tagWithId(html, 'source-file')).get('type') ?? '').trim().toLowerCase(), 'file', '#source-file should be a file input');
  assert.ok(tagWithId(html, 'warning'), 'index.html has no element with id="warning"');
});

test('item 21: the flash limiter is a checkbox that is checked in the markup and not disabled', async () => {
  const html = await readWorkspaceFile('index.html');
  const tag = tagWithId(html, 'limiter');
  assert.match(tag, /^<input\b/i, '#limiter should be an <input>');
  const attrs = attrsOf(tag);
  assert.equal((attrs.get('type') ?? '').trim().toLowerCase(), 'checkbox', '#limiter should be a checkbox');
  assert.ok(attrs.has('checked'), '#limiter should be checked in the markup: the limiter is on by default');
  assert.ok(!attrs.has('disabled') && !attrs.has('hidden'), '#limiter must stay usable');
  assert.doesNotMatch(attrs.get('style') ?? '', /display\s*:\s*none|visibility\s*:\s*hidden/i);
});

test('item 21: the warning is visible in the markup (script hides it once acknowledged), not hidden by default', async () => {
  const html = await readWorkspaceFile('index.html');
  const attrs = attrsOf(tagWithId(html, 'warning'));
  assert.ok(!attrs.has('hidden'), '#warning must not start hidden: if the script fails the warning still shows');
  assert.doesNotMatch(attrs.get('style') ?? '', /display\s*:\s*none|visibility\s*:\s*hidden/i);
});

const GRADED = new Set(['src/analysis.js', 'src/palette.js', 'src/onsets.js', 'src/safety.js', 'src/capture.js', 'src/synth.js']);

test('item 21: the page loads its modules, and page-level code calls the synth, the warning and both capture APIs', async () => {
  const html = await readWorkspaceFile('index.html');
  assert.ok(moduleScripts(html).length > 0, 'needs a <script type="module">');
  const { files, texts } = await pageGraph(html);
  assert.ok(files.length > 0, 'index.html loads no module from the workspace');
  // Only the page's own code counts: a call inside the graded modules (their definitions) does not.
  const pageCode = [...texts].filter(([file]) => !GRADED.has(file)).map(([, text]) => text).join(String.fromCharCode(10));
  for (const name of ['createSynth', 'shouldShowWarning', 'acknowledgeWarning', 'getUserMedia', 'getDisplayMedia']) {
    assert.ok(new RegExp(`\\b${name}\\s*\\(`).test(pageCode), `the page's own code (index.html and the modules it loads, other than the graded ones) never calls ${name}()`);
  }
});
