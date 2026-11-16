// Backend task: GET /api/trails gains a `difficulty` field, computed from length and climb.
import { test } from "node:test";
import assert from "node:assert/strict";
import { SKELETON_IDS, SKELETON_TRAILS, WANTED_DIFFICULTY, expectedDifficulty, getJson, originalFields, servedFromCopy, withBackend } from "./helpers.mjs";

// A backend is started for each check and stopped when it has answered.
async function trails() {
  return withBackend(async (base) => {
    const { status, body } = await getJson(`${base}/api/trails`);
    assert.equal(status, 200, "GET /api/trails should answer 200");
    assert.ok(Array.isArray(body.trails), "the response should be {\"trails\": [...]}");
    return body.trails;
  });
}

test("backend: starts on a free port and answers /api/health", async () => {
  await withBackend(async (base) => {
    const { status, body } = await getJson(`${base}/api/health`);
    assert.equal(status, 200);
    assert.equal(body.ok, true);
  });
});

test("backend: /api/trails still serves every trail with its original fields", async () => {
  const list = await trails();
  assert.deepEqual(list.map((t) => t.id).sort(), [...SKELETON_IDS].sort());
  const byId = new Map(list.map((t) => [t.id, t]));
  for (const want of SKELETON_TRAILS) {
    const got = originalFields(byId.get(want.id));
    assert.deepEqual(got, want, `${want.id}: served ${JSON.stringify(got)}, the skeleton has ${JSON.stringify(want)}`);
  }
});

test("backend: every trail carries a difficulty field", async () => {
  const list = await trails();
  const missing = list.filter((t) => !("difficulty" in t)).map((t) => t.id);
  assert.deepEqual(missing, [], `trails without difficulty: ${missing.join(", ")}`);
  for (const t of list) {
    assert.ok(["easy", "moderate", "hard"].includes(t.difficulty), `${t.id}: ${JSON.stringify(t.difficulty)}`);
  }
});

test("backend: difficulty follows the rule, boundaries included", async () => {
  const list = await trails();
  // The answer comes from the skeleton's data, so editing a trail's numbers cannot move its expectation.
  const wrong = list
    .filter((t) => t.difficulty !== WANTED_DIFFICULTY[t.id])
    .map((t) => `${t.id}: got ${JSON.stringify(t.difficulty)}, want ${WANTED_DIFFICULTY[t.id]}`);
  assert.ok(wrong.length === 0, `wrong difficulty: ${wrong.join("; ")}`);
  const byId = Object.fromEntries(list.map((t) => [t.id, t.difficulty]));
  assert.equal(byId.quillpond, "easy", "score 7.99 is easy");
  assert.equal(byId.saltcedar, "moderate", "score exactly 8 is moderate");
  assert.equal(byId["cinder-stair"], "hard", "score exactly 15 is hard");
  await checkProbes();
});

// The shipped catalogue leaves bands unprobed (nothing scores between 13.2 and 15, none is a fractional
// climb that rounds across a bound), so the rule is also run on a data file written for the purpose.
// It only counts when the workspace's backend reads backend/trails.json, as the skeleton's does.
const PROBES = [
  [0, 0], [3, 499], [6, 200], [0, 800], [8, 0], [7.5, 99], [10, 499], [5, 1000], [15, 0], [0, 1500],
  [14.5, 99], [10, 501], [100, 5000], [2, 150],
].map(([length_km, climb_m], i) => ({ id: `probe-${i}`, name: `Probe ${i}`, length_km, climb_m }));

async function checkProbes() {
  const served = await servedFromCopy(PROBES);
  if (!served) return; // the data is not read from backend/trails.json, so it cannot be swapped
  const wrong = served
    .filter((t) => t.difficulty !== expectedDifficulty(PROBES.find((p) => p.id === t.id)))
    .map((t) => {
      const p = PROBES.find((q) => q.id === t.id);
      return `${p.length_km} km + ${p.climb_m} m: got ${JSON.stringify(t.difficulty)}, want ${expectedDifficulty(p)}`;
    });
  assert.ok(wrong.length === 0, `wrong difficulty on probe data: ${wrong.join("; ")}`);
}

test("backend: an unknown API path keeps the error envelope", async () => {
  await withBackend(async (base) => {
    const { status, body } = await getJson(`${base}/api/no-such-route`);
    assert.equal(status, 404);
    assert.equal(body?.error?.code, "not_found");
    assert.equal(typeof body.error.message, "string");
  });
});
