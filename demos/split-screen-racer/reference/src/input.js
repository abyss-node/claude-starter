// Keyboard and optional gamepad to { throttle, brake, steer }. Browser only.

const held = new Set();

export function listen(target = window) {
  target.addEventListener('keydown', (e) => {
    held.add(e.code);
    if (e.code.startsWith('Arrow') || e.code === 'Space') e.preventDefault();
  });
  target.addEventListener('keyup', (e) => held.delete(e.code));
  target.addEventListener('blur', () => held.clear());
}

const SETS = {
  wasd: { up: 'KeyW', down: 'KeyS', left: 'KeyA', right: 'KeyD' },
  arrows: { up: 'ArrowUp', down: 'ArrowDown', left: 'ArrowLeft', right: 'ArrowRight' },
};

function fromKeys(set) {
  const k = SETS[set];
  return {
    throttle: held.has(k.up) ? 1 : 0,
    brake: held.has(k.down) ? 1 : 0,
    steer: (held.has(k.right) ? 1 : 0) - (held.has(k.left) ? 1 : 0),
  };
}

function fromPad(index) {
  const pads = typeof navigator !== 'undefined' && navigator.getGamepads ? navigator.getGamepads() : [];
  const pad = pads[index];
  if (!pad) return null;
  const axis = pad.axes[0] ?? 0;
  const steer = Math.abs(axis) < 0.15 ? 0 : axis;
  const throttle = pad.buttons[7]?.value ?? (pad.buttons[0]?.pressed ? 1 : 0);
  const brake = pad.buttons[6]?.value ?? (pad.buttons[1]?.pressed ? 1 : 0);
  if (!steer && !throttle && !brake) return null;
  return { throttle, brake, steer };
}

// Player 0 drives with WASD (and the arrows too in solo); player 1 with the arrows.
export function readInput(player, solo) {
  const pad = fromPad(player);
  if (pad) return pad;
  if (player === 0 && solo) {
    const a = fromKeys('wasd');
    const b = fromKeys('arrows');
    return {
      throttle: Math.max(a.throttle, b.throttle),
      brake: Math.max(a.brake, b.brake),
      steer: Math.max(-1, Math.min(1, a.steer + b.steer)),
    };
  }
  return fromKeys(player === 0 ? 'wasd' : 'arrows');
}

export function pressed(code) {
  return held.has(code);
}
