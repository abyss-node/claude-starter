// Browser entry: fetch the trails and put the board on the page.
import { escapeHtml, renderBoard } from "./render.js";

const root = document.querySelector("#board");

try {
  const response = await fetch("/api/trails");
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message ?? `HTTP ${response.status}`);
  root.innerHTML = renderBoard(body.trails);
} catch (err) {
  root.innerHTML = `<p class="error">Could not load trails: ${escapeHtml(err.message)}</p>`;
}
