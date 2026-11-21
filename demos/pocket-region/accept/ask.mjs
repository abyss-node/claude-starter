// How a numbered check asks the workspace something: a scenario of one of the sc-*.mjs modules, run by
// demos/probe.mjs in a process of its own beside the workspace's code. Each probe is one process start, and its
// timeout is what stops an endless loop in the workspace from hanging a check.
import { scenario } from '../../probe.mjs';

export const ask = (file, name, ...args) => scenario(new URL(file, import.meta.url).href, name, args, { timeoutMs: 25000 });
