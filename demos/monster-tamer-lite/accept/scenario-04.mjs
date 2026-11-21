// Item 4: The content. Runs beside the workspace (demos/probe.mjs, scenario()) and returns the content of
// src/data.js as it is, with the kinds of value it holds, and the creatures makeCreature makes from each species at
// levels 1 and 30, with what a copy of each cannot carry (fixtures.mjs uncopied); 04-content.test.mjs holds them to
// the brief.
import { engineOf, uncopied } from './fixtures.mjs';

export const LEVELS = [1, 30];

export async function run({ load }) {
  const { data, rules } = await engineOf(load);
  const { TYPES, STATUS_TURNS, MOVES, SPECIES, WILD_TABLE, MAP } = data;
  return {
    TYPES: structuredClone(TYPES),
    STATUS_TURNS: structuredClone(STATUS_TURNS),
    MOVES: structuredClone(MOVES),
    SPECIES: structuredClone(SPECIES),
    WILD_TABLE: structuredClone(WILD_TABLE),
    MAP: structuredClone(MAP),
    uncopied: { MOVES: uncopied(MOVES, 'MOVES'), SPECIES: uncopied(SPECIES, 'SPECIES'), WILD_TABLE: uncopied(WILD_TABLE, 'WILD_TABLE') },
    creatures: (Array.isArray(SPECIES) ? SPECIES : []).map((s) => LEVELS.map((level) => {
      const c = rules.makeCreature(s, level);
      return { creature: structuredClone(c), uncopied: uncopied(c, `creature ${s && s.id}`) };
    })),
  };
}
