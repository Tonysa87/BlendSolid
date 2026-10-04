"""Headless screenshots of a part's display mesh: shaded (flat, so folds and facets show) with the wireframe on top,
from a few views, to look at what the worker made — a run without errors can still give a bad mesh.

Run with Blender's Python (no bpy):
    PY=~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13
    "$PY" tools/mesh_shot.py part.py out.png [--tol 1.0] [--face N] [--views iso,top,front] [--size 900]
`part.py` is a part script (as the worker runs it). `--face N[,M...]` zooms on those faces (BRep face ids, as the
display mesh numbers them) and dims the others; `--face curved` zooms on every face that isn't flat. Triangles and
quads with a corner under 1 degree are tinted red, under 5 degrees orange; back faces are purple.
"""
import argparse
import math
import os
import sys

ROOT = os.environ.get("BS_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # BS_ROOT: another checkout
sys.path[:0] = [os.path.join(ROOT, "blendsolid", "worker"),
                os.environ.get("BLENDSOLID_WORKER_LIBS") or os.path.join(ROOT, ".dev", "worker_libs")]

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

VIEWS = {"iso": (35.0, 30.0), "iso2": (215.0, 30.0), "top": (0.0, 89.9), "bottom": (0.0, -89.9),
         "front": (0.0, 0.0), "back": (180.0, 0.0), "left": (90.0, 0.0), "right": (-90.0, 0.0)}


def polygons(loops, sizes):
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    return [loops[s:s + n] for s, n in zip(starts, sizes)]


def min_corner(v, poly):
    p = v[poly]
    a, b = np.roll(p, 1, axis=0) - p, np.roll(p, -1, axis=0) - p
    cos = np.einsum("ij,ij->i", a, b) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-300)
    return float(np.degrees(np.arccos(np.clip(cos, -1, 1))).min())


def view_basis(az, el):
    az, el = math.radians(az), math.radians(el)
    d = np.array([math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)])  # towards the eye
    up = np.array([0.0, 0.0, 1.0])
    x = np.cross(up, d)
    if np.linalg.norm(x) < 1e-6:
        x = np.array([1.0, 0.0, 0.0])
    x /= np.linalg.norm(x)
    y = np.cross(d, x)
    return x, y, d


def render(v, polys, poly_face, az, el, size, focus=None):
    """`focus`: a set of face ids to frame (the others dimmed), or None for all."""
    x, y, d = view_basis(az, el)
    sx, sy, sz = v @ x, v @ y, v @ d
    chosen = [p for p, f in zip(polys, poly_face) if focus is None or f in focus]
    pick = np.unique(np.concatenate(chosen)) if chosen else np.arange(len(v))
    lo = np.array([sx[pick].min(), sy[pick].min()])
    hi = np.array([sx[pick].max(), sy[pick].max()])
    span = max(hi - lo) * 1.08 or 1.0
    centre = (lo + hi) / 2
    px = (sx - centre[0]) / span * size + size / 2
    py = size / 2 - (sy - centre[1]) / span * size
    zbuf = np.full((size, size), -np.inf)
    rgb = np.full((size, size, 3), 255.0)
    light = np.array([0.3, 0.2, 1.0])
    light = light / np.linalg.norm(light)
    edges = set()
    for poly, face in zip(polys, poly_face):
        n = len(poly)
        for k in range(n):
            a, b = int(poly[k]), int(poly[(k + 1) % n])
            edges.add((min(a, b), max(a, b)))
        p3 = v[poly]
        normal = np.zeros(3)
        for k in range(n):  # Newell
            normal += np.cross(p3[k], p3[(k + 1) % n])
        length = np.linalg.norm(normal)
        if length < 1e-300:
            continue
        normal /= length
        facing = normal @ d
        shade = 0.25 + 0.75 * abs(normal @ (light[0] * x + light[1] * y + light[2] * d))
        colour = np.array([200.0, 205.0, 215.0]) if facing >= 0 else np.array([120.0, 60.0, 160.0])  # back: purple
        angle = min_corner(v, poly) if n <= 4 else 90.0  # a flat face's n-gon may have sharp corners
        if angle < 1.0:
            colour = np.array([255.0, 40.0, 40.0])
        elif angle < 5.0:
            colour = np.array([255.0, 170.0, 40.0])
        if focus is not None and face not in focus:
            colour = colour * 0.35 + 255 * 0.65
        # fill: the polygon's scanline mask (any n-gon, convex or not), depth from its plane in screen space
        X, Y, Z = px[poly], py[poly], sz[poly]
        x0, x1 = max(int(math.floor(X.min())), 0), min(int(math.ceil(X.max())), size - 1)
        y0, y1 = max(int(math.floor(Y.min())), 0), min(int(math.ceil(Y.max())), size - 1)
        if x0 > x1 or y0 > y1:
            continue
        sp = np.column_stack([X, Y, Z])
        ns = np.zeros(3)
        for k in range(n):
            ns += np.cross(sp[k], sp[(k + 1) % n])
        if abs(ns[2]) < 1e-9 * max(np.linalg.norm(ns), 1e-300):
            continue  # edge-on: the wireframe shows it
        c = sp.mean(axis=0)
        mask = Image.new("1", (x1 - x0 + 1, y1 - y0 + 1), 0)
        ImageDraw.Draw(mask).polygon([(float(a - x0), float(b - y0)) for a, b in zip(X, Y)], fill=1, outline=1)
        inside = np.asarray(mask, dtype=bool)
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        z = c[2] - (ns[0] * (gx - c[0]) + ns[1] * (gy - c[1])) / ns[2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        win = inside & (z > sub)
        sub[win] = z[win]
        rgb[y0:y1 + 1, x0:x1 + 1][win] = colour * shade
    # wireframe with a depth test (a little in front of the surface it lies on)
    eps = span * 2e-3
    img = Image.fromarray(rgb.clip(0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    zr = sz.max() - sz.min() + 1e-12
    for a, b in edges:
        steps = int(max(abs(px[a] - px[b]), abs(py[a] - py[b]))) + 2
        t = np.linspace(0, 1, steps)
        X, Y = px[a] + (px[b] - px[a]) * t, py[a] + (py[b] - py[a]) * t
        Z = sz[a] + (sz[b] - sz[a]) * t
        ix, iy = X.astype(int), Y.astype(int)
        ok = (ix >= 0) & (ix < size) & (iy >= 0) & (iy < size)
        seen = np.zeros_like(ok)
        seen[ok] = Z[ok] >= zbuf[iy[ok], ix[ok]] - eps - 1e-9 * zr
        for i in np.nonzero(seen)[0]:
            draw.point((int(ix[i]), int(iy[i])), fill=(20, 20, 30))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--tol", type=float, default=1.0)
    ap.add_argument("--face", default=None)
    ap.add_argument("--views", default="iso,iso2,top")
    ap.add_argument("--size", type=int, default=900)
    a = ap.parse_args()
    import runner
    r = runner.run_script(open(a.script).read(), a.tol, 0.3)
    if not r.ok:
        sys.exit(f"the script failed: {r.error} (line {r.line})")
    v = r.verts.astype(np.float64)
    polys = polygons(r.loops.astype(np.int64), r.poly_sizes.astype(np.int64))
    focus = None
    if a.face == "curved":
        import tessellate
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
        shape = runner._build(open(a.script).read(), runner.SCRIPT_NAME, [], runner.ShapeCache()).wrapped
        focus = {i for i, f in enumerate(tessellate.face_map(shape))
                 if BRepAdaptor_Surface(f).GetType() != GeomAbs_Plane}
    elif a.face:
        focus = {int(f) for f in a.face.split(",")}
    shots = [render(v, polys, r.poly_face, *VIEWS[name], a.size, focus) for name in a.views.split(",")]
    sheet = Image.new("RGB", (a.size * len(shots), a.size), "white")
    for i, shot in enumerate(shots):
        sheet.paste(shot, (i * a.size, 0))
    sheet.save(a.out)
    bad = sum(1 for p in polys if len(p) <= 4 and min_corner(v, p) < 1.0)
    print(f"{len(polys)} polygons, {len(v)} vertices, {bad} with a corner under 1 degree, warnings: {r.warnings}")


if __name__ == "__main__":
    main()
