"""Held-out acceptance checks for the trippy-video brief.

The workspace under test is the copy acceptkit names (DEMO_WORKSPACE); its entry point is trippy.py. Every
render runs as a process of its own, started by acceptkit.run() with the validated Python and -s -B -S (no
site-packages, so a third-party import fails), from a work folder whose path contains a space and an apostrophe,
with an environment that holds no DEMO_ variable. The checks never import the workspace's code.

Plain `def test_*` functions with asserts; TESTS lists them in order for accept/run.py.
Python 3.9+, standard library only.
"""
import ast
import concurrent.futures
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import time
import zlib

import acceptkit as ak

# ------------------------------------------------------------ the contract

# Named cosine palettes, copied from BRIEF.md:
#   colour(t) = clamp01(a + b * cos(2*pi*(c*t + d))) * 255, per channel, t in [0, 1]
PALETTES = {
    "acid": ((0.50, 0.50, 0.50), (0.50, 0.50, 0.50), (1.00, 1.00, 1.00), (0.00, 0.33, 0.67)),
    "ember": ((0.55, 0.35, 0.25), (0.45, 0.35, 0.25), (1.00, 1.00, 1.00), (0.00, 0.08, 0.15)),
    "lagoon": ((0.25, 0.50, 0.60), (0.25, 0.40, 0.40), (1.00, 1.00, 1.00), (0.50, 0.25, 0.00)),
    "dusk": ((0.50, 0.40, 0.60), (0.50, 0.30, 0.40), (2.00, 1.00, 1.00), (0.25, 0.00, 0.50)),
}
PALETTE_TOL = 3.0        # max RGB distance (0-255 units) from the palette curve
LOOP_PHASE_TOL = 2       # per-channel difference allowed between same-phase frames
SEAM_FACTOR = 1.5        # seam step may be at most 1.5x the largest ordinary step ...
SEAM_SLACK = 1.0         # ... plus 1.0 (mean absolute difference, 0-255 units)
SEAM_FPS = 480           # seam renders: 16x9, 480 fps, 1 s, so one step is 1/480 of the cycle
SEAM_SEEDS = (3, 8, 12, 7, 11)  # tuned to the reference's seed-to-block mapping, which another solution
                                # need not share: rings+swirl; warp+swirl; warp+rings+swirl;
                                # swirl+rings+fold (7-fold); rings+swirl+fold (7-fold)
GIVEN_SEEDS = (1, 2, 3, 4,                  # picked blocks differ per seed
               0, -7, 2 ** 40 + 9)          # a falsy seed, a negative one, one wider than 32 bits
EDGE_SEEDS = (0, 7, -7, 9, 2 ** 40 + 9,     # all different: zero, a seed and its negative, a seed
              3, -3, 5, -5, 11, -11,         # and its 40-bit lift; then three more s / -s pairs;
              2 ** 40 + 3, 2 ** 32 + 7)      # two more wide ones, over seeds whose blocks use no noise
NAMED_SEEDS = EDGE_SEEDS + (1, 2, 4, 6)   # item 4 names these too; with the edge seeds they are all
                                          # different (5 is already in EDGE_SEEDS)
HASH_ORDER_SEEDS = (1, 2, 4, 5, 6, 7)    # seeds whose recipes hold two or three blocks, compared across
HASH_ORDER_HASHSEEDS = ("1", "2", "3")   # these PYTHONHASHSEED values (the cached renders use "0")
NOSEED_RUNS = 6          # runs without --seed, started together
SEED_LINE_RE = re.compile(r"^seed: (-?[0-9]+)$", re.MULTILINE)   # exactly "seed: " and the number
MIN_COLOURS = 24         # distinct colours in one 64x36 frame
RUNTIME_LIMIT_S = 20.0   # 64x36, 2 fps, 2 s render, wall time
FRAME_RE = re.compile(r"^frame_(\d{4})\.png$")

# ------------------------------------------------------------ workspace

_CACHE = {}
_WORK = []     # the work folder, made on first use
_COUNT = [0]


def workspace():
    return str(ak.workspace())


def entry():
    path = os.path.join(workspace(), "trippy.py")
    assert os.path.isfile(path), "no trippy.py at the workspace root"
    return path


def work_root():
    """A folder outside the copy whose path holds a space and an apostrophe; removed with ak.scratch()."""
    if not _WORK:
        root = ak.scratch() / "trippy accept '"
        root.mkdir()
        _WORK.append(str(root))
    return _WORK[0]


def new_dir(prefix):
    _COUNT[0] += 1
    d = os.path.join(work_root(), "%s%d" % (prefix, _COUNT[0]))
    os.mkdir(d)
    return d


def run_cli(args, out=None, env_extra=None, path_override=None, timeout=120):
    """Run trippy.py; return (CompletedProcess, out_dir, seconds)."""
    if out is None:
        out = new_dir("out '")
    extra = dict(env_extra or {})
    if path_override is not None:
        extra["PATH"] = path_override
    cmd = ak.python_argv(entry(), *[str(a) for a in args], "--out", out, stdlib_only=True)
    start = time.perf_counter()
    proc = ak.run(cmd, timeout, cwd=work_root(), env=ak.child_env(**extra))
    return proc, out, time.perf_counter() - start


def render(*args, hashseed="0"):
    """Cached successful render; returns dict with out, frames (sorted paths), seconds."""
    key = (tuple(str(a) for a in args), hashseed)
    if key not in _CACHE:
        proc, out, secs = run_cli(list(args), env_extra={"PYTHONHASHSEED": hashseed})
        assert proc.returncode == 0, "trippy.py %s exited %d: %s" % (
            " ".join(key[0]), proc.returncode, (proc.stderr or proc.stdout).strip()[-400:])
        _CACHE[key] = {"out": out, "frames": frame_files(out), "seconds": secs}
    return _CACHE[key]


def frame_files(out):
    names = sorted(n for n in os.listdir(out) if n.startswith("frame_") and n.endswith(".png"))
    return [os.path.join(out, n) for n in names]


def basic(seed=5, palette="ember", hashseed="0"):
    return render("--seed", seed, "--width", 64, "--height", 36, "--fps", 2,
                  "--seconds", 2, "--palette", palette, hashseed=hashseed)


def looped(fps):
    return render("--seed", 11, "--width", 64, "--height", 36, "--fps", fps,
                  "--seconds", 2, "--palette", "acid", "--loop")


# ------------------------------------------------------------ PNG reading

def read_png(path):
    """Decode an 8-bit RGB or RGBA, non-interlaced PNG. Returns (w, h, rgb bytes)."""
    with open(path, "rb") as fh:
        data = fh.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "%s: not a PNG signature" % os.path.basename(path)
    pos, ihdr, idat, ended = 8, None, [], False
    while pos < len(data):
        assert pos + 8 <= len(data), "truncated chunk header"
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        crc = data[pos + 8 + length:pos + 12 + length]
        assert len(body) == length and len(crc) == 4, "truncated chunk %r" % kind
        assert struct.unpack(">I", crc)[0] == zlib.crc32(kind + body) & 0xFFFFFFFF, \
            "bad CRC in chunk %r" % kind
        pos += 12 + length
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            ended = True
            break
    assert ihdr is not None, "no IHDR chunk"
    assert ended, "no IEND chunk"
    w, h, depth, ctype, comp, filt, interlace = ihdr
    assert depth == 8 and ctype in (2, 6), "want 8-bit RGB or RGBA, got depth %d type %d" % (depth, ctype)
    assert comp == 0 and filt == 0 and interlace == 0, "unsupported compression/filter/interlace"
    bpp = 3 if ctype == 2 else 4
    raw = zlib.decompress(b"".join(idat))
    stride = w * bpp
    assert len(raw) == h * (stride + 1), "pixel data is %d bytes, want %d" % (len(raw), h * (stride + 1))
    out = bytearray()
    prev = bytearray(stride)
    for y in range(h):
        ftype = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        assert ftype <= 4, "bad filter type %d" % ftype
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ftype == 1:
                line[i] = (line[i] + a) & 255
            elif ftype == 2:
                line[i] = (line[i] + b) & 255
            elif ftype == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 255
        prev = line
        if bpp == 3:
            out += line
        else:
            for i in range(0, stride, 4):
                assert line[i + 3] == 255, "transparent pixel in frame"
                out += line[i:i + 3]
    return w, h, bytes(out)


def pixels(path):
    return read_png(path)[2]


def colours(rgb):
    return {rgb[i:i + 3] for i in range(0, len(rgb), 3)}


def mean_abs_diff(a, b):
    assert len(a) == len(b)
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ------------------------------------------------------------ palette geometry

def cosine_far_colours(name, cols):
    """Colours farther than PALETTE_TOL from the named cosine curve, t in [0, 1]."""
    a, b, c, d = PALETTES[name]
    cell = 8.0
    grid = {}
    steps = 8192
    for k in range(steps + 1):
        t = k / steps
        pt = tuple(255.0 * min(1.0, max(0.0, a[i] + b[i] * math.cos(2 * math.pi * (c[i] * t + d[i]))))
                   for i in range(3))
        grid.setdefault(tuple(int(v // cell) for v in pt), []).append(pt)
    far = []
    for col in cols:
        key = tuple(int(v // cell) for v in col)
        best = float("inf")
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for pt in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        dist = math.sqrt(sum((col[i] - pt[i]) ** 2 for i in range(3)))
                        if dist < best:
                            best = dist
        if best > PALETTE_TOL:
            far.append((tuple(col), round(best, 1) if best < cell else ">%d" % cell))
    return far


def ramp_position(stops, col):
    """Where col sits on the ramp through evenly spaced stops: t in [0, 1] of the nearest point."""
    best, best_t = float("inf"), 0.0
    nseg = len(stops) - 1
    for k, (p, q) in enumerate(zip(stops, stops[1:])):
        seg = [q[i] - p[i] for i in range(3)]
        rel = [col[i] - p[i] for i in range(3)]
        ll = sum(v * v for v in seg)
        u = 0.0 if ll == 0 else max(0.0, min(1.0, sum(rel[i] * seg[i] for i in range(3)) / ll))
        dist = math.sqrt(sum((rel[i] - u * seg[i]) ** 2 for i in range(3)))
        if dist < best:
            best, best_t = dist, (k + u) / nseg
    return best_t


def polyline_far_colours(stops, cols):
    """Colours farther than PALETTE_TOL from the piecewise-linear ramp through stops."""
    far = []
    for col in cols:
        best = float("inf")
        for p, q in zip(stops, stops[1:]):
            seg = [q[i] - p[i] for i in range(3)]
            rel = [col[i] - p[i] for i in range(3)]
            ll = sum(s * s for s in seg)
            u = 0.0 if ll == 0 else max(0.0, min(1.0, sum(rel[i] * seg[i] for i in range(3)) / ll))
            dist = math.sqrt(sum((rel[i] - u * seg[i]) ** 2 for i in range(3)))
            best = min(best, dist)
        if best > PALETTE_TOL:
            far.append((tuple(col), round(best, 1)))
    return far


def hexes(text):
    return [tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) for h in text.split(",")]


# ------------------------------------------------------------ tests

def test_frame_count():
    r = basic()
    names = [os.path.basename(p) for p in r["frames"]]
    assert names == ["frame_%04d.png" % i for i in range(4)], \
        "64x36 at 2 fps for 2 s should give frame_0000..frame_0003.png, got %s" % names
    r = render("--seed", 3, "--width", 16, "--height", 9, "--fps", 4, "--seconds", 1.5)
    assert len(r["frames"]) == 6, "4 fps for 1.5 s should give 6 frames, got %d" % len(r["frames"])
    # Non-whole products: fps x seconds is rounded to the nearest whole number, but never
    # below 1 (1 fps for 0.2 s is 0.2 frames, which rounds to 0 and must still give one frame).
    # (No .5 products: those depend on the rounding rule for halves.)
    for fps, secs, want in ((4, 0.9, 4), (3, 0.7, 2), (1, 0.2, 1)):
        r = render("--seed", 3, "--width", 8, "--height", 8, "--fps", fps, "--seconds", secs)
        assert len(r["frames"]) == want, "%d fps for %s s is %.1f frames, which rounds to %d%s; got %d" % (
            fps, secs, fps * secs, int(round(fps * secs)),
            " (at least 1 frame is always written)" if want == 1 else "", len(r["frames"]))


def test_png_decodes_at_requested_size():
    for r, size in ((basic(), (64, 36)),
                    (render("--seed", 5, "--width", 17, "--height", 5, "--fps", 1, "--seconds", 2),
                     (17, 5))):
        assert r["frames"], "no frames written"
        for path in r["frames"]:
            w, h, _ = read_png(path)
            assert (w, h) == size, "%s is %dx%d, want %dx%d" % (os.path.basename(path), w, h, size[0], size[1])


def tiny(seed, hashseed="0"):
    return render("--seed", seed, "--width", 16, "--height", 9, "--fps", 1, "--seconds", 1, hashseed=hashseed)


def recipe_of(out):
    path = os.path.join(out, "recipe.json")
    assert os.path.isfile(path), "no recipe.json next to the frames"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_same_seed_same_hashes():
    first = [sha(p) for p in basic(hashseed="1")["frames"]]
    second = [sha(p) for p in basic(hashseed="2")["frames"]]
    assert first and first == second, \
        "seed 5 rendered twice (PYTHONHASHSEED 1 and 2) gave different frame SHA-256s"
    # Any whole number is a seed and is used as given: 0 is not "no seed" (that would pick a
    # random one each run), a negative number is not an error, a wide one is not truncated.
    for s in GIVEN_SEEDS:
        a, b = tiny(s), tiny(s, hashseed="3")
        assert sha(a["frames"][0]) == sha(b["frames"][0]), (
            "seed %d rendered twice (PYTHONHASHSEED 0 and 3) gave different frames; a --seed that is "
            "given is used as is, whatever the number" % s)
        got = recipe_of(a["out"]).get("seed")
        assert type(got) is int and got == s, \
            "--seed %d: recipe.json seed is %r, want the whole number %d (not a float, string or bool)" % (s, got, s)
    # The recipe's block order must not depend on string hashing (a set of block names iterates in an
    # order that PYTHONHASHSEED decides). Frames alone cannot show it: two fields summed commute, so only
    # some orders change a picture. Comparing the recorded blocks across fixed hash seeds can, and a given
    # hash seed always gives the same set order on a given Python, so the check does not rest on chance.
    for s in HASH_ORDER_SEEDS:
        want = recipe_of(tiny(s)["out"]).get("blocks")
        for h in HASH_ORDER_HASHSEEDS:
            got = recipe_of(tiny(s, hashseed=h)["out"]).get("blocks")
            assert got == want, (
                "seed %d gave blocks %r under PYTHONHASHSEED 0 and %r under PYTHONHASHSEED %s; the "
                "order of the blocks must come from the seed alone, not from string hashing"
                % (s, want, got, h))


def test_different_seed_differs():
    a = [sha(p) for p in basic(seed=5)["frames"]]
    b = [sha(p) for p in basic(seed=6)["frames"]]
    assert not set(a) & set(b), "seeds 5 and 6 share identical frames"
    firsts = [sha(tiny(s)["frames"][0]) for s in (1, 2, 3, 4)]
    assert len(set(firsts)) == 4, "seeds 1-4 did not give four different first frames"
    # The edge seeds the brief names are seeds like any other: they must not collapse onto
    # each other. A negative seed is not its absolute value, and a wide seed is not cut down
    # to 32 bits, however the picture is derived (the recipe and the noise both count).
    edge = dict((s, sha(tiny(s)["frames"][0])) for s in NAMED_SEEDS)
    for s in NAMED_SEEDS:
        twins = [t for t in NAMED_SEEDS if t != s and edge[t] == edge[s]]
        assert not twins, ("seeds %d and %d (16x9, 1 fps, 1 s) gave identical first frames; every "
                           "whole number is a different seed, so each must give a different picture"
                           % (s, twins[0]))


def test_animates_with_detail():
    frames = [pixels(p) for p in basic()["frames"]]
    for i in range(len(frames) - 1):
        assert frames[i] != frames[i + 1], "frame %d and %d are identical" % (i, i + 1)
    n = len(colours(frames[0]))
    assert n >= MIN_COLOURS, "frame 0 has only %d distinct colours, want >= %d" % (n, MIN_COLOURS)


def test_named_palettes_on_curve():
    checks = [("ember", basic()),
              ("lagoon", render("--seed", 4, "--width", 32, "--height", 18, "--fps", 1, "--seconds", 2,
                                "--palette", "lagoon")),
              ("dusk", render("--seed", 6, "--width", 32, "--height", 18, "--fps", 1, "--seconds", 1,
                              "--palette", "dusk")),
              ("acid", render("--seed", 9, "--width", 32, "--height", 18, "--fps", 1, "--seconds", 1))]
    for name, r in checks:
        assert r["frames"], "no frames written for the %s palette" % name
        cols = set()
        for p in r["frames"]:
            cols |= colours(pixels(p))
        assert cols, "the %s palette frames hold no pixels to check" % name
        far = cosine_far_colours(name, cols)
        assert not far, "%d colours off the %s palette curve%s, e.g. (colour, distance) %s" % (
            len(far), name, " (no --palette given, so the default)" if name == "acid" else "", far[:3])


def test_hex_palettes_on_ramp():
    for spec in ("000000,ffffff", "#ff0055,#22ccaa,#110033"):
        r = render("--seed", 12, "--width", 32, "--height", 18, "--fps", 2, "--seconds", 1,
                   "--palette", spec)
        cols = set()
        for p in r["frames"]:
            cols |= colours(pixels(p))
        far = polyline_far_colours(hexes(spec), cols)
        assert not far, "%d colours off the %s ramp, e.g. (colour, distance) %s" % (len(far), spec, far[:3])
        assert len(cols) >= 8, "palette %s used only %d colours" % (spec, len(cols))
        # Every stop is used: some colour lands in each quarter of the ramp, t in
        # [0, 0.25), [0.25, 0.5), [0.5, 0.75) and [0.75, 1]. A ramp that drops or
        # squeezes a stop leaves a quarter empty.
        stops = hexes(spec)
        used = {min(3, int(ramp_position(stops, c) * 4)) for c in cols}
        empty = sorted(set(range(4)) - used)
        assert not empty, (
            "palette %s: no colour falls in quarter(s) %s of the ramp (t from 0 to 1, stops evenly "
            "spaced), so a stop is missing or misplaced"
            % (spec, ", ".join("%.2f-%.2f" % (q / 4.0, (q + 1) / 4.0) for q in empty)))


def test_bad_palette_rejected():
    proc, _, _ = run_cli(["--seed", 1, "--width", 8, "--height", 8, "--fps", 1, "--seconds", 1,
                          "--palette", "ff0000,0000ff"])
    assert proc.returncode == 0, "a valid --palette ff0000,0000ff failed (exit %d)" % proc.returncode
    for spec in ("notacolour", "ff0000", "ff00zz,000000"):
        proc, out, _ = run_cli(["--seed", 1, "--width", 8, "--height", 8, "--fps", 1, "--seconds", 1,
                                "--palette", spec])
        assert proc.returncode != 0, "--palette %s was accepted (exit 0)" % spec


def test_loop_phase_matches_across_fps():
    six = [pixels(p) for p in looped(3)["frames"]]
    twelve = [pixels(p) for p in looped(6)["frames"]]
    assert len(six) == 6 and len(twelve) == 12, "loop renders gave %d and %d frames" % (len(six), len(twelve))
    for k in range(6):
        a, b = six[k], twelve[2 * k]
        bad = sum(1 for x, y in zip(a, b) if abs(x - y) > LOOP_PHASE_TOL)
        assert bad <= len(a) // 100 and mean_abs_diff(a, b) <= 0.5, (
            "with --loop, frame %d of 6 should match frame %d of 12 (same phase %d/6); "
            "%d channel values differ" % (k, 2 * k, k, bad))


def test_loop_is_one_cycle():
    six = [pixels(p) for p in looped(3)["frames"]]
    short = [pixels(p) for p in render("--seed", 11, "--width", 64, "--height", 36, "--fps", 6,
                                       "--seconds", 1, "--palette", "acid", "--loop")["frames"]]
    assert len(short) == 6, "6 fps for 1 s gave %d frames" % len(short)
    for k in range(6):
        a, b = six[k], short[k]
        bad = sum(1 for x, y in zip(a, b) if abs(x - y) > LOOP_PHASE_TOL)
        assert bad <= len(a) // 100 and mean_abs_diff(a, b) <= 0.5, (
            "with --loop the video is one cycle, so frame %d should be the same at 3 fps x 2 s "
            "and 6 fps x 1 s (phase %d/6); %d channel values differ" % (k, k, bad))


def test_loop_seam_is_smooth():
    # Many frames of a tiny picture, so one step is a small move and a seam
    # that jumps (a part that runs a non-whole number of cycles) stands out.
    for seed in SEAM_SEEDS:
        r = render("--seed", seed, "--width", 16, "--height", 9, "--fps", SEAM_FPS, "--seconds", 1,
                   "--palette", "acid", "--loop")
        frames = [pixels(p) for p in r["frames"]]
        assert len(frames) == SEAM_FPS, "%d fps for 1 s gave %d frames" % (SEAM_FPS, len(frames))
        steps = [mean_abs_diff(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]
        seam = mean_abs_diff(frames[-1], frames[0])
        assert seam > 0, "seed %d: with --loop the last frame is a copy of the first (the loop stutters)" % seed
        limit = SEAM_FACTOR * max(steps) + SEAM_SLACK
        assert seam <= limit, ("seed %d, 16x9 at %d fps for 1 s with --loop: the jump from the last frame "
                               "to the first is %.2f, over the limit %.2f (largest ordinary step %.2f)"
                               % (seed, SEAM_FPS, seam, limit, max(steps)))


def no_seed_runs():
    """NOSEED_RUNS runs with no --seed, at tiny size, started together and cached.

    Returns a list of (printed seed or None, CompletedProcess, out dir). They start together so
    that a build seeding from the clock in whole seconds gives them at most two different seeds.
    """
    key = ("no-seed runs",)
    if key not in _CACHE:
        work_root()  # create the shared work folder before the threads race to do it

        # Start just after a whole-second tick, so that six runs which each take only a moment all fall
        # in the same wall-clock second; a seed taken from the clock in whole seconds is then the same
        # for all of them, and a tick landing between two of them cannot save such a build.
        wait = 1.0 - (time.time() % 1.0)
        if wait < 0.95:
            time.sleep(wait + 0.02)

        def one(_):
            proc, out, _secs = run_cli(["--width", 16, "--height", 9, "--fps", 2, "--seconds", 1])
            assert proc.returncode == 0, "run without --seed exited %d: %s" % (
                proc.returncode, (proc.stderr or proc.stdout).strip()[-300:])
            found = SEED_LINE_RE.findall(proc.stdout)
            return (int(found[0]) if len(found) == 1 else None), proc, out

        with concurrent.futures.ThreadPoolExecutor(max_workers=NOSEED_RUNS) as pool:
            _CACHE[key] = list(pool.map(one, range(NOSEED_RUNS)))
    return _CACHE[key]


def test_random_seed_printed_and_reproducible():
    # Every run is checked, not one: a printed seed that does not reproduce its frames can show
    # only for the seeds whose blocks use the broken part, so a single run often passes by luck.
    for seed, proc, out in no_seed_runs():
        assert seed is not None, (
            "run without --seed should print one line 'seed: <whole number>' on standard output; "
            "stdout was %r" % proc.stdout.strip()[-200:])
        first = frame_files(out)
        assert len(first) == 2, "run without --seed wrote %d frames, want 2" % len(first)
        again = render("--seed", seed, "--width", 16, "--height", 9, "--fps", 2, "--seconds", 1)
        assert [sha(p) for p in first] == [sha(p) for p in again["frames"]], (
            "re-running with --seed %d (the seed printed by a no-seed run) gave different frames" % seed)
        got = recipe_of(out).get("seed")
        assert type(got) is int and got == seed, (
            "recipe.json seed is %r but the run printed seed: %d (want the same whole number)" % (got, seed))


def test_random_seed_differs_between_runs():
    seeds, firsts = [], []
    for seed, proc, out in no_seed_runs():
        assert seed is not None, "run without --seed printed no 'seed: N' line"
        seeds.append(seed)
        firsts.append(sha(frame_files(out)[0]))
    # A clock read in whole seconds can give at most two different values to runs that all start
    # within one second, however the second boundary falls, so three or more are needed.
    assert len(set(seeds)) >= 3, "%d runs without --seed picked only %d different seeds (%s); want at least 3" % (
        len(seeds), len(set(seeds)), sorted(set(seeds)))
    assert len(set(firsts)) >= 2, "%d runs without --seed (seeds %s) gave identical frames" % (
        len(seeds), seeds)


def test_motion_follows_time_not_frames():
    two = [pixels(p) for p in render("--seed", 13, "--width", 32, "--height", 18, "--fps", 2,
                                     "--seconds", 1)["frames"]]
    four = [pixels(p) for p in render("--seed", 13, "--width", 32, "--height", 18, "--fps", 4,
                                      "--seconds", 1)["frames"]]
    a, b = two[1], four[2]  # both at t = 0.5 s
    bad = sum(1 for x, y in zip(a, b) if abs(x - y) > LOOP_PHASE_TOL)
    assert bad <= len(a) // 100, "frame 1 at 2 fps and frame 2 at 4 fps (both t=0.5 s) differ in %d values" % bad
    # --seconds sets the length, not the speed: without --loop, frame 1 at 2 fps is t = 0.5 s
    # whether the video lasts 1 s or 2 s. (Only --loop stretches the cycle over the length.)
    long_run = [pixels(p) for p in render("--seed", 13, "--width", 32, "--height", 18, "--fps", 2,
                                          "--seconds", 2)["frames"]]
    assert len(long_run) == 4, "2 fps for 2 s gave %d frames" % len(long_run)
    bad = sum(1 for x, y in zip(a, long_run[1]) if abs(x - y) > LOOP_PHASE_TOL)
    assert bad <= len(a) // 100, (
        "without --loop, frame 1 at 2 fps (t=0.5 s) differs between a 1 s and a 2 s render in %d "
        "values; --seconds must set the length, not the speed of the motion" % bad)


def test_seed_picks_blocks():
    sets = set()
    for s in range(1, 9):
        recipe = recipe_of(tiny(s)["out"])
        assert type(recipe.get("seed")) is int and recipe.get("seed") == s, (
            "recipe.json seed is %r, want the whole number %d" % (recipe.get("seed"), s))
        blocks = recipe.get("blocks")
        assert isinstance(blocks, list) and all(isinstance(b, str) for b in blocks), \
            "recipe.json blocks must be a list of names"
        assert len(set(blocks)) >= 2, "seed %d used fewer than two building blocks: %r" % (s, blocks)
        sets.add(tuple(sorted(set(blocks))))
    assert len(sets) >= 2, "seeds 1-8 all chose the same building blocks %r" % (sorted(sets),)


def test_stale_frames_removed():
    out = new_dir("stale '")
    args = ["--seed", 2, "--width", 8, "--height", 8, "--fps", 4, "--seconds", 1]
    proc, _, _ = run_cli(args, out=out)
    assert proc.returncode == 0, proc.stderr[-300:]
    proc, _, _ = run_cli(args[:-2] + ["--seconds", 0.5], out=out)
    assert proc.returncode == 0, proc.stderr[-300:]
    n = len(frame_files(out))
    assert n == 2, "re-rendering 2 frames into a folder that held 4 left %d frame files" % n


def test_mp4_without_ffmpeg_explains():
    # PATH is a single empty folder, so ffmpeg cannot be found (Python runs by full path).
    empty = new_dir("nopath '")
    proc, out, _ = run_cli(["--seed", 1, "--width", 16, "--height", 9, "--fps", 1, "--seconds", 2, "--mp4"],
                           path_override=empty)
    assert proc.returncode == 0, "--mp4 without ffmpeg should exit 0, got %d: %s" % (
        proc.returncode, proc.stderr[-300:])
    assert len(frame_files(out)) == 2, "--mp4 without ffmpeg should still write the frames"
    assert "ffmpeg" in (proc.stdout + proc.stderr).lower(), "--mp4 without ffmpeg printed no ffmpeg instructions"


# Run by -I -S, so neither the current folder, the kit's demos/ folder nor site-packages can answer for a name.
_FIND_SPECS = (
    "import importlib.util, sys\n"
    "for n in sys.argv[1:]:\n"
    "    s = importlib.util.find_spec(n)\n"
    "    print('%s\\t%s' % (n, '' if s is None else (s.origin or 'namespace')))\n"
)


def test_stdlib_only():
    ws = workspace()
    local = set()
    sources = []
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "venv", ".venv")]
        for f in files:
            if f.endswith(".py"):
                local.add(f[:-3])
                sources.append(os.path.join(root, f))
        if root != ws:
            local.add(os.path.basename(root))
    wanted = {}   # top-level module name -> the files that import it
    for path in sources:
        with open(path, "rb") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top not in local and top != "__future__":
                    wanted.setdefault(top, set()).add(os.path.relpath(path, ws))
    bad = []
    if wanted:
        proc = ak.run(ak.python_argv("-I", "-c", _FIND_SPECS, *sorted(wanted), stdlib_only=True), 60)
        assert proc.returncode == 0, "could not look the imports up: %s" % proc.stderr.strip()[-200:]
        found = dict(line.split("\t", 1) for line in proc.stdout.splitlines() if "\t" in line)
        for top in sorted(wanted):
            origin = found.get(top, "")
            if not origin or "site-packages" in origin or "dist-packages" in origin:
                bad.extend("%s imports %s" % (f, top) for f in sorted(wanted[top]))
    assert not bad, "non-stdlib imports: %s" % ", ".join(sorted(set(bad)))


def test_runtime_bound():
    r = basic()
    assert r["seconds"] < RUNTIME_LIMIT_S, "64x36, 2 fps, 2 s took %.1f s, limit %.0f s" % (
        r["seconds"], RUNTIME_LIMIT_S)


TESTS = [(fn.__name__, fn) for fn in (
    test_frame_count,
    test_png_decodes_at_requested_size,
    test_same_seed_same_hashes,
    test_different_seed_differs,
    test_animates_with_detail,
    test_named_palettes_on_curve,
    test_hex_palettes_on_ramp,
    test_bad_palette_rejected,
    test_loop_phase_matches_across_fps,
    test_loop_is_one_cycle,
    test_loop_seam_is_smooth,
    test_random_seed_printed_and_reproducible,
    test_random_seed_differs_between_runs,
    test_motion_follows_time_not_frames,
    test_seed_picks_blocks,
    test_stale_frames_removed,
    test_mp4_without_ffmpeg_explains,
    test_stdlib_only,
    test_runtime_bound,
)]
