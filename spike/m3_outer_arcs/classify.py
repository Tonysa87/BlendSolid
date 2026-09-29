"""Why flat faces of the corpus have slivers: per face, loops, curved holes, collared or not, concave outer runs.
$PY spike/m3_outer_arcs/classify.py [step ...]"""
import sys, glob, math, collections; sys.path[:0] = ["spike/m3_outer_arcs"]
import numpy as np, measure, tessellate
calls = []
orig = tessellate._collared
def spy(t, verts, normal, keep=()):
    out = orig(t, verts, normal, keep)
    cyc = tessellate._cycles(t)
    info = {"loops": len(cyc) if cyc else None, "collared": out is not None}
    vv = verts.astype(float)
    if out is not None:
        polys, extra = out; vv = np.concatenate([vv, extra])
    else:
        polys = tessellate._merge_convex(t, verts.astype(float), keep)
    info["slivers"] = sum(1 for q in polys if measure.angles(vv[q]).min() < 5)
    if cyc:
        p = verts.astype(float); ez = normal / np.linalg.norm(normal)
        areas = [float(np.dot(np.cross(p[c], np.roll(p[c], -1, 0)).sum(0), ez)) / 2 for c in cyc]
        o = int(np.argmax(areas)); oc = p[cyc[o]]
        a, b = oc - np.roll(oc, 1, 0), np.roll(oc, -1, 0) - oc
        turn = np.einsum("ij,j->i", np.cross(a, b), ez) / np.maximum(1e-30, np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
        info["reflex_outer"] = int((turn < -1e-6).sum())
        info["curved_holes"] = sum(1 for k, c in enumerate(cyc) if k != o and len(c) >= 8)
    calls.append(info)
    return out
tessellate._collared = spy
cnt = collections.Counter(); sl = collections.Counter()
for f in (sys.argv[1:] or sorted(glob.glob(measure.CORPUS + "/*.step")) + ["test2"]):
    for s in (measure.test2() if f == "test2" else measure.step_solids(f)):
        calls.clear()
        try:
            m = tessellate.display_mesh(s, 1.0, 0.3)
        except Exception:
            continue
        for c in calls:
            key = ("collared" if c["collared"] else "fallback", "outer-reflex" if c.get("reflex_outer", 0) >= 4 else "outer-ok",
                   "holes" if c.get("curved_holes") else "no-curved-holes")
            cnt[key] += 1; sl[key] += c["slivers"]
for k, v in sorted(cnt.items()):
    print(v, "faces", sl[k], "slivers", k)
