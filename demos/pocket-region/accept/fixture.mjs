// The held-out test world. Every call returns a fresh object.
export function fixture() {
  return {
    title: 'Fixture',
    start: { map: 'town', x: 4, y: 3, facing: 'up', party: [{ species: 'pup', level: 5 }], inventory: { tag: 1 } },
    endFlag: 'the_end',
    maps: {
      town: {
        id: 'town', name: 'Town', width: 9, height: 6,
        rows: ['#########', '#.......#', '#.......#', '#........', '#.......#', '#########'],
        warps: [{ x: 8, y: 3, to: 'wild', tx: 1, ty: 2, facing: 'right' }],
        gates: [{ x: 7, y: 3, flag: 'pass' }],
        npcs: [{ id: 'sage', x: 4, y: 2, tree: 'sage' }],
      },
      wild: {
        id: 'wild', name: 'Wild', width: 8, height: 5,
        rows: ['########', '#,,,,,,#', '........', '#,,,,,,#', '########'],
        warps: [
          { x: 0, y: 2, to: 'town', tx: 6, ty: 3, facing: 'left' },
          { x: 7, y: 2, to: 'keep', tx: 1, ty: 2, facing: 'right' },
        ],
        gates: [], npcs: [],
        encounterRate: 0, encounters: [],
      },
      keep: {
        id: 'keep', name: 'Keep', width: 6, height: 4,
        rows: ['######', '#....#', '#....#', '######'],
        warps: [], gates: [],
        npcs: [{ id: 'chief', x: 4, y: 2, tree: 'chief' }],
      },
    },
    trees: {
      sage: {
        start: [{ if: 'pass', node: 'done' }, { node: 'hi' }],
        nodes: {
          hi: { text: 'Hello', choices: [
            { text: 'Open the way', next: 'open', set: ['asked'] },
            { text: 'Just passing', next: 'bye' },
            { text: 'Secret', if: 'met_secret', next: 'bye' },
          ] },
          open: { text: 'Go on', set: ['pass'], give: [{ item: 'salve', count: 2 }], next: null },
          bye: { text: 'Bye', next: null },
          done: { text: 'Already open', next: null },
        },
      },
      chief: {
        start: [{ if: 'chief_beaten', node: 'thanks' }, { node: 'fight' }],
        nodes: {
          fight: { text: 'Fight!', battle: { party: [{ species: 'rockling', level: 6 }], win: 'chief_beaten' }, next: null },
          thanks: { text: 'You win', set: ['the_end'], next: null },
        },
      },
    },
    species: {
      pup: { id: 'pup', name: 'Pup', type: 'ember', hp: 40, atk: 50, def: 40, spd: 30, moves: ['jab', 'flare'] },
      sprig: { id: 'sprig', name: 'Sprig', type: 'moss', hp: 45, atk: 40, def: 45, spd: 35, moves: ['vine', 'jab'] },
      pool: { id: 'pool', name: 'Pool', type: 'brine', hp: 50, atk: 45, def: 50, spd: 25, moves: ['rinse', 'jab'] },
      rockling: { id: 'rockling', name: 'Rockling', type: 'plain', hp: 60, atk: 5, def: 60, spd: 5, moves: ['jab'] },
    },
    moves: {
      jab: { id: 'jab', name: 'Jab', type: 'plain', power: 40, accuracy: 100 },
      flare: { id: 'flare', name: 'Flare', type: 'ember', power: 50, accuracy: 100 },
      vine: { id: 'vine', name: 'Vine', type: 'moss', power: 50, accuracy: 100 },
      rinse: { id: 'rinse', name: 'Rinse', type: 'brine', power: 50, accuracy: 100 },
      fast: { id: 'fast', name: 'Fast', type: 'plain', power: 30, accuracy: 100, priority: 1 },
      dud: { id: 'dud', name: 'Dud', type: 'plain', power: 0, accuracy: 100 },
      wobbly: { id: 'wobbly', name: 'Wobbly', type: 'plain', power: 40, accuracy: 50 },
    },
    items: {
      salve: { id: 'salve', name: 'Salve', kind: 'heal', amount: 15 },
      spark: { id: 'spark', name: 'Spark', kind: 'revive' },
      tag: { id: 'tag', name: 'Tag', kind: 'key' },
    },
  };
}

// A hand-made creature: only the fields the battle rules read.
export function mon(over = {}) {
  return {
    species: 'pup', name: 'Pup', type: 'plain', level: 5,
    hp: 500, maxHp: 500, atk: 30, def: 30, spd: 20, moves: ['jab'], ...over,
  };
}
