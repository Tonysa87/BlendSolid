"""PNG of the flat face with the most polygons of cc_folds.py's parts (system python3 draws):
$PY spike/m2_flat_faces/plot_face.py out.json name... ; python3 spike/m2_flat_faces/plot.py out.json out.png"""
import sys, json; sys.argv, names = sys.argv[:2], sys.argv[2:]
exec(open("spike/m2_flat_faces/cc_folds.py").read().split("SHAPES = {")[0])
SHAPES = {"default_part": default_part, **{k: v[0] for k, v in COLLARED.items()}}
out = {}
for name in names:
    w = SHAPES[name]().wrapped; m = tessellate.display_mesh(w, 1.0, 0.3)
    st = np.concatenate([[0], np.cumsum(m.poly_sizes)[:-1]]); v = m.verts.astype(float)
    planes = tessellate.face_planes(w) if hasattr(tessellate, "face_planes") else None
    best, bestn = None, 0
    for fid in np.unique(m.poly_face):
        idx = np.where(m.poly_face == fid)[0]
        P = [v[m.loops[st[i]:st[i] + m.poly_sizes[i]]] for i in idx]
        allp = np.concatenate(P); n = np.cross(P[0][1] - P[0][0], P[0][2] - P[0][0])
        if np.abs((allp - P[0][0]) @ (n / np.linalg.norm(n))).max() > 1e-4: continue
        if len(idx) > bestn: best, bestn = P, len(idx)
    out[name] = [p.tolist() for p in best]
json.dump(out, open(sys.argv[1], "w"))
