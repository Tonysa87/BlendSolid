"""Independent volume check of a groove/rib: point membership from the path's geometry and the profile, Monte
Carlo over the tool's box (session 15). The worker builds the sweep with OCCT (pipe shells, revolved corners,
fused pieces); this only measures distances to lines, arcs and corner points, so a missing, doubled or wrong piece
shows as a volume difference. Usage (Blender's Python): oracle.py cases.json [first] [count]
  cases.json: [{"src": part script, "now": {"ok", "volume"}}, ...] (rerun.py's changed_grooves.json format)."""
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path[:0] = [os.path.join(ROOT, "blendsolid", "worker"), os.path.join(ROOT, ".dev", "worker_libs")]
import numpy as np  # noqa: E402

OVER = 0.5
SHARP = 1e-6


def parse(src):
    m = re.search(r"groove\(sketch_1\.path_1, width=([-\d.e]+), depth=([-\d.e]+)(.*)\)", src)
    width, depth, rest = float(m.group(1)), float(m.group(2)), m.group(3)
    profile = re.search(r'profile="(\w+)"', rest)
    corners = re.search(r'corners="(\w+)"', rest)
    box = re.search(r"Box\(([-\d.]+), ([-\d.]+), ([-\d.]+), align=\(Align.CENTER, Align.CENTER, Align.MIN\)\)", src)
    return dict(width=width, depth=depth, profile=profile.group(1) if profile else "rect",
                corners=corners.group(1) if corners else "mitre", add="Mode.ADD" in rest,
                box=tuple(map(float, box.groups())) if box else None)


def path_elements(src):
    """The sketch's path as elements in plane coordinates, from the worker's own path() (only to get the curve)."""
    import runner
    import provenance
    tracker = provenance.Tracker()
    body = src.split("    groove(")[0] + "result = part.part\n"
    runner._build(body, runner.SCRIPT_NAME, [], runner.ShapeCache(), tracker=tracker)
    sk = tracker.sketches[0]
    o, x, z = sk.plane.origin, sk.plane.x_dir, sk.plane.z_dir
    plane = (np.array([o.X, o.Y, o.Z]), np.array([x.X, x.Y, x.Z]), np.array([z.X, z.Y, z.Z]))
    edges = sk.entities["path_1"]
    out = []
    from build123d import GeomType
    for e in edges:
        a, b = e.position_at(0), e.position_at(1)
        if e.geom_type == GeomType.LINE:
            out.append(("line", np.array([a.X, a.Y]), np.array([b.X, b.Y])))
        else:
            c = e.arc_center
            r = e.radius
            ta, tb = e.tangent_at(0), e.tangent_at(1)
            out.append(("arc", np.array([a.X, a.Y]), np.array([b.X, b.Y]), np.array([c.X, c.Y]), r,
                        np.array([ta.X, ta.Y]), np.array([tb.X, tb.Y]), e.length))
    closed = np.linalg.norm(out[0][1] - out[-1][2]) < 1e-6
    return plane, out, closed


def tangent(el, end):
    if el[0] == "line":
        d = el[2] - el[1]
        return d / np.linalg.norm(d)
    t = el[5] if end == 0 else el[6]
    return t / np.linalg.norm(t)


def inside_profile(s, w, p):
    """(|lateral|, height above the plane along `up`) inside the profile."""
    hw, depth, prof = p["width"] / 2, p["depth"], p["profile"]
    over = p["over"]
    if prof == "circle":
        return s * s + w * w <= hw * hw
    if prof == "rect":
        return (s <= hw) & (w >= -depth) & (w <= over)
    if prof == "v":
        below = (w >= -depth) & (w <= 0) & (s <= hw * (1 + w / depth))
        above = (w > 0) & (w <= over) & (s <= hw)
        return below | above
    if prof == "round":
        c = -depth + hw
        straight = (w >= c) & (w <= over) & (s <= hw)
        bottom = (w < c) & (s * s + (w - c) ** 2 <= hw * hw)
        return straight | bottom
    raise ValueError(prof)


def membership(uv, w, els, closed, p):
    inside = np.zeros(len(uv), dtype=bool)
    for el in els:  # runs: lines and arcs, points whose nearest point is inside the element
        if el[0] == "line":
            a, b = el[1], el[2]
            d = b - a
            L = np.linalg.norm(d)
            t = ((uv - a) @ d) / (L * L)
            lat = np.abs((uv[:, 0] - a[0]) * d[1] - (uv[:, 1] - a[1]) * d[0]) / L
            inside |= (t >= 0) & (t <= 1) & inside_profile(lat, w, p)
        else:
            a, b, c, r = el[1], el[2], el[3], el[4]
            rel = uv - c
            dist = np.linalg.norm(rel, axis=1)
            ang = np.arctan2(rel[:, 1], rel[:, 0])
            a0 = math.atan2(a[1] - c[1], a[0] - c[0])
            span = el[7] / r
            ccw = (a - c)[0] * el[5][1] - (a - c)[1] * el[5][0] > 0
            rel_ang = (ang - a0) % (2 * math.pi) if ccw else (a0 - ang) % (2 * math.pi)
            inside |= (rel_ang <= span) & inside_profile(np.abs(dist - r), w, p)
    joints = list(zip(els, els[1:])) + ([(els[-1], els[0])] if closed else [])
    for before_el, after_el in joints:
        point = before_el[2]
        tb, ta = tangent(before_el, 1), tangent(after_el, 0)
        turn = math.acos(max(-1.0, min(1.0, float(tb @ ta))))
        if turn <= SHARP:
            continue
        if p["corners"] == "round" or turn < math.radians(5):
            rel = uv - point
            inside |= inside_profile(np.linalg.norm(rel, axis=1), w, p)
        else:  # mitre: inside both runs' straight extensions past the corner
            rel = uv - point
            t1 = rel @ tb
            l1 = np.abs(rel[:, 0] * tb[1] - rel[:, 1] * tb[0])
            t2 = rel @ ta
            l2 = np.abs(rel[:, 0] * ta[1] - rel[:, 1] * ta[0])
            inside |= (t1 >= 0) & (t2 <= 0) & inside_profile(l1, w, p) & inside_profile(l2, w, p)
    return inside


def check(case, n=400000, seed=0):
    src = case["src"]
    p = parse(src)
    (o, x, z), els, closed = path_elements(src)
    y = np.cross(z, x)
    on_face = p["box"] is not None
    p["over"] = OVER if (not p["add"] or on_face) else 0.0
    up = z if not p["add"] else -z  # a rib is a groove turned over
    pts2 = np.array([el[1] for el in els] + [el[2] for el in els] + [el[3] for el in els if el[0] == "arc"])
    reach = p["width"] / 2 + p["depth"] + OVER + 1e-6
    arcs = [el for el in els if el[0] == "arc"]
    lo2, hi2 = pts2.min(axis=0) - reach, pts2.max(axis=0) + reach
    for el in arcs:
        lo2, hi2 = np.minimum(lo2, el[3] - el[4] - reach), np.maximum(hi2, el[3] + el[4] + reach)
    if p["corners"] == "mitre":  # a mitre's tip reaches half the width / cos(turn / 2) from its corner
        joints = list(zip(els, els[1:])) + ([(els[-1], els[0])] if closed else [])
        for a, b in joints:
            turn = math.acos(max(-1.0, min(1.0, float(tangent(a, 1) @ tangent(b, 0)))))
            if turn > SHARP:
                tip = reach / max(math.cos(turn / 2), 1e-3)
                lo2, hi2 = np.minimum(lo2, a[2] - tip), np.maximum(hi2, a[2] + tip)
    hmin, hmax = -p["depth"] - 1e-6, max(OVER, p["width"] / 2) + 1e-6
    if p["profile"] == "circle":
        hmin = -p["width"] / 2 - 1e-6
    rng = np.random.default_rng(seed)
    uv = rng.uniform(lo2, hi2, (n, 2))
    w = rng.uniform(hmin, hmax, n)
    sample_volume = float(np.prod(hi2 - lo2) * (hmax - hmin))
    tool = membership(uv, w, els, closed, p)
    world = o + uv[:, :1] * x + uv[:, 1:] * y + w[:, None] * up
    if on_face:
        bx, by, bz = p["box"]
        in_box = (np.abs(world[:, 0]) <= bx / 2) & (np.abs(world[:, 1]) <= by / 2) & (world[:, 2] >= 0) & \
                 (world[:, 2] <= bz)
        if p["add"]:
            counted = tool & ~in_box
            if p["profile"] != "circle":
                counted &= (world - o) @ z >= 0  # the sunk strip past the part is trimmed (G7)
            expected = bx * by * bz + counted.mean() * sample_volume
        else:
            expected = bx * by * bz - (tool & in_box).mean() * sample_volume
        scale = (tool.mean() * sample_volume)
    else:
        expected = tool.mean() * sample_volume
        scale = expected
    frac = max(tool.mean(), 1e-9)
    noise = sample_volume * math.sqrt(frac * (1 - frac) / n) * 3  # 3 sigma of the tool's own estimate
    return expected, noise, scale


def main():
    cases = json.load(open(sys.argv[1]))
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    count = int(sys.argv[3]) if len(sys.argv) > 3 else len(cases)
    bad = 0
    for i, case in enumerate(cases[first:first + count], first):
        now = case["now"]
        if not now.get("ok"):
            continue
        try:
            exp, noise, scale = check(case)
        except Exception as e:
            print(i, "ORACLE FAIL", type(e).__name__, e)
            continue
        diff = now["volume"] - exp
        flag = "BAD" if abs(diff) > noise + 1e-3 * scale else "ok"
        bad += flag == "BAD"
        print(i, flag, f"worker {now['volume']:.4f} oracle {exp:.4f} ±{noise:.4f} tool {scale:.4f} diff {diff:+.4f}",
              case["cat"][:40])
    print("BAD", bad)


if __name__ == "__main__":
    main()
