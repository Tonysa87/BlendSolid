# Where we are / what's next (bookmark)

Updated: 2026-09-28, session 9. Read this first when resuming, then "Next step".

## State
- **Milestone 0 (spike):** done — `SPIKE_REPORT.md`.
- **Milestone 1 (history as code):** done — `docs/milestone-1-report.md`.
- **Milestone 1.5 (build without selectors):** done, signed off 2026-09-27 — `docs/milestone-1.5-report.md`
  (SDD ledger and GUI check report archived in `docs/milestone-1.5/`).
- **Milestone 2 (selectors from clicks):** done, signed off 2026-09-28 (GUI tests 1–5), merged into `main`
  (tag `m2`) — `docs/milestone-2-report.md` (what was built, criterion, history, known limits).
- 276 unit + 227 Blender tests; `tools/gui_check.py` 21/21 on Linux and Windows. The Windows portable Blender has
  the sign-off build (`MESH_FORMAT` 7); the session 9 consolidation (branch `consolidate-m2`: README, docs, shared
  operator helpers, `MESH_FORMAT` 8) isn't installed yet.

## Next step — resume exactly here
1. **Partial collars for arcs in a face's outer loop** (a boss or hole cutting a corner or an edge: test2.blend's
   top and side faces fan from the arc to one far point). Research first (products + literature, e.g. template
   meshing around boundary arcs, medial-axis decomposition), then extend `tessellate._collared`; measure on
   test2's part (`/mnt/e/bs_debug/test2.blend`, script `.Box.py.001`) with the scratch tools
   `spike/m2_flat_faces/plot_face.py` / `metrics.py`; Bevel tests must stay green; bump `part.MESH_FORMAT`.
2. **Complete the chamfer** in the Fillet tool: two distances or distance + angle, choice of side. The spec
   schedules it in 3b; done now as a small exception because it is UI only (`worker/blends.chamfer` already
   accepts `length2`/`angle`/`reference`).
3. **Plan 3a** (sketch 2D + extrude with taper/up-to-face + revolve + STEP/IGES/BREP I/O) from research.
4. Consider: Draw Solid placements that follow the face they were drawn on (the maintainer hit the limit).
5. Open M2 follow-ups (`docs/milestone-2-report.md`, "Known limits / follow-ups").

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
  research are its starting input.
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
