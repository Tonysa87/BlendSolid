# Where we are / what's next (bookmark)

Updated: 2026-09-27, end of session 3 (manual GUI test, first half). Read this first when resuming.

## State
- **Milestone 0 (spike):** done — `SPIKE_REPORT.md`.
- **Milestone 1 (history as code):** done, merged to `main` and pushed — `docs/milestone-1-report.md`
  (105 automated tests, smoke tests on Windows + Linux, manual GUI test 8/8 OK).
- **Milestone 1.5 (build without selectors): manual GUI test half done** — `docs/milestone-1.5-report.md`.
  On 2026-09-27 the maintainer ran steps 1–11 and 14 by hand; every problem found was fixed test-first and
  re-checked by them (display tessellation + tolerance + exact normals, ADR 0005; Draw Solid snap ladder,
  sidebar access, worker warm-up, exact placements, edge picking, curved-face clearance, arrows hidden while
  drawing, ADR 0006; restorable deleted cutters and a per-part booleans list, ADR 0007). 327 automated tests
  pass; `tools/gui_check.py` PASS on Linux and Windows on the final code. All merged to `main` **locally, not pushed** (push only when the
  milestone is signed off). The Windows 0.2.0 zip with all of it is installed in the portable Blender.

## Next step (session with the maintainer)
Finish the manual GUI test (plan `docs/superpowers/plans/2026-09-26-milestone-1.5-build-without-selectors.md`,
Task 14 Step 1), guided one step at a time with exact actions and expected results (the maintainer asked for
that level of detail):
- Launch: `/mnt/e/blender-5.2.2-windows-x64/blender.exe >> spike/logs/gui-m1.5.log 2>&1` (run in background).
  To install a new build, the maintainer must close Blender first (the running worker locks the files):
  `"$PY" tools/build_extension.py --platform windows-x64 --blender "$BL"`, then `install-file`, then
  `tools/smoke_installed.py` on Windows.
- **Step 12:** Ctrl+Numpad + / * and Object menu → BlendSolid Boolean by hand; ask about other add-ons using the
  same keys (Bool Tool).
- **Step 13:** Draw Solid through a wire cutter picks the part behind it.
- **Step 15:** Ctrl+Z back to the empty scene and Ctrl+Shift+Z to the end; each press is one action.
- **Step 16:** save, quit, restart with *Auto Run Python Scripts* off, open: cached meshes, untrusted panel,
  *Recompute* greyed with its tooltip; *Trust Scripts in This File* recomputes the stale parts; quit → no
  worker left in Task Manager.
- Corrections still valid: switch to Select Box (`W`) before steps that click objects; pick the wire cutter by
  its lines or in the Outliner; use an angled view for the height stage of a drag.
- Then: fill in the remaining "Manual" cells and the sign-off in `docs/milestone-1.5-report.md`, set the README
  status to `✅ **Done**` (and mention the new tolerance/snapping/booleans list in "Try it" if useful), delete the
  git-ignored SDD ledger (`.superpowers/sdd/2026-09-26-milestone-1.5-build-without-selectors/`), push `main`.

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
- From milestone 1.5 (full list and reasoning: `docs/milestone-1.5-report.md`'s "Concerns / follow-ups"):
  fixed Draw Solid placements don't follow later upstream changes to their target; no hover highlight or real
  grid snapping in Draw Solid; "Apply" (inlining a cutter into its target) not built; a cutter's `SyntaxError`
  still shows an opaque filename to script-editing users; duplicating/pasting a target+cutter pair twice
  double-cuts the second target; `ref()` is re-parsed every reconcile tick with no perf test against many
  cutters; tag stability relies on 6-decimal rounding; the cone primitive can't be dialled to a perfectly
  pointed top from the panel; `gizmos._layout_cache` is never pruned.
