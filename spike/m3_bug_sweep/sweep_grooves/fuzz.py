import sys, math, json, random, time
sys.path.insert(0, sys.argv[1])
from harness import *
from shapely.geometry import LineString

SEED = int(sys.argv[2]); NPATH = int(sys.argv[3]); OUT = sys.argv[4]
rng = random.Random(SEED)
FACES = {"+Z": (-20, 20, -10, 10), "+X": (-10, 10, 0, 10), "-Y": (-20, 20, 0, 10), "XY": (-20, 20, -10, 10)}

def turn_angle():
    k = rng.random()
    s = rng.choice((-1, 1))
    if k < 0.08: return 0.0, "collinear"
    if k < 0.16: return s * 10 ** rng.uniform(-7, -2), "tiny"
    if k < 0.30: return s * 90.0, "90"
    if k < 0.45: return s * rng.uniform(150, 170), "acute"
    if k < 0.55: return s * rng.uniform(170, 179.9), "reversal"
    return s * rng.uniform(1, 150), "any"

def seg_len(scale):
    k = rng.random()
    if k < 0.06: return 1e-3, "1e-3"
    if k < 0.18: return rng.uniform(0.01, 0.5), "short"
    return rng.uniform(1, scale), "normal"

def gen_path(face):
    x0, x1, y0, y1 = FACES[face]
    scale = min(x1 - x0, y1 - y0) * 0.8
    start = (rng.uniform(x0 + 1, x1 - 1), rng.uniform(y0 + 1, y1 - 1))
    heading = rng.uniform(0, 360)
    here = start
    segs, tags = [], []
    n = rng.randint(1, 6)
    for i in range(n):
        if i > 0 and rng.random() < 0.35:
            # tangent arc: sweep and radius
            k = rng.random()
            if k < 0.03:
                sweep, tg = 0.0, "arc-straight"
            elif k < 0.2:
                sweep, tg = rng.uniform(180, 340), "arc>180"
            elif k < 0.3:
                sweep, tg = rng.uniform(1, 10), "arc-small"
            else:
                sweep, tg = rng.uniform(10, 180), "arc"
            sweep *= rng.choice((-1, 1))
            r = rng.choice([rng.uniform(0.3, 2), rng.uniform(2, 12)])
            h = math.radians(heading)
            if sweep == 0.0:
                end = (here[0] + r * math.cos(h), here[1] + r * math.sin(h))
            else:
                # centre to the left (sweep > 0) or right
                sgn = 1 if sweep > 0 else -1
                cx, cy = here[0] - sgn * r * math.sin(h), here[1] + sgn * r * math.cos(h)
                a0 = math.atan2(here[1] - cy, here[0] - cx)
                a1 = a0 + math.radians(sweep)
                end = (cx + r * math.cos(a1), cy + r * math.sin(a1))
                heading += sweep
            segs.append(("A", end)); tags.append(tg)
            here = end
        else:
            if i > 0:
                ta, tg = turn_angle()
                heading += ta
            else:
                tg = "first"
            L, lt = seg_len(scale)
            h = math.radians(heading)
            end = (here[0] + L * math.cos(h), here[1] + L * math.sin(h))
            segs.append(("L", end)); tags.append(tg + "/" + lt)
            here = end
    closed = rng.random() < 0.2
    if rng.random() < 0.05:  # explicitly end at the start too
        segs.append(("L", start)); tags.append("back-to-start")
    return start, segs, closed, tags

cases = []
for _ in range(NPATH):
    face = rng.choice(["+Z", "+Z", "+X", "-Y", "XY"])
    start, segs, closed, tags = gen_path(face)
    combos = [(p, c, rib) for p in ("rect", "round", "v", "circle") for c in ("mitre", "round") for rib in (False, True)]
    rng.shuffle(combos)
    for p, c, rib in combos[:6]:
        if face == "XY": rib = True
        k = rng.random()
        width = rng.uniform(0.2, 1.0) if k < 0.3 else rng.uniform(1.0, 4.0) if k < 0.85 else rng.uniform(4.0, 8.0)
        width = round(width, 6); depth = rng.uniform(0.5, 4.0)
        if p == "round": depth = max(depth, width / 2 + rng.choice([0.0, 0.3, 1.0]))
        cases.append(dict(face=face, start=start, segs=segs, closed=closed, tags=tags,
                          grooves=[dict(width=width, depth=depth, profile=p, corners=c, rib=rib)]))
srcs = [script(c) for c in cases]
t0 = time.time()
res = run_many(srcs, timeout=60, jobs=2)
print("ran", len(cases), "in", time.time() - t0, file=sys.stderr)
with open(OUT, "w") as f:
    for c, s, r in zip(cases, srcs, res):
        r.pop("edge_refs", None); r.pop("face_refs", None)
        f.write(json.dumps({"case": c, "src": s, "res": r}, default=str) + "\n")
