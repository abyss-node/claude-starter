import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { observe, workspace, readWorkspaceFile, textFiles, htmlTags, namesIn } from './helpers.mjs';

const EXPECTED = {
  'src/rng.js': ['createRng', 'nextFloat'],
  'src/data.js': ['TYPES', 'TYPE_CHART', 'STATUS_TURNS', 'MOVES', 'SPECIES', 'WILD_TABLE', 'MAP'],
  'src/rules.js': ['MAX_LEVEL', 'typeMultiplier', 'calcStat', 'calcMaxHp', 'calcDamage', 'effectiveSpeed', 'xpForLevel', 'levelForXp', 'xpReward', 'catchChance', 'attemptCatch', 'makeCreature', 'gainXp'],
  'src/battle.js': ['createBattle', 'legalActions', 'isLegalAction', 'resolveTurn'],
  'src/ai.js': ['chooseAction'],
  'src/duel.js': ['createDuel', 'duelContinue', 'duelPick', 'duelView'],
  'src/replay.js': ['hashLog', 'replayBattle'],
  'src/game.js': ['createGame', 'walk', 'endBattle', 'saveGame', 'loadGame'],
};

test('Graded 1: layout, page and originality', async () => {
  // The exports and the fixed values of src/data.js, from the workspace's code in a process of its own.
  const { modules, data } = observe('./scenario-01.mjs', [Object.keys(EXPECTED)]);
  for (const [file, names] of Object.entries(EXPECTED)) {
    const m = modules && modules[file];
    assert.ok(m && typeof m === 'object', `nothing was reported for ${file}`);
    assert.equal(m.loadError, null, `${file} did not load: ${m.loadError}`);
    for (const n of names) assert.ok(n in m.exports, `${file} does not export ${n}`);
    for (const n of names) {
      if (/^[a-z]/.test(n)) assert.equal(m.exports[n], 'function', `${file}: ${n} should be a function`);
    }
  }
  assert.ok(data && typeof data === 'object', 'nothing was reported for src/data.js');
  assert.equal(data.loadError, null, `src/data.js: ${data.loadError}`);
  assert.deepEqual(data.TYPES, ['cinder', 'tide', 'moss', 'spark', 'stone']);
  assert.deepEqual(data.STATUS_TURNS, { scorch: 3, daze: 2, chill: 3 });
  assert.equal(data.chartType, 'object');
  assert.equal(data.TYPES.length, 5);
  await readFile(join(workspace(), 'src/main.js'), 'utf8');
  await readFile(join(workspace(), 'index.html'), 'utf8');

  // Originality: no franchise name anywhere in the shipped source.
  const files = await textFiles();
  for (const f of files) {
    if (!/\.(js|mjs|html|css|json)$/i.test(f.rel)) continue;
    const named = namesIn(await readFile(f.full, 'utf8'));
    assert.deepEqual(named, [], `${f.rel} contains a name from the kit's list of franchise names; creatures, moves and places must be your own`);
  }

  // No binary assets.
  for (const f of files) {
    assert.ok(!/\.(png|jpe?g|gif|webp|bmp|ico|svg|mp3|wav|ogg|oga|flac|m4a|aac|mid|midi|woff2?|ttf|otf|eot)$/i.test(f.rel), `${f.rel} is an image, audio or font file`);
    if (!/\.(js|mjs|html|css|json)$/i.test(f.rel)) continue;
    const text = await readFile(f.full, 'utf8');
    assert.ok(!/data:(image|audio|font|application\/font)/i.test(text), `${f.rel} has an embedded data: image, audio or font`);
    assert.ok(!/[A-Za-z0-9+/=]{1024,}/.test(text), `${f.rel} has a base64-looking run over 1 KB`);
  }

  // The page, read from the tags themselves.
  const html = await readWorkspaceFile('index.html');
  const tags = htmlTags(html);
  const byId = (id) => tags.find((t) => t.attrs.id === id);
  assert.equal(byId('screen')?.name, 'canvas', '#screen must be a <canvas>');
  assert.equal(byId('seed')?.name, 'input', '#seed must be an <input>');
  for (const id of ['mode-adventure', 'mode-solo', 'mode-duel']) assert.equal(byId(id)?.name, 'button', `#${id} must be a <button>`);
  const mod = tags.filter((t) => t.name === 'script' && String(t.attrs.type || '').toLowerCase() === 'module');
  assert.ok(mod.some((t) => /^(\.\/|\/)?src\/main\.js$/.test(String(t.attrs.src || ''))), 'index.html needs <script type="module" src="src/main.js">');

  const main = await readWorkspaceFile('src/main.js');
  for (const m of ['game.js', 'duel.js', 'ai.js']) {
    const re = new RegExp(`from\\s*['"][^'"]*\\b${m.replace('.', '\\.')}['"]`);
    assert.ok(re.test(main), `src/main.js does not import from ${m}`);
  }
});
