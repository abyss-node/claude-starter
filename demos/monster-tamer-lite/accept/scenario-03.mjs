// Item 3: The type chart. Runs beside the workspace (demos/probe.mjs, scenario()) and returns TYPES, TYPE_CHART and
// what typeMultiplier gave for every pair (and for unknown types); 03-type-chart.test.mjs compares.
import { thrown } from './fixtures.mjs';

export const NAMES = ['cinder', 'tide', 'moss', 'spark', 'stone'];
export const BAD_PAIRS = [['fire', 'tide'], ['cinder', 'water'], [undefined, 'tide']];

export async function run({ load }) {
  const { TYPES, TYPE_CHART } = await load('src/data.js');
  const { typeMultiplier } = await load('src/rules.js');
  return {
    TYPES: structuredClone(TYPES),
    chart: Object.fromEntries(NAMES.map((att) => [att, NAMES.map((def) => (TYPE_CHART && TYPE_CHART[att] ? TYPE_CHART[att][def] : null))])),
    multiplier: Object.fromEntries(NAMES.map((att) => [att, NAMES.map((def) => typeMultiplier(att, def))])),
    bad: BAD_PAIRS.map(([a, d]) => thrown(() => typeMultiplier(a, d))),
  };
}
