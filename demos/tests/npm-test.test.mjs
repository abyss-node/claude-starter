// demos/npm-test.mjs is what a demo workspace's `npm test` runs. Its exit code is the grade's exit code, so a
// shim that swallowed it would turn every FAIL into a pass for whoever reads only the exit code (the verifier
// reads output too, but CI and scripts do not). demos/tests/test_demos.py runs this file.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SHIM = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'npm-test.mjs');
const PYTHON = process.env.DEMO_TEST_PYTHON;

function shim(...args) {
  return spawnSync(process.execPath, [SHIM, ...args], { encoding: 'utf8' });
}

test('the shim passes the checker its arguments and returns its exit code', { skip: !PYTHON && 'DEMO_TEST_PYTHON unset' }, () => {
  const dir = mkdtempSync(path.join(tmpdir(), "demo shim it's-"));
  try {
    const script = path.join(dir, 'fake starter.py');
    writeFileSync(script, 'import sys\nprint("args", sys.argv[1:])\nsys.exit(int(sys.argv[-1]))\n');
    for (const code of [0, 1, 2]) {
      const run = shim(PYTHON, script, 'demo', 'check', String(code));
      assert.equal(run.status, code, run.stderr);
      assert.match(run.stdout, new RegExp(`args \\['demo', 'check', '${code}'\\]`));
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a Python that cannot start exits 2 and says what to do without starting over', () => {
  const run = shim(path.join(tmpdir(), 'no-such-python-here'), 'starter.py', 'demo', 'check', 'x');
  assert.equal(run.status, 2);
  // demos/start.py refuses a folder that is not empty, so "run it again" would cost the agent's work.
  assert.doesNotMatch(run.stderr, /start\.py again/);
  assert.match(run.stderr, /could not start .*change that path \(the second quoted one\)/);
  assert.match(run.stderr, /python "starter\.py" demo check x --dir "/);
});

test('no arguments is a usage error, exit 2', () => {
  const run = shim();
  assert.equal(run.status, 2);
  assert.match(run.stderr, /usage/);
});
