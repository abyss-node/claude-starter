// A demo workspace's `npm test`: start the kit's launcher (`starter.py demo check <name>`) with the Python that
// made the workspace, and exit with its exit code. npm runs `test` through cmd.exe on Windows, where a script
// that begins with a quoted program path fails ("is not recognized", npm 11), so demos/start.py writes a `test`
// that begins with a bare `node` running this file and passes the Python's path as an argument.
import { spawnSync } from 'node:child_process';

const [python, launcher, ...rest] = process.argv.slice(2);
if (!python || !launcher) {
  console.error('usage: node npm-test.mjs <python> <starter.py> demo check <name>');
  process.exit(2);
}
const run = spawnSync(python, [launcher, ...rest], { stdio: 'inherit' });
if (run.error) {
  // Not "run start.py again": it refuses a folder that is not empty, so that would mean deleting the work.
  // check.py accepts any absolute path to a Python outside the workspace there, so editing that one path is enough.
  console.error(`could not start ${python}: ${run.error.message}. That is the Python that made this folder, ` +
    `named in package.json's "test" script: change that path (the second quoted one) to a Python 3.9 or ` +
    `newer, or grade it from a terminal: python "${launcher}" ${rest.join(' ')} --dir "${process.cwd()}"`);
  process.exit(2);
}
process.exit(run.status === null ? 1 : run.status);
