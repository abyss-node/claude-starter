// Fair Share: split a bill between friends in whole cents. See BRIEF.md for what each function promises.

function checkCents(totalCents) {
  if (!Number.isInteger(totalCents) || totalCents < 0) {
    throw new RangeError(`the total must be a whole number of cents, zero or more, not ${totalCents}`);
  }
}

export function split(totalCents, people) {
  checkCents(totalCents);
  if (!Number.isInteger(people) || people < 1) {
    throw new RangeError(`the number of people must be a whole number, one or more, not ${people}`);
  }
  const base = Math.floor(totalCents / people);
  const left = totalCents - base * people;
  const shares = new Array(people).fill(base);
  // The cents left over go one each to the first people, so the larger shares come first.
  for (let given = 0; given < left; given++) shares[given] += 1;
  return shares;
}

export function withTip(totalCents, tipPercent) {
  checkCents(totalCents);
  if (typeof tipPercent !== 'number' || !Number.isFinite(tipPercent) || tipPercent < 0) {
    throw new RangeError(`the tip must be a percentage, zero or more, not ${tipPercent}`);
  }
  return Math.floor((totalCents * (100 + tipPercent)) / 100 + 0.5);
}
