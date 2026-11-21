export function countOf(inv, id) {
  return Object.hasOwn(inv, id) ? inv[id] : 0;
}

export function addItem(inv, id, n = 1) {
  return { ...inv, [id]: countOf(inv, id) + n };
}

export function removeItem(inv, id, n = 1) {
  const have = countOf(inv, id);
  if (have < n) throw new RangeError(`only ${have} of ${id}, wanted ${n}`);
  const out = { ...inv };
  if (have - n === 0) delete out[id];
  else out[id] = have - n;
  return out;
}

export function useItem(content, inventory, party, itemId, index) {
  const fail = (reason) => ({ ok: false, reason, inventory: { ...inventory }, party: structuredClone(party) });
  const def = Object.hasOwn(content.items, itemId) ? content.items[itemId] : undefined;
  if (!def || countOf(inventory, itemId) < 1) return fail('none');
  if (def.kind === 'key') return fail('key');
  if (!Number.isInteger(index) || index < 0 || index >= party.length) return fail('bad-target');
  const target = party[index];
  const out = structuredClone(party);
  if (def.kind === 'heal') {
    if (target.hp <= 0) return fail('fainted');
    if (target.hp >= target.maxHp) return fail('full');
    out[index].hp = Math.min(target.maxHp, target.hp + def.amount);
  } else if (def.kind === 'revive') {
    if (target.hp > 0) return fail('alive');
    out[index].hp = Math.max(1, Math.floor(target.maxHp / 2));
  } else {
    return fail('key');
  }
  return { ok: true, reason: null, inventory: removeItem(inventory, itemId, 1), party: out };
}
