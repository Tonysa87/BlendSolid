# Milestone 2 phase B — Provenance and references: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the worker names every face and edge of a canonical part by the feature that made it and its role there,
part scripts can refer to faces and edges with readable helpers (`face("box_1", "+Z")`,
`edge_between(face(...), face(...))`), and every face/edge of a result comes with the reference text a click will
write.

**Architecture:** a new worker module `provenance.py`. The worker compiles canonical scripts through an AST pass
that calls a hook after each `# feature:` statement; the hook reads build123d's per-operation `ShapeHistory` on
the builder's part (spike 1) and relabels the part's faces. Reference helpers injected into the script namespace
resolve labels against the live tracker. After the build, the worker synthesizes each face's and edge's reference
text and sends them with the mesh; Blender stores them on the mesh.

**Tech Stack:** Python 3.13, build123d 0.13 (worker), OCP 8, ast.

**Spec:** `docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md`, section B.

## Global Constraints

- Scripts are millimetres; numbers written with 6 decimals (`near=` points too).
- The script text is never rewritten by the worker; line numbers of errors stay the user's.
- Non-canonical scripts still run (no provenance; layer-3 references only).
- Everything in English; verified with numbers; headless tests.

## Decisions taken while planning (recorded in ADR 0009)

- **Roles are uniform across primitives:** a planar face whose normal is a feature-frame axis is `+X -X +Y -Y +Z
  -Z`; other planar faces `slope`; cylindrical/conical faces `side`; spherical/toroidal `surface`; any other surface
  type its build123d `GeomType` name in lower case. (The design's `top/bottom` for cylinders becomes `+Z/-Z`: one
  vocabulary, and it reads the same for a box and a cylinder.) Faces a feature *generates* from an edge (fillet,
  chamfer) are `blend`.
- **The feature frame** is the rotation of the feature's literal `Location(..., (a, b, c))` (Draw Solid, primitives
  at an angle); features without one use the part frame.
- **Tie-break `near=`** is a point in the part frame (millimetres): the design's feature frame needs every
  feature's location at resolution time for little gain on the corpus's changes; revisit if the criterion test
  shows splits failing on position changes.
- A live cutter's faces (`insert(ref(...))`) get roles computed on the cutter's shape in the part frame.

## Review Focus

1. A face split by a later feature into pieces with the same label, then one piece removed by another feature:
   `near=` must still pick the right survivor (Task 3 test with a slot and a later cut).
2. Faces merged by build123d's `clean()` (coplanar faces of two features): the survivor keeps one label, the
   other label must still resolve to it (Task 1 test: box + coplanar wall).
3. A reference to a feature name that doesn't exist or a role it never had: a clear `BrokenReference` naming the
   feature and role, reported on the calling line (Task 2).
4. Scripts that are not canonical (milestone 1 hand edits, `result = Box(...)`): run exactly as before, no hook,
   texts fall back to `nearest_face`/`nearest_edge` (Task 3).
5. A feature statement that raises (OCCT fillet failure): the error still points at the user's line, not at the
   hook (Task 1).

---

### Task 1: Labels from the history

**Files:** Create `blendsolid/worker/provenance.py`; test `tests/unit/test_provenance.py`.

**Interfaces (produced):**
- `provenance.instrument(source, filename) -> code | None` — compiled code with hook calls
  `__bs_feature__(<name>, <builder>, <rotation degrees tuple>)` after each marked statement of the
  `with BuildPart() as <name>:` body; None if the script has no such block or no markers.
- `class Tracker` with `step(name, part_shape, rotation)`, `labels() -> list[(TopoDS_Face, Label)]`,
  `label_of(face) -> Label | None`, `edge_label(edge) -> tuple[Label, Label] | None` (sorted pair).
- `Label = tuple[str, str]` — `(feature, role)`.

- [ ] Tests: default part: 9 faces, all labels unique, `('box_1', '+Z')`, `('boss_1', 'side')`,
  `('fillet_1', 'blend')` present; the same label set after `box_1_length` 40 → 55; a bracket (box + wall +
  3 holes + fillet on the wall's top edges) all faces labelled, the coplanar wall/box faces resolve to a single
  label each; a slot splitting the top gives two faces labelled `('box_1', '+Z')`; a box rotated with
  `Location((0,0,0), (0, 90, 0))` keeps `+Z` for its own top; a failing fillet raises with the user's line number.
- [ ] Implement (spike code cleaned up): AST pass with `ast.fix_missing_locations` and copied locations so
  tracebacks keep the user's line; the hook reads `builder.part` and its `_history` (`rec._from()` traces), maps
  roles through the inverse feature rotation.
- [ ] Commit `Worker: face provenance from build123d's history`.

### Task 2: Reference helpers in part scripts

**Files:** Modify `blendsolid/worker/provenance.py`, `blendsolid/worker/runner.py` (`_build` injects helpers and
uses `instrument`); test `tests/unit/test_provenance.py`, `tests/unit/test_runner.py`.

**Interfaces (produced):**
- In the script namespace: `face(feature, role=None, near=None) -> ShapeList[Face]`,
  `edge_between(a, b, near=None) -> ShapeList[Edge]`, `edges_of(x) -> ShapeList[Edge]`,
  `nearest_face(point) -> Face`, `nearest_edge(point) -> Edge`. `a`, `b`, `x` are ShapeLists of faces (results of
  `face()`); `role=None` means every face of the feature.
- `provenance.BrokenReference(Exception)`; the runner reports it like any script error (message + line).

- [ ] Tests: `fillet(edge_between(face("box_1", "+Z"), face("box_1", "-Y")), radius=2)` in a canonical script gives
  the same volume as the hand-written build123d selector; `chamfer(edges_of(face("boss_1", "+Z")), length=1)`;
  `face("box_1", "+Q")` → `BrokenReference` "box_1 has no face '+Q'" on that line; `face("nope_1", "+Z")` →
  "no feature 'nope_1' before this line"; `near=` picks one of the two slot-split halves; `nearest_face` works in
  a non-canonical script.
- [ ] Implement; commit `Part scripts: face()/edge_between()/edges_of() references`.

### Task 3: Reference texts for every face and edge

**Files:** Modify `provenance.py` (`reference_texts(tracker, shape) -> (face_texts, edge_texts)`), `runner.py`
(`RunResult.face_refs`, `edge_refs`), `server.py` (in the JSON header), `blendsolid/part.py` (store on the mesh:
`FACE_REFS_KEY`, `EDGE_REFS_KEY`; `part.face_reference(obj, fid)`, `part.edge_reference(obj, eid)`); tests
`tests/unit/test_provenance.py`, `tests/blender/test_parts.py`.

- [ ] Tests: on the default part, the bracket, the slot and a non-canonical script, every face text and every edge
  text, evaluated in a script appended after the last feature (`probe = <text>`), resolves to exactly that
  face/edge (same `TopoDS` IsSame); texts are unique per entity; the Blender mesh carries them after a recompute.
- [ ] Implement synthesis: face → `face("f", "role")` when the label is unique, else with `near=` (its centre,
  6 decimals); edge → `edge_between(face(A), face(B))` when that pair names one edge, else with `near=` (edge
  midpoint); no label → `nearest_face((x, y, z))` / `nearest_edge(...)`. Every text is checked by resolving it
  before it is sent (a text that doesn't resolve uniquely falls back to the next layer).
- [ ] Commit `Worker: reference text for every face and edge`.

### Task 4: ADR 0009

- [ ] `docs/decisions/0009-references-to-faces-and-edges.md`: the grammar, roles, layers, count contract, what is
  deferred (silent re-binding signature: phase E). Commit.
