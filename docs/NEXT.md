# Where we are / what's next (bookmark)

Updated: 2026-09-27, session 5 (milestone 1.5 signed off; milestone 2 phase A built). Read this first when resuming.

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
  tests pass; `tools/gui_check.py` PASS on Linux (16/16). **Awaiting the maintainer's GUI check** (below).

## Next step
1. **GUI check of phase A with the maintainer** (Windows; the maintainer closes Blender first, then:
   `"$PY" tools/build_extension.py --platform windows-x64 --blender "$BL"`, `install-file`, `smoke_installed.py`,
   relaunch `blender.exe >> spike/logs/gui-m2.log 2>&1`):
   - Add a default part (sidebar or Shift+A → BlendSolid). Wireframe overlay: box faces are quads, the boss top an
     n-gon, the top face around the boss a few convex polygons; no islands.
   - Add a Bevel modifier, Limit Method **Weight**, Amount 1 mm, Segments 3: only the CAD edges are rounded (not
     the tangent edges of the fillet), with Clamp Overlap on.
   - Weighted Normal, Solidify, Array, Mirror, Subdivision: the part behaves like any Blender mesh.
   - Draw Solid on a face of a part with a Bevel modifier: the drawing starts on the face (exact plane); on an
     Array copy: it starts on the copy's face.
   - Parts saved before this build recompute once when opened (MESH_FORMAT 4).
2. Then phase B (provenance and references in the worker): write its plan from the design, execute, and so on.

## Working agreement with the maintainer
- Repo content in English; chat in Italian.
- Work autonomously; record non-trivial decisions as ADRs (`docs/decisions/`) or ledger rulings; ask only for
  spec scope changes, publication/licensing/distribution, or anything touching the maintainer's own Blender install.
- Commit trailer: keep the fixed `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` line for this
  project (settled 2026-09-27); the maintainer wants it removed for good in the future.
- GUI tests: one step at a time, exact actions and expected results; when a screenshot shows a mesh problem,
  measure exactly what it shows first; installing a build needs the maintainer to close Blender.

## Open follow-ups (not blocking)
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
