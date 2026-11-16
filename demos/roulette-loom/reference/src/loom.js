// Rolling-circle curves: a circle of radius r rolls round the inside of a ring of radius R, and a pen at
// distance d from its centre draws the curve. Angles are in radians; the ring is centred on the origin.

function checkRadii(R, r) {
  if (!Number.isInteger(R) || !Number.isInteger(r) || r <= 0 || r >= R) {
    throw new RangeError(`the radii must be whole numbers with 0 < r < R, not R=${R} and r=${r}`);
  }
}

function checkPen(d) {
  if (typeof d !== 'number' || !Number.isFinite(d) || d < 0) {
    throw new RangeError(`the pen's distance d must be a number, zero or more, not ${d}`);
  }
}

export function gcd(a, b) {
  if (!Number.isInteger(a) || !Number.isInteger(b) || a <= 0 || b <= 0) {
    throw new RangeError(`gcd takes two positive whole numbers, not ${a} and ${b}`);
  }
  while (b !== 0) [a, b] = [b, a % b];
  return a;
}

// The rolling circle's centre is back where it began after every lap; the pen is back only once the circle
// has also turned a whole number of times, which first happens after r / gcd(R, r) laps.
export function laps(R, r) {
  checkRadii(R, r);
  return r / gcd(R, r);
}

export function point(R, r, d, t) {
  checkRadii(R, r);
  checkPen(d);
  const spin = ((R - r) * t) / r;
  return { x: (R - r) * Math.cos(t) + d * Math.cos(spin), y: (R - r) * Math.sin(t) - d * Math.sin(spin) };
}

export function trace(R, r, d, steps) {
  checkRadii(R, r);
  checkPen(d);
  if (!Number.isInteger(steps) || steps < 1) {
    throw new RangeError(`steps must be a whole number, one or more, not ${steps}`);
  }
  const end = 2 * Math.PI * laps(R, r);
  const points = [];
  for (let i = 0; i <= steps; i++) points.push(point(R, r, d, (end * i) / steps));
  return points;
}
