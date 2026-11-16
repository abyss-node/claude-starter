// Turns API data into HTML strings. No DOM here, so node --test can import it.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

export function renderTrailRow(trail) {
  const stats = `${trail.length_km} km · ${trail.climb_m} m climb`;
  return [
    `<li class="trail" data-id="${escapeHtml(trail.id)}">`,
    `<span class="trail-name">${escapeHtml(trail.name)}</span>`,
    `<span class="trail-stats">${escapeHtml(stats)}</span>`,
    `</li>`,
  ].join("");
}

export function renderBoard(trails) {
  if (!trails.length) return `<p class="empty">No trails yet.</p>`;
  return `<ul class="board">${trails.map(renderTrailRow).join("")}</ul>`;
}
