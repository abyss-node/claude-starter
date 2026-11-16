// Fixture builder, not part of a solution: turns this reference into a finished workspace with git history.
//   node make-workspace.mjs --skeleton <skeleton dir> --out <new empty dir> [--mode lanes|skeleton|one-commit]
// lanes (default): initial commit = skeleton, then one backend commit, then one frontend commit.
// skeleton: initial commit only. one-commit: both lanes in one commit.
// It reads its own files beside itself, names git by DEMO_GIT, and fixes every identity and date.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const flag = (name) => {
  const at = process.argv.indexOf(name);
  return at > 0 ? process.argv[at + 1] : undefined;
};
const [skeleton, target] = [flag("--skeleton"), flag("--out")].map((p) => p && resolve(p));
const mode = flag("--mode") ?? "lanes";
if (!skeleton || !target || !["lanes", "skeleton", "one-commit"].includes(mode)) {
  console.error("usage: node make-workspace.mjs --skeleton <dir> --out <empty dir> [--mode lanes|skeleton|one-commit]");
  process.exit(2);
}
if (!process.env.DEMO_GIT) {
  console.error("DEMO_GIT is not set: this builder runs git by the path the kit gives it");
  process.exit(2);
}
if (existsSync(target) && readdirSync(target).length) {
  console.error(`refusing: ${target} is not empty`);
  process.exit(2);
}

const DATE = "2026-01-01T12:00:00+00:00";
const env = {
  ...process.env,
  GIT_AUTHOR_NAME: "demo", GIT_AUTHOR_EMAIL: "demo@example.invalid", GIT_AUTHOR_DATE: DATE,
  GIT_COMMITTER_NAME: "demo", GIT_COMMITTER_EMAIL: "demo@example.invalid", GIT_COMMITTER_DATE: DATE,
};
const git = (...args) => {
  const r = spawnSync(process.env.DEMO_GIT, ["-C", target, "-c", "core.autocrlf=false", ...args],
    { encoding: "utf8", env });
  if (r.status !== 0) throw new Error(`git ${args.join(" ")}: ${r.stderr}`);
  return r.stdout;
};
const copy = (sub) => cpSync(join(here, sub), join(target, sub), { recursive: true, force: true });
const commit = (msg, ...paths) => {
  git("add", "--", ...paths);
  git("commit", "-q", "-m", msg);
};

cpSync(skeleton, target, { recursive: true });
git("init", "-q");
commit("Initial skeleton", ".");
if (mode === "lanes") {
  copy("backend");
  commit("backend: add difficulty to /api/trails", "backend");
  copy("frontend");
  commit("frontend: show the difficulty badge", "frontend");
} else if (mode === "one-commit") {
  copy("backend");
  copy("frontend");
  commit("Add difficulty end to end", "backend", "frontend");
}
console.log(git("log", "--oneline").trim());
