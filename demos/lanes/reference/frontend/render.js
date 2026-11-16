// Turns API data into HTML strings. No DOM here, so node --test can import it.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const LEVELS = new Set(["easy", "moderate", "hard"]);

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

// The difficulty badge, or nothing when the backend sent no difficulty. An unknown level still
// shows (escaped) but gets no level class, so the stylesheet only colours the three it knows.
export function renderDifficulty(level) {
  if (level === undefined || level === null || level === "") return "";
  const cls = LEVELS.has(level) ? `difficulty difficulty-${level}` : "difficulty";
  return `<span class="${cls}">${escapeHtml(level)}</span>`;
}

export function renderTrailRow(trail) {
  const stats = `${trail.length_km} km · ${trail.climb_m} m climb`;
  return [
    `<li class="trail" data-id="${escapeHtml(trail.id)}">`,
    `<span class="trail-name">${escapeHtml(trail.name)}</span>`,
    `<span class="trail-stats">${escapeHtml(stats)}</span>`,
    renderDifficulty(trail.difficulty),
    `</li>`,
  ].join("");
}

export function renderBoard(trails) {
  if (!trails.length) return `<p class="empty">No trails yet.</p>`;
  return `<ul class="board">${trails.map(renderTrailRow).join("")}</ul>`;
}
