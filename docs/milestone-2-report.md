# Milestone 2 report — Selectors from clicks

## Success criterion

From `docs/spec.md`'s milestone table, verbatim:

> Starts with face/edge → feature provenance from the worker. 95% of the edges **and faces** clicked on a set of
> 20 parts produce a unique selector that survives 3 upstream changes.

Plus, from the design (`docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md`): **zero silent wrong
bindings** — a reference that no longer names what it named is reported (error or warning), never re-bound.

**Met by automated evidence** (`tests/unit/test_criterion.py`, harness `tests/unit/criterion.py`, parts
`tests/unit/criterion_corpus.py`), 2026-09-28:

| Measure | Result |
|---|---|
| Parts | 20, built with the tools' own feature specs (primitives, Draw Solid union/cut, Fillet/Chamfer on clicked edges and faces, Push/Pull on clicked faces) |
| Clicked entities | 559 faces and CAD edges (seams excluded: they are not clickable) |
| Unique at click time | 559 / 559 |
| Survive 3 upstream changes | **543 / 559 = 97.1%** (oracle lost 9 entities, left out) |
| Survive an unrelated feature inserted upstream | **548 / 548 = 100%** |
| Silent wrong bindings | **0** |

- **Changes:** per part, three parameters or placements of early features changed by ±20% (dimensions of the
  base solid, a boss radius, a fillet radius, a push amount) or a feature moved by a few mm, one after the other.
- **Oracle, independent of the labels:** continuation tracking. Each change goes in 20 steps; every entity is
  followed from step to step by nearest geometry (same kind and surface/curve type, centre, direction, size).
  An entity whose best match isn't clearly better than the runner-up, or jumps, is "lost" and excluded. For the
  insert: entities with identical geometry before and after.
- **Scored:** "ok" = the reference resolves to exactly the oracle's entity without warning; "flagged" = error or
  warning (not silent); "wrong" = another entity without warning (silent: must be 0).
- **The 16 flagged references** are all correct reports: faces split by a change (a wall or step that no longer
  reaches the base's edge splits the base's top face: bracket, step, L-shape; the reference now names 2 faces and
  says so), and the corner edges of a fillet on a tangent chain whose recorded point no longer tells two
  candidates apart (the warning is right: the resolution would be the other edge).

Found and fixed by this test: the role of a cut's face depended on whether OCCT left the face untouched or
rebuilt it (a subtraction reverses untouched faces): a slot's walls swapped +X/−X after a width change, 8 silent
wrong bindings. Roles now always use the face as it is in the feature's own solid (ADR 0009 addendum).

## What was built (phases A–F)

- **A. Display mesh compatible with modifiers** (ADR 0008 + addendum): welded, closed meshes; flat faces as one
  polygon, or convex pieces with collars of radial quads around curved holes; CAD edges carry `brep_edge_id`,
  `sharp_edge`, `bevel_weight_edge`; exact corner normals; picking on the evaluated mesh. Checked by the maintainer
  with Bevel, Solidify, Array, Subdivision, Weighted Normal. Session 8: collars without Subdivision folds (a merge
  rule on Catmull–Clark face points, narrower collars; a Catmull–Clark simulation in the unit tests).
- **Tessellation** (ADR 0010): edge-first, grid-based meshing of trimmed faces; fuzzed.
- **B. Provenance and references** (ADR 0009): labels `(feature, role)` from build123d's per-operation history;
  `face()`, `edge_between()`, `edges_of()`, `nearest_*()` in part scripts; a reference text per face and edge.
- **C. Fillet tool:** click edges or a face, drag the radius, C for chamfer, Ctrl snap; one undo step.
  Session 8: errors that give the largest working size, name seams/tangent/free edges and slivers, and say
  "another face is in the way" when the working sizes aren't an interval; tangent edges refused on click; the drag
  header shows the error (research `docs/research/2026-09-28-fillet-edge-cases.md`, tests T1–T23).
- **D. Push/Pull tool** on flat faces.
- **E. Broken references:** errors on the feature's line (a reference naming nothing); warnings (a split face or
  edge behind a plain reference, an ambiguous `near=`) shown in the sidebar as "Check these references".
- **F.** The success criterion test above.
- **UX (maintainer's request, ADR 0011):** the arrows of one focused feature per part, only on an active, selected,
  visible part; clicking a face focuses the feature that made it; cutters of live booleans put away in a hidden
  collection, parented to their target.

## Automated tests

- `tools/test.sh`: 281 unit tests (Blender's Python, no bpy) + 227 Blender tests (`blender -b`), all passing.
- `tools/gui_check.py`: 21 steps in a real window, PASS on Linux (WSLg) and on the Windows portable Blender.
- Fuzz of the tessellation (`spike/m2_flat_faces/fuzz_valid.py`): 7 seeds, no BRepMesh fallback, closed, < 0.35 s.

## Maintainer's GUI check (2026-09-28 evening)

Tests 1–4 passed on the Windows portable Blender (focused arrows, hidden cutters, collars + Bevel, fillet
messages), after fixing the focus click with the Tweak tool and the sidebar redraw; the collar wedges were
reduced (face-point rule 20° → 10°; Subdivision goes on convert-to-quads). Test 5 (reference warnings), session 9:
a Fillet on a box's top face, then a cut lengthened through the box splits the face — "Check these references"
appears, both halves stay rounded, Ctrl+Z clears it: passed.

**Signed off by the maintainer on 2026-09-28**; `milestone-2` merged into `main`.

## Known limits / follow-ups

- A hole within a few mm of a straight edge leaves a thin strip of fans on that flat face (no vertex may be added
  on a BRep edge).
- Split faces: the reference uses all pieces, with a warning; no automatic choice of the continuing piece.
- Fillet errors don't highlight the failing edges in the viewport yet; no geometric radius bound with a reason
  ("the fillets would meet across the 30 mm face") — the research lists both.
- Repair of broken references is manual (undo, remove the feature, redo it with the tool); ghost overlay and
  suggested repairs are follow-ups.
- The tools' on-screen feedback (yellow handle, preview) is to be redesigned (maintainer).
