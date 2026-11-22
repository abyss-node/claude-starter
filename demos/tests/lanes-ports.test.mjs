// demos/lanes/accept/helpers.mjs starts the lanes demo's Python backend once per check, several at a time. Two
// starts must never be handed one port: when each took a port from listening on port 0 and closing, Linux could
// hand the same just-closed port to two starts at once (it picks port 0 at random), and the start whose backend
// lost the bind had its health check answered by the other's backend. CI's demo-mutants job failed that way
// ("probe-N: not a skeleton trail", "fetch failed"). Nor may a start be handed a port another program already
// answers on, or have its claim held by a stray connection. A port the claim judged free can still turn out to be
// one the backend cannot bind (a server without SO_REUSEADDR, on a port the kit's previous backend left in
// TIME_WAIT, failed with [Errno 98] on Linux): such a start is made again on a fresh port, and no other failure is.
// demos/tests/test_demos.py runs this file.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import { createRequire, syncBuiltinESMExports } from 'node:module';
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
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
async function foreignService(band = BAND) {
  const seen = { connections: 0 };
  const server = http.createServer((req, res) => {
    const body = JSON.stringify({ ok: true, trails: [{ id: 'FOREIGN', name: 'FOREIGN', length_km: 1, climb_m: 1 }] });
    res.writeHead(200, { 'Content-Type': 'application/json' }).end(body);
  });
  server.on('connection', () => seen.connections++);
  for (let attempt = 0; attempt < 50; attempt++) {
    const port = band.low + crypto.randomInt(band.count);
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

// The claim's lock listens at the backend port plus LOCK_OFFSET for the backend's whole life, and drops every
// connection it gets. Where a listen there succeeds beside another program's, the lock would take that program's
// loopback traffic away from it until the backend stops.
const LOCK_BAND = { low: BAND.low + 6000, count: BAND.count };

test("a port another program answers on is never taken for a claim's lock either", { skip: NO_PYTHON }, async () => {
  process.env.DEMO_PYTHON = PYTHON;
  const dir = folderServing('ours');
  const foreign = await foreignService(LOCK_BAND);
  const undoDraw = firstDrawIs(foreign.port - 6000);
  const listens = listensSucceedBeside(foreign.server, foreign.port);
  let start;
  try {
    start = await startBackend(dir).then((value) => ({ value }), (reason) => ({ reason }));
  } finally {
    listens.undo();
    undoDraw();
  }
  try {
    assert.equal(start.reason?.message?.split('\n')[0], undefined, 'the backend should start');
    assert.equal(listens.beside, 0, `a lock listened on port ${foreign.port}, where another program answers`);
    assert.notEqual(start.value.base, `http://127.0.0.1:${foreign.port - 6000}`, "the backend was handed the port whose lock another program holds");
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

// The draws helpers.mjs makes are `ports`, in order; later draws are random again. Returns the undo.
function drawsAre(...ports) {
  const real = crypto.randomInt;
  const queue = [...ports];
  crypto.randomInt = (...args) => (queue.length ? queue.shift() - BAND.low : real(...args));
  syncBuiltinESMExports();
  return () => {
    crypto.randomInt = real;
    syncBuiltinESMExports();
  };
}

// Records the port of every backend helpers.mjs spawns, in order. Returns { ports, undo }.
function spawnsRecorded() {
  const childProcess = createRequire(import.meta.url)('node:child_process');
  const real = childProcess.spawn;
  const seen = { ports: [] };
  childProcess.spawn = function (command, args, ...rest) {
    const at = Array.isArray(args) ? args.indexOf('--port') : -1;
    if (at >= 0) seen.ports.push(Number(args[at + 1]));
    return real.call(this, command, args, ...rest);
  };
  syncBuiltinESMExports();
  seen.undo = () => {
    childProcess.spawn = real;
    syncBuiltinESMExports();
  };
  return seen;
}

const REFERENCE_SERVER = readFileSync(path.join(REFERENCE_BACKEND, 'server.py'), 'utf8');
// The reference server with `prelude` run first, before it binds (a checkout may give it CRLF line ends).
function serverAfter(prelude) {
  const edited = REFERENCE_SERVER.replace(/from __future__ import annotations\r?\n/, (m) => `${m}${prelude}\n`);
  assert.notEqual(edited, REFERENCE_SERVER, 'the reference server no longer starts with a __future__ import');
  return edited;
}

// startBackend's outcome, { value } or { reason }, never a throw.
const outcome = (dir) => startBackend(dir).then((value) => ({ value }), (reason) => ({ reason }));

test('a backend without SO_REUSEADDR, started where the previous backend just stopped, is started again on a fresh port', { skip: NO_PYTHON }, async () => {
  process.env.DEMO_PYTHON = PYTHON;
  // socketserver.TCPServer leaves allow_reuse_address False, so on Linux and macOS its bind fails ([Errno 98],
  // [Errno 48]) while the port holds the TIME_WAIT that the previous backend's served connection left there.
  // Node's own listen gets SO_REUSEADDR from libuv there, so the claim's look at the port cannot see it.
  const plain = REFERENCE_SERVER.replace('server = ThreadingHTTPServer(', "server = __import__('socketserver').TCPServer(");
  assert.notEqual(plain, REFERENCE_SERVER, 'the reference server no longer builds a ThreadingHTTPServer');
  const dirs = { shipped: folderServing('shipped'), plain: folderServing('plain', plain) };
  const spawns = spawnsRecorded();
  const port = BAND.low + crypto.randomInt(BAND.count);
  let start;
  try {
    const undoDraws = drawsAre(port, port);
    try {
      const shipped = await startBackend(dirs.shipped);
      try {
        const { body } = await getJson(`${shipped.base}/api/trails`);
        assert.deepEqual(body?.trails?.map((t) => t.id), ['shipped']);
      } finally {
        await shipped.stop();
      }
      start = await outcome(dirs.plain);
    } finally {
      undoDraws();
    }
    assert.deepEqual(spawns.ports.slice(0, 2), [port, port], `the draws were not forced to ${port}: has BACKEND_PORTS in helpers.mjs moved?`);
    assert.equal(start.reason?.message, undefined, 'the second backend should start');
    const { body } = await getJson(`${start.value.base}/api/trails`);
    assert.deepEqual(body?.trails?.map((t) => t.id), ['plain'], `${start.value.base} answered with another backend's trails`);
  } finally {
    spawns.undo();
    await start?.value?.stop();
    Object.values(dirs).forEach(remove);
  }
});

// What a backend prints when the port it was given is taken or refused, as Python words it on each OS.
const PORT_UNAVAILABLE = {
  'Linux EADDRINUSE': 'raise OSError(98, "Address already in use")',
  'macOS EADDRINUSE': 'raise OSError(48, "Address already in use")',
  'Windows WSAEADDRINUSE': 'raise OSError("[WinError 10048] Only one usage of each socket address (protocol/network address/port) is normally permitted")',
  'Windows WSAEACCES': 'raise PermissionError("[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions")',
  'Unix EACCES on the bind': 'def bind():\n    raise PermissionError(13, "Permission denied")\nbind()',
};

for (const [name, raise] of Object.entries(PORT_UNAVAILABLE)) {
  test(`a backend whose port turns out to be unavailable (${name}) is started again on a fresh port`, { skip: NO_PYTHON }, async () => {
    process.env.DEMO_PYTHON = PYTHON;
    // It fails on its first start only: the marker file next to it says it has been started before.
    const once = [
      'import pathlib as _pl',
      '_marker = _pl.Path(__file__).with_name("started-once")',
      'if not _marker.exists():',
      '    _marker.write_text("x")',
      raise.replace(/^/gm, '    '),
    ].join('\n');
    const dir = folderServing('retried', serverAfter(once));
    const spawns = spawnsRecorded();
    let start;
    try {
      start = await outcome(dir);
    } finally {
      spawns.undo();
    }
    try {
      assert.equal(start.reason?.message, undefined, 'the second start should succeed');
      assert.equal(spawns.ports.length, 2, 'the backend should have been started twice');
      assert.equal(start.value.base, `http://127.0.0.1:${spawns.ports[1]}`);
      const { body } = await getJson(`${start.value.base}/api/trails`);
      assert.deepEqual(body?.trails?.map((t) => t.id), ['retried']);
    } finally {
      await start.value?.stop();
      remove(dir);
    }
  });
}

// Another program, started by the backend's first start: it listens on that start's port, accepts and drops every
// connection for at most 60 s, and writes its pid to argv[2] once it is listening.
const HOLDER = [
  'import os, pathlib, socket, sys, time',
  's = socket.socket()',
  's.bind(("127.0.0.1", int(sys.argv[1])))',
  's.listen(5)',
  's.settimeout(0.5)',
  'pathlib.Path(sys.argv[2]).write_text(str(os.getpid()))',
  'end = time.time() + 60',
  'while time.time() < end:',
  '    try:',
  '        s.accept()[0].close()',
  '    except OSError:',
  '        pass',
].join('\n');

test('a backend whose port another program holds is started again without waiting for that program to leave', { skip: NO_PYTHON }, async () => {
  process.env.DEMO_PYTHON = PYTHON;
  const prelude = [
    'import pathlib as _pl, subprocess as _sp, sys as _sys, time as _t',
    '_marker = _pl.Path(__file__).with_name("started-once")',
    'if not _marker.exists():',
    '    _marker.write_text("x")',
    '    _pid = _pl.Path(__file__).with_name("holder.pid")',
    `    _sp.Popen([_sys.executable, "-c", ${JSON.stringify(HOLDER)}, _sys.argv[_sys.argv.index("--port") + 1], str(_pid)],`,
    '              stdin=_sp.DEVNULL, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)',
    '    for _ in range(400):',
    '        if _pid.exists() and _pid.read_text():',
    '            break',
    '        _t.sleep(0.025)',
    '    raise OSError(98, "Address already in use")',
  ].join('\n');
  const dir = folderServing('held-elsewhere', serverAfter(prelude));
  const pidFile = path.join(dir, 'backend', 'holder.pid');
  const spawns = spawnsRecorded();
  let start;
  try {
    const began = Date.now();
    start = await outcome(dir);
    const took = Date.now() - began;
    assert.equal(start.reason?.message, undefined, 'the second start should succeed');
    assert.equal(spawns.ports.length, 2, 'the backend should have been started twice');
    const held = await new Promise((yes) => {
      const socket = net.createConnection({ port: spawns.ports[0], host: '127.0.0.1' });
      socket.once('connect', () => (socket.destroy(), yes(true)));
      socket.once('error', () => yes(false));
    });
    assert.ok(held, `nothing holds port ${spawns.ports[0]}: the test did not set up what it is about`);
    assert.ok(took < 4000, `the start took ${took} ms: it waited for the other program to leave the first port`);
  } finally {
    spawns.undo();
    await start?.value?.stop();
    try {
      process.kill(Number(readFileSync(pidFile, 'utf8')));
    } catch {
      // gone already, or never started
    }
    remove(dir);
  }
});

test('a backend whose port is taken on every start fails after a few, with its own output', { skip: NO_PYTHON }, async () => {
  process.env.DEMO_PYTHON = PYTHON;
  const dir = folderServing('always-taken', serverAfter('raise OSError(98, "Address already in use")'));
  const spawns = spawnsRecorded();
  let start;
  try {
    start = await outcome(dir);
    assert.match(String(start.reason?.message), /^backend exited with 1 before answering/);
    assert.match(start.reason.message, /OSError: \[Errno 98\] Address already in use/);
    assert.ok(spawns.ports.length > 1 && spawns.ports.length <= 5, `started ${spawns.ports.length} times, not 2 to 5`);
  } finally {
    spawns.undo();
    await start?.value?.stop();
    remove(dir);
  }
});

// A broken workspace fails at once with its own output: started again, it would only take longer to fail.
const BROKEN = {
  'a syntax error': ['def broken(:\n', /SyntaxError/],
  'a file it may not read': [
    serverAfter('raise PermissionError(13, "Permission denied", "backend/trails.json")'),
    /PermissionError: \[Errno 13\] Permission denied: 'backend\/trails.json'/,
  ],
};

for (const [name, [server, said]] of Object.entries(BROKEN)) {
  test(`a backend that exits before answering for ${name} is not started again`, { skip: NO_PYTHON }, async () => {
    process.env.DEMO_PYTHON = PYTHON;
    const dir = folderServing('broken', server);
    const spawns = spawnsRecorded();
    let start;
    try {
      start = await outcome(dir);
      assert.match(String(start.reason?.message), /^backend exited with 1 before answering/);
      assert.match(start.reason.message, said);
      assert.equal(spawns.ports.length, 1, `started ${spawns.ports.length} times`);
    } finally {
      spawns.undo();
      await start?.value?.stop();
      remove(dir);
    }
  });
}
