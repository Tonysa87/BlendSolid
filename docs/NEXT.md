# Where we are / what's next (bookmark)

Updated: 2026-09-27, end of session 5 (milestone 1.5 signed off; milestone 2 phases A–D built on branch `milestone-2`). Read this first when resuming.

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

- **Maintainer's bug, 2026-09-27 evening:** fans of slivers on fillet faces (`/mnt/e/bs_debug/fillet.blend`, a corner
  cut by a big cylinder with every edge filleted). Cause and fix: ADR 0005 addendum (trimmed curved faces
  re-triangulated in the surface's metric), commit `72a1076`; 217 unit + 210 Blender tests pass. **Not yet
  installed/checked in the GUI.** Remaining: thin triangles along long boundary edges (edge refinement).

## Next step (session 6)
1. **Install and check the trimmed-face fix with the maintainer:** close Blender, build the Windows zip, install,
   smoke test, relaunch `blender.exe >> spike/logs/gui-m2.log 2>&1`; open `E:\bs_debug\fillet.blend`, wireframe
   overlay: the fillet bands are regular lattices (no fans); only a row of thinner triangles along their long
   edges remains. Then fix that: refine the discretization of long boundary edges for both adjacent faces
   (insert the same nodes in both; planar neighbours are rebuilt as polygons anyway), test on
   `tests/unit/data/maintainer_fillet_part.py` (fraction of thin triangles → 0).
2. **Fillet edge cases (maintainer's request):** research online the typical failure cases of CAD fillets/chamfers
   (OCCT `BRepFilletAPI_MakeFillet` known failures and forum threads, FreeCAD/Fusion/Onshape/SolidWorks docs:
   radius larger than a face, vertex blends where 3+ fillets meet, fillets across tangent chains, fillets on edges
   between a face and a fillet, mixed convex/concave, fillets touching holes, chamfer asymmetric, variable edges,
   filleting after booleans with tiny faces, seam edges, self-intersecting results); write
   `docs/research/…-fillet-edge-cases.md`; turn each case into a test on our system (script + Fillet tool path),
   and fix what fails following best practices (clear errors on the fillet's line, `max_fillet`, suggestions),
   otherwise document the limitation.
3. Then milestone 2 phases E (broken references) and F (20-part corpus criterion test), report, sign-off.
4. Later: UX redesign of the tools' on-screen feedback (the maintainer dislikes the yellow handle and the preview).

## Working agreement with the maintainer
- Repo content in English; chat in Italian.
- Work autonomously; record non-trivial decisions as ADRs (`docs/decisions/`) or ledger rulings; ask only for
  spec scope changes, publication/licensing/distribution, or anything touching the maintainer's own Blender install.
- Commit trailer: keep the fixed `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` line for this
  project (settled 2026-09-27); the maintainer wants it removed for good in the future.
- GUI tests: one step at a time, exact actions and expected results; when a screenshot shows a mesh problem,
  measure exactly what it shows first; installing a build needs the maintainer to close Blender.

## Open follow-ups (not blocking)
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
- **Trimmed curved faces' triangulation** (ADR 0005): shading is right (exact normals) but the wireframe of a
  curved face cut by booleans still shows BRepMesh's slivers: structured grid + a band along the cut.
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
