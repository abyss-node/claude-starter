// Frontend task: each row shows the trail's difficulty as a badge. Checked through render.js, which runs in a
// process of its own (the kit's probe.mjs) with no page, so a module that touches `document` fails here.
import { test } from "node:test";
import assert from "node:assert/strict";
import { values } from "../../probe.mjs";
import { badges, injected, textOf } from "./helpers.mjs";

const RENDER = "frontend/render.js";
const row = (trails) => values(RENDER, trails.map((t) => ["renderTrailRow", t]));
const base = { id: "t1", name: "Test Trail", length_km: 3, climb_m: 120 };
const LEVELS = ["easy", "moderate", "hard"];

test("frontend: a row shows its difficulty as a badge with the level's class", () => {
  const rows = row(LEVELS.map((level) => ({ ...base, difficulty: level })));
  LEVELS.forEach((level, i) => {
    const html = rows[i];
    const found = badges(html);
    assert.equal(found.length, 1, `${level}: want one difficulty badge in ${html}`);
    assert.ok(found[0].classes.includes(`difficulty-${level}`), `${level}: class difficulty-${level} in ${html}`);
    for (const other of LEVELS.filter((l) => l !== level)) {
      assert.ok(!found[0].classes.includes(`difficulty-${other}`), `${level}: must not carry difficulty-${other} in ${html}`);
    }
    assert.equal(found[0].text.toLowerCase(), level, `${level}: badge text in ${html}`);
  });
});

test("frontend: a row without difficulty renders no badge and no 'undefined'", () => {
  const rows = row([base, { ...base, difficulty: undefined }]);
  for (const html of rows) {
    assert.match(html, /Test Trail/);
    assert.equal(badges(html).length, 0, `no badge expected in ${html}`);
    assert.doesNotMatch(html, /\bundefined\b|\bnull\b/);
  }
});

// A value that reaches the page must come out inert (no injected tag, no event handler) and, where the
// workspace shows it as text, read back as exactly what the API sent.
const HOSTILE = [
  '"><img src=x onerror=alert(1)>',
  "<zz-inject>x</zz-inject>",
  'x" onmouseover="alert(1)',
  "a & b &amp; c &lt;b&gt; 'p' \"q\"",
];

test("frontend: the difficulty value is escaped like every other API value", () => {
  const rows = row(HOSTILE.map((value) => ({ ...base, difficulty: value })));
  HOSTILE.forEach((value, i) => {
    const html = rows[i];
    assert.deepEqual(injected(html), [], `difficulty ${JSON.stringify(value)} injected markup into ${html}`);
    assert.match(html, /Test Trail/);
    for (const badge of badges(html)) {
      assert.equal(badge.text.toLowerCase(), value.toLowerCase(), `difficulty ${JSON.stringify(value)} shows as ${JSON.stringify(badge.text)} in ${html}`);
    }
  });
});

test("frontend: names are still escaped and the board still renders", () => {
  const trails = [{ ...base, difficulty: "hard" }, { ...base, id: "t2", name: "Second Trail", difficulty: "easy" }];
  const calls = [
    ...HOSTILE.map((name) => ["renderTrailRow", { ...base, name, difficulty: "easy" }]),
    ...HOSTILE.map((id) => ["renderTrailRow", { ...base, id, difficulty: "easy" }]),
    ["renderTrailRow", { ...base, difficulty: "easy" }],
    ["renderBoard", []],
    ["renderBoard", trails],
  ];
  const got = values(RENDER, calls);
  const n = HOSTILE.length;
  HOSTILE.forEach((value, i) => {
    assert.deepEqual(injected(got[i]), [], `name ${JSON.stringify(value)} injected markup into ${got[i]}`);
    assert.ok(textOf(got[i]).includes(value), `name ${JSON.stringify(value)} does not read back from ${got[i]}`);
    assert.deepEqual(injected(got[n + i]), [], `id ${JSON.stringify(value)} injected markup into ${got[n + i]}`);
  });
  assert.match(got[2 * n], /Test Trail/);
  assert.match(got[2 * n + 1], /No trails yet/);
  assert.ok(got[2 * n + 2].includes("Test Trail") && got[2 * n + 2].includes("Second Trail"), `both rows on the board: ${got[2 * n + 2]}`);
});
