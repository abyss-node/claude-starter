import { hasFlag } from './map.js';

function passes(entry, flags) {
  if (entry.if !== undefined && !hasFlag(flags, entry.if)) return false;
  if (entry.ifNot !== undefined && hasFlag(flags, entry.ifNot)) return false;
  return true;
}

function visibleChoices(node, flags) {
  return (node.choices || []).filter((c) => passes(c, flags));
}

const ENDED = (battle = null) => ({ node: null, text: '', choices: [], ended: true, battle });

function addItem(inv, id, n) {
  return { ...inv, [id]: (inv[id] || 0) + n };
}

function enter(tree, game, nodeId) {
  const node = tree.nodes[nodeId];
  const flags = { ...game.flags };
  for (const f of node.set || []) flags[f] = true;
  let inventory = game.inventory;
  for (const g of node.give || []) inventory = addItem(inventory, g.item, g.count ?? 1);
  const next = { ...game, flags, inventory };
  const view = {
    node: nodeId,
    text: node.text,
    choices: visibleChoices(node, flags).map((c) => c.text),
    ended: false,
    battle: null,
  };
  return { game: next, view };
}

export function startDialogue(tree, game) {
  let nodeId = null;
  if (typeof tree.start === 'string') nodeId = tree.start;
  else {
    const hit = tree.start.find((e) => passes(e, game.flags));
    nodeId = hit ? hit.node : null;
  }
  if (nodeId === null) return { game: { ...game }, view: ENDED() };
  return enter(tree, game, nodeId);
}

export function advanceDialogue(tree, game, view, choice) {
  if (view.ended) return { game: { ...game }, view: { ...view } };
  const node = tree.nodes[view.node];
  const visible = visibleChoices(node, game.flags);
  let target;
  let cur = game;
  if (visible.length > 0) {
    if (!Number.isInteger(choice) || choice < 0 || choice >= visible.length) {
      throw new RangeError(`choice ${String(choice)} is not one of ${visible.length} visible choices`);
    }
    const picked = visible[choice];
    const flags = { ...game.flags };
    for (const f of picked.set || []) flags[f] = true;
    cur = { ...game, flags };
    target = picked.next;
  } else {
    if (node.battle) return { game: { ...game }, view: ENDED(node.battle) };
    target = node.next;
  }
  if (target === null || target === undefined) return { game: cur, view: ENDED() };
  return enter(tree, cur, target);
}
