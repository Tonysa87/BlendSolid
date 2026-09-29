"""Flat-face quality of display meshes: test2's part and the STEP corpus.
Run from the repo root: $PY spike/m3_outer_arcs/measure.py [test2] [step ...]  (PY = Blender's Python)
Per part: flat faces with more than one polygon, their polygon count, min corner angle, slivers (< 5°)."""
import sys, math, glob, os, time; sys.path[:0] = ["blendsolid/worker", ".dev/worker_libs", "blendsolid"]
import numpy as np
import tessellate, runner, provenance
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.STEPControl import STEPControl_Reader
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID

CORPUS = "/mnt/e/bs_debug/step_corpus"
TEST2 = open(os.path.join(os.path.dirname(__file__), "test2_box.py")).read()


def test2():
    return [runner._build(TEST2, "test2", [], runner.ShapeCache(), tracker=provenance.Tracker()).wrapped]


def step_solids(path):
    r = STEPControl_Reader(); r.ReadFile(path); r.TransferRoots()
    out, ex = [], TopExp_Explorer(r.OneShape(), TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current()); ex.Next()
    return out


def angles(p):
    a = np.roll(p, 1, 0) - p; b = np.roll(p, -1, 0) - p
    c = np.einsum("ij,ij->i", a, b) / np.maximum(1e-30, np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


def face_stats(shape, lin=1.0, ang=0.3):
    m = tessellate.display_mesh(shape, lin, ang)
    v = m.verts.astype(np.float64); st = np.concatenate([[0], np.cumsum(m.poly_sizes)[:-1]])
    out = []
    for fid, f in enumerate(tessellate.face_map(shape)):
        if BRepAdaptor_Surface(f).GetType() != GeomAbs_Plane:
            continue
        idx = np.where(m.poly_face == fid)[0]
        if len(idx) < 2:
            continue
        mins = [angles(v[m.loops[st[i]:st[i] + m.poly_sizes[i]]]).min() for i in idx]
        out.append((fid, len(idx), float(min(mins)), int(sum(x < 5 for x in mins))))
    return out


if __name__ == "__main__":
    names = sys.argv[1:] or ["test2"] + sorted(glob.glob(CORPUS + "/*.step"))
    total = [0, 0, 0]
    for name in names:
        solids = test2() if name == "test2" else step_solids(name)
        t0 = time.perf_counter(); rows = []
        for s in solids:
            try:
                rows += face_stats(s)
            except Exception as e:
                print("  ERR", type(e).__name__, e)
        bad = [r for r in rows if r[3]]
        total[0] += len(rows); total[1] += len(bad); total[2] += sum(r[3] for r in rows)
        print(f"{os.path.basename(name)[:40]:40s} solids {len(solids):3d} multi-poly flat faces {len(rows):4d} "
              f"with slivers {len(bad):4d} slivers {sum(r[3] for r in rows):5d} {time.perf_counter() - t0:.1f}s")
        if name == "test2":
            for r in rows:
                print("   face", r)
    print("TOTAL faces", total[0], "with slivers", total[1], "slivers", total[2])
