# Milestone 2 phase A — Modifier-compatible display mesh: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** part meshes become ordinary closed Blender meshes (vertices welded along CAD edges, CAD edges marked sharp,
bevel-weighted and numbered), so Blender modifiers work on parts, and the tools pick faces on the evaluated mesh.

**Architecture:** the worker keeps its per-face tessellation (ADR 0005) and adds one welding stage that merges the
coincident boundary nodes of neighbouring faces, moves the exact normals to face corners and finds, for each mesh
edge lying on a BRep edge, that edge's index and whether it is sharp. Blender fills the welded mesh and sets
`brep_edge_id`, `sharp_edge` and `bevel_weight_edge` on its edges. Picking reads the evaluated mesh (after
modifiers) and uses a face's exact plane only when the hit point lies on it.

**Tech Stack:** Python 3.13, numpy, OCP 8.0.1 (worker), Blender 5.2 `bpy` (mesh attributes, evaluated depsgraph).

**Spec:** `docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md`, section A.

## Global Constraints

- Blender 5.2 LTS / Python 3.13; worker libraries only in the worker process.
- Everything in the repository in English.
- Every geometric result verified with numbers (counts, closedness, volumes), headless tests (`tools/test.sh`).
- Scripts are millimetres; meshes scaled by the unit factor (ADR 0003); the tolerance is part of the tag (ADR 0005).
- float32 on the Blender side: exact values (planes) come from the worker in float64.
- Bump `part.MESH_FORMAT` (3 → 4) so saved meshes recompute once.

## Review Focus

1. A part whose faces meet at a tangent (fillet next to a flat face): the shared edge is welded but **not** sharp
   — shading must stay smooth across it. Test in Task 1 (fillet box) and Task 2.
2. A cylinder/cone seam and sphere/torus own grids: welded smooth, no `brep_edge_id` on a seam, closed mesh. Task 1.
3. A mesh already carrying the old POINT-domain `custom_normal` (saved file, Edit Mode toggles): refilling must not
   keep a stale attribute on the wrong domain. Task 2.
4. A modifier that moves geometry (Solidify, Array, Mirror offset): the exact-plane shortcut must not snap a drawing
   to the original face's plane when the ray hit a moved copy. Task 3.
5. Linked duplicates (Alt+D) sharing one mesh, each with its own modifiers: picking on each uses its own evaluated
   mesh. Task 3.

---

### Task 1: Welded display mesh in the worker

**Files:**
- Modify: `blendsolid/worker/tessellate.py` (new `display_mesh()` and `DisplayMesh`, edge helpers)
- Modify: `blendsolid/worker/runner.py` (use it; new `RunResult` fields)
- Modify: `blendsolid/worker/server.py:124-125` (send the new arrays)
- Test: `tests/unit/test_tessellate.py`, `tests/unit/test_runner.py`

**Interfaces:**
- Produces: `tessellate.display_mesh(shape, lin_defl, ang_defl) -> DisplayMesh` with fields
  `verts (n,3) float32`, `tris (t,3) int32`, `tri_face (t,) int32`, `corner_normals (t*3,3) float32`
  (corner k of triangle i at row 3i+k), `edges (e,2) int32` (vertex pairs of mesh edges lying on BRep edges,
  sorted per row), `edge_ids (e,) int32` (index in `edge_map(shape)` order), `edge_sharp (e,) int32` (1/0).
  `tessellate.edge_map(shape) -> list[TopoDS_Edge]`.
- Worker reply arrays: `verts, tris, tri_face, planes, corner_normals, edges, edge_ids, edge_sharp`
  (no more `normals`).

- [ ] **Step 1: failing tests** — in `tests/unit/test_tessellate.py` add, with `display()` = `display_mesh(SHAPES[name]().wrapped, LIN, ANG)` and new shapes `"filleted_box": lambda: bd.fillet(bd.Box(40, 30, 20).edges().filter_by(bd.Axis.Z), 5)` (in a helper, not in `SHAPES`, to leave the per-face tests alone):
  - `test_display_mesh_is_closed(name)` for every shape plus the filleted box: every mesh edge has exactly two
    triangles; the volume equals the per-face mesh's volume (1e-6 relative); vertex count < per-face count for
    shapes with more than one face.
  - `test_edges_carry_brep_edge_ids(name)`: every mesh edge between two triangles of different faces is in `edges`;
    `edge_ids` cover every non-seam, non-degenerate BRep edge of `edge_map` (a cylinder: 2 circles, not its seam);
    each mesh edge's midpoint lies within `LIN` of its BRep edge's curve (`BRepExtrema_DistShapeShape` with a
    vertex).
  - `test_sharp_edges`: box: all 12 edges sharp; cylinder: the 2 circles sharp; filleted box: the 8 tangent edges
    between fillet and flat faces **not** sharp, the others sharp.
  - `test_corner_normals_follow_their_face`: corner normals equal the per-face mesh's vertex normals of that
    corner (same face), so a welded vertex on a sharp edge has different normals in its two faces.
- [ ] **Step 2:** `tools/test.sh -k "display_mesh or brep_edge or sharp_edges or corner_normals"` → FAIL
  (`display_mesh` not defined).
- [ ] **Step 3: implement** in `tessellate.py`:
  - `edge_map(shape)` like `face_map` with `TopAbs_EDGE` (cast `TopoDS.Edge`).
  - `display_mesh()`: call `tessellate_with_normals` (per-face islands; keep it unchanged), then
    `corner_normals = normals[tris].reshape(-1, 3)`; weld: `key = np.round(verts / 1e-6)` (int64) →
    `np.unique(key, axis=0, return_inverse=True)`; remap `tris`; a second pass merges the remaining open-edge
    vertices pairwise within 1e-5 mm (brute force on the few open-edge vertices; rounding can split a pair that
    straddles a grid line); drop nothing else (faces were already non-degenerate).
  - Mesh edges: sorted vertex pairs of all triangle sides → `np.unique(..., return_inverse=True)`; for each unique
    edge the face ids of its two triangles; an edge is a CAD edge when they differ.
  - BRep edge of a CAD edge: `TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, ...)` gives each BRep
    edge's faces; candidates for (fa, fb) are the BRep edges shared by those two faces; one candidate → it; several
    → the one nearest the mesh edge's midpoint (`BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(p), edge)`).
  - Sharp: the angle between the two faces' corner normals at the edge's first vertex > 1e-3 rad (tangent faces
    have equal normals there).
  - Return `DisplayMesh`.
- [ ] **Step 4:** `runner.run_script` uses `display_mesh`; `RunResult` gets `corner_normals, edges, edge_ids,
  edge_sharp` (drop `normals`); `server.py` sends them. Update `tests/unit/test_runner.py` expectations that read
  `normals` (grep) to `corner_normals`.
- [ ] **Step 5:** `tools/test.sh` (unit part) → PASS. Commit
  `Worker: welded display mesh with BRep edge ids and sharp edges`.

### Task 1b: One polygon per flat face without holes (found while probing Task 4)

Blender's Bevel with *Clamp Overlap* (its default) clamps the whole bevel to the tightest vertex: a flat cap
triangulated without interior nodes has chords between neighbouring rim nodes, and the default part's bevel removed
0.35 mm³ instead of ~78 (clamp off: 78). Blender's own primitives use n-gon caps. So the display mesh emits one
polygon (the face's boundary loop) for every planar face with a single wire; other faces stay triangulated.

- `DisplayMesh` gets `loops (L,) int32` (vertex index per polygon corner), `poly_sizes (P,) int32`,
  `poly_face (P,) int32`, `corner_normals (L,3)`; `tris`/`tri_face` are removed (a test helper fan-triangulates).
- Tests: box → 6 quads; cylinder → 2 n-gon caps + triangulated side; box with a through hole → top and bottom stay
  triangles; closedness, volume, edge ids and corner normals as in Task 1 on the new representation; Blender: the
  default part's Bevel (weight, 1 mm, clamp on) removes within 15% of the clamp-off volume.
- Blender side: `fill_mesh(mesh, verts, loops, poly_sizes, poly_face, ...)`, `part.mesh_volume` fan-triangulates
  polygons.

### Task 2: Blender fills the welded mesh

**Files:**
- Modify: `blendsolid/part.py` (`fill_mesh`, `apply_result`, `MESH_FORMAT = 4`, new `EDGE_ATTR`)
- Modify: `blendsolid/runtime.py` if it reads `normals` (grep `"normals"`)
- Test: `tests/blender/test_parts.py` (or the file holding mesh tests: grep `fill_mesh`)

**Interfaces:**
- Consumes: the worker reply arrays of Task 1.
- Produces: `part.EDGE_ATTR = "brep_edge_id"` (EDGE, INT, -1 off CAD edges); mesh attributes `sharp_edge` (EDGE,
  BOOLEAN), `bevel_weight_edge` (EDGE, FLOAT, 1.0 on sharp CAD edges), `custom_normal` (CORNER, FLOAT_VECTOR).
  `part.fill_mesh(mesh, verts, tris, tri_face, corner_normals=None, edges=None, edge_ids=None, edge_sharp=None)`.

- [ ] **Step 1: failing tests** (Blender): the default part (box + boss + fillet): mesh closed (every edge two
  faces: `len(mesh.edges) * 2 == sum(len(p.vertices) for p in mesh.polygons)` and no loose edges); `brep_edge_id`
  set on exactly the CAD edges; sharp edges = CAD edges minus the fillet's tangent edges; `bevel_weight_edge` 1.0
  exactly there; `custom_normal` on CORNER; volume in mm³ still matches (`part.mesh_volume`); refilling a mesh that
  has a POINT-domain `custom_normal` leaves only the CORNER one.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `fill_mesh`: as today up to the polygons; `mesh.update()` to build edges; then map
  `edges` pairs to mesh edge indices (`mesh.edges.foreach_get("vertices")` → dict of sorted pairs, or numpy
  lexsort + searchsorted) and set the three edge attributes with `foreach_set`; remove a `custom_normal` whose
  domain isn't CORNER before creating the CORNER one. `apply_result` passes the new arrays. `MESH_FORMAT = 4`.
- [ ] **Step 4:** full `tools/test.sh` → PASS (fix tests that assumed unshared vertices — grep
  `test_*` for `vertices` counts). Commit `Parts: welded meshes with CAD edge attributes (MESH_FORMAT 4)`.

### Task 3: Picking on the evaluated mesh

**Files:**
- Modify: `blendsolid/part.py` (`face_plane`, `curved_face_normal` take the evaluated mesh)
- Modify: `blendsolid/ops_draw.py:285-316` (`pick()`)
- Test: `tests/blender/test_draw_solid.py`

**Interfaces:**
- Produces: `part.face_id(mesh, polygon_index) -> int | None` (from `brep_face_id`, None if missing/invalid);
  `part.face_plane(obj, fid)` now takes a **BRep face id**, not a polygon index; `part.curved_face_normal(mesh,
  matrix_world, polygon_index, location)` reads the evaluated mesh's `corner_normals` (triangles only; else None).
  `pick()` evaluates `obj.evaluated_get(depsgraph).data`.

- [ ] **Step 1: failing tests:** a box part with a Solidify modifier (thickness 5 mm, offset 1): drawing on the
  outer top face picks `box_1`'s top **exact** plane (hit lies on it); a hit on the solidify's inner shell (ray
  from inside the part is awkward — use an Array modifier with relative offset 1.5 in X instead: a hit on the copy's
  top face gives a plane through the hit point, **not** the original face's exact plane moved back); a Bevel
  (weight) modifier: a hit on a flat face still gives the exact plane; a hit on a bevel face (no valid id or not on
  a plane) gives a plane through the hit. The cone test of `test_hovering_around_a_cone_turns_the_grid_smoothly`
  still passes with a Subdivision modifier level 1 on the cone (the curved normal falls back to polygon normals on
  quads: relax to the polygon normal's accuracy, continuity checked only without the modifier).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement:** in `pick()` take `eval_obj = obj.evaluated_get(depsgraph)`, `mesh = eval_obj.data`,
  `fid = part.face_id(mesh, index)`; exact plane only if `fid` is valid, the face is flat and the hit location lies
  on the plane (`abs(n·p_local - d) < 1e-4 mm`); curved normal from the evaluated mesh if the face is curved; drop
  the `not obj.modifiers` guards.
- [ ] **Step 4:** full `tools/test.sh` → PASS. Commit `Draw Solid: pick faces on the evaluated mesh (modifiers)`.

### Task 4: Modifier compatibility tests

**Files:**
- Create: `tests/blender/test_modifiers.py`

- [ ] **Step 1:** tests on the default part (and the cone part) with, one at a time: Bevel (limit Weight, width
  1 mm, segments 3), Weighted Normal, Solidify (2 mm), Mirror (X, with offset via mirror object at x=100 mm), Array
  (count 2, relative offset 1.5), Subdivision Surface (level 1), Triangulate, Edge Split. For each: the evaluated
  mesh has no non-manifold edges where the modifier keeps a closed input closed (all but Edge Split, which splits
  sharp edges on purpose: check it splits exactly the sharp CAD edges); the evaluated volume is the expected one
  (Bevel: smaller than the part by the removed wedges, within the analytic bound; Array/Mirror: twice the part;
  Solidify: shell volume > 0; Triangulate/Weighted Normal/Edge Split: equal); a ray cast on the centre of the top
  face returns a polygon whose `brep_face_id` is the top face's id. Record per modifier what it does to
  `brep_face_id` on new faces (Bevel's faces) in the test's docstring — this is the evidence for ADR 0008.
- [ ] **Step 2:** run; fix what fails in Tasks 1–3's code (not the tests) unless the modifier's own behaviour is
  the cause, then document it in ADR 0008 and assert the documented behaviour.
- [ ] **Step 3:** commit `Tests: parts under Blender modifiers`.

### Task 5: ADR, docs, GUI check hand-off

**Files:**
- Create: `docs/decisions/0008-modifier-compatible-display-mesh.md`
- Modify: `CLAUDE.md` (pitfalls found), `docs/NEXT.md` (state, GUI check steps for the maintainer)

- [ ] **Step 1:** ADR 0008 (context: islands vs modifiers; decision: weld + edge attributes + evaluated picking +
  exact plane only on-plane; consequences: per-modifier findings from Task 4; MESH_FORMAT 4).
- [ ] **Step 2:** `tools/test.sh` full; `tools/gui_check.py` on Linux (WSLg, see CLAUDE.md) → PASS; build the
  Windows zip (install waits for the maintainer to close Blender).
- [ ] **Step 3:** NEXT.md: GUI check steps — add a Bevel modifier (Limit Method: Weight) on a part and see only the
  CAD edges bevelled; Weighted Normal on a part with a fillet; Draw Solid on a part with an Array modifier. Commit
  `Docs: ADR 0008, NEXT.md`.
