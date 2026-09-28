# Where we are / what's next (bookmark)

Updated: 2026-09-28, end of session 8: **milestone 2 complete, waiting for the maintainer's GUI check and
sign-off** (`docs/milestone-2-report.md`). Read this first when resuming, then "Session 8".

## State
- **Milestone 0 (spike):** done — `SPIKE_REPORT.md`.
- **Milestone 1 (history as code):** done — `docs/milestone-1-report.md`.
- **Milestone 1.5 (build without selectors):** **done, signed off by the maintainer on 2026-09-27** —
  `docs/milestone-1.5-report.md` (manual GUI test 16/16, then the snap guides checked in the Windows viewport:
  empty space, top/side/cylindrical faces, Ctrl+Wheel step, zoom fading, drag labels, cursor rotated 40°; no
  tuning asked). The Windows 0.2.0 zip installed in the portable Blender is `main`'s code.
- The SDD ledger's two useful files are archived in `docs/milestone-1.5/` (`sdd-ledger.md`,
  `gui-check-report.md`); the git-ignored `.superpowers/sdd/` folder is deleted by the maintainer by hand.

## Milestone 2 (selectors from clicks) — in progress, branch `milestone-2`
- Research: `docs/research/2026-09-27-selectors-and-click-operations.md` (Plasticity, Fusion, Onshape, SOLIDWORKS,
  Shapr3D, MoI, FreeCAD, KCL; persistent naming). Design (decided autonomously from the research, the maintainer
  asked for no questions): `docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md` — phases A (mesh
  compatible with modifiers), B (provenance + readable references `face("box_1", "+Z")`, `edge_between(...)`),
  C (Fillet tool on clicked edges), D (Push/Pull tool), E (broken references), F (20-part corpus criterion test).
  Spikes: provenance from build123d's per-operation history works (all faces/edges of the test parts uniquely
  named, stable across upstream changes; splits need a tie-break); OCCT fillets propagate along tangent chains.
- **Phase A done** (plan `docs/superpowers/plans/2026-09-27-m2a-modifier-compatible-mesh.md`, ADR 0008): welded
  closed meshes, flat faces as one polygon / convex polygons around holes, CAD edges with `brep_edge_id`,
  `sharp_edge`, `bevel_weight_edge`, exact corner normals, picking on the evaluated mesh. 190 unit + 192 Blender
  tests pass; `tools/gui_check.py` PASS on Linux (16/16). **Checked by the maintainer on Windows (2026-09-27):**
  quads/n-gons in the wireframe, Bevel by weight rounds exactly the CAD edges (parameters still draggable),
  Solidify/Array/Subdivision/Weighted Normal work. Draw Solid on a beveled part (the maintainer couldn't check
  it) is `gui_check` step 17, PASS on Linux and in the real Windows window. Review findings fixed.
- **Phase B (worker side) done** (plan `docs/superpowers/plans/2026-09-27-m2b-provenance-and-references.md`,
  ADR 0009): labels from build123d's history, `face()/edge_between()/edges_of()/nearest_*()` in part scripts,
  a reference text per face and edge on the mesh. Nothing to see in the GUI yet.

- **Phase C done** (plan `docs/superpowers/plans/2026-09-27-m2c-fillet-tool.md`): `blendsolid/picking.py` (the CAD
  edge or face under the mouse, through modifiers), `blendsolid/ops_fillet.py` (the `blendsolid.fillet` operator
  and the **Fillet** toolbar tool: click edges, Shift+click to add, click a face for all its edges, drag the
  radius, C chamfer, Ctrl snap, one undo step). `gui_check` 18/18 PASS on Linux (step 18: two edges picked by
  reference, dragged, undone). The Windows zip with the tool is built (`dist/`) but **not installed**: the
  maintainer's Blender was open.

- **Phase D done:** `blendsolid/ops_pushpull.py` (the `blendsolid.push_pull` operator and the **Push/Pull** tool:
  press on a flat face, drag along its normal, out adds / in cuts, Ctrl snaps; writes
  `extrude(face("box_1", "+X"), amount=push_1_amount, mode=Mode.ADD)`). `gui_check` 19/19 PASS on Linux;
  215 unit + 206 Blender tests pass. The Windows zip in `dist/` has phases A–D; **not installed yet**.

- **Fillet and Push/Pull checked by the maintainer on Windows (2026-09-27 evening):** they work; after their
  feedback the drag got faster (edit → mesh 106 → 59 ms: `runtime.kick()` and 10 ms polling while busy), an
  immediate overlay preview, a drag handle and Draw Solid's snapping (ticks, labels, Ctrl+Wheel). **The maintainer
  doesn't like the yellow arrow and the preview's look**: to redo in a dedicated UX redesign (not now).

- **Maintainer's bug, 2026-09-27 evening:** fans of slivers on fillet faces (`/mnt/e/bs_debug/fillet.blend`). A first
  fix (ADR 0005 addendum, Delaunay lattice) still looked like a mosaic to the maintainer ("topologia pessima").

- **Session 6 (2026-09-28): CAD-style tessellation, ADR 0010.** Researched how Rhino, MoI, ACIS, Parasolid, SALOME
  and Gmsh mesh trimmed faces (`docs/research/2026-09-28-*.md`); the maintainer set the scope: display meshes
  follow CAD conventions (triangles), a later "convert to quads" button for CAD parts and NURBS surfaces.
  `blendsolid/worker/meshing.py`: every edge discretized once and shared; four-sided curved faces as structured
  grids with matched opposite sides (fillet bands in rows, trimmed cylinders in aligned columns); other curved
  faces as grids trimmed by their boundary; flat faces from their boundary; BRepMesh only as a loud fallback.
  `MESH_FORMAT` 6. The maintainer's first GUI test **hung the worker** (1000 mm box, cylinder cut on an edge,
  Fillet drag): fuzzing found curvature spikes on OCCT's vertex blends, unbounded density and endless side
  matching, quadratic boundary recovery and broken OCCT fillet results (now a clear part error); fixed (ADR 0010
  addendum) with regression tests; over 1,000 fuzzed parts all under 1.5 s and closed. 233 unit + 210 Blender tests and `gui_check` (20/20, Linux) pass. Windows zip built and installed. **Checked by the maintainer
  on Windows (2026-09-28, session 7):** fillet.blend's bands/columns "ottimi"; the scenario that hung (1000 mm box,
  cylinder cut on an edge, Fillet drag) is fast and correct. They then pointed at the fans of slivers on flat faces
  with holes (ADR 0008's convex pieces, e.g. boolean holes of cylinders): to improve (research
  `docs/research/2026-09-28-planar-faces-with-holes.md`).

## Session 8 (2026-09-28) — done, waiting for the maintainer's GUI check
- **Flat faces with holes, fixed and merged into `milestone-2`** (ADR 0008 addendum). The collars folded under
  Subdivision because a big convex polygon holding a run of collinear collar nodes has its Catmull–Clark face
  point far along the run. `_thin_children` refuses such merges (20°), and collars take 35% of the clearance (45%
  left 2° wedges that Bevel + SubD folded). New unit test simulates one Catmull–Clark step
  (`test_subdivision_folds_nothing_around_holes`); milestone 2's old fans folded too (plate 72 children), now 0
  on every test part; Bevel is not clamped on the default part (Blender's clamp code read: an interior edge at a
  mid-arc node "collapses" the arc's short chords). Fuzz 7 seeds clean. `MESH_FORMAT` 7. Limit: a hole within a
  few mm of a straight edge leaves a thin strip of fans (no vertices may be added on BRep edges).
- **Handles and cutters (maintainer's request, ADR 0011, research `docs/research/2026-09-28-handles-and-tool-bodies.md`):**
  arrows of one *focused* feature per part (`Object.blendsolid_focus`, `blendsolid/focus.py`), only while the part
  is active + selected + visible; clicking a face focuses the feature that made it (Object Mode keymap item after
  Blender's select click); Draw Solid/Boolean/Fillet/Push-Pull focus what they add; the sidebar has "Arrows of:"
  buttons. Cutters of live booleans go to a hidden `BlendSolid Cutters` collection (`hide_set`, never
  `hide_viewport`/exclude: stale `matrix_world`), parented to the target; back with Select Cutter, the eye toggle
  in "Booleans of this part", or Alt+H; Remove Boolean brings the cutter home. `gui_check` 21/21 PASS on Linux and
  in the real Windows window; 244 unit + 225 Blender tests. Windows zip built and **installed in the portable
  Blender** (smoke PASS).

- **Fillet edge cases** (research `docs/research/2026-09-28-fillet-edge-cases.md`, ~60 measured cases): part
  scripts use `worker/blends.py`'s fillet()/chamfer(): results must be one valid solid of positive volume; errors
  give the largest working size (bisection with a 2 s budget and probes around the limit), name seams/tangent/free
  edges and slivers, and say "another face is in the way" when the working sizes aren't an interval. The Fillet
  tool refuses clicks on tangent edges and shows the worker's error in the drag header. Tests T1–T23
  (`tests/unit/test_blends.py`).
- **Phase E (warnings)**: split faces/edges behind plain references and ambiguous `near=` build with a warning on
  the feature's line, shown in the sidebar ("Check these references"). ADR 0009 addendum.
- **Phase F (success criterion)**: `tests/unit/test_criterion.py` — 20 parts, 559 clicked entities, 97.1% survive 3
  upstream changes, 100% an inserted feature, 0 silent wrong bindings. It found a provenance bug (roles of a cut's
  untouched faces were reversed: +X/−X swapped), fixed. Milestone report written.
- 281 unit + 227 Blender tests; `gui_check` 21/21 on Linux and Windows; the Windows zip (all of the above) is
  installed in the portable Blender.

## Next step (session 9) — resume exactly here
1. **The maintainer's GUI check of milestone 2** (they are about to run it; steps below). Compare their reports with
   the numbers; fix what they find; then sign-off and merge `milestone-2` into `main`.
2. **Complete the chamfer** in the Fillet tool: two distances or distance + angle, choice of side (the kernel
   already supports `length2`; `worker/blends.py`), in the Adjust Last Operation panel and a key while dragging.
3. **Plan 3a** (sketch 2D on a face/plane, extrude with taper and up-to-face, revolve, STEP/IGES/BREP I/O): research
   Plasticity/Fusion/Shapr3D/Onshape/FORGE sketching and recent literature first (sketch solvers, region detection
   from curves), then design + plan + ADRs. After 3a: the usage checkpoint (the maintainer models 2–3 real objects;
   friction orders what follows; backlog in `docs/spec.md` "Candidate features").
4. Open M2 follow-ups (report): highlight failing fillet edges; a geometric radius bound with a reason; the
   continuing piece of a split face; a per-job time budget in the worker; UX redesign of the tools' feedback;
   ADR 0011's open points.

### GUI check steps (portable Blender, `E:\blender-5.2.2-windows-x64`, zip of session 8 installed)
1. Shift+A → BlendSolid → Box; Draw Solid tool, draw a cylinder into the top face (a cut). Expected: blue arrows
   only on the hole. Select tool: click the top face → the box's arrows; click the hole's bottom → the hole's;
   click empty space → none. Sidebar "Arrows of:" lists box_1 / cut_1.
2. A cylinder through the box; select the cylinder, then the box (active), Ctrl+Numpad −. Expected: the cylinder
   disappears (collection "BlendSolid Cutters"), the hole stays; G on the box → the hole follows; the eye in
   "Booleans of this part" shows/hides the cutter; Select Cutter selects it.
3. The two-bosses scene (a box with two cylinders near an edge) in wireframe: collars of radial quads around
   the bosses; add Bevel (Limit Method: Weight) then Subdivision: nothing folds (screenshot).
4. Fillet tool: select an edge, drag the radius far beyond the part. Expected: the header says "can't: fillet
   radius … mm is too large …: the largest that works is … mm"; releasing leaves the error in the sidebar, Ctrl+Z
   undoes it. Click an edge between a fillet and a flat face: "nothing to round" warning, nothing selected.
5. A face split by a later change (e.g. a wall that stops reaching an edge): the sidebar shows "Check these
   references".

## Working agreement with the maintainer
- Repo content in English; chat in Italian.
- Work autonomously; record non-trivial decisions as ADRs (`docs/decisions/`) or ledger rulings; ask only for
  spec scope changes, publication/licensing/distribution, or anything touching the maintainer's own Blender install.
- Commit trailer: keep the fixed `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` line for this
  project (settled 2026-09-27); the maintainer wants it removed for good in the future.
- GUI tests: one step at a time, exact actions and expected results; when a screenshot shows a mesh problem,
  measure exactly what it shows first; installing a build needs the maintainer to close Blender.

## Open follow-ups (not blocking)
- **Subdivision goes after "convert to quads" (maintainer, 2026-09-28):** the display mesh's Catmull–Clark rule
  (`tessellate._thin_children`, ADR 0008 addendum) adds wedge lines from the collar sides to the face corners; the
  maintainer finds 4 corner diagonals cleaner but accepts it for now. Once convert-to-quads exists, reconsider
  dropping the rule (or applying it only when the part has a Subdivision modifier).
- **Convert to quads (maintainer's idea, 2026-09-28):** the display mesh follows CAD conventions (triangles, as
  Rhino/Plasticity/MoI show them); later, a button converts a part's triangle mesh into a quad mesh, destructively
  or on a copy. The same button serves the NURBS surface modeling to come (spec: Surfaces, SubD → NURBS, G2
  milestones), whose results are converted to quads the same way. It is the spec's "Blender output" row (v2: quad
  mesh for simple faces; R&D: quads on trimmed faces). Quad-meshing findings from the 2026-09-28 tessellation
  research are its starting input.
- **Fixes after the 1.5 sign-off (2026-09-27)**, checked by the maintainer in the Windows GUI and merged: the tangent plane on a curved face follows the surface (ADR 0006 point 4; a solid drawn
  there is still tilted up to ~1.4° from the exact normal); the wedge has a `top_length` arrow along its top edge.
  Known: when a wedge's top is longer than its base, build123d centres the wider bounding box, and the
  `length` arrow (drawn from the box's middle) no longer ends on the base's edge.
- **Live cutters, after milestone 1.5** (maintainer's request, 2026-09-27; research: Fusion 360 timeline
  suppress/remove, HardOps/BoxCutter hidden cutters and Bool Scroll, Onshape/SolidWorks feature suppress):
  a per-boolean on/off toggle (suppress without removing, like a modifier's eye); "Apply" — inline a cutter
  into the target's history so the cutter is no longer needed; cycling through a part's cutters
  (HardOps' Bool Scroll). Deleting a cutter keeps it restorable and "Remove cut" exist since the manual test.
- Windows worker watchdog blocked while a C call holds the GIL → use a Job object with kill-on-close.
- Windows zip built with the build machine's pip environment markers (no colorama, has pexpect) → fix before any
  public release (milestone 3).
- `PR_SET_PDEATHSIG` is thread-scoped: comment it when the client is next touched.
- Maintainer reported an error on `Ctrl+D` during the milestone 1 GUI test (not a Blender 5.2 default duplicate key;
  nothing in the console) — not investigated.
- Optional GPU acceleration (fairing, SubD → NURBS) is an R&D note in the spec.
- Snap guides: not compared in detail with BoxCutter's grid or CAD sketch grids (Plasticity, Fusion 360) —
  worth a look if the maintainer finds them lacking (e.g. grid clipped to the face, snapping to edges/midpoints).
- The drag's grid/labels are drawn by the modal; the hover marker hides while a modal runs (`ops_draw._drawing`).
- **SurfacePsycho analysed** (2026-09-27): `docs/research/2026-09-27-surfacepsycho.md` — Geometry Nodes kernel,
  GPL-3.0, no booleans/fillets; its Blend Surfaces UX and analysis tools are inputs for milestones 4–5.
- The maintainer's logos and icons in several sizes are in `logo/BlendSolid_icone_e_logo.pdf` (for the
  extension icon, README and the GitHub page when needed).
- From milestone 1.5 (full list and reasoning: `docs/milestone-1.5-report.md`'s "Concerns / follow-ups"):
  fixed Draw Solid placements don't follow later upstream changes to their target; no hover highlight of the face
  in Draw Solid (the snap guides show the plane); "Apply" (inlining a cutter) not built; a cutter's `SyntaxError`
  still shows an opaque filename to script-editing users; duplicating/pasting a target+cutter pair twice
  double-cuts the second target; `ref()` is re-parsed every reconcile tick with no perf test against many
  cutters; tag stability relies on 6-decimal rounding; the cone primitive can't be dialled to a perfectly
  pointed top from the panel; `gizmos._layout_cache` is never pruned.
