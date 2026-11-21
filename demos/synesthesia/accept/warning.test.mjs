import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ask } from './helpers.mjs';

const ok = (o, label) => {
  assert.ok(o.ok, `${label} threw ${o.error?.name}: ${o.error?.message}`);
  return o.value;
};

test('item 18: the warning shows on a first run and stops showing once acknowledged', () => {
  const w = ask('warnings');
  assert.equal(typeof w.key, 'string');
  assert.ok(w.key.length > 0);
  assert.equal(ok(w.first, 'shouldShowWarning'), true, 'first run');
  assert.equal(ok(w.again, 'shouldShowWarning'), true, 'asking does not acknowledge');
  assert.equal(ok(w.acknowledged, 'acknowledgeWarning'), true, 'acknowledge reports that it saved');
  assert.equal(ok(w.after, 'shouldShowWarning'), false, 'after acknowledging');
  assert.equal(w.stored, 'yes');
  assert.equal(ok(w.earlierVisit, 'shouldShowWarning'), false, 'a saved acknowledgement from an earlier visit');
});

test('item 18: other stored values do not count as an acknowledgement', () => {
  const w = ask('warnings');
  assert.equal(ok(w.otherKey, 'shouldShowWarning'), true);
  ['no', '', '1', 'true', 'YES'].forEach((v, i) => assert.equal(ok(w.otherValues[i], 'shouldShowWarning'), true, `stored value ${JSON.stringify(v)}`));
});

test('item 18: with no usable storage the warning shows every time and nothing throws', () => {
  const w = ask('warnings');
  for (const none of w.noStorage) {
    assert.equal(ok(none.show, 'shouldShowWarning'), true);
    assert.equal(ok(none.ack, 'acknowledgeWarning'), false);
  }
  assert.equal(ok(w.broken.show, 'shouldShowWarning'), true);
  assert.equal(ok(w.broken.ack, 'acknowledgeWarning'), false);
});

test('item 18: WARNING_TEXT warns about flashing light and photosensitivity and mentions the limiter', () => {
  const { text } = ask('warnings');
  assert.equal(typeof text, 'string');
  assert.ok(text.length >= 80, 'WARNING_TEXT is too short to be a warning');
  assert.match(text, /flash/i);
  assert.match(text, /photosensitiv|epilep|seizure/i);
  assert.match(text, /limiter/i);
});
