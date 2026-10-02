# Where we are / what's next (bookmark)

Updated: 2026-09-30, session 12 end (milestone 3a in progress, branch `m3a`, pushed to GitHub). Read this first when resuming, then "Next step".

## State
- **Milestone 0 (spike):** done — `SPIKE_REPORT.md`.
- **Milestone 1 (history as code):** done — `docs/milestone-1-report.md`.
- **Milestone 1.5 (build without selectors):** done, signed off 2026-09-27 — `docs/milestone-1.5-report.md`
  (SDD ledger and GUI check report archived in `docs/milestone-1.5/`).
- **Milestone 2 (selectors from clicks):** done, signed off 2026-09-28 (GUI tests 1–5), merged into `main`
  (tag `m2`) — `docs/milestone-2-report.md` (what was built, criterion, history, known limits).
- `main`: 283 unit + 236 Blender tests; `tools/gui_check.py` steps 1-21 PASS on Linux and Windows (as of session 9,
  not re-run since). Branch `m3a`: 330 unit + 244 Blender tests, step 22 PASS (Linux and Windows).
- **The Windows portable Blender has branch `m3a` installed** (built from 791d9b4; `MESH_FORMAT` 12, smoke PASS).
- **Merged into `main` (session 10):** partial collars for curved runs of a flat face's loops, collars that shrink
  instead of cancelling, collar safety nets, planar cells of curved faces as quads (the maintainer's GUI review:
  a fillet of sliver triangles); `MESH_FORMAT` 10 — ADR 0008 and ADR 0010 addenda of 2026-09-29 (measured on a
  STEP corpus in `/mnt/e/bs_debug/step_corpus`, copied from the maintainer's Google Drive; scratch tools
  `spike/m3_outer_arcs/`).
- **Merged into `main` (session 11):** branch `chamfer-options` — Equal / Two Distances / Distance and Angle +
  Flip in the Fillet operator's Adjust Last Operation panel (research `docs/research/2026-09-29-chamfer-options.md`),
  and undo/redo/panel re-runs that keep showing the part while recomputing (`runtime._meshes` put back in the undo
  handler; test `test_undo_and_redo_panel_keep_showing_the_part`). Both checked in the GUI by the maintainer
  (2026-09-29: "tutto perfetto", no flash on Type changes, undo or redo).

## Milestone 3a in progress (branch `m3a`, session 11, not merged)
- Research: `docs/research/2026-09-29-milestone-3a-sketch-extrude-io.md` (scope, data model, I/O) and
  `docs/research/2026-09-29-sketch-drawing-ux.md` (drawing UX, BoxCutter/Hard Ops, sweep probes); decision: ADR 0012
  and its addendum (paths and grooves).
- **History of the design:** the first Sketch tool (rectangle, circle, single line; regions only from the sketch's
  own curves) was rejected by the maintainer's GUI test: "forme come cubi e cerchi possiamo farli direttamente col
  draw solid ... la linea ad oggi non fa nulla". What they want: draw a line, then use it to guide a cut or union
  with a profile, "like Blender's curve + bevel profile". Reframed as "draw a path, then use it" (addendum).
- **Built** (worker `blendsolid/worker/sketches.py`; Blender `ops_sketch.py`, `ops_extrude.py`, `sketching.py`):
  - **Sketch** tool: shape **Path** (default: click points; press-drag or A for an arc tangent to the path; click
    the first point to close; Enter/right-click/double-click ends; Backspace removes the last point), plus
    Rectangle and Circle; on a flat face (a new sketch, or the unused sketch on that plane), on a sketch, or on the
    3D cursor's plane (a new part that is only a sketch); snaps to sketch points, Ctrl to the grid.
  - A sketch on a face **splits the face**: its edges bound the regions (a line across it gives two pieces).
  - **Groove** tool: press on a sketch curve and drag into the part (groove) or out (rib); profile Rectangle /
    Round / V / Circle, width, corners Sharp/Round in the tool header and Adjust Last Operation.
  - **Extrude Sketch**: drag a region (out joins, in cuts); Adjust Last Operation: operation, up to next/last,
    symmetric, taper (straight prism + draft, exact planes). **Revolve Sketch**: a region, then a straight sketch
    curve as the axis.
  - All the sketch tools sit in the Draw Solid toolbar group (hold for the menu), like Fillet and Push/Pull.
- **Maintainer's GUI test of this version (2026-09-29), steps given in the chat:** 1 add a Box; 2 Sketch Path on
  the top face (line, dragged arc, line, Enter); 3 Groove: drag down on the path, then change Profile (Round, V);
  4 Sketch a line across the top face from just outside one edge to just outside the other; 5 Extrude Sketch: one
  half highlights, drag it down (a step); 6 Groove dragged up with Profile Circle (a pipe rib). Steps 1-4 done;
  **step 4 exposed the bug below**, so 5-6 are still to be seen.

## Next step — resume exactly here
**Session 12 ended with everything built, installed in the portable Blender and passing gui_check 1-25, but not
yet checked by the maintainer** (they couldn't test tonight). Resume with their GUI test of:
1. Sketch Path started just off the top face (stays on the face's plane), Extrude Sketch of one half.
2. Sketch snaps: near a corner ("vertex"), an edge's middle ("midpoint"); Shift after the first click ("15° lock").
3. Groove, Profile Circle, dragged up (a pipe rib) — the old test's step 6.
4. Pie: right-click (Blender's menu), right-drag to Edit > Fillet / Chamfer, E tap > Sketch > Circle,
   E hold > Add > Cylinder. Ask whether two flicks feel slow (ADR 0013 point 3).
5. Add (E > Add > Box): placed where the pie opened, round size, mouse scales, Ctrl grid, typed size, Esc.
6. Fillet: drag far past the limit (stops at the max), test6.blend's error label, a new fillet on a failing part
   refused. Open question for the maintainer: were fillet_3-5 in test6 attempts to change fillet_2's radius (then
   a click on an existing fillet should show its radius arrow instead of adding a new fillet)?

**Test progress (session 13, 2026-10-02):** step 1 PASS (path from just off the face, Extrude Sketch of one half).
Maintainer's note: the blue hover fill had cut corners — fixed (791d9b4, sketch outlines sampled per edge,
`MESH_FORMAT` 12), installed; check it in passing during step 2.

**Queue after that test (in order):**
1. Fix what the maintainer's test finds (one fix at a time, rebuild + install, re-check only what changed).
2. Editing an existing fillet from the viewport, if the maintainer confirms the intent (question above): a click on
   a fillet face focuses its feature and shows a radius handle, instead of appending a new fillet.
3. The rest of the UI pass (`docs/superpowers/plans/2026-09-30-ui-pass.md`, ADR 0013/0014): task 3 right-click
   entries by selection kind; task 4 sidebar = context only, tools as one toolbar group; task 5 hover/selection
   highlights with depth; task 6 the real result as the only preview (drop `preview_lines`); task 7 native
   `GIZMO_GT_button_2d` handle for Fillet and Push/Pull, drag out = fillet / in = chamfer; task 8 tangent chain
   shown before dragging.
4. Sketch features still to do (item 2 below): snaps to edges, typed segment length, corner radius per vertex,
   slice by path, offset to a band, named groove faces (ADR 0009 addendum).
5. Rest of 3a (item 3 below): STEP/IGES/BREP import/export, up-to-face, New Part/Cutter for extrudes, arcs/polygon/
   slot, editing sketch entities in the viewport; then the 3a acceptance criterion, the usage checkpoint, merge
   `m3a` into `main`.

0. **Merged into `m3a` (session 12):** the maintainer's morning research branch `research/ui-pass` (docs only:
   pie menus, fillet feedback, OCCT fillets after 8.0.1; `docs/handoff-2026-09-30.md`), decisions recorded as
   ADR 0013 (commands: two-level pie + selection context menu, sidebar = context; pie key still open) and ADR 0014
   (Fillet/Push-Pull: real result as the only preview, Blender's native handle, fillet out / chamfer in). The
   **UI pass** (`docs/superpowers/plans/2026-09-30-ui-pass.md`) comes when 3a is stable and before the 3a usage
   checkpoint: first check the draft plan against the code, do its two cheap GUI checks, then implement.
   **Session 12, built and installed for the maintainer's test:** the command pie (plan task 1) and its keys
   (task 2, research `docs/research/2026-09-30-pie-key.md`): **E** (tap or hold) and a **right-button drag** in
   Object Mode (a right-click without a drag re-opens Blender's Object context menu; checked on Windows, gui_check
   step 23 + screenshot). Not built yet: tasks 3-8 (right-click entries by selection, sidebar = context, depth
   highlights, real result as preview, native handle, tangent chain).
   Also built in session 12 (maintainer's requests after testing): **interactive Add** (ADR 0015: placed where
   the pie was opened, round size from the view, scaled by the mouse) and the **failing-feature fixes** (ADR 0014
   addendum: error shown in the viewport, no features added to a failing part, the Fillet drag stops at the
   largest radius that works). gui_check steps 1-25 PASS on Linux.
1. **Done (session 12, 4f716fd):** the hovered face's plane sticks (`ops_sketch.hover_target`): a path started
   just off a face stays on its plane; released by another face, a curved face, empty space farther than 1.5 part
   radii, or a change to the part's script/placement. Test `test_the_hovered_face_plane_sticks_just_off_the_face`;
   gui_check step 22 draws its line from off the face first (FAILs without the fix). Not built: a key to lock the
   plane (Space was proposed; it is Blender's play key). **Installed** in the Windows portable Blender (smoke PASS).
   Next: the maintainer's GUI test from step 4 (line from just outside the top face), then 5-6.
2. **Done (session 12):** snaps to the part's exact vertices, edge midpoints and circle centres projected on the
   sketch plane (worker `tessellate.snap_points`, `MESH_FORMAT` 11); Shift = 15° lock (H/V exact). Installed.
   Next sketch features, in the research's order (`sketch-drawing-ux.md`, "Recommendation"): snaps to edges
   (nearest point on a projected edge); typed segment length (Tab/digits); a corner radius per path vertex (`FilletPolyline`); slice a part by a path;
   offset a path to a closed band. Also: the groove's faces all get role `wall` (references to them need `near=`):
   name them (floor, walls by path segment, ends) in an ADR 0009 addendum.
3. Rest of 3a: STEP/IGES/BREP import/export (research section 7: embedded compressed BRep blobs, one part per
   leaf solid, invalid solids as warnings); up to a picked face; New Part / Cutter operations for extrudes; arcs,
   polygon, slot; editing/deleting sketch entities from the viewport; the 3a acceptance criterion (research,
   "Acceptance criteria"); the usage checkpoint (the maintainer models 2-3 real objects); then merge `m3a`.
   Known limits to keep in mind: Extrude Sketch's up-to options show the distance field as "Direction (sign)";
   Revolve's axis is only a straight sketch curve; used sketches are hidden unless a sketch tool is active;
   entities can't be moved/deleted from the viewport (script or undo only).
   Before the usage checkpoint: the UI pass (item 0).
4. Open corpus findings on flat faces (ADR 0008 addendum of 2026-09-29, known limits): BRepMesh-fallback
   board faces, `meshing._recover`'s budget on faces with ~200 holes, small holes in a big hole's rectangle
   corners, polygonal holes; the thin strip between a hole's collar and a straight edge (maintainer's GUI note).
5. Consider: Draw Solid placements that follow the face they were drawn on (sketches do: `on_face`).
6. Open M2 follow-ups (`docs/milestone-2-report.md`, "Known limits / follow-ups").

## Working agreement with the maintainer
- Repo content in English; chat in Italian.
- Work autonomously; record non-trivial decisions as ADRs (`docs/decisions/`) or ledger rulings; ask only for
  spec scope changes, publication/licensing/distribution, or anything touching the maintainer's own Blender install.
- Commit trailer: keep the fixed `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` line for this
  project (settled 2026-09-27); the maintainer wants it removed for good in the future.
- GUI tests: one step at a time, exact actions and expected results; use the UI's own labels and tool names, no
  new jargon, and skip steps already verified — go straight to what the test is about; when a screenshot shows a mesh problem,
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
  research are its starting input. Research and the maintainer's decision (merged from `research/cad-to-quads`,
  2026-10-02): `docs/research/2026-09-30-cad-to-quad-meshing.md` — start with the classic methods (Plasticity-like
  Tris / Quads / Ngons, triangle pairing, no vertex moved), then study Gmsh's quasi-structured quads; spec 3e.
- **Live cutters, after milestone 1.5** (maintainer's request, 2026-09-27; research: Fusion 360 timeline
  suppress/remove, HardOps/BoxCutter hidden cutters and Bool Scroll, Onshape/SolidWorks feature suppress):
  a per-boolean on/off toggle (suppress without removing, like a modifier's eye); "Apply" — inline a cutter
  into the target's history so the cutter is no longer needed; cycling through a part's cutters
  (HardOps' Bool Scroll). Deleting a cutter keeps it restorable and "Remove cut" exist since the manual test.
- From the fixes after the 1.5 sign-off: a solid drawn on the tangent plane of a curved face is still tilted up
  to ~1.4° from the exact normal; when a wedge's top is longer than its base, build123d centres the wider
  bounding box and the `length` arrow (drawn from the box's middle) no longer ends on the base's edge.
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
