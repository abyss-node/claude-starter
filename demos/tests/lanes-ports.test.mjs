// demos/lanes/accept/helpers.mjs starts the lanes demo's Python backend once per check, several at a time. Two
// starts must never be handed one port: when each took a port from listening on port 0 and closing, Linux could
// hand the same just-closed port to two starts at once (it picks port 0 at random), and the start whose backend
// lost the bind had its health check answered by the other's backend. CI's demo-mutants job failed that way
// ("probe-N: not a skeleton trail", "fetch failed"). demos/tests/test_demos.py runs this file.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { cpSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { getJson, startBackend } from '../lanes/accept/helpers.mjs';

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
