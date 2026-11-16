// Vehicle handling, defined as data. One step = one fixed tick of DT seconds.
// Units: world units (about one pixel at scale 1) and seconds.

export const TICK_HZ = 60;
export const DT = 1 / TICK_HZ;

export const VEHICLES = {
  car: {
    kind: 'car',
    name: 'Brick',
    topSpeed: 420, // world units per second on road
    accel: 165, // peak forward acceleration from rest
    brakeDecel: 520,
    coastDecel: 70,
    turnRate: 2.0, // radians per second at full steer, once rolling
    steerSpeed: 40, // below this forward speed steering fades out
    grip: 9, // how fast sideways slip dies (per second)
    offSpeedFactor: 0.62, // top speed off track, as a share of topSpeed
    offGrip: 0.6, // grip off track, as a share of grip
    offDrag: 260, // how fast excess speed bleeds off when over the off-track top speed
    mass: 1200,
    radius: 14,
    length: 34,
    breadth: 18,
  },
  bike: {
    kind: 'bike',
    name: 'Wisp',
    topSpeed: 345,
    accel: 270,
    brakeDecel: 470,
    coastDecel: 55,
    turnRate: 3.0,
    steerSpeed: 30,
    grip: 7,
    offSpeedFactor: 0.42,
    offGrip: 0.3,
    offDrag: 320,
    mass: 260,
    radius: 9,
    length: 26,
    breadth: 8,
  },
};

function unit(v) {
  return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0;
}

function signed(v) {
  return Number.isFinite(v) ? Math.min(1, Math.max(-1, v)) : 0;
}

export function createVehicle(kind, pose = {}) {
  const spec = typeof kind === 'string' ? VEHICLES[kind] : kind;
  if (!spec) throw new Error(`unknown vehicle: ${kind}`);
  return {
    kind: spec.kind ?? String(kind),
    spec,
    x: pose.x ?? 0,
    y: pose.y ?? 0,
    heading: pose.heading ?? 0,
    vx: 0,
    vy: 0,
    speed: 0,
  };
}

// Advances one tick in place. surface is 'road' or 'off'.
export function stepVehicle(v, input = {}, surface = 'road') {
  const s = v.spec;
  const throttle = unit(input?.throttle);
  const brake = unit(input?.brake);
  const steer = signed(input?.steer);
  const off = surface !== 'road';

  let fx = Math.cos(v.heading);
  let fy = Math.sin(v.heading);
  const fwd0 = v.vx * fx + v.vy * fy;
  const steerScale = Math.min(1, Math.abs(fwd0) / s.steerSpeed) * (fwd0 < 0 ? -1 : 1);
  let h = v.heading + steer * s.turnRate * steerScale * DT;
  h -= 2 * Math.PI * Math.floor((h + Math.PI) / (2 * Math.PI));
  v.heading = h;

  fx = Math.cos(h);
  fy = Math.sin(h);
  const rx = -fy;
  const ry = fx;
  let fwd = v.vx * fx + v.vy * fy;
  let lat = v.vx * rx + v.vy * ry;

  const top = s.topSpeed * (off ? s.offSpeedFactor : 1);
  if (throttle > 0 && fwd < top) {
    const r = Math.max(0, fwd) / top;
    fwd = Math.min(top, fwd + s.accel * throttle * (1 - r * r) * DT);
  }
  if (fwd > top) fwd = Math.max(top, fwd - s.offDrag * DT);
  if (brake > 0) fwd = fwd > 0 ? Math.max(0, fwd - s.brakeDecel * brake * DT) : Math.min(0, fwd + s.brakeDecel * brake * DT);
  if (throttle === 0) fwd = fwd > 0 ? Math.max(0, fwd - s.coastDecel * DT) : Math.min(0, fwd + s.coastDecel * DT);

  lat *= Math.exp(-s.grip * (off ? s.offGrip : 1) * DT);

  v.vx = fx * fwd + rx * lat;
  v.vy = fy * fwd + ry * lat;
  v.x += v.vx * DT;
  v.y += v.vy * DT;
  v.speed = Math.hypot(v.vx, v.vy);
  return v;
}
