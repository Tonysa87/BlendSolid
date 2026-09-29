"""Details of fallback faces: hole sizes (nodes, diameter), why the collars failed. $PY .../detail.py"""
import sys, glob, collections; sys.path[:0] = ["spike/m3_outer_arcs"]
import numpy as np, measure, tessellate
why = collections.Counter(); rows = []
orig_collar = tessellate._collar
state = {}
def spy_collar(hole, others, lo, hi):
    out = orig_collar(hole, others, lo, hi)
    state.setdefault("res", []).append(out is not None)
    return out
tessellate._collar = spy_collar
orig = tessellate._collared
def spy(t, verts, normal, keep=()):
    state.clear()
    out = orig(t, verts, normal, keep)
    if out is None:
        cyc = tessellate._cycles(t)
        if cyc is None:
            why["cycles None (loops touch)"] += 1; return out
        p = verts.astype(float)
        sizes = sorted(len(c) for c in cyc)
        diam = sorted(float(np.ptp(p[c], axis=0).max()) for c in cyc)
        polys = tessellate._merge_convex(t, p, keep)
        sl = sum(1 for q in polys if measure.angles(p[q]).min() < 5)
        res = state.get("res", [])
        reason = "no hole >=8" if not res else ("all collars None" if not any(res) else "overlap/other")
        why[reason] += sl
        rows.append((sl, reason, len(cyc), sizes[:6], [round(d, 2) for d in diam[:4]], round(diam[-1], 1)))
    return out
tessellate._collared = spy
for f in sorted(glob.glob(measure.CORPUS + "/*.step")):
    for s in measure.step_solids(f):
        try: tessellate.display_mesh(s, 1.0, 0.3)
        except Exception: pass
for r in sorted(rows, reverse=True)[:25]: print(r)
print(why)
