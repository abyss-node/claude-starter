// Tile maps as data. A map is { id, name, width, height, rows, warps, gates, npcs, ... }.

export const WALKABLE = new Set(['.', ',']);

export function hasFlag(flags, name) {
  return Object.hasOwn(flags, name) && flags[name] === true;
}

export function tileAt(map, x, y) {
  if (!Number.isInteger(x) || !Number.isInteger(y)) return null;
  if (x < 0 || y < 0 || y >= map.height || x >= map.width) return null;
  return map.rows[y][x] ?? null;
}

// null when the tile can be entered, else 'edge' | 'tile' | 'npc' | 'gate'.
export function blockedReason(map, x, y, flags) {
  const t = tileAt(map, x, y);
  if (t === null) return 'edge';
  if (!WALKABLE.has(t)) return 'tile';
  if ((map.npcs || []).some((n) => n.x === x && n.y === y)) return 'npc';
  if ((map.gates || []).some((g) => g.x === x && g.y === y && !hasFlag(flags, g.flag))) return 'gate';
  return null;
}

export function canEnter(map, x, y, flags) {
  return blockedReason(map, x, y, flags) === null;
}
