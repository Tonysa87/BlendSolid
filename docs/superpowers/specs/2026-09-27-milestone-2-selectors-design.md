# Milestone 2 — Selectors from clicks: design

- **Date:** 2026-09-27
- **Status:** decided by the controller (the maintainer asked for choices grounded in research on comparable
  software, not for questions); to be reviewed by the maintainer with the first GUI check.
- **Inputs:** `docs/spec.md` (milestone 2 row, risks), `docs/research/2026-09-27-selectors-and-click-operations.md`
  (Plasticity, Fusion, Onshape, SOLIDWORKS, Shapr3D, MoI, FreeCAD, KCL; persistent naming literature),
  `docs/research/2026-09-26-modeling-workflows.md`, spikes `spike/m2_s01_provenance.py` and
  `spike/m2_s03_fillet_tangent.py` (results below), the maintainer's requirement of 2026-09-27 that parts work with
  Blender modifiers (mixed CAD + modifier workflow).

## Success criterion (from docs/spec.md)

> Starts with face/edge → feature provenance from the worker. 95% of the edges **and faces** clicked on a set of
> 20 parts produce a unique selector that survives 3 upstream changes.

Plus, from this design: **zero silent wrong bindings** — a reference that no longer resolves to what it named must
be reported, never re-bound to another entity without a warning.

## Spike results (2026-09-27, Linux, build123d 0.13.0, OCP 8.0.1)

1. **Provenance from build123d's own per-operation history (PASS).** BuildPart keeps a `ShapeHistory` record
   (OCCT `BRepTools_History`, with the inputs that were there before and the ones brought in) on the part after
   every operation, for `Select.LAST/NEW`. Instrumenting the feature boundaries of a canonical script from the
   worker (an AST pass that calls a hook after each `# feature:` statement; the script text is untouched) labels
   every face with `(feature, role)`: untouched and modified faces keep their label, faces brought in by the feature
   get the feature and their role on the primitive, faces generated from an edge (fillets) get the feature and the
   edge's label. Edges are named by the labels of their two faces.
   - Default part: 9/9 faces and 18/18 edges uniquely labelled; the same labels after `box_1_length` 40 → 55.
   - Bracket with a wall, 3 holes and a fillet: 13/13 faces, 33/33 edges; the same labels after a hole radius and
     the wall height change.
   - A slot splitting the top face: 8/10 faces, 20/24 edges unique — the two halves share `box_1 +Z` (expected:
     splits need a geometric tie-break).
   - Cost: 10–50 ms for the whole script including the build.
2. **Roles** are computed on the primitive's own faces (surface type + outward normal); in the spike in world axes,
   in the design in the feature's frame (a rotated feature keeps its roles).
3. **OCCT's fillet propagates along tangent chains (PASS).** Filleting one straight top edge of a box with rounded
   vertical corners gives exactly the result of filleting all 8 top edges (18 faces, same volume). A tangent chain is
   stored as one seed edge; propagation cannot be turned off in `BRepFilletAPI_MakeFillet`, which matches every
   reference tool's default.
4. **Perturbation cost:** a whole-script rebuild is 10–50 ms on these parts; used by the tests' oracle, not per
   click (see §6).

## Scope

In: (A) a display mesh that works with Blender modifiers and carries edge ids; (B) provenance and readable
references in part scripts; (C) the **Fillet** tool on clicked edges (and faces → their edges), chamfer included;
(D) the **Push/Pull** tool on clicked planar faces; (E) broken-reference detection and reporting; (F) the corpus test
of the success criterion.

Out (later, in this order): Draw Solid attached to a face (the most fragile reference class — FreeCAD's docs advise
against sketching on solid faces; it follows once the corpus proves face references), shell with clicked openings,
repair UI beyond "reselect by redoing the feature" (ghost overlay, suggested repair, Repair All), draft/move face,
variable fillets, STEP import (layer-3 selectors are designed but only exercised by hand-written scripts).

## A. Display mesh compatible with modifiers (ADR 0008)

Today every BRep face is a separate island (vertices duplicated along edges): Blender modifiers such as Bevel,
Weighted Normal or Solidify see only open borders.

- The worker **welds** vertices along BRep edges. Neighbouring faces are already conforming (BRepMesh's edge
  nodes; the structured grids of ADR 0005 take their boundary rings from those nodes), so the weld is exact: it
  merges coincident boundary vertices within 1e-6 of the model size, and a test checks that the welded mesh is
  closed (every edge has two faces) on every test part.
- **Edge data:** an EDGE-domain `brep_edge_id` attribute (the index in the result's edge map, -1 for a mesh edge
  inside a face), `sharp_edge` = True and `bevel_weight_edge` = 1.0 on edges between two different BRep faces whose
  normals differ (a seam of a cylinder is not sharp). With Bevel's *Limit Method: Weight* only the CAD edges bevel.
- **Normals:** the exact surface normals move from the POINT domain to the CORNER domain (`custom_normal`), since a
  welded vertex on a sharp edge has one normal per face.
- **Picking reads the evaluated mesh.** Ray casts return polygon indices of the evaluated mesh; tools read
  `brep_face_id`/`brep_edge_id` and normals from `obj.evaluated_get(depsgraph).data`, not `obj.data`. Blender
  propagates attributes through modifiers; where a modifier makes new faces (Bevel's bevel faces, Solidify's rims)
  the value it propagates is checked by the tests, and a face without a valid id is "not a CAD face" (tools draw on
  it as on a foreign mesh, as today). The exact-plane shortcut (`part.face_plane`) is used only when the hit
  polygon's face id is valid and the modifier stack doesn't move geometry (no modifiers, or only modifiers from an
  allow-list that keep positions: Weighted Normal, Bevel/Solidify/Mirror/Array faces that carry the original id and
  lie on the original plane — decided by a test per modifier, not assumed).
- **Tests (headless):** for each of Bevel (weight), Weighted Normal, Solidify, Mirror, Array, Subdivision Surface,
  Triangulate, Edge Split: the evaluated mesh is manifold where the modifier keeps it so, counts and volume match the
  expectation, and a ray cast on a CAD face resolves to the right BRep face id.
- Mesh format bump (`part.MESH_FORMAT` 4): saved parts recompute their meshes once.

## B. Provenance and references (ADR 0009)

### Provenance in the worker

- The worker compiles a canonical script through an AST pass that inserts a hook call after each feature
  statement of the `with BuildPart()` body (line numbers kept, so errors still point at the user's line). Non-canonical
  scripts run without the hook (no provenance; layer-3 references only).
- After each feature the hook labels the part's faces from the part's `ShapeHistory` record:

  | Face of the current part | Label |
  | --- | --- |
  | untouched / modified from a face that was there before | that face's label |
  | untouched / modified from a face the feature brought in | `(feature, role of that face on the feature)` |
  | generated from an edge that was there before (fillet, chamfer) | `(feature, "edge", label of that edge)` |
  | generated from a face the feature brought in (extrude sides) | `(feature, role)` |
  | no record, or none of the above | `(feature, "new")` — counted as unlabelled |

- **Roles** are computed on the brought-in shape in the feature's own frame (the inverse of the feature's
  `Location`, known from the script model): Box `+X -X +Y -Y +Z -Z`; Cylinder and Cone `top bottom side`; Sphere
  `surface`; Torus `surface`; Wedge `bottom top front back left slope` (part axes of the M1.5 wedge); a live cutter's
  `insert(ref(...))` faces take `ref:<cutter feature>:<cutter role>` from the cutter part's own labels; an extrude
  (push/pull) `end start side`. When unification merges faces the surviving face keeps one label (OCCT reports the
  others as modified into it); both labels resolve to it.
- **Edges** are named by the labels of their two faces (unordered). When two faces share several edges (e.g. a
  slot's floor and a side both split), the tie-break is geometric (below).
- The worker returns per BRep face and per BRep edge its **reference text** (layer 1 when unique, layer 2 when a
  tie-break is needed, layer 3 without provenance), so a click needs no round trip.

### The reference grammar (in the part script)

Helpers injected into the script namespace like `ref()`, resolved against the live labels at that point of the
script (a reference can only name what exists before its feature):

```python
fillet(edge_between(face("box_1", "+Z"), face("box_1", "-Y")), radius=fillet_1_radius)  # feature: fillet_1
chamfer(edges_of(face("boss_1", "top")), length=chamfer_1_length)                    # feature: chamfer_1
extrude(face("cut_1", "bottom"), amount=push_1_amount, mode=Mode.SUBTRACT)           # feature: push_1
fillet(edge_between(face("box_1", "+Z"), face("slot_1", "+X"), near=(4.0, 12.0, 20.0)), radius=r)
fillet(nearest_edge((12.0, 0.0, 20.0)), radius=r)                                     # layer 3
```

- `face(feature, role)` → the faces labelled so. `edge_between(a, b)` → the edges shared by the faces of `a` and
  `b`. `edges_of(x)` → all edges of the faces of `x` (Fusion "All Edges", FreeCAD "Use All Edges": the intent is
  stored, not the expanded list). `near=(x, y, z)` (millimetres, **feature frame of the first face's feature**)
  keeps the one entity whose centre is closest — used only when the label matches several entities.
- Several references in one call: `fillet(edge_between(...), edge_between(...), radius=...)`.
- **Count contract:** `face`/`edge_between` without `near=` must match ≥ 1 entity, with `near=` exactly 1; an empty
  match raises `BrokenReference("fillet_1: no edge between box_1 +Z and slot_1 +X any more")` (not Python's own `ReferenceError`, which is about weak references), which the worker
  reports on the feature's line like any script error. A multi-reference call where some references still match
  and others don't computes on the matching ones and reports a **warning** (Fusion's model); none left → error.
- **Silent re-binding check:** the worker stores, outside the script (the part's mesh data, next to the face planes),
  a signature of each reference's last good match (type, count, total length/area, centre); after a recompute a
  match whose signature moved by more than the change of the parameters explains is reported as a warning
  ("fillet_1: the edge it rounds changed shape"). The threshold is calibrated on the corpus.
- Numbers in references follow the scripts' rules (6 decimals; `near=` points are tie-breaks, not placements).

## C. Fillet tool (ADR 0009 for the UX choices)

Reference: Plasticity (edge selection runs Fillet; negative distance = chamfer; T toggles tangent edges; Ctrl
adds/removes during the command), Fusion (edges, faces or features; tangent chain on by default), Blender's own
conventions (Alt+click loops, Shift+click extends).

- A `WorkSpaceTool` **Fillet** next to Draw Solid (Object mode). Hover draws the BRep edge under the mouse and the
  tangent chain it would bring (edge picking: ray cast on the evaluated mesh, then the nearest CAD edge of the hit
  face within a few pixels, the same ring of rays as `ops_draw.pick(near=...)` for silhouettes).
- Click selects an edge (its chain); Shift+click adds/removes; click on a face's interior selects all its edges
  (`edges_of(face(...))`). Selection is shown as an overlay, per part (one part at a time).
- **Drag** from a selected edge sets the radius (distance of the mouse from the edge on screen, converted at the
  edge's depth); Ctrl snaps to the Draw Solid step (Ctrl+Wheel), typed numbers work (Blender's `NumInput`), C toggles
  chamfer (a negative typed value is a chamfer too, as in Plasticity), Enter/release commits, Esc/right-click cancels.
  Tangent propagation is always on (OCCT's builder can't turn it off; §spike 3); the hover shows the chain.
- Commit appends one feature (`fillet_N` / `chamfer_N`, radius/length parameter, one undo step, one script edit).
  The parameter gets an arrow gizmo on the rounded edge (like the primitives' arrows) and a panel field.
- A fillet that OCCT can't build (radius too large) is an error on its line, as today; the drag preview is the
  worker's result (throttled, latest value wins) — no approximate client-side preview.

## D. Push/Pull tool

Reference: Plasticity Push Face, Fusion Press Pull, SketchUp, Onshape Move Face (offset).

- A `WorkSpaceTool` **Push/Pull**: hover highlights the planar CAD face under the mouse; drag along its normal —
  out adds (`mode=Mode.ADD`), in cuts (`Mode.SUBTRACT`), like Draw Solid's height; Ctrl snaps; typed numbers.
- Commit appends `extrude(face("<feature>", "<role>"), amount=push_N_amount, mode=...)` (`push_N`). Non-planar
  faces are refused with a message (offset of curved faces is v2).
- A click on a face that is the cap of a primitive whose parameter controls it (e.g. `box_1 +Z` ↔
  `box_1_height`) already has an arrow gizmo when the part is selected; the tool does not duplicate it.

## E. Broken references

- States (Fusion): **warning** (the feature computed on part of its references, or a match changed shape), shown
  in the BlendSolid panel next to the feature with the message; **error** (nothing matched, or OCCT failed) — the
  part keeps its last good mesh and shows the error, as today.
- Repair in milestone 2: the panel names the feature and the reference; the user undoes the upstream change, or
  removes the feature (Remove Feature, already available for cuts), or redoes it with the tool. Ghost overlay,
  suggested repair and Repair All are follow-ups (research §3.4).

## F. The success criterion test

- **Corpus:** 20 canonical parts built by the tools' own operators (not hand-written scripts): the M1 default part,
  the M1.5 bracket with 3 holes, boxes with fillets/chamfers on edges and on chains, parts with bosses in symmetric
  patterns, a slot splitting a face, a wedge with a chamfer, a cylinder with a push/pull, a part with a live cutter,
  rotated features, cones and tori with fillets where OCCT can build them.
- **Clicks:** every face and every CAD edge of every corpus part (hundreds of entities) → the worker's reference.
  Uniqueness: the reference resolves to exactly the clicked entity.
- **3 upstream changes per part**, applied to parameters of features *before* the entity's own: (1) a dimension
  change of ±20%, (2) a second dimension change, (3) a position change of a feature (`Location`), plus separately
  (4) inserting an unrelated feature upstream. Oracle, independent of the labels: **continuation tracking** — the
  change is applied in 20 small steps and each entity is followed from step to step by nearest geometry (type,
  centre, normal/axis, size); for the insertion, geometric identity of entities the inserted feature doesn't touch.
- **Metric:** share of entities whose reference, after the 3 changes, resolves to the oracle's entity ≥ 95%, and
  zero cases where it resolves to a different entity without an error or warning. Reported per corpus part in the
  milestone report.

## Architecture changes (files)

- `blendsolid/worker/provenance.py` (new, worker side): AST instrumentation, labels, roles, reference helpers,
  reference texts, signatures.
- `blendsolid/worker/tessellate.py`: weld, edge ids, sharp/bevel-weight edges, corner normals.
- `blendsolid/worker/runner.py`: provenance-aware build, new result fields (edge ids, per-face/edge reference
  texts, warnings).
- `blendsolid/part.py`: fill the welded mesh and edge attributes; evaluated-mesh lookups; MESH_FORMAT 4.
- `blendsolid/picking.py` (new, Blender side): face/edge picking on the evaluated mesh shared by the tools
  (moves the ray-casting helpers out of `ops_draw.py`).
- `blendsolid/ops_fillet.py`, `blendsolid/ops_pushpull.py` (new): the two tools.
- `blendsolid/script_model.py`: fillet/chamfer/push features (kinds, parameters, feature specs).
- `blendsolid/ui.py`: warnings per feature.

## Order of work

1. A — welded, modifier-compatible mesh with edge ids and evaluated-mesh picking (independent of the rest;
   ships the maintainer's modifier requirement first).
2. B — provenance and references in the worker, with unit tests on the spike's parts.
3. C — Fillet tool.
4. D — Push/Pull tool.
5. E — warnings and reporting.
6. F — corpus and criterion test; milestone report; GUI check with the maintainer.
