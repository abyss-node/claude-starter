// The shipped world: three towns and one route, all original.

const hollow = {
  id: 'hollow', name: 'Wick Hollow', width: 12, height: 8,
  rows: [
    '############',
    '#..........#',
    '#..........#',
    '#..TT......#',
    '#..TT.......',
    '#..........#',
    '#..........#',
    '############',
  ],
  warps: [{ x: 11, y: 4, to: 'route1', tx: 1, ty: 3, facing: 'right' }],
  gates: [{ x: 9, y: 4, flag: 'met_elder' }],
  npcs: [
    { id: 'elder', x: 6, y: 3, tree: 'elder' },
    { id: 'tansy', x: 2, y: 5, tree: 'tansy' },
  ],
};

const route1 = {
  id: 'route1', name: 'Marrow Lane', width: 16, height: 7,
  rows: [
    '################',
    '#..,,,,,,,,,,..#',
    '#..,,,,,,,,,,..#',
    '................',
    '#..,,,,,,,,,,..#',
    '#..,,,,,,,,,,..#',
    '################',
  ],
  warps: [
    { x: 0, y: 3, to: 'hollow', tx: 10, ty: 4, facing: 'left' },
    { x: 15, y: 3, to: 'lanternfall', tx: 1, ty: 4, facing: 'right' },
  ],
  gates: [],
  npcs: [],
  encounterRate: 20,
  encounters: [
    { species: 'cindermoth', minLevel: 3, maxLevel: 5, weight: 3 },
    { species: 'pebblet', minLevel: 2, maxLevel: 4, weight: 5 },
    { species: 'tidepup', minLevel: 3, maxLevel: 4, weight: 2 },
  ],
};

const lanternfall = {
  id: 'lanternfall', name: 'Lanternfall', width: 12, height: 8,
  rows: [
    '############',
    '#..........#',
    '#..~~......#',
    '#..~~......#',
    '............',
    '#..........#',
    '#..........#',
    '############',
  ],
  warps: [
    { x: 0, y: 4, to: 'route1', tx: 14, ty: 3, facing: 'left' },
    { x: 11, y: 4, to: 'saltmere', tx: 1, ty: 3, facing: 'right' },
  ],
  gates: [{ x: 9, y: 4, flag: 'bell_rung' }],
  npcs: [{ id: 'bellkeeper', x: 6, y: 3, tree: 'bellkeeper' }],
};

const saltmere = {
  id: 'saltmere', name: 'Saltmere', width: 10, height: 7,
  rows: [
    '##########',
    '#........#',
    '#........#',
    '..~~.....#',
    '#..~~....#',
    '#........#',
    '##########',
  ],
  warps: [{ x: 0, y: 3, to: 'lanternfall', tx: 10, ty: 4, facing: 'left' }],
  gates: [],
  npcs: [{ id: 'warden', x: 7, y: 3, tree: 'warden' }],
};

const trees = {
  elder: {
    start: [{ if: 'met_elder', node: 'again' }, { node: 'hello' }],
    nodes: {
      hello: { text: 'Elder Orrin: The lane east is long. Take these tonics, and carry them well.', set: ['met_elder'], give: [{ item: 'tonic', count: 2 }], next: 'hello2' },
      hello2: { text: 'Elder Orrin: Ring the bell at Lanternfall and the harbour road will open.', next: null },
      again: { text: 'Elder Orrin: Go on. The lane will not walk itself.', next: null },
    },
  },
  tansy: {
    start: 'a',
    nodes: {
      a: { text: 'Tansy: Do you like the wick-smoke smell? Everyone in the Hollow does.', choices: [{ text: 'It is lovely', next: 'yes' }, { text: 'It makes me sneeze', next: 'no' }] },
      yes: { text: 'Tansy: Then you will fit right in.', next: null },
      no: { text: 'Tansy: Bless you, then. Walk faster.', next: null },
    },
  },
  bellkeeper: {
    start: [{ if: 'bell_rung', node: 'after' }, { node: 'ask' }],
    nodes: {
      ask: {
        text: 'Bellkeeper: The harbour bell rings only for a steady hand. Will you ring it?',
        choices: [
          { text: 'Ring the bell', next: 'rung', set: ['bell_rung'] },
          { text: 'Who are you?', next: 'who' },
          { text: 'Not yet', next: 'later' },
        ],
      },
      who: { text: 'Bellkeeper: Just the one who keeps the rope dry.', next: 'ask' },
      rung: { text: 'Bellkeeper: There. Hear it roll down to the water? The gate is open.', give: [{ item: 'harbour_token', count: 1 }], next: null },
      later: { text: 'Bellkeeper: The rope will wait.', next: null },
      after: { text: 'Bellkeeper: The gate is open. Mind the pier.', next: null },
    },
  },
  warden: {
    start: [{ if: 'warden_beaten', node: 'end' }, { node: 'challenge' }],
    nodes: {
      challenge: {
        text: 'Warden Ilse: I keep the Saltmere pier. Show me what your partner is worth.',
        battle: { party: [{ species: 'tidepup', level: 7 }], win: 'warden_beaten' },
        next: null,
      },
      end: { text: 'Warden Ilse: The pier is yours. Your road ends here, and begins again.', set: ['pocket_region_clear'], next: null },
    },
  },
};

export const CONTENT = {
  title: 'Pocket Region',
  start: { map: 'hollow', x: 6, y: 4, facing: 'up', party: [{ species: 'mossling', level: 8 }], inventory: {} },
  endFlag: 'pocket_region_clear',
  maps: { hollow, route1, lanternfall, saltmere },
  trees,
  species: {
    mossling: { id: 'mossling', name: 'Mossling', type: 'moss', hp: 45, atk: 50, def: 45, spd: 40, moves: ['leafnip', 'bump'] },
    cindermoth: { id: 'cindermoth', name: 'Cindermoth', type: 'ember', hp: 38, atk: 55, def: 35, spd: 60, moves: ['embertap', 'quickstep'] },
    tidepup: { id: 'tidepup', name: 'Tidepup', type: 'brine', hp: 50, atk: 45, def: 50, spd: 35, moves: ['brinejet', 'bump'] },
    pebblet: { id: 'pebblet', name: 'Pebblet', type: 'plain', hp: 40, atk: 40, def: 60, spd: 20, moves: ['bump', 'quickstep'] },
  },
  moves: {
    bump: { id: 'bump', name: 'Bump', type: 'plain', power: 40, accuracy: 100 },
    quickstep: { id: 'quickstep', name: 'Quickstep', type: 'plain', power: 30, accuracy: 100, priority: 1 },
    leafnip: { id: 'leafnip', name: 'Leaf Nip', type: 'moss', power: 45, accuracy: 100 },
    embertap: { id: 'embertap', name: 'Ember Tap', type: 'ember', power: 45, accuracy: 95 },
    brinejet: { id: 'brinejet', name: 'Brine Jet', type: 'brine', power: 45, accuracy: 95 },
  },
  items: {
    tonic: { id: 'tonic', name: 'Tonic', kind: 'heal', amount: 20 },
    sparkroot: { id: 'sparkroot', name: 'Sparkroot', kind: 'revive' },
    harbour_token: { id: 'harbour_token', name: 'Harbour Token', kind: 'key' },
  },
  walkthrough: { seed: 7, inputs: ["up","action","action","action","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","right","up","action","choose:1","action","choose:0","action","right","right","right","right","right","up","right","right","right","down","right","right","right","action","action","move:0","action","action"] },
};
