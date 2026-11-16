// The lane discipline, read from git history: after the initial commit, no commit touches both lanes.
import { test } from "node:test";
import assert from "node:assert/strict";
import { git, isBytecode, laneOf, samePath, workspace } from "./helpers.mjs";

function lines(out, sep = "\n") {
  return out.split(sep).map((s) => s.trim()).filter(Boolean);
}

function history() {
  const top = git("rev-parse", "--show-toplevel");
  assert.equal(top.status, 0, `the workspace is not a git repository: ${top.stderr.trim()}`);
  assert.ok(samePath(top.stdout.trim(), workspace()),
    `the workspace must be its own git repository, but git found ${top.stdout.trim()}`);
  const roots = git("rev-list", "--max-parents=0", "HEAD");
  assert.equal(roots.status, 0, `no commits yet: ${roots.stderr.trim()}`);
  const initial = new Set(lines(roots.stdout));
  const all = git("rev-list", "--reverse", "--no-merges", "HEAD");
  const later = lines(all.stdout).filter((sha) => !initial.has(sha));
  return later.map((sha) => {
    const files = git("diff-tree", "--no-commit-id", "--name-only", "-r", "--no-renames", "-z", sha);
    const subject = git("log", "-1", "--format=%s", sha).stdout.trim();
    const paths = lines(files.stdout, "\0");
    const lanes = [...new Set(paths.map(laneOf).filter(Boolean))].sort();
    return { sha: sha.slice(0, 10), subject, paths, lanes };
  });
}

test("lanes: the workspace is its own git repository with an initial commit", () => {
  history();
});

test("lanes: every commit after the initial one touches only one lane", () => {
  const crossing = history()
    .filter((c) => c.lanes.length > 1)
    .map((c) => `${c.sha} "${c.subject}" touches ${c.lanes.join(" and ")}: ${c.paths.join(", ")}`);
  assert.ok(crossing.length === 0, `commits that cross lanes: ${crossing.join("; ")}`);
});

test("lanes: the backend change and the frontend change are each committed", () => {
  const commits = history();
  assert.ok(commits.some((c) => c.lanes.includes("backend")), "no commit after the initial one touches backend/");
  assert.ok(commits.some((c) => c.lanes.includes("frontend")), "no commit after the initial one touches frontend/");
  const status = git("status", "--porcelain", "-z", "--no-renames", "--untracked-files=all", "--", "frontend", "backend");
  assert.equal(status.status, 0, status.stderr);
  // Each -z entry is "XY path", and X or Y may be a space, so entries are not trimmed before slicing.
  const entries = status.stdout.split("\0").filter(Boolean);
  const dirty = entries.map((e) => e.slice(3)).filter((p) => p && !isBytecode(p));
  assert.ok(dirty.length === 0, `uncommitted changes under frontend/ or backend/: ${dirty.join(", ")}`);
});
