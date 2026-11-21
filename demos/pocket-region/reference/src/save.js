export function canonicalJson(value) {
  if (value === null) return 'null';
  switch (typeof value) {
    case 'boolean': return value ? 'true' : 'false';
    case 'string': return JSON.stringify(value);
    case 'number':
      if (!Number.isFinite(value)) throw new TypeError(`cannot save ${value}`);
      return Object.is(value, -0) ? '0' : JSON.stringify(value);
    case 'object': {
      if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
      const keys = Object.keys(value).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
      return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(',')}}`;
    }
    default:
      throw new TypeError(`cannot save a value of type ${typeof value}`);
  }
}

export const SAVE_VERSION = 1;

export function saveGame(game) {
  return canonicalJson({ version: SAVE_VERSION, game });
}

export function loadGame(text) {
  if (typeof text !== 'string') throw new TypeError('a save is text');
  const data = JSON.parse(text);
  if (data === null || typeof data !== 'object' || data.version !== SAVE_VERSION) {
    throw new Error(`unsupported save version: ${data && data.version}`);
  }
  if (data.game === null || typeof data.game !== 'object') throw new Error('save has no game');
  return data.game;
}
