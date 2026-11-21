// The photosensitivity limiter and the first-run warning.

export const MAX_FLASHES_PER_SECOND = 3;
export const MIN_FLASH_GAP = 1 / MAX_FLASHES_PER_SECOND;
export const MAX_BRIGHTNESS_SLEW = 1.5; // brightness units per second
export const MAX_ZOOM_SLEW = 1.5; // zoom units per second
export const MAX_HUE_SLEW = 240; // degrees per second

export const WARNING_KEY = 'synesthesia.warning-acknowledged';
export const WARNING_TEXT =
  'Photosensitivity warning: this page shows moving light and colour that can flash in time with sound. ' +
  'Flashing lights can trigger seizures in people with photosensitive epilepsy. ' +
  'The flash limiter is on and caps flashes at about three per second; leave it on unless you know it is safe for everyone watching.';

export function createFlashLimiter() {
  let last = -Infinity;
  return {
    // Checks and records: true means this flash may happen.
    allow(time) {
      if (time - last >= MIN_FLASH_GAP - 1e-9) {
        last = time;
        return true;
      }
      return false;
    },
    // Records a flash that happened without asking (limiter off), so turning the limiter on mid-run still spaces from it.
    note(time) {
      last = Math.max(last, time);
    },
  };
}

export function slewToward(current, target, maxChange) {
  const limit = Math.max(0, maxChange);
  const delta = target - current;
  if (Math.abs(delta) <= limit) return target;
  return current + Math.sign(delta) * limit;
}

function wrapHue(h) {
  return ((h % 360) + 360) % 360;
}

// Moves a hue along the shorter arc, by at most maxChange degrees; the result is in [0, 360).
export function slewHue(current, target, maxChange) {
  const limit = Math.max(0, maxChange);
  const delta = ((((target - current) % 360) + 540) % 360) - 180;
  if (Math.abs(delta) <= limit) return wrapHue(target);
  return wrapHue(current + Math.sign(delta) * limit);
}

function storageOk(storage) {
  return storage && typeof storage.getItem === 'function' && typeof storage.setItem === 'function';
}

export function shouldShowWarning(storage) {
  try {
    if (!storageOk(storage)) return true;
    return storage.getItem(WARNING_KEY) !== 'yes';
  } catch {
    return true;
  }
}

export function acknowledgeWarning(storage) {
  try {
    if (!storageOk(storage)) return false;
    storage.setItem(WARNING_KEY, 'yes');
    return true;
  } catch {
    return false;
  }
}
