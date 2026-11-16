// How a numbered check asks the workspace something: a scenario of scenarios.mjs, run by demos/probe.mjs in a
// process of its own beside the workspace's code. Each probe is one process start, and its timeout is what stops
// an endless loop in the workspace's step from hanging a check.
import { scenario } from '../../probe.mjs';

const SCENARIOS = new URL('./scenarios.mjs', import.meta.url).href;

export const ask = (name, ...args) => scenario(SCENARIOS, name, args, { timeoutMs: 25000 });
