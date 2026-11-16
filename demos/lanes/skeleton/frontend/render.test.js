// Frontend lane tests. Run from the project root:  node --test frontend/render.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { renderBoard, renderTrailRow } from "./render.js";

const trail = { id: "t1", name: "Test Trail", length_km: 3, climb_m: 120 };

test("a row shows the name and the stats", () => {
  const html = renderTrailRow(trail);
  assert.match(html, /Test Trail/);
  assert.match(html, /3 km · 120 m climb/);
});

test("names are escaped", () => {
  const html = renderTrailRow({ ...trail, name: "<img src=x onerror=alert(1)>" });
  assert.doesNotMatch(html, /<img/);
});

test("an empty board says so", () => {
  assert.match(renderBoard([]), /No trails yet/);
});
