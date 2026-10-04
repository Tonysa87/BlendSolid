"""Seeded random part scripts covering milestone 3a features."""
import json
import math
import random
import sys

HEAD = "with BuildPart() as part:\n"
TAIL = "result = part.part\n"


def f(x):
    return f"{x:.6f}"


def box(L, W, H):
    return f"    Box({f(L)}, {f(W)}, {f(H)}, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n"


def rand_path(rng, hx, hy, s, closed=False):
    """A path in [-hx, hx] x [-hy, hy]: lines and tangent arcs, sharp corners at random angles."""
    n = rng.randint(1, 6)
    x, y = rng.uniform(-hx, hx) * 0.8, rng.uniform(-hy, hy) * 0.8
    segs = []
    pts = [(x, y)]
    for i in range(n):
        if i > 0 and rng.random() < 0.4:
            segs.append(f"arc_to(({f(rng.uniform(-hx, hx) * 0.8)}, {f(rng.uniform(-hy, hy) * 0.8)}))")
        else:
            segs.append(f"({f(rng.uniform(-hx, hx) * 0.8)}, {f(rng.uniform(-hy, hy) * 0.8)})")
    c = ", closed=True" if closed else ""
    return f"path(({f(x)}, {f(y)}), {', '.join(segs)}{c})"


def structured_path(rng, hx, hy):
    """Manhattan-ish paths with tangent arcs, like the maintainer's: line, arc_to (semicircle/quarter), corners."""
    x, y = -hx * 0.7, -hy * 0.6
    pts = [f"({f(x)}, {f(y)})"]
    k = rng.randint(2, 6)
    cx, cy = x, y
    dirx, diry = 1, 0
    for i in range(k):
        L = rng.uniform(0.15, 0.5) * min(hx, hy) * 2
        nx, ny = cx + dirx * L, cy + diry * L
        nx, ny = max(-hx * 0.85, min(hx * 0.85, nx)), max(-hy * 0.85, min(hy * 0.85, ny))
        if (nx, ny) == (cx, cy):
            continue
        pts.append(f"({f(nx)}, {f(ny)})")
        cx, cy = nx, ny
        if rng.random() < 0.5:
            # tangent arc: a semicircle or a quarter turn
            r = rng.uniform(0.08, 0.25) * min(hx, hy) * 2
            if rng.random() < 0.5:  # semicircle: end = here + 2r * left normal
                ex, ey = cx - diry * 2 * r, cy + dirx * 2 * r
                dirx, diry = -dirx, -diry
            else:  # quarter: end = here + r*dir + r*left
                ex, ey = cx + dirx * r - diry * r, cy + diry * r + dirx * r
                dirx, diry = -diry, dirx
            pts.append(f"arc_to(({f(ex)}, {f(ey)}))")
            cx, cy = ex, ey
        else:
            # sharp corner: turn left or right by 90 or a random angle
            if rng.random() < 0.7:
                dirx, diry = (-diry, dirx) if rng.random() < 0.5 else (diry, -dirx)
            else:
                a = math.atan2(diry, dirx) + rng.choice([-1, 1]) * rng.uniform(0.3, 2.6)
                dirx, diry = math.cos(a), math.sin(a)
    return f"path({', '.join(pts)})"


def groove_case(rng, scale):
    L, W, H = 40 * scale, 30 * scale, 10 * scale
    profile = rng.choice(["rect", "round", "v", "circle"])
    corners = rng.choice(["mitre", "round"])
    mode = rng.choice(["Mode.SUBTRACT", "Mode.ADD"])
    width = rng.uniform(0.5, 3.5) * scale
    depth = rng.uniform(0.5, 1.5) * width if profile != "v" else rng.uniform(0.3, 2.0) * width
    if profile == "round":
        depth = max(depth, width / 2 * rng.choice([1.0, 1.0, 1.2, 2]))
    if profile == "circle":
        depth = 0.0
    face = rng.choice(["+Z", "+Z", "+X", "-Y"])
    hx, hy = {"+Z": (L / 2, W / 2), "+X": (W / 2, H / 2), "-Y": (L / 2, H / 2)}[face]
    if face != "+Z":  # on side faces the sketch frame may differ: keep the path near the centre
        hx, hy = hx, hy
    p = structured_path(rng, hx, hy) if rng.random() < 0.6 else rand_path(rng, hx, hy, scale, closed=rng.random() < 0.15)
    src = HEAD + box(L, W, H)
    src += f'    with sketch(on_face(face("box_1", "{face}"))) as sketch_1:  # feature: sketch_1\n'
    src += f"        sketch_1.path_1 = {p}\n"
    src += (f'    groove(sketch_1.path_1, width={f(width)}, depth={f(depth)}, profile="{profile}", '
            f'corners="{corners}", mode={mode})  # feature: groove_1\n')
    extra = rng.random()
    if extra < 0.25:  # a second groove crossing
        p2 = rand_path(rng, hx, hy, scale)
        prof2 = rng.choice(["rect", "round", "v", "circle"])
        d2 = 0.0 if prof2 == "circle" else depth if prof2 != "round" else max(depth, width)
        src += f"        \n"[:0]
        src += f'    with sketch(on_face(face("box_1", "{face}"))) as sketch_2:  # feature: sketch_2\n'
        src += f"        sketch_2.path_1 = {p2}\n"
        src += (f'    groove(sketch_2.path_1, width={f(width)}, depth={f(d2 if d2 else 0.0)}, profile="{prof2}", '
                f'corners="{rng.choice(["mitre", "round"])}", mode={mode})  # feature: groove_2\n')
    elif extra < 0.45:  # a hole through, crossing the groove
        src += f'    with sketch(on_face(face("box_1", "{face}"))) as sketch_2:  # feature: sketch_2\n'
        hxp, hyp = rng.uniform(-hx, hx) * 0.6, rng.uniform(-hy, hy) * 0.6
        src += f"        sketch_2.c = Pos({f(hxp)}, {f(hyp)}) * Circle({f(rng.uniform(0.3, 3) * width)})\n"
        src += (f"    extrude(regions(sketch_2, ({f(hxp)}, {f(hyp)})), dir=-sketch_2.plane.z_dir, until=Until.LAST, "
                f"mode=Mode.SUBTRACT)  # feature: hole_1\n")
    elif extra < 0.65:  # fillet or chamfer on the top face edges (groove rims included)
        r = rng.uniform(0.05, 0.4) * width
        op = rng.choice(["fillet", "chamfer"])
        kw = "radius" if op == "fillet" else "length"
        src += f"    {op}(part.faces().sort_by(Axis.Z)[-1].edges(), {kw}={f(r)})  # feature: blend_1\n"
    elif extra < 0.75:  # fillet every edge of the groove's faces that isn't on the box
        r = rng.uniform(0.05, 0.3) * width
        src += (f"    {rng.choice(['fillet', 'chamfer'])}(part.edges().filter_by(GeomType.LINE, reverse=True), "
                f"{f(r)})  # feature: blend_1\n")
    return src + TAIL, {"family": "groove", "profile": profile, "corners": corners, "mode": mode, "scale": scale}


def region_shape(rng, s):
    kind = rng.choice(["rect", "circle", "poly", "L", "slot"])
    cx, cy = rng.uniform(-5, 5) * s, rng.uniform(-3, 3) * s
    if kind == "rect":
        return f"Pos({f(cx)}, {f(cy)}) * Rectangle({f(rng.uniform(2, 12) * s)}, {f(rng.uniform(2, 10) * s)})", (cx, cy)
    if kind == "circle":
        return f"Pos({f(cx)}, {f(cy)}) * Circle({f(rng.uniform(1, 6) * s)})", (cx, cy)
    if kind == "slot":
        return f"Pos({f(cx)}, {f(cy)}) * SlotOverall({f(rng.uniform(6, 14) * s)}, {f(rng.uniform(2, 4) * s)})", (cx, cy)
    if kind == "L":
        a, b, t = rng.uniform(6, 12) * s, rng.uniform(6, 10) * s, rng.uniform(1.5, 3) * s
        pts = [(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)]
        pts = [(x - a / 2, y - b / 2) for x, y in pts]
        return "Polygon(" + ", ".join(f"({f(x)}, {f(y)})" for x, y in pts) + ", align=None)", (-a / 2 + t / 2, -b / 2 + t / 2)
    n = rng.randint(3, 7)
    r = rng.uniform(2, 7) * s
    pts = [(cx + r * math.cos(2 * math.pi * k / n + 0.3), cy + r * math.sin(2 * math.pi * k / n + 0.3)) for k in range(n)]
    return "Polygon(" + ", ".join(f"({f(x)}, {f(y)})" for x, y in pts) + ", align=None)", (cx, cy)


def taper_case(rng, scale):
    L, W, H = 40 * scale, 30 * scale, 10 * scale
    shape, seed = region_shape(rng, scale)
    taper = rng.choice([-1, 1]) * rng.uniform(0.5, 20)
    mode = rng.choice(["Mode.ADD", "Mode.SUBTRACT"])
    amount = rng.uniform(1, 8) * scale
    if mode == "Mode.SUBTRACT":
        amount = -min(amount, 9 * scale)
    src = HEAD + box(L, W, H)
    src += '    with sketch(on_face(face("box_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
    src += f"        sketch_1.r = {shape}\n"
    src += (f"    extrude(regions(sketch_1, ({f(seed[0])}, {f(seed[1])})), amount={f(amount)}, taper={f(taper)}, "
            f"mode={mode})  # feature: extrude_1\n")
    if rng.random() < 0.4:
        r = rng.uniform(0.1, 1.0) * scale
        op = rng.choice(["fillet", "chamfer"])
        src += f"    {op}(part.edges().filter_by(Axis.Z, reverse=True).group_by(Axis.Z)[-1], {f(r)})  # feature: blend_1\n"
    return src + TAIL, {"family": "taper", "taper": taper, "mode": mode, "scale": scale}


def revolve_case(rng, scale):
    s = scale
    kind = rng.choice(["rect", "circle", "poly", "slot"])
    off = rng.uniform(0.0, 15) * s
    if kind == "rect":
        w, h = rng.uniform(1, 8) * s, rng.uniform(1, 12) * s
        if rng.random() < 0.3:
            off = w / 2  # touches the axis
        shape, seed = f"Pos({f(off + w / 2 if off != w/2 else off)}, {f(rng.uniform(-3, 3) * s)}) * Rectangle({f(w)}, {f(h)})", None
        cx = off + w / 2 if off != w / 2 else off
        shape = f"Pos({f(cx)}, 0.0) * Rectangle({f(w)}, {f(h)})"
        seed = (cx, 0.0)
    elif kind == "circle":
        r = rng.uniform(0.5, 5) * s
        cx = off + r + rng.uniform(0.01, 3) * s
        shape, seed = f"Pos({f(cx)}, 0.0) * Circle({f(r)})", (cx, 0.0)
    elif kind == "slot":
        cx = off + 3 * s
        shape, seed = f"Pos({f(cx)}, 0.0) * SlotOverall({f(4 * s)}, {f(2 * s)})", (cx, 0.0)
    else:
        n = rng.randint(3, 6)
        r = rng.uniform(1, 5) * s
        cx = off + r + 0.1 * s
        pts = [(cx + r * math.cos(2 * math.pi * k / n + 0.2), r * math.sin(2 * math.pi * k / n + 0.2)) for k in range(n)]
        shape = "Polygon(" + ", ".join(f"({f(x)}, {f(y)})" for x, y in pts) + ", align=None)"
        seed = (cx, 0.0)
    arc = rng.choice([360, 360, rng.uniform(5, 355)])
    src = HEAD
    src += "    with sketch(Plane.XZ) as sketch_1:  # feature: sketch_1\n"
    src += f"        sketch_1.r = {shape}\n"
    src += f"        sketch_1.axis = Line((0.0, {f(-40 * s)}), (0.0, {f(40 * s)}))\n"
    src += (f'    revolve(regions(sketch_1, ({f(seed[0])}, {f(seed[1])})), axis=sketch_1.axis("axis"), '
            f"revolution_arc={f(arc)})  # feature: revolve_1\n")
    if rng.random() < 0.3:
        r = rng.uniform(0.05, 0.5) * s
        src += f"    fillet(part.edges().filter_by(GeomType.CIRCLE), {f(r)})  # feature: blend_1\n"
    return src + TAIL, {"family": "revolve", "kind": kind, "arc": arc, "scale": scale}


def until_case(rng, scale):
    s = scale
    tilt = rng.choice([0.0, rng.uniform(-25, 25)])
    src = HEAD
    src += "    with Locations(Location((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))):  # feature: base_1\n"
    src += f"        Box({f(40 * s)}, {f(30 * s)}, {f(5 * s)}, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
    src += f"    with Locations(Location((0.0, 0.0, {f(20 * s)}), (0.0, {f(tilt)}, 0.0))):  # feature: roof_1\n"
    src += f"        Box({f(60 * s)}, {f(40 * s)}, {f(2 * s)}, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
    if rng.random() < 0.4:
        src += f"    with Locations(Location((0.0, 0.0, {f(10 * s)}), (0.0, 0.0, 0.0))):  # feature: mid_1\n"
        src += f"        Cylinder({f(6 * s)}, {f(30 * s)}, rotation=(90, 0, 0))\n"
    shape, seed = region_shape(rng, s)
    until = rng.choice(["NEXT", "LAST"])
    src += '    with sketch(on_face(face("base_1", "+Z"))) as sketch_1:  # feature: sketch_1\n'
    src += f"        sketch_1.r = {shape}\n"
    src += f"    extrude(regions(sketch_1, ({f(seed[0])}, {f(seed[1])})), until=Until.{until})  # feature: extrude_1\n"
    if rng.random() < 0.3:
        src += '    with sketch(on_face(face("roof_1", "+Z"))) as sketch_2:  # feature: sketch_2\n'
        src += f"        sketch_2.c = Circle({f(rng.uniform(1, 5) * s)})\n"
        src += (f"    extrude(regions(sketch_2, (0.0, 0.0)), dir=-sketch_2.plane.z_dir, until=Until.{rng.choice(['NEXT', 'LAST'])}, "
                f"mode=Mode.SUBTRACT)  # feature: cut_1\n")
    return src + TAIL, {"family": "until", "until": until, "tilt": tilt, "scale": scale}


FAMILIES = {"groove": groove_case, "taper": taper_case, "revolve": revolve_case, "until": until_case}
SCALES = [0.01, 0.1, 1, 1, 1, 10, 100, 125]   # 125 * 40 = 5000 mm box
TOLS = [1.0, 1.0, 1.0, 0.1, 0.01, 5.0]


def make(seed, family=None):
    rng = random.Random(seed)
    fam = family or rng.choice(["groove", "groove", "groove", "taper", "revolve", "until"])
    scale = rng.choice(SCALES)
    tol = rng.choice(TOLS)
    src, meta = FAMILIES[fam](rng, scale)
    meta.update(seed=seed, tol=tol)
    return src, meta


if __name__ == "__main__":
    n0, n1 = int(sys.argv[1]), int(sys.argv[2])
    fam = sys.argv[3] if len(sys.argv) > 3 else None
    cases = []
    for s in range(n0, n1):
        src, meta = make(s, fam)
        cases.append({"src": src, "meta": meta})
    json.dump(cases, sys.stdout)
