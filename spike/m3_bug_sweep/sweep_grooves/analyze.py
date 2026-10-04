import sys, math, json, multiprocessing as mp
sys.path.insert(0, sys.argv[1])
from harness import *
from shapely.geometry import LineString

def features(c):
    """path facts: min arc radius, max sharp turn, simple."""
    pts, closed = path_coords(c)
    try:
        w = sketches.path(tuple(float(fmt(x)) for x in c["start"]),
                          *[sketches.arc_to(tuple(float(fmt(x)) for x in p)) if k == "A" else tuple(float(fmt(x)) for x in p)
                            for k, p in c["segs"]], closed=c["closed"])
    except Exception as e:
        return {"path_error": f"{type(e).__name__}: {e}"}
    runs, sharp = sketches._runs(w)
    radii = [e.radius for e in w.edges() if e.geom_type.name == "CIRCLE"]
    turns = [math.degrees(math.radians(b.get_angle(a))) for _, b, a in sharp]
    turns = [b.get_angle(a) for _, b, a in sharp]
    simple = LineString([p for e in pts.edges for p, _ in e]).is_simple if not closed else True
    return {"min_r": (min(radii) if radii else None),
            "max_turn": max(turns) if turns else 0.0, "min_turn": min(turns) if turns else None,
            "nsharp": len(sharp), "simple": simple, "closed": w.is_closed, "nedges": len(w.edges())}

def one(line):
    d = json.loads(line)
    c, r = d["case"], d["res"]
    out = {"src": d["src"], "res": r, "case": c}
    try:
        out["feat"] = features(c)
    except Exception as e:
        out["feat"] = {"feat_error": repr(e)}
    if r["ok"]:
        try:
            exp, lip = expected(c)
            out["exp"], out["lip"] = (float(exp) if exp is not None else None), (float(lip) if not isinstance(lip, str) else lip)
        except Exception as e:
            out["exp"] = None; out["lip"] = repr(e)
    return out

if __name__ == "__main__":
    lines = open(sys.argv[2]).read().splitlines()
    with mp.get_context("fork").Pool(2) as pool:
        outs = pool.map(one, lines, chunksize=1)
    with open(sys.argv[3], "w") as f:
        for o in outs:
            f.write(json.dumps(o, default=str) + "\n")
