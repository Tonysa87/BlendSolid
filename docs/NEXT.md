# Where we are / what's next (bookmark)

Updated: 2026-09-27, end of session 4 (manual GUI test finished, snap guides built). Read this first when resuming.

## State
- **Milestone 0 (spike):** done — `SPIKE_REPORT.md`.
- **Milestone 1 (history as code):** done, merged to `main` and pushed — `docs/milestone-1-report.md`
  (105 automated tests, smoke tests on Windows + Linux, manual GUI test 8/8 OK).
- **Milestone 1.5 (build without selectors): manual GUI test passed (16/16), sign-off pending one check** —
  `docs/milestone-1.5-report.md`. Session 4 (2026-09-27 afternoon) ran steps 12, 13, 15, 16 with the maintainer
  and fixed what they showed: placements on exact face planes written with 10 decimals (a 5e-07 mm skin over a
  pocket drawn from an earlier pocket's wall), Draw Solid as its own toolbar button (it sat inside Blender's Add
  group with a `None` separator that made Blender's toolbar code raise). At the end the maintainer asked for
  **snap guides**, now built (ADR 0006 point 5): axis-coloured marker (X red / Y green / Z blue, mixed on tilted
  planes) with a normal stub and an orange/white ring, a local fading grid of the current step, height ticks,
  and labels (size/height, snap step). 160 unit + 175 Blender = 335 tests pass; `tools/gui_check.py` PASS on
  Linux and Windows; the snap guides were checked in the real Windows viewport (gui_check screenshot) and with an
  offscreen probe on Linux — **not yet by the maintainer**. Everything is merged to `main` and **pushed** (at the
  maintainer's request, before the sign-off). The Windows 0.2.0 zip installed in the portable Blender is exactly
  `main`'s code. *Auto Run Python Scripts* in the portable preferences was turned off for step 16 and turned
  back on (as it was).

## Next step (session with the maintainer)
1. **Check the snap guides** (the last open item), guided step by step. Launch
   `/mnt/e/blender-5.2.2-windows-x64/blender.exe >> spike/logs/gui-m1.5.log 2>&1` (in background), then:
   - Draw Solid tool, mouse over empty space: white ring, red/green cross, blue stub up, white grid around it;
     over a box's top face: orange ring and orange grid; over a side face: red/blue cross, green stub (±Y).
   - Ctrl+Wheel before clicking: the grid spacing changes at once (50 → 20 → 10 mm…); zoomed far out the fine
     lines disappear first (only every 5th), then the whole grid.
   - Ctrl+drag a base: the grid follows the dragged corner, the label shows `L × W mm` and `snap N mm`; release,
     move for the height with Ctrl: ticks every step along the normal, label `H … mm`.
   - A cursor rotated 30–45°: the cross/stub colours mix (e.g. purple between X and Z).
   Ask whether size (20 px), grid reach (8 steps), fade and label size feel right; tune the constants
   (`ops_draw.MARKER_ARM_PX`, `drawing.GRID_HALF`, `GRID_MAJOR`, `MIN_GRID_PX`, grid alphas in `_draw_grid`).
   To install a new build, the maintainer must close Blender first (the worker locks the files):
   `"$PY" tools/build_extension.py --platform windows-x64 --blender "$BL"`, `install-file`, then
   `tools/smoke_installed.py` on Windows.
2. **Sign off milestone 1.5:** sign-off line in `docs/milestone-1.5-report.md` (and the snap guides' "Manual"
   note), README status `✅ **Done**`, delete the git-ignored SDD ledger
   (`.superpowers/sdd/2026-09-26-milestone-1.5-build-without-selectors/`), commit and push.
3. Then the next milestone (2, selectors from clicks) — or first the post-1.5 follow-ups the maintainer picks
   (live cutter suppress/apply/cycling below). Ask which.

## Working agreement with the maintainer
- Repo content in English; chat in Italian.
- Work autonomously; record non-trivial decisions as ADRs (`docs/decisions/`) or ledger rulings; ask only for
  spec scope changes, publication/licensing/distribution, or anything touching the maintainer's own Blender install.
- Commit trailer: keep the fixed `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` line for this
  project (settled 2026-09-27); the maintainer wants it removed for good in the future.
- GUI tests: one step at a time, exact actions and expected results; when a screenshot shows a mesh problem,
  measure exactly what it shows first; installing a build needs the maintainer to close Blender.

## Open follow-ups (not blocking)
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
- **To analyse (maintainer's pointer, 2026-09-27):** SurfacePsycho, a Blender NURBS/CAD add-on —
  https://extensions.blender.org/add-ons/surfacepsycho/ — what it does, how (kernel, data model, UI), license,
  and whether it helps or overlaps BlendSolid (especially milestones 4–6: SubD → NURBS, G2 surfaces/fillets).
- The maintainer's logos and icons in several sizes are in `logo/BlendSolid_icone_e_logo.pdf` (for the
  extension icon, README and the GitHub page when needed).
- From milestone 1.5 (full list and reasoning: `docs/milestone-1.5-report.md`'s "Concerns / follow-ups"):
  fixed Draw Solid placements don't follow later upstream changes to their target; no hover highlight of the face
  in Draw Solid (the snap guides show the plane); "Apply" (inlining a cutter) not built; a cutter's `SyntaxError`
  still shows an opaque filename to script-editing users; duplicating/pasting a target+cutter pair twice
  double-cuts the second target; `ref()` is re-parsed every reconcile tick with no perf test against many
  cutters; tag stability relies on 6-decimal rounding; the cone primitive can't be dialled to a perfectly
  pointed top from the panel; `gizmos._layout_cache` is never pruned.
