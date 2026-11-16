import { test } from 'node:test';
import assert from 'node:assert/strict';
import { momentum, energy, spinRose } from './helpers.mjs';
import { ask } from './ask.mjs';

const close = (a, b, scale) => Math.abs(a - b) <= 1e-9 * Math.max(1, scale);
const motion = (tops) => JSON.stringify(tops.map((t) => [t.vx, t.vy, t.spin]));

// One recorded collide on two overlapping, approaching tops (the tops before it, after it, and after a second call),
// held to the rules of the brief: equal and opposite impulse, moving apart afterwards, no second impulse on the
// separating pair, and spin that never rises (friction on) or does not change at all (friction off), and energy
// that is kept (friction off) or only ever lost (friction on).
function checkClash({ label, friction, before, hit, after, again, afterAgain }) {
  const [px, py] = momentum({ tops: before });
  const scale = Math.abs(px) + Math.abs(py);
  assert.equal(hit, true, `${label}: overlapping, approaching tops must collide`);
  const [qx, qy] = momentum({ tops: after });
  assert.ok(close(px, qx, scale) && close(py, qy, scale), `${label}: momentum (${px}, ${py}) became (${qx}, ${qy})`);
  const e0 = energy({ tops: before });
  const e1 = energy({ tops: after });
  if (friction) {
    assert.ok(e1 <= e0 * (1 + 1e-9), `${label}: a clash gained energy (${e0} -> ${e1}); with friction on it may only lose it`);
  } else {
    assert.ok(Math.abs(e1 - e0) <= 1e-9 * e0, `${label}: friction off, the bounce must be perfectly elastic (energy ${e0} -> ${e1})`);
  }
  after.forEach((t, k) => {
    if (friction) {
      assert.ok(!spinRose(before[k].spin, t.spin),
        `${label}: top ${t.name}'s spin rose across collide (${before[k].spin} -> ${t.spin}); a clash may lose spin, never gain it`);
    } else {
      assert.equal(t.spin, before[k].spin, `${label}: friction off, top ${t.name}'s spin changed across collide (${before[k].spin} -> ${t.spin})`);
    }
  });
  const [a, b] = after;
  const nx = b.x - a.x;
  const ny = b.y - a.y;
  const vn = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
  assert.ok(vn > 0, `${label}: the tops are still approaching after the impulse`);

  assert.equal(again, false, `${label}: separating tops must not get a second impulse`);
  assert.equal(motion(afterAgain), motion(after), `${label}: collide changed velocities or spin of separating tops`);
}

// Two tops that do not touch, closing on each other: collide must say false and leave their velocities and
// spins alone.
function checkNoContact({ label, before, hit, after }) {
  const dist = Math.hypot(before[1].x - before[0].x, before[1].y - before[0].y);
  assert.equal(hit, false, `${label}: tops whose centres are ${dist.toFixed(3)} apart (radii 0.1 and 0.1, so they only touch inside 0.2) are not touching: collide must return false`);
  assert.equal(motion(after), motion(before), `${label}: collide changed the velocities or spins of tops that are not touching`);
}

test('Graded 6: momentum is conserved across one two-top impulse, and no spin rises', () => {
  const { contacts, clashes } = ask('clashes');
  // Approaching tops that are not touching, from just apart to far apart. A reach compared squared, or no reach
  // test at all, collides some of these.
  assert.equal(contacts.length, 10);
  for (const c of contacts) checkNoContact(c);

  // Fixed clashes (the tops' own friction high, low and nil; a tiny top against a wide one with almost no spin,
  // in both orders) and forty seeded ones, each with friction on and off: 6 + 6 + 80 in all.
  assert.equal(clashes.length, 92);
  for (const c of clashes) checkClash(c);
});
