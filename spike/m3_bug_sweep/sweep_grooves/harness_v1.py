"""Groove/rib fuzz harness: builds scripts, runs them in forked children with a timeout, computes reference
volumes from 2D offset bands (shapely) integrated over the profile height."""
import math
import multiprocessing as mp
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = ["/home/tony/Projects/BlendSolid/blendsolid/worker", "/home/tony/Projects/BlendSolid/.dev/worker_libs"]
sys.path.append(os.path.join(HERE, "libs"))

import numpy as np  # noqa: E402
import runner  # noqa: E402
import sketches  # noqa: E402
import tessellate  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, LinearRing, Polygon, box as sbox  # noqa: E402

BOXES = {  # face -> (box line, F polygon in sketch coords, thickness under the face, box volume)
    "+Z": ("Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))", sbox(-20, -10, 20, 10), 10.0, 8000.0),
    "+X": ("Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))", sbox(-10, 0, 10, 10), 40.0, 8000.0),
    "-Y": ("Box(40, 20, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))", sbox(-20, 0, 20, 10), 20.0, 8000.0),
    "XY": (None, None, 0.0, 0.0),
}


def fmt(x):
    return repr(round(float(x), 6) + 0.0)


def path_text(start, segs, closed):
    parts = [f"({fmt(start[0])}, {fmt(start[1])})"]
    for kind, p in segs:
        t = f"({fmt(p[0])}, {fmt(p[1])})"
        parts.append(f"arc_to({t})" if kind == "A" else t)
    return f"path({', '.join(parts)}{', closed=True' if closed else ''})"


def script(case):
    face = case["face"]
    lines = ["with BuildPart() as part:"]
    if face != "XY":
        lines.append(f"    {BOXES[face][0]}  # feature: box_1")
        lines.append(f'    with sketch(on_face(face("box_1", "{face}"))) as sketch_1:  # feature: sketch_1')
    else:
        lines.append("    with sketch(Plane.XY) as sketch_1:  # feature: sketch_1")
    lines.append(f"        sketch_1.path_1 = {case.get('path_src') or path_text(case['start'], case['segs'], case['closed'])}")
    for i, g in enumerate(case["grooves"]):
        mode = ", mode=Mode.ADD" if g["rib"] else ""
        name = ("rib_" if g["rib"] else "groove_") + str(i + 1)
        lines.append(f'    groove(sketch_1.path_1, width={fmt(g["width"])}, depth={fmt(g["depth"])}, '
                     f'profile="{g["profile"]}", corners="{g["corners"]}"{mode})  # feature: {name}')
    lines += case.get("extra", [])
    lines.append("result = part.part")
    return "\n".join(lines) + "\n"


# -- reference -------------------------------------------------------------------------------------------------

def path_coords(case):
    """Sampled path in sketch coords and whether it is closed (via the code's own path(); None if it raises)."""
    try:
        if case.get("path_src"):
            from build123d import Vector  # noqa
            w = eval(case["path_src"], {"path": sketches.path, "arc_to": sketches.arc_to})
        else:
            w = sketches.path(case["start"] if False else tuple(float(fmt(c)) for c in case["start"]),
                              *[sketches.arc_to(tuple(float(fmt(c)) for c in p)) if k == "A"
                                else tuple(float(fmt(c)) for c in p) for k, p in case["segs"]],
                              closed=case["closed"])
    except Exception:
        return None, None
    pts = []
    for e in w.edges():
        if e.geom_type.name == "LINE":
            ts = [0.0, 1.0]
        else:
            ang = e.length / max(e.radius, 1e-9)
            n = max(2, int(math.degrees(ang) / 0.1) + 1)
            ts = list(np.linspace(0, 1, n + 1))
        for t in ts:
            p = e.position_at(t)
            q = (p.X, p.Y)
            if not pts or math.dist(pts[-1], q) > 1e-9:
                pts.append(q)
    return pts, w.is_closed


def band(pts, closed, hw, corners):
    if hw <= 0:
        return Polygon()
    if closed:
        geom = LinearRing(pts[:-1] if math.dist(pts[0], pts[-1]) < 1e-9 else pts)
    else:
        geom = LineString(pts)
    return geom.buffer(hw, cap_style="flat", join_style="mitre" if corners == "mitre" else "round",
                       mitre_limit=1000.0, quad_segs=256)


def hw_fn(profile, width, depth, rib, over):
    """(intervals of h, outward from the part = +, hw(h)) for the solid's cross-section at height h."""
    w, r = width / 2, width / 2
    s = 1.0 if rib else -1.0  # direction the depth goes (out for a rib, in for a groove)
    if profile == "circle":
        return [((-r, r), lambda h: math.sqrt(max(r * r - h * h, 0.0)), "sqrt0")]
    if profile == "rect":
        return [(tuple(sorted((-s * over, s * depth))), lambda h: w, "const")]
    if profile == "v":
        k = w / depth
        # hw at depth-distance t from the plane (t measured in the depth direction): w - k t
        return [(tuple(sorted((-s * over, s * depth))), lambda h: w - k * (s * h), "lin")]
    if profile == "round":
        c = depth - r
        return [(tuple(sorted((-s * over, s * c))), lambda h: r, "const"),
                (tuple(sorted((s * c, s * depth))), lambda h: math.sqrt(max(r * r - (s * h - c) ** 2, 0.0)), "sqrt")]


GL_X, GL_W = np.polynomial.legendre.leggauss(24)


def integrate(f, a, b):
    if b <= a:
        return 0.0
    m, hl = (a + b) / 2, (b - a) / 2
    return sum(wi * f(m + hl * xi) for xi, wi in zip(GL_X, GL_W)) * hl


def expected(case):
    """(expected volume, lip volume) or (None, why)."""
    pts, closed = path_coords(case)
    if pts is None:
        return None, "path() raised"
    face = case["face"]
    _, F, T, V0 = BOXES[face]
    pieces = []  # per groove: list of (interval, hwfun)
    for g in case["grooves"]:
        on_part = face != "XY"
        over = sketches.OVERSHOOT if (not g["rib"] or on_part) else 0.0
        pieces.append((g, hw_fn(g["profile"], g["width"], g["depth"], g["rib"], over)))
    ribs = [g for g in case["grooves"] if g["rib"]]
    cuts = [g for g in case["grooves"] if not g["rib"]]
    if ribs and cuts:
        return None, "mixed"
    # region at height h: union over grooves of band(hw_g(h)) where h in its interval
    def region(h, which):
        geoms = []
        for g, ivs in pieces:
            if g not in which:
                continue
            for (a, b), f, _ in ivs:
                if a - 1e-12 <= h <= b + 1e-12:
                    geoms.append(band(pts, closed, f(h), g["corners"]))
                    break
        return shapely.union_all(geoms) if geoms else Polygon()

    # breakpoints of h
    bps = set()
    for g, ivs in pieces:
        for (a, b), _, _ in ivs:
            bps.update((a, b))
    bps.add(0.0)
    bps = sorted(bps)

    def integ(fun, a, b, kinds):
        # sqrt pieces: integrate in angle for accuracy
        total = 0.0
        if b - a <= 0:
            return 0.0
        if any(k.startswith("sqrt") for k in kinds):
            n = 400  # midpoint in the substitution would need the centre; use dense GL subdivision instead
            edges = np.linspace(a, b, 41)
            # refine near the ends (sqrt singular derivative)
            return sum(integrate(fun, x0, x1) for x0, x1 in zip(edges, edges[1:]))
        return integrate(fun, a, b)

    kinds = [k for _, ivs in pieces for _, _, k in ivs]
    if not ribs:  # grooves: removed = int over h in [-T, 0] of area(region ∩ F)
        total = 0.0
        for a, b in zip(bps, bps[1:]):
            a2, b2 = max(a, -T), min(b, 0.0)
            if b2 > a2:
                total += integ(lambda h: region(h, cuts).intersection(F).area, a2, b2, kinds)
        return V0 - total, 0.0
    total, lip = 0.0, 0.0
    for a, b in zip(bps, bps[1:]):
        if b <= 0 and F is not None:  # below the face plane: only what is outside the box's section counts
            a2 = max(a, -T)
            if F is not None:
                # the profile's own part below the plane (circle) counts; the overshoot lip is reported apart
                for g, ivs in pieces:
                    pass
                def below(h):
                    return region(h, ribs).difference(F).area
                v = integ(below, a2, b, kinds)
                if any(g["profile"] == "circle" for g in ribs):
                    total += v
                else:
                    lip += v
            continue
        if b <= 0:  # XY plane, no part
            total += integ(lambda h: region(h, ribs).area, a, b, kinds)
            continue
        a2 = max(a, 0.0)
        total += integ(lambda h: region(h, ribs).area, a2, b, kinds)
    return V0 + total, lip


# -- running --------------------------------------------------------------------------------------------------

def _child(source, conn):
    info = {}
    orig = tessellate.check

    def check(shape):
        d = orig(shape)
        info.update(d)
        return d
    tessellate.check = check
    t0 = time.perf_counter()
    try:
        r = runner.run_script(source)
        out = {"ok": r.ok, "error": r.error, "line": r.line, "volume": r.volume, "faces": r.faces,
               "warnings": r.warnings, "solids": info.get("solids"), "valid": info.get("valid"),
               "edge_refs": r.edge_refs, "face_refs": r.face_refs}
    except BaseException as e:
        out = {"ok": False, "error": "HARNESS: " + traceback.format_exc(), "line": None}
    out["time"] = time.perf_counter() - t0
    conn.send(out)
    conn.close()


def run_many(sources, timeout=60.0, jobs=2):
    ctx = mp.get_context("fork")
    results = [None] * len(sources)
    pending = list(enumerate(sources))
    active = {}
    while pending or active:
        while pending and len(active) < jobs:
            i, src = pending.pop(0)
            a, b = ctx.Pipe(False)
            p = ctx.Process(target=_child, args=(src, b))
            p.start()
            active[i] = (p, a, time.perf_counter())
        time.sleep(0.01)
        for i, (p, a, t0) in list(active.items()):
            if a.poll():
                try:
                    results[i] = a.recv()
                except EOFError:
                    results[i] = {"ok": False, "error": "CRASH (no result)", "time": time.perf_counter() - t0}
                p.join(5)
                del active[i]
            elif not p.is_alive():
                results[i] = {"ok": False, "error": f"CRASH exit {p.exitcode}", "time": time.perf_counter() - t0}
                del active[i]
            elif time.perf_counter() - t0 > timeout:
                p.kill()
                p.join()
                results[i] = {"ok": False, "error": "HANG (timeout)", "time": timeout}
                del active[i]
    return results
