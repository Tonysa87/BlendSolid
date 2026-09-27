# ADR 0009 — Naming faces and edges in part scripts

- **Status:** accepted
- **Date:** 2026-09-27
- **Context from:** milestone 2 design (`docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md`,
  section B), research `docs/research/2026-09-27-selectors-and-click-operations.md`, spike
  `spike/m2_s01_provenance.py`

## Context

Milestone 2's tools write operations on clicked faces and edges (fillet, push/pull) into the part script. The
reference must be a line of Python a user can read, and it must keep naming the same face or edge when upstream
parameters change (the topological naming problem). build123d's own selectors (`filter_by`, `sort_by`, indices)
are readable but break silently on upstream changes; OCCT's history is robust but not readable. Onshape, Fusion and
the persistent-naming literature (Kripac; Bidarra) name entities by the feature that made them and their role on it,
mapped forward through the history.

## Decision

1. **Provenance from build123d's history.** The worker runs a canonical script with a hook after each
   `# feature:` statement (an AST pass; the script text is unchanged, errors keep the user's lines). The hook
   relabels the part's faces from the `ShapeHistory` build123d keeps after every BuildPart operation: faces left or
   modified keep their label; faces the feature brought in get `(feature, role)`; faces generated from an edge
   (fillet, chamfer) `(feature, "blend")`.
2. **Roles** are uniform across primitives, in the feature's frame (the rotation of its literal `Location`):
   `+X -X +Y -Y +Z -Z` for planar faces along a frame axis, `slope` for other planar faces, `side` for cylinders
   and cones, `surface` for spheres and tori, `blend` for faces generated from edges. One vocabulary reads the same
   for a box and a cylinder (`face("boss_1", "+Z")` is the boss's top).
3. **The grammar** (helpers in the script namespace, like `ref()`):
   - `face(feature, role=None, near=None)` → the faces with that label; `edge_between(a, b, near=None)` → the edges
     shared by faces of `a` and `b`; `edges_of(faces)` → all their edges; `nearest_face(point, shape=None)`,
     `nearest_edge(point, shape=None)` → layer 3, geometry only.
   - `near=(x, y, z)` (millimetres, part frame) keeps the entity whose **centre** is closest — the tie-break when a
     label names several entities (a face split by a slot, the holes of a pattern).
4. **Count contract:** a reference that matches nothing raises `BrokenReference` with what is missing
   ("box_1 has no face '+Q'", "no edge between box_1 +Z and box_1 -Z", "no feature 'nope_1' before this line"),
   reported on the script line like any error.
5. **Reference texts.** The worker sends, with each result, the text a click on each face and edge writes:
   `face("f", "role")`, `edge_between(face(A), face(B))`, with `near=` when needed, `nearest_*()` without
   provenance, `""` for seams and degenerate edges. They are built by the same rules the helpers apply (not by
   evaluating them), and the tests resolve every text of every test part back to its own entity. Blender stores
   them on the mesh (`bs_face_refs`, `bs_edge_refs`). Scripts without features (the tools don't edit them) get none.

## Consequences

- Measured: every face and edge of the default part, a bracket with a wall, holes and a fillet, a slot splitting a
  face and a rotated boss has a unique reference that resolves to it; labels are identical after upstream
  dimension changes. 0.1 s for a part with 169 holes.
- `near=` in the part frame can pick the wrong piece if an upstream change moves pieces past each other; the
  criterion test (phase F) measures it. A feature-frame `near=` is the fallback plan.
- Deferred to phase E: the signature of a reference's last good match (to catch silent re-binding), warnings for
  multi-reference features that lose part of their references.
- A live cutter's faces get roles computed on the cutter in the part frame, not the cutter's own labels.
