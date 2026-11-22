// demos/lanes/accept/helpers.mjs starts the lanes demo's Python backend once per check, several at a time. Two
// starts must never be handed one port: when each took a port from listening on port 0 and closing, Linux could
// hand the same just-closed port to two starts at once (it picks port 0 at random), and the start whose backend
// lost the bind had its health check answered by the other's backend. CI's demo-mutants job failed that way
// ("probe-N: not a skeleton trail", "fetch failed"). Nor may a start be handed a port another program already
// answers on, or have its claim held by a stray connection. demos/tests/test_demos.py runs this file.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import { createRequire, syncBuiltinESMExports } from 'node:module';
import { cpSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getJson, startBackend } from '../lanes/accept/helpers.mjs';

const crypto = createRequire(import.meta.url)('node:crypto');
// The band helpers.mjs claims backend ports from: BACKEND_PORTS there.
const BAND = { low: 20000, count: 6000 };

const REFERENCE_BACKEND = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'lanes', 'reference', 'backend');
const PYTHON = process.env.DEMO_TEST_PYTHON;
const NO_PYTHON = !PYTHON && 'DEMO_TEST_PYTHON unset';

// A folder whose backend serves one trail, `id`, so an answer says which backend gave it. `server` replaces
// backend/server.py when given.
function folderServing(id, server) {
  const dir = mkdtempSync(path.join(tmpdir(), 'lanes-port-'));
  cpSync(REFERENCE_BACKEND, path.join(dir, 'backend'), { recursive: true, filter: (s) => !/__pycache__/.test(s) });
  writeFileSync(path.join(dir, 'backend', 'trails.json'), JSON.stringify([{ id, name: id, length_km: 1, climb_m: 1 }]));
  if (server) writeFileSync(path.join(dir, 'backend', 'server.py'), server);
  return dir;
}

// Best effort: on Windows a folder can stay busy a moment after its process is gone, and the OS temp folder keeps it.
function remove(dir) {
  try {
    rmSync(dir, { recursive: true, force: true });
  } catch {
    // left in the temp folder
  }
}

// Every listen on port 0 in this process is told the port the first one got, as Linux can tell two starts at once.
// That makes the collision certain instead of rare. Returns the undo.
function portZeroRepeatsItself() {
  const { listen, address } = net.Server.prototype;
  const askedForZero = new WeakSet();
  let first = null;
  net.Server.prototype.listen = function (...args) {
    if (args[0] === 0 || args[0]?.port === 0) askedForZero.add(this);
    return listen.apply(this, args);
  };
  net.Server.prototype.address = function () {
    const got = address.call(this);
    if (!askedForZero.has(this) || got === null || typeof got !== 'object') return got;
    first ??= got.port;
    return { ...got, port: first };
  };
  return () => Object.assign(net.Server.prototype, { listen, address });
}

test('two backends started at once get a port each and answer for themselves, even when port 0 repeats itself', { skip: NO_PYTHON }, async () => {
  process.env.DEMO_PYTHON = PYTHON;
  const dirs = ['alpha', 'bravo'].map((id) => folderServing(id));
  const undo = portZeroRepeatsItself();
  let starts;
  try {
    starts = await Promise.allSettled(dirs.map((dir) => startBackend(dir)));
  } finally {
    undo();
  }
  const up = starts.filter((s) => s.status === 'fulfilled').map((s) => s.value);
  try {
    const refused = starts.filter((s) => s.status === 'rejected').map((s) => String(s.reason?.message).split('\n')[0]);
    assert.deepEqual(refused, [], 'both backends should start');
    assert.notEqual(up[0].base, up[1].base, 'both backends were handed one port');
    for (const [backend, id] of [[up[0], 'alpha'], [up[1], 'bravo']]) {
      const { body } = await getJson(`${backend.base}/api/trails`);
      assert.deepEqual(body?.trails?.map((t) => t.id), [id], `${backend.base} answered with another backend's trails`);
    }
  } finally {
    await Promise.all(up.map((b) => b.stop()));
    dirs.forEach(remove);
  }
});

// The first port helpers.mjs draws is `port`; later draws are random again. Returns the undo.
function firstDrawIs(port) {
  const real = crypto.randomInt;
  let drawn = false;
  crypto.randomInt = (...args) => (drawn ? real(...args) : ((drawn = true), port - BAND.low));
  syncBuiltinESMExports();
  return () => {
    crypto.randomInt = real;
    syncBuiltinESMExports();
  };
}

// A listen on 127.0.0.1:port by any server but `owner` succeeds beside it, as Windows lets a listen on 127.0.0.1
// sit beside another program's on 0.0.0.0 or [::] (here the other program is on 127.0.0.1 itself, which needs no
// firewall prompt and is reached the same way). Returns { undo, beside: how many such listens there were }.
function listensSucceedBeside(owner, port) {
  const { listen } = net.Server.prototype;
  const seen = { beside: 0 };
  net.Server.prototype.listen = function (...args) {
    if (this !== owner && args[0] === port) {
      seen.beside++;
      args[0] = 0;
    }
    return listen.apply(this, args);
  };
  seen.undo = () => Object.assign(net.Server.prototype, { listen });
  return seen;
}

// Another program on the machine: an HTTP service on 127.0.0.1 at a free port of the band that answers any path
// with 200 and a FOREIGN trail. Resolves to { server, port, connections }.
async function foreignService() {
  const seen = { connections: 0 };
  const server = http.createServer((req, res) => {
    const body = JSON.stringify({ ok: true, trails: [{ id: 'FOREIGN', name: 'FOREIGN', length_km: 1, climb_m: 1 }] });
    res.writeHead(200, { 'Content-Type': 'application/json' }).end(body);
  });
  server.on('connection', () => seen.connections++);
  for (let attempt = 0; attempt < 50; attempt++) {
    const port = BAND.low + crypto.randomInt(BAND.count);
    const up = await new Promise((ok) => {
      server.once('error', () => ok(false));
      server.listen(port, '127.0.0.1', () => ok(true));
    });
    if (up) return Object.assign(seen, { server, port });
  }
  throw new Error('no free port in the band for the foreign service');
}

test('a port another program already answers on is never handed to a backend, even where a listen there succeeds', { skip: NO_PYTHON }, async () => {
  process.env.DEMO_PYTHON = PYTHON;
  const dir = folderServing('ours');
  const foreign = await foreignService();
  const undoDraw = firstDrawIs(foreign.port);
  const listens = listensSucceedBeside(foreign.server, foreign.port);
  let start;
  try {
    start = await startBackend(dir).then((value) => ({ value }), (reason) => ({ reason }));
  } finally {
    listens.undo();
    undoDraw();
  }
  try {
    assert.ok(foreign.connections > 0 || listens.beside > 0, `the claim never looked at port ${foreign.port}: has BACKEND_PORTS in helpers.mjs moved?`);
    assert.equal(start.reason?.message?.split('\n')[0], undefined, 'the backend should start');
    assert.notEqual(start.value.base, `http://127.0.0.1:${foreign.port}`, 'the backend was handed the port the foreign service answers on');
    const { body } = await getJson(`${start.value.base}/api/trails`);
    assert.deepEqual(body?.trails?.map((t) => t.id), ['ours'], `${start.value.base} answered with another program's trails`);
  } finally {
    await start.value?.stop();
    foreign.server.closeAllConnections();
    await new Promise((done) => foreign.server.close(done));
    remove(dir);
  }
});

test('a connection held open on a claim does not hold up stop()', { skip: NO_PYTHON }, async () => {
  process.env.DEMO_PYTHON = PYTHON;
  const dir = folderServing('held');
  const { listen } = net.Server.prototype;
  const servers = [];
  net.Server.prototype.listen = function (...args) {
    servers.push(this);
    return listen.apply(this, args);
  };
  let backend;
  try {
    backend = await startBackend(dir);
  } finally {
    Object.assign(net.Server.prototype, { listen });
  }
  const claims = servers.filter((s) => s.listening);
  const clients = [];
  try {
    assert.ok(claims.length > 0, 'startBackend should hold a listening socket for its claim');
    for (const claim of claims) {
      const client = net.createConnection({ port: claim.address().port, host: '127.0.0.1' });
      client.on('error', () => {}); // the claim may drop it once connected: that is the point
      clients.push(client);
      await new Promise((ok, fail) => {
        client.once('connect', ok);
        client.once('close', () => fail(new Error('could not connect to the claim')));
      });
    }
    const verdict = await Promise.race([
      backend.stop().then(() => 'stopped'),
      new Promise((ok) => setTimeout(() => ok('still waiting after 10 s'), 10000).unref()),
    ]);
    assert.equal(verdict, 'stopped', 'stop() waited for a client of its claim to leave');
  } finally {
    clients.forEach((c) => c.destroy());
    await backend.stop();
    remove(dir);
  }
});

test('a backend that exits before answering fails its start with its own output', { skip: NO_PYTHON }, async () => {
  process.env.DEMO_PYTHON = PYTHON;
  const dir = folderServing('gone', 'import sys\nsys.stderr.write("cannot bind: the port is taken\\n")\nsys.exit(3)\n');
  try {
    await assert.rejects(startBackend(dir), (e) => {
      assert.match(e.message, /^backend exited with 3 before answering/);
      assert.match(e.message, /cannot bind: the port is taken/);
      return true;
    });
  } finally {
    remove(dir);
  }
});
