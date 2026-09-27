# Milestone 2 phase C — Fillet tool: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a toolbar tool that fillets (or chamfers) clicked CAD edges of a part, writing one readable feature,
e.g. `fillet(edge_between(face("box_1", "+Z"), face("box_1", "-Y")), radius=fillet_1_radius)`.

**Architecture:** `blendsolid/picking.py` finds the CAD edge or face under the mouse (ray cast on the evaluated
mesh for the face; the part's own mesh edges carrying `brep_edge_id` for the edges around it, nearest on screen).
`blendsolid/ops_fillet.py` holds the `blendsolid.fillet` operator (execute appends the feature; redo edits it), the
tool's click/drag modal, the hover/selection overlay and the WorkSpaceTool. The selection is kept as reference
texts (they survive recomputes; ids don't).

**Spec:** `docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md`, section C.

## Global Constraints
- One feature per commit of the tool, one undo step, one script edit; the drag preview edits the script without
  undo and is replaced by the operator's own edit on release.
- Tangent propagation is always on (OCCT); negative radius is not used: `C` toggles chamfer (a typed negative value
  is not supported in this version).
- Everything in English; numbers in tests.

## Review Focus
1. Clicking an edge of a part whose script isn't canonical, or an untrusted/linked/scaled part: refused with the
   same messages as Draw Solid (operator test).
2. A selection that no longer resolves after an upstream change (undo in the middle): drawn only for the references
   still present; committing with none left does nothing (operator test with an empty reference list).
3. Fillet radius too large for OCCT: the part shows the worker's error on the fillet line; undo removes it (test).
4. Parts with a Bevel modifier: picking still finds the CAD edges (original mesh edges) (picking test).
5. Several parts: a selection belongs to one part; clicking another part starts a new selection (modal logic).

### Task 1: picking
- `picking.pick(context, coord) -> Pick | None` with `Pick(obj, kind: "EDGE"|"FACE", id, reference, polylines)`:
  ray (the ring of near rays too) → part hit → face id (evaluated mesh) → the CAD edges of that face (original
  mesh) → the nearest on screen within `EDGE_PX` (10 px × UI scale) is an EDGE pick, else the FACE pick
  (`edges_of(<face reference>)`). Parts without reference texts give None.
- `picking.edge_polylines(obj, eid)` (world segments) and `picking.face_edge_ids(obj, fid)`; a per-mesh cache keyed
  by the mesh tag.
- Tests (Blender): default part: a ray at the top face 0.3 mm from the -Y edge → EDGE with
  `edge_between(face("box_1", "+Z"), face("box_1", "-Y"))`; at the top face's middle → FACE with
  `edges_of(face("box_1", "+Z"))`; the same with a Bevel modifier on the part.

### Task 2: the fillet operator
- `blendsolid.fillet` (REGISTER, UNDO): `target`, `references` (newline-separated), `radius` (mm), `chamfer` (bool);
  execute appends `fillet(<refs joined by " + ">, radius=fillet_N_radius)` or
  `chamfer(..., length=chamfer_N_length)`; the part's error handling as Draw Solid.
- Tests: fillet on the default part's box top -Y edge r = 2 → volume − (1 − π/4)·4·40 within tolerance; after
  `box_1_length` 40 → 60 the same edge is still filleted (volume − (1 − π/4)·4·60); chamfer 2 → −2·40; the face
  selection `edges_of(face("boss_1", "+Z"))` → the boss top rounded; radius 50 → error on that line.

### Task 3: the tool
- WorkSpaceTool "Fillet" after Draw Solid; hover overlay (the edge, or the face's edges, under the mouse) from a
  gizmo like the snap marker; selected edges drawn in the selection colour.
- Click: select (Shift+click toggles/extends; a click on another part starts over; a click on nothing clears).
  Press on the part and drag: radius = on-screen distance × pixel size at the press point; Ctrl snaps to the Draw
  Solid step; `C` toggles chamfer; the script is edited live for the preview; release commits through
  `blendsolid.fillet` (one undo step); Esc/right-click cancels and restores the script.
- `tools/gui_check.py` step 18 with simulated events: click an edge, drag → one fillet feature, volume as expected.
