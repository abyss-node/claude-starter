// Both tasks together: what the real backend serves, the real render module shows. The page's code runs in a
// process of its own (the kit's probe.mjs); the backend answers over HTTP from the Python process started here.
import { test } from "node:test";
import assert from "node:assert/strict";
import { values } from "../../probe.mjs";
import { WANTED_DIFFICULTY, badges, getJson, withBackend } from "./helpers.mjs";

test("end to end: the board built from /api/trails shows each trail's difficulty", async () => {
  const { body } = await withBackend((base) => getJson(`${base}/api/trails`));
  const trails = body.trails;
  assert.ok(Array.isArray(trails), "the response should be {\"trails\": [...]}");
  const [board, ...rows] = values("frontend/render.js", [["renderBoard", trails], ...trails.map((t) => ["renderTrailRow", t])]);
  trails.forEach((t, i) => {
    const want = WANTED_DIFFICULTY[t.id];
    assert.ok(want, `${t.id}: not a skeleton trail`);
    const row = badges(rows[i]);
    assert.equal(row.length, 1, `${t.id}: want one badge`);
    assert.ok(row[0].classes.includes(`difficulty-${want}`), `${t.id}: want difficulty-${want}, got ${row[0].classes}`);
    assert.equal(row[0].text.toLowerCase(), want, `${t.id}: badge text`);
    assert.ok(board.includes(t.name), `${t.id}: name on the board`);
  });
  const counts = (list) => list.reduce((acc, x) => ({ ...acc, [x]: (acc[x] ?? 0) + 1 }), {});
  assert.equal(badges(board).length, trails.length, "one badge per trail on the board");
  const shown = counts(badges(board).map((b) => b.classes.find((c) => c.startsWith("difficulty-"))));
  const wanted = counts(trails.map((t) => `difficulty-${WANTED_DIFFICULTY[t.id]}`));
  assert.deepEqual(shown, wanted, `badges by level: shown ${JSON.stringify(shown)}, want ${JSON.stringify(wanted)}`);
});
