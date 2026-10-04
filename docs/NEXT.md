# Where we are / what's next (bookmark)

Updated: 2026-10-04, session 14 end (milestone 3a in progress, branch `m3a`, pushed to GitHub). Read this first when resuming, then "Next step".

## State
- **Milestone 0 (spike):** done — `SPIKE_REPORT.md`.
- **Milestone 1 (history as code):** done — `docs/milestone-1-report.md`.
- **Milestone 1.5 (build without selectors):** done, signed off 2026-09-27 — `docs/milestone-1.5-report.md`
  (SDD ledger and GUI check report archived in `docs/milestone-1.5/`).
- **Milestone 2 (selectors from clicks):** done, signed off 2026-09-28 (GUI tests 1–5), merged into `main`
  (tag `m2`) — `docs/milestone-2-report.md` (what was built, criterion, history, known limits).
- `main`: 283 unit + 236 Blender tests; `tools/gui_check.py` steps 1-21 PASS on Linux and Windows (as of session 9,
  not re-run since). Branch `m3a`: 378 unit + 278 Blender tests (session 14); gui_check 1-25 PASS on Linux
  (session 12; not re-run since session 13).
- **The Windows portable Blender has branch `m3a` installed from a87af0b** (session 14; `MESH_FORMAT` 12, smoke
  PASS); everything after it (the bug-sweep fixes) is not installed yet.
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
**Session 14 (2026-10-04) ended mid-bug-sweep; the maintainer then said: work autonomously (they will `/clear`
from remote).** Start with `git fetch` (docs-only research branches are merged into `m3a`), then the plan below.

### Where session 14 left things
- Maintainer's GUI test of session 12's build: steps 1-4 PASS (session 13), step 5 keypad typing PASS. Two bugs
  they found are fixed: the Add "pop" on confirm (a87af0b, installed, confirmed) and the Round rib failing at a
  sharp corner after an arc (`StdFail_NotDone`; e5affbc: paths with sharp corners are swept run by run and the
  corners filled; file `E:\bs_debug\s14_rib.blend`). **Not installed**: everything after a87af0b (the Windows
  portable Blender still has a87af0b).
- **Headless bug sweep** (the maintainer's request before rebuilding: "prenditi il tempo che serve"): 4 searches,
  ~10,000 cases. **Ledger with every finding, its status and commit: `docs/research/2026-10-04-bug-sweep.md`**
  (B = Blender side, R = regions/extrude/revolve, M = display mesh, G = grooves/paths). Tools to rerun them:
  `spike/m3_bug_sweep/` (README; `rerun.py grooves|tapers` reruns 3000 groove / 895 taper cases, 2 processes).
- Fixed so far (each with a test that fails without it): B1-B11, B13 (warning), B14; R2, R3 (sure-vanish bound),
  R4, R5, R7, R10; G1, G2, G3, G5, G6, G8. Two regressions of the path fixes, found by rerunning the groove
  cases, are fixed too (065b189). Branch `m3a`: 378 unit + 278 Blender tests pass.
- Learned (CLAUDE.md pitfalls): OCCT's draft can hang holding the GIL; `BRepOffsetAPI_MakeOffset` segfaults on
  some faces (a volume check of tapers against offset sections was measured and dropped for that); rounding
  fixes must stay at the rounding level (1e-6 rad) or they move real geometry.

### Plan (agreed with the maintainer at the end of session 14; follow it in order)
Goal: reach the **3a usage checkpoint** (the maintainer models 2-3 real objects) as soon as possible, fixing first
only what would make that test misleading: wrong results without an error, raw errors, and mesh defects seen on
almost every groove. The checkpoint, not the fuzzers, orders what comes after it. Principles from the docs: a
failure is never silent (CLAUDE.md), references never re-bind silently (ADR 0009, 3a criterion 3), every
geometric result verified with numbers.
1. **Silent wrong results** (ledger `docs/research/2026-10-04-bug-sweep.md`): R11 (a region seed silently lands in
   another region after an upstream change — research how Onshape/Fusion identify sketch regions first; ADR
   0012's fallback: identify regions by their bounding entity names); R12 (regions tapered one by one leave a
   V-groove: taper their union); G7 (a rib's overshoot hangs below the face beyond its edge); G4 (a self-crossing
   tangent run passes: check the path in 2D before sweeping); R13, R15, R8, R9.
2. **Clear messages instead of raw ones:** R6, R14, R16, B12, G9, G10, G11, the G1 residue.
3. **Display mesh, loud failures:** M3, M4, M5 (open or wrong meshes), M13 (blend hangs: at least a clear error).
   Fuzz with `spike/m3_bug_sweep/sweep_mesh/check.py` before/after; bump `part.MESH_FORMAT` on any mesh change.
4. **Display mesh quality, only what shows on almost every groove:** M1 (sliver fans and folds: a tfi face demoted
   to a trimmed grid keeps its edge counts) and M2 (partial cones ~8x too many columns; also M12's excess). Same
   fuzz before/after; measure, don't eyeball (ADR 0010).
5. **Build for the maintainer:** full tests, `tools/gui_check.py` on Linux, Windows zip, install **only if the
   portable Blender is closed** (`powershell.exe Get-Process blender`; never kill it), smoke PASS, update this file.
6. **When the maintainer is back:** GUI step 5b (E > Add > Box: mouse scales in round steps, Ctrl = grid steps, a
   click confirms with object scale 1, Esc leaves nothing), step 6 (Fillet: drag past the limit stops at the max,
   test6.blend's error label, a new fillet on a failing part refused; ask whether fillet_3-5 in test6 were
   attempts to change fillet_2's radius), a quick re-check of `s14_rib.blend`, and what the fixes changed in the
   GUI. Short steps, in Italian.
7. **The rest of 3a needed before the checkpoint:** the UI pass (queue item 3: tasks 3-8) and STEP/IGES/BREP
   import/export (real parts to work on); then the usage checkpoint.
8. **Deferred until the checkpoint has spoken** (each stays in the ledger with its reason): R1 and the rest of R3
   (taper hang — the worker is killed after 120 s with a message — and drafts wrong past a partly vanishing
   outline: needs a design note first), M6-M11 (rarer mesh defects), the remaining fuzz edge cases, and the
   sketch features of queue item 4 (snaps to edges, typed length, corner radius per vertex...): the
   maintainer's use decides which are needed.

**Queue (after the plan above):**
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

Earlier items (sessions 12-13, kept for reference):
0. **Merged into `m3a` (session 12):** the maintainer's morning research branch `research/ui-pass` (docs only:
   pie menus, fillet feedback, OCCT fillets after 8.0.1; `docs/handoff-2026-09-30.md`), decisions recorded as
   ADR 0013 (commands: two-level pie + selection context menu, sidebar = context; pie keys settled 2026-10-02: right-drag and E) and ADR 0014
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
- **Never saturate the PC** (session 14): background jobs and subagents at most ~8 busy processes in total (2 per
  agent, said in each prompt); no hurry.
- Every reply in Italian, including GUI steps and bug explanations (session 14: one slipped into English).
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
