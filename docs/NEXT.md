# Where we are / what's next (bookmark)

Updated: 2026-09-26, end of session 2. Read this first when resuming.

## State
- **Milestone 0 (spike):** done — `SPIKE_REPORT.md`.
- **Milestone 1 (history as code):** done, merged to `main` and pushed — `docs/milestone-1-report.md`
  (105 automated tests, smoke tests on Windows + Linux, manual GUI test 8/8 OK).
- **Milestone 1.5 (build without selectors): implemented** on branch `milestone-1.5` — `docs/milestone-1.5-report.md`
  (238 automated tests, `tools/gui_check.py` PASS on Linux and Windows covering all 16 plan steps, both 0.2.0
  zips built and smoke-tested). The branch is merged to `main` **locally** by the controller after this session's
  last commit; **not pushed yet**. The maintainer was unavailable for the manual GUI test this session (a
  controller ruling): **it is postponed to the next session**, so the milestone is not fully signed off and
  `main` should not be pushed until it is done.

## Next step (session with the maintainer)
Run the manual GUI test, guided step by step, using the plan's 16 steps
(`docs/superpowers/plans/2026-09-26-milestone-1.5-build-without-selectors.md`, Task 14 Step 1):
- Launch the portable Windows Blender from WSL with the console redirected to a log file:
  `/mnt/e/blender-5.2.2-windows-x64/blender.exe > spike/logs/gui-m1.5.log 2>&1` (WSL-side path: the redirect is bash's) (0.2.0, with all
  final-review fixes, is already installed there — no rebuild needed unless `main` changes before the session).
- Corrections to the plan's step wording, found during the final review and the automated GUI check:
  - **Before step 11 and after step 13,** switch back to the Select Box tool (`W`) — Draw Solid's own LMB
    binding captures clicks while it is active.
  - **Picking the wire cutter** (steps 11, 13, 14): click its wire lines directly, or select it in the Outliner
    — clicking where a solid part used to be no longer hits the cutter once it's a wireframe.
  - **Step 4 (gizmo drag), and generally the height stage of any drag:** use an angled view, not one looking
    straight down the face normal — `height_along_normal` reads 0 in that degenerate case (a known, parked
    limitation, not a bug to report).
  - **Step 16 wording:** after *Trust Scripts in This File*, only the **stale** parts (the ones edited while
    the file was untrusted) recompute — not every part in the file.
- Focus the session on what `tools/gui_check.py` cannot check by itself (from `docs/milestone-1.5-report.md`'s
  "Manual GUI test" section): gizmo-drag feel and arrow colours vs. the Move gizmo (step 4); the Draw Solid
  preview outline's colour/look and the on-screen header text while drawing, and Ctrl-snapping feel (steps
  6–9); the *Adjust Last Operation* panel as a widget, typing values by hand (steps 1, 6, 8); opening Shift+A
  and the Object menu by hand, and key conflicts with other installed add-ons such as Bool Tool (steps 3, 12);
  the wireframe look of a cutter (step 11); quitting/restarting Blender with *Auto Run* off and the *Recompute*
  tooltip text, checked in Task Manager (step 16); and, throughout, a **real** mouse and keyboard — every
  automated step used simulated events.
- The SDD ledger with every ruling (`.superpowers/sdd/2026-09-26-milestone-1.5-build-without-selectors/`, git-ignored)
  is kept until the manual test is done; delete it after the report is signed off.
- Then: record the results in `docs/milestone-1.5-report.md` (fill in the "manual" column and the sign-off),
  set the README status to `✅ **Done**`, and push `main` (the maintainer's rule: push only at the end of a
  milestone).

## Open question for the maintainer
- **Commit trailer rule:** should every commit keep a fixed `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  line regardless of which model actually wrote it, or should the trailer name the model that wrote each commit
  (as this session's commits do)? Settle this before milestone 2's first commit.

## Working agreement with the maintainer
- Repo content in English; chat in Italian.
- Work autonomously; record non-trivial decisions as ADRs (`docs/decisions/`) or ledger rulings; ask only for
  spec scope changes, publication/licensing/distribution, or anything touching the maintainer's own Blender install.
- Commit trailer: currently the model that wrote each commit (e.g. `Co-Authored-By: Claude Sonnet 5
  <noreply@anthropic.com>`) + the session's `Claude-Session:` line — see "Open question" above.

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
