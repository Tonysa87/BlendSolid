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
    return PathGeom(w), w.is_closed


class PathGeom:
    """Edges sampled with exact tangents/normals; corners between edges (including the closing one)."""

    def __init__(self, w):
        self.edges = []
        self.radii = []
        es = w.edges()
        for e in es:
            if e.geom_type.name == "LINE":
                ts = [0.0, 1.0]
            else:
                self.radii.append(e.radius)
                ang = e.length / max(e.radius, 1e-9)
                n = max(2, int(math.degrees(ang) / 0.1) + 1)
                ts = list(np.linspace(0, 1, n + 1))
            samples = []
            for t in ts:
                p, d = e.position_at(t), e.tangent_at(t)
                samples.append(((p.X, p.Y), (d.X, d.Y)))
            self.edges.append(samples)
        self.corners = []
        pairs = list(zip(es, es[1:]))
        if w.is_closed and len(es) > 1:
            pairs.append((es[-1], es[0]))
        elif w.is_closed and len(es) == 1:
            pairs.append((es[0], es[0]))
        for e0, e1 in pairs:
            d0, d1, p = e0.tangent_at(1), e1.tangent_at(0), e1.position_at(0)
            cross = d0.X * d1.Y - d0.Y * d1.X
            dot = max(-1.0, min(1.0, d0.X * d1.X + d0.Y * d1.Y))
            turn = math.atan2(abs(cross), dot)
            if turn > 1e-9:
                self.corners.append(((p.X, p.Y), (d0.X, d0.Y), (d1.X, d1.Y), turn, 1 if cross > 0 else -1))


def _right(d):
    return (d[1], -d[0])


def band(geom, closed, hw, corners):
    if hw <= 0:
        return Polygon()
    polys = []
    for samples in geom.edges:
        left = [(p[0] - d[1] * hw, p[1] + d[0] * hw) for p, d in samples]
        right = [(p[0] + d[1] * hw, p[1] - d[0] * hw) for p, d in samples]
        poly = Polygon(left + right[::-1])
        if not poly.is_valid:
            poly = poly.buffer(0)
        polys.append(poly)
    for p, d0, d1, turn, sgn in geom.corners:
        # outside of a left turn (sgn > 0) is the right side
        n0 = _right(d0) if sgn > 0 else (-_right(d0)[0], -_right(d0)[1])
        n1 = _right(d1) if sgn > 0 else (-_right(d1)[0], -_right(d1)[1])
        if corners == "mitre":
            bis = (n0[0] + n1[0], n0[1] + n1[1])
            L = math.hypot(*bis)
            if L < 1e-12:
                continue
            k = hw / math.cos(turn / 2) / L
            tip = (p[0] + bis[0] * k, p[1] + bis[1] * k)
            polys.append(Polygon([p, (p[0] + n0[0] * hw, p[1] + n0[1] * hw), tip, (p[0] + n1[0] * hw, p[1] + n1[1] * hw)]))
        else:
            a0 = math.atan2(n0[1], n0[0])
            n = max(4, int(math.degrees(turn) / 0.1) + 1)
            # rotate from n0 towards n1 (left turn: outside normal rotates counter-clockwise)
            pts = [p] + [(p[0] + hw * math.cos(a0 + sgn * turn * i / n), p[1] + hw * math.sin(a0 + sgn * turn * i / n))
                         for i in range(n + 1)]
            polys.append(Polygon(pts))
    return shapely.union_all([q for q in polys if not q.is_empty])


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
    if pts.radii and max(g["width"] for g in case["grooves"]) / 2 >= min(pts.radii):
        return None, "hw >= arc radius"
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
            # h = a + (b - a)(1 - cos t)/2: smooths sqrt end singularities
            g = lambda t: fun(a + (b - a) * (1 - math.cos(t)) / 2) * (b - a) / 2 * math.sin(t)
            return integrate(g, 0.0, math.pi)
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
