// Shared helpers for the held-out lanes checks. The checks never load the workspace's code into their own
// process: the frontend is reached through the kit's probe.mjs, and the backend is a Python process of its
// own, started here on the kit's Python and asked over HTTP. The workspace is DEMO_WORKSPACE, a copy the kit made.
import { spawn, spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { createConnection, createServer } from "node:net";
import { basename, join, resolve } from "node:path";

export function workspace() {
  const ws = process.env.DEMO_WORKSPACE;
  if (!ws) throw new Error("DEMO_WORKSPACE is not set: run these through demos/check.py");
  const full = resolve(ws);
  if (!existsSync(full)) throw new Error(`DEMO_WORKSPACE does not exist: ${full}`);
  return full;
}

// The rule the backend task asks for, held here so the workspace cannot redefine it.
export function expectedDifficulty(trail) {
  const score = trail.length_km + trail.climb_m / 100;
  if (score < 8) return "easy";
  if (score < 15) return "moderate";
  return "hard";
}

// The trails the skeleton ships, copied from skeleton/backend/trails.json. The tasks add a field; they
// never change the catalogue, so served values are graded against this copy, not against themselves:
// a check that derives its expectation from what the backend serves passes edited data.
export const SKELETON_TRAILS = Object.freeze([
  { id: "fernwhistle", name: "Fernwhistle Loop", length_km: 4.2, climb_m: 180 },
  { id: "saltcedar", name: "Saltcedar Spur", length_km: 6.5, climb_m: 150 },
  { id: "quillpond", name: "Quillpond Path", length_km: 5.99, climb_m: 200 },
  { id: "owl-hollow", name: "Owl Hollow Traverse", length_km: 9.0, climb_m: 420 },
  { id: "cinder-stair", name: "Cinder Stair", length_km: 7.0, climb_m: 800 },
  { id: "lowmarsh", name: "Lowmarsh Boardwalk", length_km: 2.1, climb_m: 10 },
  { id: "highcairn", name: "Highcairn Ridge", length_km: 14.5, climb_m: 1150 },
].map((t) => Object.freeze(t)));

export const SKELETON_IDS = SKELETON_TRAILS.map((t) => t.id);

// The difficulty each skeleton trail must be served with, by id.
export const WANTED_DIFFICULTY = Object.freeze(
  Object.fromEntries(SKELETON_TRAILS.map((t) => [t.id, expectedDifficulty(t)])),
);

// The fields the skeleton serves, picked from a served trail, so extra fields (difficulty) do not count.
export const originalFields = (t) => ({ id: t.id, name: t.name, length_km: t.length_km, climb_m: t.climb_m });

// A small HTML reader, enough for the strings render.js produces: start and end tags with quoted,
// single-quoted or unquoted attributes. It reads markup the way a browser would for these cases, so a
// workspace is not failed for its choice of tag, quote style or nesting.
const TAG = /<(\/?)([a-zA-Z][\w:-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
const ATTR = /([^\s"'<>\/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
const VOID = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]);

export function tags(html) {
  const out = [];
  for (const m of html.matchAll(TAG)) {
    const attrs = {};
    for (const a of m[3].matchAll(ATTR)) attrs[a[1].toLowerCase()] ??= a[2] ?? a[3] ?? a[4] ?? "";
    out.push({ name: m[2].toLowerCase(), closing: m[1] === "/", attrs, start: m.index, end: m.index + m[0].length });
  }
  return out;
}

const NAMED = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
export function decodeEntities(text) {
  return text.replace(/&(?:#(\d+)|#[xX]([0-9a-fA-F]+)|(\w+));/g, (whole, dec, hex, name) => {
    if (dec !== undefined) return String.fromCodePoint(Number(dec));
    if (hex !== undefined) return String.fromCodePoint(parseInt(hex, 16));
    return NAMED[name] ?? whole;
  });
}

// The text a reader sees: tags dropped, entities decoded.
export const textOf = (html) => decodeEntities(html.replace(TAG, ""));

// Every element whose class list holds `difficulty`, with all its classes and the text inside it.
export function badges(html) {
  const all = tags(html);
  const found = [];
  all.forEach((t, i) => {
    if (t.closing) return;
    const classes = (t.attrs.class ?? "").split(/\s+/).filter(Boolean);
    if (!classes.includes("difficulty")) return;
    let end = t.end;
    if (!VOID.has(t.name)) {
      end = html.length;
      let depth = 1;
      for (const u of all.slice(i + 1)) {
        if (u.name !== t.name) continue;
        depth += u.closing ? -1 : 1;
        if (depth === 0) {
          end = u.start;
          break;
        }
      }
    }
    found.push({ classes, text: textOf(html.slice(t.end, end)).trim() });
  });
  return found;
}

// Markup a hostile value could have injected: a tag that no template writes, or an event-handler attribute.
export function injected(html) {
  return tags(html)
    .filter((t) => !t.closing)
    .filter((t) => ["img", "script", "iframe", "svg", "zz-inject"].includes(t.name) || Object.keys(t.attrs).some((a) => a.startsWith("on")))
    .map((t) => `<${t.name} ${Object.keys(t.attrs).join(" ")}>`);
}

// A program the kit validated, by the absolute path it gave: never one looked up on PATH.
function program(variable) {
  const path = process.env[variable];
  if (!path) throw new Error(`${variable} is not set: run these through demos/check.py`);
  return path;
}

function freePort() {
  return new Promise((ok, fail) => {
    const srv = createServer();
    srv.once("error", fail);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => ok(port));
    });
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// What the backend's process sees: the run's environment without the kit's variables (the result token above
// all), and no bytecode written next to the code.
function backendEnv() {
  const env = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (!/^(DEMO_|NODE_|NPM_)/i.test(k)) env[k] = v;
  }
  return { ...env, PYTHONDONTWRITEBYTECODE: "1", PYTHONUNBUFFERED: "1" };
}

// Whether something accepts connections on the port.
const accepting = (port) => new Promise((yes) => {
  const socket = createConnection({ port, host: "127.0.0.1" });
  socket.once("connect", () => {
    socket.destroy();
    yes(true);
  });
  socket.once("error", () => yes(false));
});

// Wait, for at most 5 s, until nothing accepts connections on the port: the backend is gone. The child's 'exit'
// is not that moment. On Windows a venv's python.exe is a launcher that starts the real interpreter as its child:
// kill() ends the launcher, 'exit' fires, and the interpreter is ended by the launcher's job object a moment later,
// while it still holds the port and the backend's cwd, so removing that folder fails with EBUSY.
async function untilClosed(port) {
  for (let i = 0; i < 200 && (await accepting(port)); i++) await sleep(25);
}

// Start `python -B backend/server.py --port <free port>` with the folder `root` (default: the workspace) as
// its cwd, wait for /api/health, and hand back the base URL and a stop().
export async function startBackend(root = workspace()) {
  const server = join(root, "backend", "server.py");
  if (!existsSync(server)) throw new Error("missing backend/server.py in the workspace");
  const port = await freePort();
  const child = spawn(program("DEMO_PYTHON"), ["-B", server, "--port", String(port)], {
    cwd: root,
    env: backendEnv(),
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  let output = "";
  child.stdout.on("data", (d) => (output += d));
  child.stderr.on("data", (d) => (output += d));
  let exited = null;
  child.on("exit", (code) => (exited = code ?? "a signal"));
  const stop = () => new Promise((done) => {
    if (exited !== null) return done();
    child.once("exit", () => untilClosed(port).then(done));
    child.kill();
  });
  const base = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    if (exited !== null) throw new Error(`backend exited with ${exited} before answering:\n${output.slice(-2000)}`);
    try {
      const r = await fetch(`${base}/api/health`);
      if (r.ok) return { base, stop };
    } catch {
      // not listening yet
    }
    await sleep(150);
  }
  await stop();
  throw new Error(`backend did not answer /api/health on ${base} within 20 s:\n${output.slice(-2000)}`);
}

// Run `fn(base)` against a backend started in the workspace, and stop it afterwards, whatever fn does.
export async function withBackend(fn, root = workspace()) {
  const backend = await startBackend(root);
  try {
    return await fn(backend.base);
  } finally {
    await backend.stop();
  }
}

export async function getJson(url) {
  const r = await fetch(url);
  const text = await r.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    throw new Error(`${url} did not return JSON (status ${r.status}): ${text.slice(0, 200)}`);
  }
  return { status: r.status, body };
}

export function git(...args) {
  const r = spawnSync(program("DEMO_GIT"), ["-C", workspace(), ...args], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  if (r.error) throw new Error(`git could not run: ${r.error.message}`);
  return r;
}

export function samePath(a, b) {
  const norm = (p) => {
    let full = resolve(p);
    try {
      full = realpathSync.native(full);
    } catch {
      // keep the resolved path
    }
    return process.platform === "win32" ? full.toLowerCase() : full;
  };
  return norm(a) === norm(b);
}

// Which lane a path is in. Rules files (CLAUDE.md, AGENTS.md) are lane configuration, not lane code,
// so setting lanes up across both folders in one commit is allowed. Root files belong to no lane.
const RULES_FILES = new Set(["claude.md", "agents.md"]);
export function laneOf(path) {
  if (RULES_FILES.has(basename(path).toLowerCase())) return null;
  if (path.startsWith("frontend/")) return "frontend";
  if (path.startsWith("backend/")) return "backend";
  return null;
}

export const isBytecode = (path) => /(^|\/)__pycache__\//.test(path) || path.endsWith(".pyc");

// Remove a throwaway folder, trying again for up to 10 s while a process still has it as its cwd (Windows).
// fs.rmSync's maxRetries does not wait for that: it fails at once with EBUSY (Node 22.13 and 24). A folder that
// stays can be left in the OS temp directory at no cost, whereas an error thrown from here would replace the
// verdict of the check that asked for it, so this never throws.
async function removeFolder(dir) {
  for (let attempt = 0; attempt < 40; attempt++) {
    try {
      rmSync(dir, { recursive: true, force: true });
      return;
    } catch {
      await sleep(250);
    }
  }
}

// Run the backend on a throwaway copy of the workspace whose data file holds `trails`, and return what
// /api/trails serves; null when the copy does not serve those trails (the data comes from somewhere else).
export async function servedFromCopy(trails) {
  const dir = mkdtempSync(join(tmpdir(), "lanes-probe-"));
  try {
    cpSync(workspace(), dir, {
      recursive: true,
      filter: (src) => !/[\\/](\.git|node_modules|__pycache__)$/.test(src),
    });
    writeFileSync(join(dir, "backend", "trails.json"), JSON.stringify(trails));
    const list = await withBackend(async (base) => (await getJson(`${base}/api/trails`)).body?.trails, dir);
    if (!Array.isArray(list) || list.length !== trails.length) return null;
    const ids = new Set(list.map((t) => t.id));
    return trails.every((t) => ids.has(t.id)) ? list : null;
  } finally {
    await removeFolder(dir);
  }
}
