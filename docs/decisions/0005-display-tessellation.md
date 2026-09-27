# ADR 0005 — Display tessellation: structured grids and a scene tolerance

- **Status:** accepted (2026-09-27, maintainer's request during the milestone 1.5 manual GUI test)
- **Date:** 2026-09-27
- **Context from:** manual GUI test, steps 2–3 (curved primitives)

## Context

Every part's display mesh came from OCCT's `BRepMesh_IncrementalMesh(shape, 0.1, False, 0.3, True)`. On curved
faces it is poor: BRepMesh triangulates each face with Delaunay in the (u, v) parameter space and inserts interior
nodes wherever the deflection is exceeded, so a sphere got fans of up to 17 triangles on a vertex, slivers
(minimum angle 0°), a distorted band along the seam and duplicated seam nodes (a visible shading line under a
glossy MatCap). Measured against ND Primitives (Blender's native mesh nodes: regular grids, valence 4) the
BRepMesh sphere had valences 3–10. No BRepMesh setting fixes it: Delabella, finer deflections and
`ControlSurfaceDeflection = False` keep or worsen the fans. The linear deflection was also absolute (0.1 mm),
so a one-metre sphere had 80,000 triangles and a five-metre torus 857,000 (55 s to tessellate).

The maintainer asked for a correct triangle topology, with no artifacts (quad meshes stay a later topic, spec
"Blender output" row), and for a user-set tolerance, 1 mm by default.

## Decision

1. **Structured grids for full faces of revolution** (`blendsolid/worker/tessellate.py`). A face whose surface is
   a sphere, torus, cylinder or cone, closed in u and bounded only by its seam, poles and v-iso circles (an
   untrimmed primitive face), is triangulated by BlendSolid instead of BRepMesh:
   - **sphere:** a geodesic grid, an octahedron subdivided and projected onto the exact sphere: uniform
     triangles, valence 6 except its 6 corners (4), which sit on the sphere's axes so the mesh has the exact
     extents; the lowest frequency whose flat triangles all lie within the tolerance;
   - **torus:** staggered rings (each ring shifted half a step), periodic both ways, near-equilateral, valence 6;
     rings at 0/90/180/270° and nodes on the axes for exact extents;
   - **cylinder, cone between two circles:** one row of triangles (the generatrix is straight, the normal constant
     along it), its rings being BRepMesh's own edge nodes so it stays conforming with the neighbouring faces; the
     edge angle is chosen so both circles of a cone get the same node count;
   - **cone to an apex:** rings graded by the local spacing, halving the node count as the radius shrinks.
   Seams are welded inside a face. Vertices stay unshared between BRep faces (sharp edges, face map).
   BRepMesh still meshes every other face (planes, trimmed faces after booleans), with its seam and pole copies
   welded; it is not run on spheres and tori at all.
2. **A display tolerance per scene:** `Scene.blendsolid_tolerance`, millimetres, default **1 mm**, in the
   BlendSolid sidebar's *Display* subpanel: the largest distance between a mesh and its exact surface. The
   angular limit stays 0.3 rad, so small parts stay round. The tolerance is part of every mesh tag (next to the
   unit factor, ADR 0003): changing it recomputes every part.

3. **Exact vertex normals** (added the same day, after MatCap showed bands on a cylinder side trimmed by holes,
   where BRepMesh's triangles had minimum angles down to 0.09° and averaged normals were off by up to 6.3°):
   the worker sends each vertex's exact surface normal and Blender shades with it (`custom_normal` point
   attribute), so shading no longer depends on the triangles' shapes.

## Consequences

- Measured at 1 mm: a 10 mm sphere has 648 triangles, a 1 m sphere 8,192 (14 ms), a 5 m torus 87,552 (139 ms).
- Meshes saved by earlier versions carry a tag without the tolerance: they are recomputed once (trusted files) or
  shown as stale until trusted (ADR 0004). The tessellation changed anyway.
- Trimmed curved faces (a hole side cut by another curved surface) still get BRepMesh's triangulation, welded:
  they shade right (exact normals) but their wireframe shows slivers. A structured grid with a triangulated band
  along the cut is the next step (after milestone 1.5).
- The mesh is inscribed: volumes are slightly under the exact ones, bounded by area × tolerance (tested).
- Tests: `tests/unit/test_tessellate.py` (welding, valence, minimum angle, deviation from the exact surface,
  orientation, conformity with neighbours), `tests/blender/test_tolerance.py`.
