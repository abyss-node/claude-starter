#!/usr/bin/env python3
"""Render a seeded, looping maths animation to numbered PNG frames.

Python standard library only. Example:

    python trippy.py --seed 7 --width 320 --height 180 --fps 12 --seconds 4 --loop
"""
import argparse
import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import zlib

TAU = 2.0 * math.pi

# Cosine palettes: colour(t) = clamp(a + b * cos(TAU * (c * t + d))), t in [0, 1].
PALETTES = {
    "acid": ((0.50, 0.50, 0.50), (0.50, 0.50, 0.50), (1.00, 1.00, 1.00), (0.00, 0.33, 0.67)),
    "ember": ((0.55, 0.35, 0.25), (0.45, 0.35, 0.25), (1.00, 1.00, 1.00), (0.00, 0.08, 0.15)),
    "lagoon": ((0.25, 0.50, 0.60), (0.25, 0.40, 0.40), (1.00, 1.00, 1.00), (0.50, 0.25, 0.00)),
    "dusk": ((0.50, 0.40, 0.60), (0.50, 0.30, 0.40), (2.00, 1.00, 1.00), (0.25, 0.00, 0.50)),
}
DEFAULT_PALETTE = "acid"

TRANSFORMS = ("fold", "swirl")
FIELDS = ("warp", "rings")
BLOCKS = TRANSFORMS + FIELDS

# Without --loop, the motion repeats every DRIFT_PERIOD seconds, chosen so it
# does not line up with a whole number of seconds.
DRIFT_PERIOD = 3.7
LUT_SIZE = 1024
FRAME_RE = re.compile(r"^frame_\d+\.png$")


class UsageError(Exception):
    pass


# ---------------------------------------------------------------- palettes

def parse_palette(text):
    """Return a function t -> (r, g, b) floats in [0, 1], and a JSON-able description."""
    name = text.strip().lower()
    if name in PALETTES:
        a, b, c, d = PALETTES[name]

        def cosine(t):
            return tuple(
                min(1.0, max(0.0, a[i] + b[i] * math.cos(TAU * (c[i] * t + d[i]))))
                for i in range(3)
            )

        return cosine, {"kind": "cosine", "name": name}

    stops = []
    for part in text.split(","):
        part = part.strip().lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", part):
            raise UsageError(
                "unknown palette %r: use one of %s or a comma-separated hex list such as "
                "ff0055,22ccaa" % (text, ", ".join(sorted(PALETTES)))
            )
        stops.append(tuple(int(part[i:i + 2], 16) / 255.0 for i in (0, 2, 4)))
    if len(stops) < 2:
        raise UsageError("a hex palette needs at least two colours, got %r" % text)

    def ramp(t):
        x = t * (len(stops) - 1)
        k = min(int(x), len(stops) - 2)
        f = x - k
        p, q = stops[k], stops[k + 1]
        return tuple(p[i] + (q[i] - p[i]) * f for i in range(3))

    return ramp, {"kind": "hex", "stops": ["%02x%02x%02x" % tuple(round(v * 255) for v in s) for s in stops]}


def palette_lut(fn):
    lut = []
    for i in range(LUT_SIZE):
        r, g, b = fn(i / (LUT_SIZE - 1))
        lut.append(bytes((round(r * 255), round(g * 255), round(b * 255))))
    return lut


# ---------------------------------------------------------------- recipe

def make_recipe(seed):
    """The seed picks the building blocks and their parameters.

    CPython seeds an int by its absolute value, so random.Random(-7) would draw exactly what
    random.Random(7) draws and the two seeds would make the same picture. A negative seed
    therefore takes a string seed instead. Non-negative seeds keep the int seeding, so
    their recipes do not change.
    """
    rng = random.Random(seed if seed >= 0 else "negative-%d" % seed)
    blocks = rng.sample(BLOCKS, rng.choice((2, 3)))
    if not any(b in FIELDS for b in blocks):
        blocks.append(rng.choice(FIELDS))
    params = {
        "zoom": rng.uniform(1.2, 2.4),
        "fold_k": rng.choice((3, 4, 5, 6, 7, 8)),
        "fold_spin": rng.choice((-1, 1)),
        "swirl": rng.uniform(1.0, 3.0) * rng.choice((-1, 1)),
        "swirl_wobble": rng.uniform(0.3, 1.0),
        "warp_scale": rng.uniform(1.5, 3.5),
        "warp_strength": rng.uniform(1.0, 2.5),
        "warp_orbit": rng.uniform(0.6, 1.4),
        "ring_freq": rng.uniform(6.0, 16.0),
        "ring_speed": rng.choice((1, 2, 3)),
        "ring_cx": rng.uniform(-0.3, 0.3),
        "ring_cy": rng.uniform(-0.3, 0.3),
        "cycles": rng.uniform(1.0, 2.5),
    }
    return {"seed": seed, "blocks": blocks, "params": params}


def make_noise(rng):
    perm = list(range(256))
    rng.shuffle(perm)
    perm = perm + perm
    vals = [rng.random() for _ in range(256)]
    floor = math.floor

    def noise(x, y):
        xf = floor(x)
        yf = floor(y)
        fx = x - xf
        fy = y - yf
        xi = xf & 255
        yi = yf & 255
        sx = fx * fx * (3.0 - 2.0 * fx)
        sy = fy * fy * (3.0 - 2.0 * fy)
        pa = perm[xi]
        pb = perm[xi + 1]
        v00 = vals[perm[pa + yi]]
        v10 = vals[perm[pb + yi]]
        v01 = vals[perm[pa + yi + 1]]
        v11 = vals[perm[pb + yi + 1]]
        top = v00 + (v10 - v00) * sx
        bot = v01 + (v11 - v01) * sx
        return top + (bot - top) * sy

    def fbm(x, y):
        return (noise(x, y) * 0.5 + noise(x * 2.03 + 17.1, y * 2.03 + 3.7) * 0.25
                + noise(x * 4.01 + 41.3, y * 4.01 + 29.9) * 0.125) / 0.875

    return fbm


# ---------------------------------------------------------------- rendering

def render_frame(width, height, recipe, fbm, lut, theta):
    """theta is the animation angle; everything is periodic in theta with period TAU."""
    p = recipe["params"]
    blocks = recipe["blocks"]
    transforms = [b for b in blocks if b in TRANSFORMS]
    fields = [b for b in blocks if b in FIELDS]
    cos, sin, atan2, hypot = math.cos, math.sin, math.atan2, math.hypot

    zoom = p["zoom"]
    half = min(width, height) / 2.0
    seg = TAU / p["fold_k"]
    fold_rot = p["fold_spin"] * theta
    swirl = p["swirl"]
    swirl_off = p["swirl_wobble"] * sin(theta)
    ws = p["warp_scale"]
    wk = p["warp_strength"]
    ox = p["warp_orbit"] * cos(theta)
    oy = p["warp_orbit"] * sin(theta)
    rf = p["ring_freq"]
    rphase = p["ring_speed"] * theta
    rcx, rcy = p["ring_cx"], p["ring_cy"]
    cyc = TAU * p["cycles"]
    nfield = len(fields)
    top = LUT_SIZE - 1

    rows = []
    for j in range(height):
        row = [b"\x00"]  # PNG filter type 0 (None)
        y0 = (j + 0.5 - height / 2.0) / half * zoom
        for i in range(width):
            x = (i + 0.5 - width / 2.0) / half * zoom
            y = y0
            for t in transforms:
                r = hypot(x, y)
                a = atan2(y, x)
                if t == "fold":
                    a = (a + fold_rot) % seg
                    if a > seg * 0.5:
                        a = seg - a
                else:
                    a += swirl * r + swirl_off
                x = r * cos(a)
                y = r * sin(a)
            v = 0.0
            for f in fields:
                if f == "warp":
                    u = x * ws
                    w = y * ws
                    qx = fbm(u + ox, w + oy)
                    qy = fbm(u - oy + 5.2, w + ox + 1.3)
                    v += fbm(u + wk * qx, w + wk * qy)
                else:
                    v += 0.5 + 0.5 * cos(rf * hypot(x - rcx, y - rcy) - rphase)
            v /= nfield
            s = 0.5 - 0.5 * cos(cyc * v + theta)
            row.append(lut[int(s * top + 0.5)])
        rows.append(b"".join(row))
    return b"".join(rows)


def png_bytes(width, height, raw):
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- CLI

def positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a whole number, got %r" % text)
    if value < 1 or value > 8192:
        raise argparse.ArgumentTypeError("expected 1..8192, got %d" % value)
    return value


def positive_float(text):
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a number, got %r" % text)
    if not (value > 0 and math.isfinite(value)):
        raise argparse.ArgumentTypeError("expected a positive number, got %r" % text)
    return value


def build_parser():
    ap = argparse.ArgumentParser(description="Render a seeded maths animation to PNG frames.")
    ap.add_argument("--seed", type=int, default=None,
                    help="whole number; omitted, a random one is picked and printed as 'seed: N'")
    ap.add_argument("--width", type=positive_int, default=320)
    ap.add_argument("--height", type=positive_int, default=180)
    ap.add_argument("--fps", type=positive_int, default=12)
    ap.add_argument("--seconds", type=positive_float, default=4.0)
    ap.add_argument("--palette", default=DEFAULT_PALETTE,
                    help="a name (%s) or hex colours like ff0055,22ccaa,110033"
                    % ", ".join(sorted(PALETTES)))
    ap.add_argument("--loop", action="store_true", help="make the last frame flow into the first")
    ap.add_argument("--out", default="frames", help="folder for the frames (default: frames)")
    ap.add_argument("--mp4", action="store_true", help="also encode video.mp4 if ffmpeg is installed")
    return ap


def ffmpeg_command(ffmpeg, out, fps):
    return [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps),
            "-i", os.path.join(out, "frame_%04d.png"),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p",
            os.path.join(out, "video.mp4")]


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        pal_fn, pal_desc = parse_palette(args.palette)
    except UsageError as exc:
        print("trippy: error: %s" % exc, file=sys.stderr)
        return 2

    if args.seed is None:
        args.seed = random.SystemRandom().randrange(1, 1000000000)
        print("seed: %d" % args.seed)

    frames = max(1, int(round(args.fps * args.seconds)))
    recipe = make_recipe(args.seed)
    fbm = make_noise(random.Random("noise-%d" % args.seed))
    lut = palette_lut(pal_fn)

    out = args.out
    os.makedirs(out, exist_ok=True)
    for name in os.listdir(out):
        if FRAME_RE.match(name):
            os.remove(os.path.join(out, name))

    for k in range(frames):
        if args.loop:
            theta = TAU * k / frames
        else:
            theta = TAU * (k / args.fps) / DRIFT_PERIOD
        raw = render_frame(args.width, args.height, recipe, fbm, lut, theta)
        with open(os.path.join(out, "frame_%04d.png" % k), "wb") as fh:
            fh.write(png_bytes(args.width, args.height, raw))

    with open(os.path.join(out, "recipe.json"), "w", encoding="utf-8") as fh:
        json.dump({"seed": args.seed, "blocks": recipe["blocks"], "palette": pal_desc,
                   "width": args.width, "height": args.height, "fps": args.fps,
                   "seconds": args.seconds, "frames": frames, "loop": args.loop},
                  fh, indent=2)
    print("wrote %d frames to %s (blocks: %s)" % (frames, out, " + ".join(recipe["blocks"])))

    if args.mp4:
        ffmpeg = shutil.which("ffmpeg")
        cmd = ffmpeg_command(ffmpeg or "ffmpeg", out, args.fps)
        if ffmpeg is None:
            print("ffmpeg was not found, so no video was made. Install ffmpeg, then run:")
            print("  " + " ".join(_quote(c) for c in cmd))
            return 0
        subprocess.run(cmd, check=True)
        print("wrote %s" % os.path.join(out, "video.mp4"))
    return 0


def _quote(text):
    """Quote one argument so the printed command pastes into this OS's usual shell."""
    if re.fullmatch(r"[\w@%+=:,./\\-]+", text):
        return text
    if os.name == "nt":  # double quotes work in both cmd and PowerShell
        return '"' + text + '"'
    return "'" + text.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    sys.exit(main())
