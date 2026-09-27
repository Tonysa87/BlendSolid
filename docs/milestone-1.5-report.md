# Milestone 1.5 report — Build without selectors

## Success criterion

From `docs/spec.md`'s milestone table, milestone 1.5's success criterion, verbatim:

> A user builds the milestone 1 default part and a bracket with 3 holes using only parametric primitives
> (Shift+A), the Draw Solid tool (on a face or the grid; union/cut by drag direction) and booleans between
> parts with live cutters; every step is one undo step and one script edit

**Met by automated evidence**; the manual GUI test with the maintainer is under way (session of 2026-09-27: steps
1–11 and 14 done, with the fixes they led to; steps 12, 13, 15, 16 and the sign-off left for the next session).

- `tests/blender/test_success_criterion.py::test_build_the_default_part_and_a_bracket_with_three_holes` builds
  both parts with operators only (no hand-written script): the milestone 1 default part (box + boss, a Draw
  Solid union + a vertical fillet cut from a live-cutter boolean) and a bracket (base plate + upright flange via
  Draw Solid union, two Draw Solid cuts, one hole from a live cutter pin). Each of the 8 operator calls is
  wrapped in `one_step()`, which asserts it made **exactly one script edit** (a new single-feature part or one
  more feature in an existing part) and **exactly one undo step**, and additionally forces a recompute of the
  "after" script in flight before undoing (`runtime.tick()` right after the operator) to prove the stale-result
  guard discards it rather than applying it once the undo has reverted the script.
  - Default part volume: **24458.19 mm³** (`40·30·20 + π·6²·5 − (1 − π/4)·5²·20`, box + boss − vertical-fillet
    waste), matching the volume the worker's own template produces for `blendsolid.new_part()` within 0.5%.
  - Bracket volume: **18465.93 mm³** (`60·40·5 + 5·40·35 − 2·π·3²·5 − π·4²·5`, base + flange − two Draw Solid
    holes − one live-cutter pin hole), within 0.5%.
  - The live cutter is exercised both ways: moving the pin 0.1 mm out of the flange closes its hole
    (volume back up by `π·4²·5`); moving it back reopens it.
- `tools/gui_check.py` (below) drives the same 16 steps as the manual test plan in a real, unattended Blender
  window on both Linux and Windows, covering everything that doesn't need a real mouse or a person's judgement.

## Automated tests

Fresh run, `BL=~/blender/blender-5.2.2-linux-x64/blender tools/test.sh`:

```
105 passed in 19.29s     # unit tests, Blender's Python, no bpy
133 passed in 20.24s     # Blender tests, blender -b --factory-startup
```

Total **238 passed**, 0 failed, wall time ~40 s (`time tools/test.sh`: real 0m40.4s). After the fixes of the manual
test session (2026-09-27): **160 unit + 167 Blender = 327 passed**, 0 failed.

## What was built

**Primitives, redo panel, gizmos.** `blendsolid/primitives.py` is a small catalog (box, cylinder, sphere, cone,
torus, wedge) that says what build123d call each writes and where its parameter gizmos go; `ops_add.py` turns
each into a `blendsolid.add_<shape>` operator (`Shift+A → BlendSolid`, also six sidebar buttons) that writes a
brand-new canonical script centred on the 3D cursor's plane, trusted because it was created in the session. The
redo panel (`_draw_millimetres`) shows "Dimensions (millimetres)" with the shape's parameters as plain
`FloatProperty`s (ADR 0003: never `subtype="DISTANCE"`). Selecting a part shows light-blue arrow gizmos on its
parametrized faces (`gizmos.py`'s `GizmoGroup`, offsets computed by `arrow_matrices()`); dragging one writes the
new value straight to the script and pushes one undo step (`Gizmo.use_undo`); a scaled part shows "This part is
scaled" in the panel and the gizmo group stops drawing (parts must stay at scale 1: sizes live in the script).

**Draw Solid.** A `WorkSpaceTool` (`ops_draw.py`) with its own keymap: press-drag draws a rectangle or circle
base (header option chooses the shape) either on the grid at the 3D cursor's plane or on a BlendSolid part's
face (picked on mouse-down, wire-display cutters looked through so a target behind one can still be picked);
release, then moving the mouse away from/into the part sets the height and previews a `gpu`-drawn outline in
UNION or CUT mode depending on drag direction; a click finishes and calls the same `blendsolid.draw_solid`
operator interactively that a script or the redo panel would call non-interactively (Mode New/Union/Cut, shape,
placement and dimensions all become redo-panel properties). Esc/right-click cancel with no script change.
Holding Ctrl snaps every dimension to whole millimetres, Shift+Ctrl to tenths. A non-canonical or untrusted part
under the cursor is treated like empty space (M3 of the final review): the draw becomes a new part on its face
plane instead of silently failing at `execute()`.

**Booleans and live cutters.** `deps.py` resolves `ref("<id>")` inside a part's script into the worker request:
the selected non-active objects become cutters placed in the target's frame (with the millimetre unit factor),
folded into the target's cache tag so moving, rotating or reparametrizing a cutter recomputes the target through
the unchanged milestone 1 reconcile loop; the worker (`worker/runner.py`) resolves the same references and
caches built shapes by tag. `ops_boolean.py` adds `blendsolid.boolean` (Difference/Union/Intersect), bound to
`Ctrl+Numpad -/+/*` and an Object menu entry: selecting cutters then the target part and running it appends one
`insert(ref(id), mode=...)` feature to the target and turns every cutter into a non-renderable wireframe. Errors
(a cycle, a deleted or untrusted cutter, a scaled target or cutter) are reported in plain, script-free language
with an action a standard user can take (ADR 0002), never a Python exception.

**Canonical script structure, with an example.** Every part's script (`script_model.py`) is one `ast`-editable
shape: a parameter block, one `BuildPart()` with one line per feature (each tagged `# feature: <name>`,
optionally inside a `with Locations(...)`), and `result = part.part`. Here is the bracket the success test
builds, printed with `part.source_of(bracket)` (from a small headless run replaying the same operator calls):

```python
# BlendSolid part. The numbers below are its parameters (millimetres).
box_1_length = 60.0
box_1_width = 40.0
box_1_height = 5.0
box_2_length = 5.0
box_2_width = 40.0
box_2_height = 35.0
cut_1_radius = 3.0
cut_1_height = 5.0
cut_2_radius = 3.0
cut_2_height = 5.0

with BuildPart() as part:
    Box(box_1_length, box_1_width, box_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
    with Locations(Location((-27.5, 0.0, 5.0), (0.0, 0.0, 0.0))):  # feature: box_2
        Box(box_2_length, box_2_width, box_2_height, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations(Location((10.0, -10.0, 5.0), (0.0, 0.0, 0.0))):  # feature: cut_1
        Cylinder(cut_1_radius, cut_1_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    with Locations(Location((10.0, 10.0, 5.0), (0.0, 0.0, 0.0))):  # feature: cut_2
        Cylinder(cut_2_radius, cut_2_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    insert(ref("863071809be947efabb2916bc77794a0"), mode=Mode.SUBTRACT)  # feature: bool_1

result = part.part
```

(the hex string is the pin's part id, `Text["bs_part_id"]`, not shown to standard users — ADR 0002).

**Two milestone 1 leftovers (Task 4).** `blendsolid.recompute` now polls `False` (with a `poll_message_set`
explanation) on an untrusted part, instead of silently doing nothing; and `trust.py` closes the `-Y`/
`--disable-autoexec` gap on top of the existing preference check — a file opened with that command-line flag is
treated as untrusted even if *Auto Run Python Scripts* is on in the preferences (the remaining `-y`/"Allow
Execution" gap stays documented in ADR 0004 as accepted, safe-side risk).

## Packaging and smoke tests

Both zips are version **0.2.0** (includes the final review's fixes and the undo-mirror fix, db1171e):

| Platform | Zip | Size |
|---|---|---|
| Linux x64 | `dist/blendsolid-0.2.0-linux-x64.zip` | 255.1 MB |
| Windows x64 | `dist/blendsolid-0.2.0-windows-x64.zip` | 225.8 MB |

The Linux zip built during the final review fix wave (`43a62e5`/`02546e0`) predated the undo-mirror fix
(`db1171e`, found afterwards by the first `tools/gui_check.py` run); it was rebuilt and reinstalled in this
session, and the Linux smoke test re-run against the fresh install. The Windows zip already postdated the fix
(built and smoke-tested in the same session `db1171e` landed, per `gui-check-report.md`) and did not need a
rebuild.

Linux smoke (`$BL -b --python tools/smoke_installed.py`, rebuilt zip, this session):
```
first result after 3.8 s, volume 24454.7 mm³ (expected 24458.2), error: -
live cutter after 0.1 s, volume 11718.3 mm³ (expected 11717.3), error: -
SMOKE PASS
```

Windows smoke (`"$BW" -b --python tools/smoke_installed.py`, from the final fix wave, still current):
```
first result after 13.2 s, volume 24454.7 mm³ (expected 24458.2), error: -
live cutter after 0.1 s, volume 11718.3 mm³ (expected 11717.3), error: -
SMOKE PASS
```

## GUI check

The maintainer was unavailable for the manual test this session (a controller ruling, ledger Task 14); the 16
steps of the manual test plan were instead driven automatically, unattended, in a real Blender window
(`tools/gui_check.py`, `--enable-event-simulate`) on both platforms. Full detail, evidence and screenshots:
`.superpowers/sdd/2026-09-26-milestone-1.5-build-without-selectors/gui-check-report.md`.

| # | Step (plan Task 14, Step 1) | Linux | Windows | Manual (2026-09-27) |
|---|---|---|---|---|
| 1 | Shift+A → Box; redo panel; Adjust Last Operation | OK | OK | OK |
| 2 | Cursor rotation → cylinder on the tilted plane | OK | OK | OK after fix: display tessellation (ADR 0005) |
| 3 | Other primitives; Shift+A menu and sidebar content | OK | OK | OK after fix: display tessellation (ADR 0005) |
| 4 | Gizmos: 3 arrows, drag the height arrow, undo | OK | OK | OK |
| 5 | Scale warning; arrows disappear; undo | OK | OK | OK |
| 6 | Draw Solid on the grid → new part | OK | OK | OK (+ snap step ladder, sidebar access, worker warm-up) |
| 7 | Draw Solid on a face, union | OK | OK | OK after fixes: arrows captured the click; float32 placements |
| 8 | Draw Solid on a face, cut; redo Mode/Radius | OK | OK | OK after fixes: edge picking, curved-face clearance, normals |
| 9 | Ctrl / Shift+Ctrl snapping | OK | OK | OK |
| 10 | Esc / right-click cancel a drag | OK | OK | OK |
| 11 | Live cutter: boolean, move, rotate, edit radius | OK | OK | OK |
| 12 | Other booleans (Ctrl+Numpad +/*, Object menu) | OK | OK | booleans used OK; keys/menu/add-on conflicts pending |
| 13 | Draw through a wire cutter | OK | OK | pending |
| 14 | Deleted cutter (now restorable, see below) | OK | OK | OK (behaviour changed on request) |
| 15 | Undo to the empty scene, then redo everything | OK | OK | pending |
| 16 | Save, reopen untrusted, Trust Scripts, recompute | OK | OK | pending |

The Linux and Windows columns are the re-run of 2026-09-27 on the final code (`GUI CHECK PASS` on both; on
Windows the worker process was gone once Blender quit).

One bug was found and fixed this way (not by a person): the parameter panel could stay stale after an undo that
lands on a step pushed before the reconcile tick had mirrored the script into `blendsolid_params` (commit
`db1171e`; see "Deviations" below).

## Manual GUI test

Session of 2026-09-27 with the maintainer, portable Windows Blender (`E:\blender-5.2.2-windows-x64`), real mouse
and keyboard; results in the table above. Each problem found was reproduced with numbers, fixed test-first,
installed and re-checked by the maintainer before moving on:

- **Curved primitives looked faceted / had irregular triangles (steps 2–3).** BRepMesh's Delaunay in (u, v)
  space gives fans, slivers and a distorted seam band. Full faces of revolution are now structured grids
  (geodesic sphere, staggered rings), with a per-scene display tolerance (mm, default 1) replacing the absolute
  0.1 mm that made metre-sized parts heavy; exact vertex normals as custom normals remove shading bands on
  trimmed faces (ADR 0005).
- **Snapping (step 6, maintainer's request).** A step ladder 0.1 mm – 10 m changed with Ctrl+Wheel before or
  during a drag; Ctrl puts corners (a cylinder's centre) on grid nodes of the cursor plane or of the part's
  own grid on a face; a cross marks the node (orange over a part, white over the cursor plane). Draw Solid is
  also reachable from the sidebar; the worker starts when BlendSolid is first shown, so the first part doesn't
  wait ~2 s.
- **Selected part's arrows took the click meant to draw (step 7):** hidden while Draw Solid is active.
- **Skins and slivers in booleans drawn on faces (steps 7–8).** Placements carried float32 noise (mesh hit,
  `matrix_world`, `mathutils`, operator properties): 3e-05 mm skins, 90.000003° rotations. Flat faces' exact
  planes now come from the worker and placements are computed in float64 (`drawing.LocalPlane`).
- **A drag started on a part's corner made a new part (step 8):** rays a few pixels around the mouse are tried.
- **Cuts on curved faces left slivers (step 8):** the tangent plane touches a curved face along a line; such
  tools now reach past the face by a clearance.
- **Deleted cutters (step 14, maintainer's request, after research on Fusion 360 / HardOps / Onshape):** a
  deleted cutter keeps its script and placement and goes on cutting; the panel lists a part's booleans with
  Select, Restore and Remove. Suppress, Apply and cutter cycling are follow-ups (`docs/NEXT.md`).

Decisions recorded: ADR 0005 (display tessellation, tolerance, exact normals), ADR 0006 (Draw Solid snapping
and exact placements), ADR 0007 (live cutter lifecycle). Maintainer's session log: `spike/logs/gui-m1.5.log`.

Still for the next session: steps 12 (Ctrl+Numpad keys and the Object menu by hand, conflicts with other
add-ons), 13, 15, 16 (quit/restart with *Auto Run* off, the *Recompute* tooltip, Task Manager), then sign-off.

## Deviations from the design notes

The plan's own deviations from `docs/superpowers/plans/m1.5-design-notes.md` (unchanged by execution):

1. The part id lives on the part's script (`Text["bs_part_id"]`), not on the object, so identity follows
   Shift+D/Alt+D/Ctrl+L the same way `part.ensure_unique_scripts()` already does for the Text.
2. `insert(ref(...), mode=...)` instead of the deprecated `add(ref(...), mode=...)` (build123d 0.13).
3. The `-Y` gap is closed (`trust.autoexec_disabled_by_command_line`), not only documented.
4. Draw Solid's Ctrl/Shift+Ctrl snap to 1 mm/0.1 mm (part-local millimetres), not "grid increments" — Blender's
   zoom-dependent grid step isn't exposed to Python.
5. The drawing plane is picked on mouse-down, not highlighted while hovering before the click.
6. Primitives sit on the cursor's plane, base centred (`Align.CENTER, Align.CENTER, Align.MIN`), matching
   Blender's own Add Cube convention; the milestone 1 template keeps its `Align.MIN` box.

Plus the notes' open decisions, settled during planning: every linked duplicate (Alt+D) of a cutter cuts; Draw
Solid's redo-panel placement is always relative to the part it was drawn on; drawing on a non-BlendSolid face
makes a new part there; wire-display cutters are looked through when picking a face; the success test's fillet
is a live-cutter boolean (edge selectors are milestone 2); the extension version becomes 0.2.0.

**Controller rulings during execution** (full ledger: `.superpowers/sdd/2026-09-26-milestone-1.5-build-without-selectors/progress.md`):

- Preflight (F1–F13): a duplicated Text keeps a fresh id per later copy (F1); a Boolean with N cutters is one
  script edit appending N features (F2); Task 8's backward-compat test keeps milestone 1's literal tag formula,
  able to fail (F3); Task 4 runs unit/Blender RED stages separately (F4); an ADR edit position (F5); a
  `part_groups()` docstring wording (F6); shared helpers de-duplicated across tasks — `is_local_part`,
  `scaled_message`, a "not editable" message helper, `add_primitive_part(matrix=None)` (F7); shared Blender test
  helpers moved to `conftest.py` (F8); tool refusals for non-canonical scripts use one plain sentence, with
  detail only when scripts are shown (F9); Task 9 refuses a scaled target before `ensure_part_id` (F10); two
  comment fixes (F11); an unreachable branch dropped, shapes cached after tessellation (F12); the 6-decimal tag
  rounding risk accepted (F13).
- Per-task: the headless subprocess probe's plan-mandated duplication resolved by a shared `run_probe` helper
  (Task 4/5); nested-dependency matrices composed per instance, confirmed correct (Task 8); keymap registration
  works in `blender -b` (Task 9); `ops_draw.py`'s whole-file brief merged as additions (Task 11); viewport
  navigation passes through the Draw Solid modal, promoted from a reviewer minor because the GUI test needs to
  orbit while drawing (Task 11); `one_step()` forces the "after" recompute in flight before undoing, since
  Review Focus 1 binds (Task 12); the BRACKET volume constant, flagged as not independently checked by a
  reviewer, was recomputed and matches (Task 12, final review).
- **Final review fix wave** (`d7de2f9`, `43a62e5`, `02546e0`): **I1** Shift+D no longer hands a cutter's
  identity to the duplicate — ties broken by the primary object's age (`session_uid`), not name, so the oldest
  part keeps its script/id. **I2** the Draw Solid tool's keymap item gets `"any": True`, so Ctrl held before the
  press still starts a snapped drag. **I3** worker errors name cutters by object name (`"the cutter 'Pin' ..."`)
  instead of their 32-hex id, per ADR 0002; nested failures name the part that actually failed. **M1** primitive
  add operators poll `False` outside Object Mode. **M2** `DepError` texts use script-free, actionable wording
  ("undo the change (Ctrl+Z)"). **M3** a non-canonical or untrusted target is treated as empty space by Draw
  Solid's `pick_plane`, not accepted and then refused only at `execute()`. **M4** a cutter whose part id equals
  the target's (transient after Shift+D) is refused with a clear message instead of raising. **M5** the two
  scale tolerances (`part.is_scaled` 1e-6 vs. `deps.SCALE_TOLERANCE` 1e-5) are unified on one constant
  (`part.SCALE_TOLERANCE = 1e-5`).
- **The float32 rotation fix** (Task 7 fix round): `matrix_world` is float32; a rotation composed into OCCT's
  `gp_Trsf.SetValues` carried a tiny non-unit scale from that rounding and made booleans invalid. The worker
  (`runner._location`) now re-orthonormalizes rotations before building the transform.
- **The undo mirror fix** (`db1171e`, found by the first `tools/gui_check.py` run, not a person): an operator's
  undo step is pushed as soon as it writes the script, before the next reconcile tick mirrors the new
  parameters into `blendsolid_params`; undoing back to such a step restored a stale mirror that
  `runtime._synced` (keyed by script tag) would never re-sync. Fix: `undo_post`/`redo_post` clear `_synced` so
  every part is re-mirrored on the next tick.
- **This session's closing fixes** (own commit, `f4bb3a5`): `tools/gui_check.py` review findings (step 3's
  panel-drawn check now actually asserted, not just recorded; step 4 requires the dragged height to actually
  change and reports PARTIAL, not OK, without event simulation; steps 7/8 word the preview mode as UNION/CUT,
  not colours; step 12 also checks that Blender's default select_more/select_less keymap items did not run
  instead of the add-on's boolean); `CLAUDE.md`'s GUI-simulation pitfall corrected (events are delivered under
  WSLg with software OpenGL; only the screen read-back is black there).

## Findings / API facts

The "Known pitfalls (milestone 1.5)" section of `CLAUDE.md` (current):

- **Undo in background mode:** call `bpy.ops.ed.undo_push()` once, then run operators as
  `bpy.ops.x.y("EXEC_DEFAULT", True, ...)`; Python references to IDs die on undo.
- **Headless `matrix_world`:** call `bpy.context.view_layer.update()` after moving objects in a test.
- **build123d 0.13:** `add()` deprecated (use `insert()`); `Location((x,y,z),(a,b,c))` is intrinsic XYZ = Blender
  `Euler((a,b,c), "ZYX")`; `Wedge` rises along Y and applies `align` before `rotation`; `insert()` inside
  `with Locations(...)` is moved again by those locations.
- **Gizmos:** an arrow with `transform={"CONSTRAIN"}` and no `range=` callback segfaults Blender;
  `Gizmo.use_undo = True` gives one undo step per drag; gizmo groups don't appear in `bpy.types`.
- **`gpu` is not initialized in background mode:** import it inside draw callbacks only.
- `scene.ray_cast` hits wire-display objects (cutters) and returns world-space normals and original objects.
- **Undo restores stale derived data:** drop `runtime._synced` in `undo_post`/`redo_post`.
- **GUI checks:** `tools/gui_check.py` drives a real window with `--enable-event-simulate`; under WSLg with
  software OpenGL, simulated events ARE delivered, but the first press after a pause only focuses the window,
  and the on-screen framebuffer reads back black there (screenshots fall back to an offscreen render).
- An operator's `self.report({"ERROR"}, ...)` raises `RuntimeError` when called from Python.
- Blender's zoom-dependent grid step isn't available to Python (`overlay.grid_scale_unit` is only the base
  cell).
- Part identity is `Text["bs_part_id"]`: Shift+D copies get a new id, Alt+D/Ctrl+L share it.
- **`matrix_world` is float32:** the worker re-orthonormalizes rotations (`runner._location`).
- `part.is_local_part(obj)` is the one None-safe predicate for "writable local part".
- Headless tests of undo races must call `runtime.tick()` before `ed.undo()` to put a recompute in flight.

## Concerns / follow-ups

From the plan:
- Fixed placements (Draw Solid's target-relative `Location`) don't follow upstream geometry changes if the
  target's own earlier features move it later — research risk 2, not addressed this milestone.
- Recompute latency while dragging gizmos on complex parts is untested beyond this milestone's simple parts —
  research risk 1.
- No hover highlight of the face before a Draw Solid click (the snap cross shows the node and whether it is on a
  part) — a candidate for milestone 2 alongside face picking.
- "Apply" (inlining a cutter permanently into its target's script), per-boolean suppress and cutter cycling
  were not built (`docs/NEXT.md`).
- Trimmed curved faces are still triangulated by BRepMesh: right shading (exact normals), sliver wireframe.

Parked items from the ledger, worth keeping in view:
- A `SyntaxError` in a cutter's script still shows the compile filename as `"<ref <id>>"` to a user editing
  scripts (`worker/runner.py`); only reachable with *Show history scripts* on — milestone 2.
- Group age for `ensure_unique_scripts`/`ensure_unique_part_ids` is read from the primary object chosen by
  name-first tie-break, not `min(session_uid)` directly, in one place (`part.py` ~299/329); same result for
  every real case (a Shift+D copy is always newest) — noted, not fixed.
- Appending or pasting the same target+cutter pair twice makes the second target cut by the first copy's
  cutter (pre-existing id semantics) — milestone 2 follow-up (remap `ref` ids of incoming groups).
- `ref(...)` is re-parsed with `ast` every reconcile tick for parts that use it, with no performance test
  against many cutters; caching `references()` by source is a candidate if this ever shows up in profiling.
- Tag stability for scale/placement still relies on 6-decimal rounding (F13): accepted as never producing a
  wrong result, only an occasional spurious recompute on reopening a file.
- Draw Solid's height reads 0 when the view is exactly along the face normal (`height_along_normal`); the
  manual test session should use an angled view for that stage, as noted in `docs/NEXT.md`.
- The cone primitive's `top_radius` has `min=0.001`, so a perfectly pointed cone can't be dialled in from the
  panel (only from 0 at creation).
- `gizmos._layout_cache` is never pruned (harmless growth, deferred).
- The commit-trailer rule (a fixed model line vs. the model that actually wrote each commit) is still an open
  question for the maintainer — see `docs/NEXT.md`.

## Files changed in this closing session

- `CLAUDE.md` — merged the "GUI checks"/"GUI automation" pitfalls into one accurate entry.
- `tools/gui_check.py` — review fixes (panel-drawn assertion, height-change assertion, PARTIAL status without
  event simulation, UNION/CUT wording, select_more/select_less check in step 12).
- `docs/milestone-1.5-report.md` (new, this file).
- `README.md` — milestone 1.5/2 status, "Try it" for 0.2.0.
- `docs/NEXT.md` — bookmark for the next session.
- `spike/logs/gui-check-*.log` — re-recorded evidence (Linux re-run this session; the others carried over
  unchanged from the GUI-check task).
