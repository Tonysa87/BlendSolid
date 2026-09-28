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
  with Bevel, Solidify, Array, Subdivision, Weighted Normal. Session 8: narrower collars and a merge rule on
  Catmull–Clark face points (10° after the maintainer's review); the display mesh no longer aims to be
  Subdivision-ready (that belongs to a future "convert to quads"), so the Subdivision fold tests were removed.
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

- `tools/test.sh`: 276 unit tests (Blender's Python, no bpy) + 227 Blender tests (`blender -b`), all passing.
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
  on a BRep edge); arcs in a flat face's outer loop (a boss or hole cutting a corner or an edge) still fan to one
  far point (next step: partial collars).
- Split faces: the reference uses all pieces, with a warning; no automatic choice of the continuing piece.
- Fillet errors don't highlight the failing edges in the viewport yet; no geometric radius bound with a reason
  ("the fillets would meet across the 30 mm face") — the research lists both.
- Repair of broken references is manual (undo, remove the feature, redo it with the tool); ghost overlay and
  suggested repairs are follow-ups.
- The tools' on-screen feedback (yellow handle, preview) is to be redesigned (maintainer).
- Promised by the design (`docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md`) but not built:
  - the **signature check against silent re-binding** (a stored signature of each reference's last good match,
    warning when it moves more than the parameter change explains); the criterion test found 0 silent wrong
    bindings without it, after the role fix above;
  - the **warning + partial compute** when only some references of a multi-reference feature resolve: a reference
    that names nothing is still a `BrokenReference` error on the feature's line;
  - **typed numbers** (Blender's `NumInput`) while dragging in the Fillet and Push/Pull tools.
- The worker's `blends.chamfer` already takes `length2`/`angle`/`reference`; the Fillet tool only writes
  equal-distance chamfers (two distances or distance + angle: tool UI only).
- Scratch tools kept in `spike/`: `m2_criterion/debug.py` (why a corpus part's references fail or are flagged)
  and `m2_fillets/probe.py` (what OCCT does on typical fillet edge cases).

## History

- **Research and design (2026-09-27):** `docs/research/2026-09-27-selectors-and-click-operations.md` (Plasticity,
  Fusion, Onshape, SOLIDWORKS, Shapr3D, MoI, FreeCAD, KCL; persistent naming); design decided autonomously from
  it (the maintainer asked for no questions). Spikes: provenance from build123d's per-operation history names
  every face/edge of the test parts uniquely and stays stable across upstream changes (splits need a
  tie-break); OCCT fillets propagate along tangent chains. Plans: `docs/superpowers/plans/2026-09-27-m2{a,b,c}-*.md`.
- **Phase A** (2026-09-27): 190 unit + 192 Blender tests, `gui_check` 16/16. Checked by the maintainer on
  Windows: quads/n-gons in the wireframe, Bevel by weight rounds exactly the CAD edges (parameters still
  draggable), Solidify/Array/Subdivision/Weighted Normal work. Draw Solid on a beveled part became `gui_check`
  step 17. **Phase B** (worker side) had nothing to see in the GUI.
- **Phases C–D** (2026-09-27): `picking.py`, `ops_fillet.py` (`blendsolid.fillet`), `ops_pushpull.py`
  (`blendsolid.push_pull`, writes `extrude(face("box_1", "+X"), amount=push_1_amount, mode=Mode.ADD)`);
  `gui_check` 19/19, 215 unit + 206 Blender tests. Checked by the maintainer on Windows the same evening; after
  their feedback the drag got faster (edit → mesh 106 → 59 ms: `runtime.kick()` and 10 ms polling while busy),
  gained an immediate overlay preview, a drag handle and Draw Solid's snapping (ticks, labels, Ctrl+Wheel).
- **Fillet-face slivers** (maintainer's bug, 2026-09-27 evening): a first fix (ADR 0005 addendum, Delaunay
  lattice) still looked like a mosaic. **Session 6** (2026-09-28): CAD-style tessellation (ADR 0010, research
  `docs/research/2026-09-28-*.md`); the maintainer set the scope (display meshes follow CAD conventions,
  triangles; a later "convert to quads"). `MESH_FORMAT` 6. The maintainer's first GUI test hung the worker
  (1000 mm box, cylinder cut on an edge, Fillet drag): fuzzing found curvature spikes on OCCT's vertex blends,
  unbounded density, endless side matching, quadratic boundary recovery and broken OCCT fillet results; fixed
  (ADR 0010 addendum), over 1,000 fuzzed parts all under 1.5 s and closed. **Session 7:** the maintainer found the
  fillet bands/columns very good and the hang scenario fast, then pointed at fans of slivers on flat faces with
  holes.
- **Session 8** (2026-09-28): collars around curved holes (ADR 0008 addendum, `MESH_FORMAT` 7; research
  `docs/research/2026-09-28-planar-faces-with-holes.md`); focused handles and hidden cutters (ADR 0011, research
  `docs/research/2026-09-28-handles-and-tool-bodies.md`, `gui_check` 21/21 on Linux and Windows); fillet edge
  cases (`worker/blends.py`, ~60 measured cases, tests T1–T23); phase E warnings (ADR 0009 addendum); phase F
  criterion test.
- **Maintainer's GUI check** (session 8 evening, above): the Tweak-tool focus click and the sidebar redraw were
  fixed during test 1; in test 3 (`/mnt/e/bs_debug/test2.blend`) the face-point rule went from 20° to 10° (the
  least that keeps Bevel 2 mm fold-free; `MESH_FORMAT` 8) and Subdivision moved to convert-to-quads. Also seen
  there: a Draw Solid cut placed at z = 1000 mm floats above a box later made 257 mm tall (fixed placements
  don't follow upstream changes, a known milestone 1.5 limit).
