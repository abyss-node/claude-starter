import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readWorkspaceFile } from './helpers.mjs';

// The page's opening tags, read the way a browser would: quotes keep a ">" inside a value from ending a tag,
// and comments and <script>/<style> bodies are not searched. So quoting style, attribute order and a bare
// unquoted attribute at the end of a tag (`<input value=7 id=seed>`) all read the same.
function openTags(html) {
  const text = html
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/(<(script|style)\b(?:"[^"]*"|'[^']*'|[^'">])*>)[\s\S]*?<\/\2\s*>/gi, '$1');
  return [...text.matchAll(/<[a-z][a-z0-9-]*\b(?:"[^"]*"|'[^']*'|[^'">])*>/gi)].map((m) => m[0]);
}

// Attribute names (lower-cased) and values of one tag, so a word inside a value is not read as an attribute.
function attrsOf(tag) {
  const out = new Map();
  const body = tag.replace(/^<[a-z0-9-]+/i, '').replace(/\/?>$/, '');
  const re = /([^\s"'=<>\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  for (const m of body.matchAll(re)) out.set(m[1].toLowerCase(), m[2] ?? m[3] ?? m[4] ?? '');
  return out;
}

function tagWithId(html, id) {
  return openTags(html).find((tag) => attrsOf(tag).get('id') === id) ?? '';
}

function hasId(html, id) {
  return tagWithId(html, id) !== '';
}

// A seed box the person can see and type in: a text-like <input>, not hidden, read-only or disabled.
const TYPING_TYPES = new Set(['text', 'number', 'search', 'tel']);
function assertEditableInput(tag, id) {
  assert.match(tag, /^<input\b/i, `#${id} should be an <input> the user can edit`);
  const attrs = attrsOf(tag);
  const type = (attrs.get('type') ?? 'text').trim().toLowerCase();
  assert.ok(TYPING_TYPES.has(type), `#${id} has type="${type}": use a text-like type (text, number, search or tel) so it can be typed in`);
  for (const name of ['readonly', 'disabled', 'hidden']) {
    assert.ok(!attrs.has(name), `#${id} must not be ${name}: the person types a seed into it`);
  }
  assert.doesNotMatch(attrs.get('style') ?? '', /display\s*:\s*none|visibility\s*:\s*hidden/i, `#${id} must be visible`);
}

test('page: index.html has the named controls', async () => {
  const html = await readWorkspaceFile('index.html');
  for (const id of ['context', 'temperature', 'topk', 'topp', 'seed', 'sample', 'bars']) {
    assert.ok(hasId(html, id), `index.html has no element with id="${id}"`);
  }
  for (const id of ['temperature', 'topk', 'topp']) {
    const tag = tagWithId(html, id);
    assert.match(tag, /^<input\b/i, `#${id} should be an <input>`);
    assert.equal((attrsOf(tag).get('type') ?? '').trim().toLowerCase(), 'range', `#${id} should be a range slider`);
  }
  assert.match(tagWithId(html, 'sample'), /^<button/i, '#sample should be a button');
});

// What the page loads, read from its own markup (comments are ignored). A module under src/ is named by
// a quoted path (in an import or any string) written src/x.js, ./src/x.js, ../src/x.js or /src/x.js,
// or by the src attribute of a script tag, quoted or not.
function withoutComments(html) {
  return html.replace(/<!--[\s\S]*?-->/g, '');
}

function srcModules(html) {
  const page = withoutComments(html);
  const found = [];
  for (const m of page.matchAll(/["'`](?:[^\s"'`]*\/)?src\/([\w.-]+\.js)(?:[?#][^\s"'`]*)?["'`]/g)) found.push(m[1]);
  for (const tag of openTags(page)) {
    if (!/^<script\b/i.test(tag)) continue;
    const m = (attrsOf(tag).get('src') ?? '').trim().match(/^(?:\S*\/)?src\/([\w.-]+\.js)(?:[?#].*)?$/);
    if (m) found.push(m[1]);
  }
  return found;
}

function moduleScripts(html) {
  return openTags(withoutComments(html)).filter((tag) => /^<script\b/i.test(tag) && (attrsOf(tag).get('type') ?? '').trim().toLowerCase() === 'module');
}

test('page: index.html has the seed box and the new-seed button', async () => {
  const html = await readWorkspaceFile('index.html');
  assert.ok(hasId(html, 'newseed'), 'index.html has no element with id="newseed"');
  assert.match(tagWithId(html, 'newseed'), /^<button/i, '#newseed should be a button');
  assertEditableInput(tagWithId(html, 'seed'), 'seed');
  assert.ok(srcModules(html).includes('seed.js'), 'index.html never loads src/seed.js');
  assert.match(html, /\bparseSeed\b/, 'index.html never uses parseSeed');
  assert.match(html, /\bnewSeed\b/, 'index.html never uses newSeed');
});

test('page: index.html loads the modules from src/', async () => {
  const html = await readWorkspaceFile('index.html');
  assert.ok(moduleScripts(html).length > 0, 'needs a <script type="module">');
  assert.ok(srcModules(html).length > 0, 'index.html never references a module under src/');
});
