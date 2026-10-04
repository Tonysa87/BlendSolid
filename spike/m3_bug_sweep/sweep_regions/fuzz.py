import json, math, random, re, sys
from drive import run_cases
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 1
N = int(sys.argv[2]) if len(sys.argv) > 2 else 60
rng = random.Random(SEED)
pi = math.pi
def f6(x): return repr(round(x, 6) + 0.0)

def frame(n):
    n = list(n)
    x = [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0]
    d = sum(a*b for a, b in zip(x, n)); x = [x[i]-n[i]*d for i in range(3)]
    L = math.sqrt(sum(c*c for c in x)); x = [c/L for c in x]
    y = [n[1]*x[2]-n[2]*x[1], n[2]*x[0]-n[0]*x[2], n[0]*x[1]-n[1]*x[0]]
    return x, y

def base():
    k = rng.choice(["box", "box", "cyl", "fillet", "ext", "plane"])
    L, W, H = (round(rng.uniform(10, 60), 1) for _ in range(3))
    if k == "plane":
        return dict(kind=k, body="", plane="Plane.XY", bounds=None, V0=0.0, depth=None)
    if k == "cyl":
        r = round(rng.uniform(5, 30), 1)
        body = f"    Cylinder({r}, {H}, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: cyl_1\n"
        return dict(kind=k, body=body, plane='on_face(face("cyl_1", "+Z"))', bounds=("circle", r), V0=pi*r*r*H,
                    depth=H, farea=pi*r*r)
    body = f"    Box({L}, {W}, {H}, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1\n"
    if k == "box":
        role = rng.choice(["+Z", "+Z", "-Z", "+X", "-X", "+Y", "-Y"])
        ax = "XYZ".index(role[1]); s = 1 if role[0] == "+" else -1
        n = [0.0]*3; n[ax] = s
        x, y = frame(n)
        corners = [(a, b, c) for a in (-L/2, L/2) for b in (-W/2, W/2) for c in (0, H)]
        if ax == 2: corners = [p for p in corners if p[2] == (H if s > 0 else 0)]
        else: corners = [p for p in corners if p[ax] == s*(L, W)[ax]/2]
        us = [sum(p[i]*x[i] for i in range(3)) for p in corners]; vs = [sum(p[i]*y[i] for i in range(3)) for p in corners]
        depth = (L, W, H)[ax]
        return dict(kind=k, body=body, plane=f'on_face(face("box_1", "{role}"))', bounds=("rect", min(us), max(us), min(vs), max(vs)),
                    V0=L*W*H, depth=depth, farea=(max(us)-min(us))*(max(vs)-min(vs)))
    if k == "fillet":
        r = round(rng.uniform(0.5, min(L, W, H)/4), 1)
        body += f'    fillet(edge_between(face("box_1", "+Z"), face("box_1", "+X")), radius={r})  # feature: fillet_1\n'
        V0 = L*W*H - (r*r - pi*r*r/4)*W
        return dict(kind=k, body=body, plane='on_face(face("box_1", "+Z"))', bounds=("rect", -L/2, L/2 - r, -W/2, W/2),
                    V0=V0, depth=H, farea=(L-r)*W)
    # ext: a boss extruded from a first sketch, second sketch on its end face
    bw, bh, e = round(rng.uniform(5, L), 1), round(rng.uniform(5, W), 1), round(rng.uniform(2, 15), 1)
    body += ('    with sketch(on_face(face("box_1", "+Z"))) as sketch_0:  # feature: sketch_0\n'
             f'        sketch_0.boss = Rectangle({bw}, {bh})\n'
             f'    extrude(regions(sketch_0, (0.0, 0.0)), amount={e})  # feature: extrude_0\n')
    return dict(kind=k, body=body, plane='on_face(face("extrude_0", "end"))', bounds=("rect", -bw/2, bw/2, -bh/2, bh/2),
                V0=L*W*H + bw*bh*e, depth=H+e, farea=bw*bh)

def jitter():
    r = rng.random()
    if r < 0.6: return 0.0
    return rng.choice([-1, 1]) * rng.choice([1e-7, 5e-7, 1e-6, 4e-6, 9e-6, 2e-5, 1e-4])

def entities(b):
    if b["bounds"] is None: lo, hi, vlo, vhi = -20, 20, -20, 20
    elif b["bounds"][0] == "circle": r = b["bounds"][1]; lo, hi, vlo, vhi = -r, r, -r, r
    else: _, lo, hi, vlo, vhi = b["bounds"]
    inside = rng.random() < 0.5 and b["bounds"] is not None
    m = 0 if inside else 0.3*(hi-lo)
    U = lambda: rng.uniform(lo - m, hi + m); Vv = lambda: rng.uniform(vlo - m, vhi + m)
    special_u = [lo, hi, (lo+hi)/2]; special_v = [vlo, vhi, (vlo+vhi)/2]
    pts = []
    out = []
    n = rng.randint(1, 4)
    for i in range(n):
        t = rng.choice(["rect", "circle", "line", "line", "poly", "path", "linex"])
        name = f"{t}_{i+1}"
        if t == "rect":
            w, h = rng.uniform(1, (hi-lo)*0.8), rng.uniform(1, (vhi-vlo)*0.8)
            cu, cv = U(), Vv()
            if inside:
                cu = rng.uniform(lo + w/2, hi - w/2); cv = rng.uniform(vlo + h/2, vhi - h/2)
                if rng.random() < 0.2: cu = lo + w/2 + jitter()  # touching a face edge
            rot = "" if rng.random() < 0.7 or inside else f"Rot(0, 0, {rng.choice([15.0, 30.0, 45.0, 90.0])}) * "
            out.append((name, f"Pos({f6(cu)}, {f6(cv)}) * {rot}Rectangle({f6(w)}, {f6(h)})"))
            pts += [(cu - w/2, cv - h/2), (cu + w/2, cv + h/2)]
        elif t == "circle":
            r = rng.uniform(0.5, min(hi-lo, vhi-vlo)*0.4)
            cu, cv = U(), Vv()
            if inside:
                cu = rng.uniform(lo + r, hi - r); cv = rng.uniform(vlo + r, vhi - r)
                if rng.random() < 0.2: cu = lo + r + jitter()  # tangent to a face edge
            if b["bounds"] and b["bounds"][0] == "circle" and inside:
                R = b["bounds"][1]; d = rng.uniform(0, max(R - r, 0)); a = rng.uniform(0, 2*pi)
                cu, cv = d*math.cos(a), d*math.sin(a)
            if pts and rng.random() < 0.3:  # through / centred on a previous point
                cu, cv = rng.choice(pts)
            out.append((name, f"Pos({f6(cu)}, {f6(cv)}) * Circle({f6(r)})"))
            pts += [(cu, cv), (cu + r, cv)]
        elif t in ("line", "linex"):
            if t == "linex" and b["bounds"] is not None:  # across a face, outside to outside or edge to edge
                if rng.random() < 0.5:
                    a = (rng.choice([lo, lo - 5]) + jitter(), Vv()); c = (rng.choice([hi, hi + 5]) - jitter(), Vv())
                else:
                    a = (U(), rng.choice([vlo, vlo - 5]) + jitter()); c = (U(), rng.choice([vhi, vhi + 5]) - jitter())
            else:
                a = rng.choice(pts) if pts and rng.random() < 0.5 else (U(), Vv())
                c = (U(), Vv())
                if pts and rng.random() < 0.3:
                    p = rng.choice(pts); c = (p[0] + jitter(), p[1] + jitter())
            if math.dist(a, c) < 0.5: continue
            out.append((name, f"Line(({f6(a[0])}, {f6(a[1])}), ({f6(c[0])}, {f6(c[1])}))"))
            pts += [a, c]
        elif t == "poly":
            k = rng.randint(3, 5); cu, cv = U(), Vv(); R = rng.uniform(1, (hi-lo)/3)
            angs = sorted(rng.uniform(0, 2*pi) for _ in range(k))
            P = [(cu + R*math.cos(q), cv + R*math.sin(q)) for q in angs]
            out.append((name, "Polygon(" + ", ".join(f"({f6(p[0])}, {f6(p[1])})" for p in P) + ", align=None)"))
            pts += P
        else:
            p0 = (U(), Vv()); segs = []; here = p0
            for j in range(rng.randint(1, 4)):
                q = (U(), Vv())
                if math.dist(q, here) < 0.5: continue
                segs.append(f"arc_to(({f6(q[0])}, {f6(q[1])}))" if segs and rng.random() < 0.4 else f"({f6(q[0])}, {f6(q[1])})")
                here = q
            if not segs: continue
            closed = ", closed=True" if rng.random() < 0.4 else ""
            out.append((name, f"path(({f6(p0[0])}, {f6(p0[1])}), {', '.join(segs)}{closed})"))
            pts += [p0, here]
    if b["kind"] == "plane" or rng.random() < 0.3:
        # an axis line for revolve
        if rng.random() < 0.5:
            u = rng.uniform(lo - 30, lo - 1) if rng.random() < 0.6 else rng.uniform(lo, hi)
            out.append(("axis", f"Line(({f6(u)}, {f6(vlo - 40)}), ({f6(u)}, {f6(vlo - 35)}))"))
        else:
            v = rng.uniform(vlo - 30, vlo - 1) if rng.random() < 0.6 else rng.uniform(vlo, vhi)
            out.append(("axis", f"Line(({f6(lo - 40)}, {f6(v)}), ({f6(lo - 35)}, {f6(v)}))"))
    return out, inside

def script(b, ents, op=None):
    s = "with BuildPart() as part:\n" + b["body"] + f"    with sketch({b['plane']}) as sketch_1:  # feature: sketch_1\n"
    for name, code in ents: s += f"        sketch_1.{name} = {code}\n"
    if op: s += op + "\n"
    return s + "result = part.part\n"

bases = []
phase1 = []
for i in range(N):
    b = base(); ents, inside = entities(b)
    if not ents: continue
    bases.append((b, ents, inside))
    phase1.append(dict(id=f"s{SEED}_{i}", src=script(b, ents), loops=True))
r1 = run_cases(phase1)
json.dump(dict(phase1=phase1, r1=r1), open(f"fuzz_p1_{SEED}.json", "w"))

def loops_centroid(loops):
    tot = 0; cx = cy = 0
    for k, L in enumerate(loops):
        a = 0; x = y = 0
        for (x0, y0), (x1, y1) in zip(L, L[1:] + L[:1]):
            c = x0*y1 - x1*y0; a += c; x += (x0 + x1)*c; y += (y0 + y1)*c
        a /= 2
        if a == 0: continue
        cxk, cyk = x/(6*a), y/(6*a)
        w = abs(a) * (1 if k == 0 else -1)
        tot += w; cx += w*cxk; cy += w*cyk
    return cx/tot, cy/tot

def _unused():
    pass
def in_face(b, p):
    if b["bounds"] is None: return None
    if b["bounds"][0] == "circle": return math.hypot(*p) < b["bounds"][1]
    _, lo, hi, vlo, vhi = b["bounds"]; return lo < p[0] < hi and vlo < p[1] < vhi

phase2 = []
notes = []
for (b, ents, inside), c in zip(bases, phase1):
    x = r1[c["id"]]
    if not x["ok"]:
        notes.append((c["id"], "SKETCH FAIL", x["error"], c["src"])); continue
    areas, ins, loops = x["regions"][-1], x["inside"][-1], x["loops"][-1]
    if b["bounds"] is not None and areas:
        tot = sum(a for a, q in zip(areas, ins) if in_face(b, q))
        if abs(tot - b["farea"]) > 1e-6 * max(1, b["farea"]):
            notes.append((c["id"], "AREA SUM", tot, b["farea"], c["src"]))
    if not areas: continue
    idx = rng.sample(range(len(areas)), min(3, len(areas)))
    for j in idx:
        A, p, L = areas[j], ins[j], loops[j]
        seed = f"({f6(p[0])}, {f6(p[1])})"
        reg = f"regions(sketch_1, {seed})"
        fin = in_face(b, p)
        h = round(rng.uniform(0.5, (b["depth"] or 20) * 0.8), 3)
        ops = []
        V0 = b["V0"]
        if b["kind"] == "plane":
            ops.append(("join", f"    extrude({reg}, amount={h})  # feature: extrude_1", A*h, None))
            ops.append(("sym", f"    extrude({reg}, amount={h}, both=True)  # feature: extrude_1", 2*A*h, None))
            t = rng.choice([3.0, -3.0, 10.0, -10.0])
            ops.append(("taper", f"    extrude({reg}, amount={h}, taper={t})  # feature: extrude_1", None, (t, A*h)))
        else:
            ops.append(("join", f"    extrude({reg}, amount={h})  # feature: extrude_1", V0 + A*h, None))
            ops.append(("cut", f"    extrude({reg}, amount=-{h}, mode=Mode.SUBTRACT)  # feature: extrude_1", V0 - A*h if fin else (V0 if fin is False else None), None))
            ops.append(("symcut", f"    extrude({reg}, amount={h}, both=True, mode=Mode.SUBTRACT)  # feature: extrude_1", V0 - A*h if fin else (V0 if fin is False else None), None))
            ops.append(("lastcut", f"    extrude({reg}, dir=-sketch_1.plane.z_dir, until=Until.LAST, mode=Mode.SUBTRACT)  # feature: extrude_1",
                        V0 - A*b["depth"] if (fin and b["kind"] in ("box", "cyl", "fillet")) else None, "err-ok" if not fin else None))
            ops.append(("nextcut", f"    extrude({reg}, dir=-sketch_1.plane.z_dir, until=Until.NEXT, mode=Mode.SUBTRACT)  # feature: extrude_1",
                        V0 - A*b["depth"] if (fin and b["kind"] in ("box", "cyl", "fillet")) else None, "err-ok" if not fin else None))
            t = rng.choice([3.0, -3.0, 8.0, -8.0])
            ops.append(("taper", f"    extrude({reg}, amount={h}, taper={t})  # feature: extrude_1", None, (t, A*h, V0)))
            t = rng.choice([3.0, -3.0])
            ops.append(("tapercut", f"    extrude({reg}, amount=-{h}, taper={t}, mode=Mode.SUBTRACT)  # feature: extrude_1", None, ("cut", t, A*h, V0) if fin else None))
        if any(n == "axis" for n, _ in ents):
            ang = rng.choice([360.0, 90.0, 180.0, -45.0])
            # which side of the axis
            axis_code = dict(ents)["axis"]
            nums = [float(v) for v in re.findall(r"-?\d+\.\d+(?:e-?\d+)?", axis_code)]
            (a0, a1), (c0, c1) = (nums[0], nums[1]), (nums[2], nums[3])
            vertical = abs(a0 - c0) < 1e-12
            allpts = [q for l in L for q in l]
            side = [q[0] - a0 if vertical else q[1] - a1 for q in allpts]
            crosses = min(side) < -1e-6 and max(side) > 1e-6
            cx, cy = loops_centroid(L)
            d = abs(cx - a0) if vertical else abs(cy - a1)
            exp = None
            if b["kind"] == "plane" and not crosses:
                exp = A * 2 * pi * d * abs(ang) / 360
            ops.append(("revolve", f'    revolve({reg}, axis=sketch_1.axis("axis"), revolution_arc={ang})  # feature: revolve_1',
                        exp, "crosses" if crosses else None))
        for name, op, vol, extra in ops:
            phase2.append(dict(id=f"{c['id']}_r{j}_{name}", src=script(b, ents, op), vol=vol, extra=extra, A=A,
                               resolve=rng.random() < 0.25))
r2 = run_cases(phase2)
json.dump(dict(phase2=phase2, r2=r2, notes=notes), open(f"fuzz_p2_{SEED}.json", "w"))
print("phase1", len(phase1), "phase2", len(phase2))
for n in notes: print("NOTE", n[:4])
