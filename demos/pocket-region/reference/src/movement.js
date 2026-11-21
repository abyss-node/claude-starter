import { blockedReason } from './map.js';

export const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

// Pure: returns { player, moved, blocked, warped }; the inputs are left alone.
export function movePlayer(content, flags, player, dir) {
  const d = DIRS[dir];
  if (!Object.hasOwn(DIRS, dir)) throw new TypeError(`unknown direction: ${String(dir)}`);
  const map = content.maps[player.map];
  const tx = player.x + d[0];
  const ty = player.y + d[1];
  const why = blockedReason(map, tx, ty, flags);
  if (why !== null) {
    return { player: { ...player, facing: dir }, moved: false, blocked: why, warped: false };
  }
  const warp = (map.warps || []).find((w) => w.x === tx && w.y === ty);
  if (warp) {
    return {
      player: { map: warp.to, x: warp.tx, y: warp.ty, facing: warp.facing ?? dir },
      moved: true, blocked: null, warped: true,
    };
  }
  return { player: { map: player.map, x: tx, y: ty, facing: dir }, moved: true, blocked: null, warped: false };
}
