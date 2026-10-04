# BlendSolid

Open source (GPL) CAD/NURBS add-on for **Blender 5.2 LTS** (Python 3.13).
Extension id and Python package: `blendsolid`. Full spec: `docs/spec.md` — read it before working.

**Resuming work? Read `docs/NEXT.md` first** (current state, next step, working agreement).

## Language

Everything in the repository is in **English**: docs, code comments, docstrings, UI/log strings, commit messages.
Chat with the maintainer is in Italian.

## Spec summary

- Exact BRep/NURBS modeling in Blender, **OCCT kernel via OCP** (`cadquery-ocp-novtk` 8.0.1, cp313 wheels).
- **History = build123d script** stored in the `.blend`; every viewport action writes/edits lines of the script.
  Face/edge references are provenance references (ADR 0009): `face("box_1", "+Z")`, `edge_between(...)`,
  `near=` tie-breaks; a reference that names nothing is an error, a doubtful one a warning (never re-bound).
- **100% native Blender UI:** standard transform gizmo via Empty proxies, native gizmos bound to parameters,
  Geometry Nodes gizmos, `WorkSpaceTool`, picking via BRep IDs stored as mesh attributes + `ray_cast`.
- **Separate process** for OCCT computation (Blender doesn't support Python threads): the worker returns the
  tessellated mesh + face/edge map.
- Distribution: GitHub-hosted Blender extension repository, one zip per platform (~220–255 MB, ADR 0001);
  extensions.blender.org (max 100 MB per zip) only with a lighter build, still to be decided.
- Milestones: 0 spike → 1 history as code → 1.5 build without selectors → 2 selectors from clicks (0–2 done)
  → 3 complete hard-surface modeling (3a sketch + extrude/revolve + STEP I/O, usage checkpoint, 3b–3e)
  → 4 SubD→NURBS → 5 G2 surfaces → 6 G2 fillets; publication on extensions.blender.org only at the end.

## Project rules

- One milestone at a time; don't write code beyond the current milestone.
- Every geometric result is verified with numbers (`BRepCheck`, volumes, counts), not by eye.
- Headless Blender tests (`blender -b`) wherever possible; manual tests only for gizmos, UX and undo, with precise steps.
- A failure is never worked around silently: document the reason and propose alternatives.
- Never touch the maintainer's installed Blender: development and tests use the **portable** copy.
- GPL license; dependencies must be compatible (OCCT LGPL, build123d Apache 2.0).

## Environment

- Development from WSL2 (`/home/tony/Projects/BlendSolid`), Blender runs on Windows 11.
- Installed Blender (do NOT use for tests): `C:\Program Files\Blender Foundation\Blender 5.2` (5.2.2 LTS).
- Windows portable Blender (tests and GUI): `E:\blender-5.2.2-windows-x64` (`portable\` folder next to `blender.exe`).
  OCP for the spike scripts: `E:\blender-5.2.2-windows-x64\spike_site` (pip --target).
- Linux Blender (headless development in WSL): `~/blender/blender-5.2.2-linux-x64`, OCP in `.../spike_site`.
- Paths passed to the Windows Blender from WSL must be converted with `wslpath -w`.
- To log a GUI session launched from WSL, redirect straight to a file (`> log 2>&1`), not through `tr` (it buffers).

## Useful commands

```bash
BW=/mnt/e/blender-5.2.2-windows-x64/blender.exe          # Windows
BL=~/blender/blender-5.2.2-linux-x64/blender              # Linux (WSL)
PY=~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13   # Blender's own Python (pip downloads wheels)

tools/setup_dev.sh      # once: .dev/worker_libs (build123d + deps) and .dev/pytest for Linux Blender
tools/test.sh           # unit tests (Blender's Python) + Blender tests (blender -b); extra args go to pytest

# tools/build_extension.py: builds one platform's extension zip, worker libraries bundled in worker_libs
"$PY" tools/build_extension.py --platform linux-x64 --blender "$BL"     # → dist/blendsolid-<version>-linux-x64.zip
"$PY" tools/build_extension.py --platform windows-x64 --blender "$BL"   # → dist/blendsolid-<version>-windows-x64.zip
"$BL" --command extension install-file -r user_default -e dist/blendsolid-<version>-linux-x64.zip
"$BW" --command extension install-file -r user_default -e "$(wslpath -w dist/blendsolid-<version>-windows-x64.zip)"
# tools/smoke_installed.py: no --factory-startup (installed extensions are enabled through preferences)
"$BL" -b --python tools/smoke_installed.py                       # prints SMOKE PASS/FAIL, Linux
"$BW" -b --python "$(wslpath -w tools/smoke_installed.py)"       # prints SMOKE PASS/FAIL, Windows

"$BL" -b --factory-startup --python spike/<script>.py                      # headless test, Linux
"$BW" -b --factory-startup --python "$(wslpath -w spike/<script>.py)"     # headless test, Windows
"$BW" --factory-startup --python "$(wslpath -w spike/gui_session.py)" > spike/logs/gui.log 2>&1   # GUI session
```

## Layout

- `blendsolid/` — the extension (Blender side: operators, tools, gizmos, part/mesh handling, worker client);
  `blendsolid/worker/` — the OCCT worker process (script runner, provenance, blends, tessellation/meshing).
- `tests/unit/` — tests run with Blender's Python, no bpy; `tests/blender/` — tests run in `blender -b`.
- `tools/` — dev setup, test runner, extension build, smoke test, `gui_check.py` (real-window GUI check).
- `docs/spec.md` — spec; `docs/NEXT.md` — bookmark (state, next step, working agreement);
  `docs/decisions/` — ADRs (index in its README); `docs/research/` — research notes;
  `docs/milestone-*-report.md` — milestone reports.
- `SPIKE_REPORT.md` — spike results (PASS/FAIL, evidence, timings, proposed spec changes).
- `spike/` — throwaway experiments and measurement scripts (milestone 0 spike, `m2_*` scratch tools).
- `.dev/` — local worker libraries and pytest for development (git-ignored); `logo/` — the maintainer's logos.
- `wheels/`, `dist/` — downloaded wheels and built zips (git-ignored).

## Known pitfalls (from the spike)

- OCP 8: `OCP.collections.IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher` (not `TopTools_IndexedMapOfShape`),
  `TopoDS.Face(x)` (not `TopoDS.Face_s`).
- Blender 5.2: GN modifier inputs = `mod.properties.inputs.<identifier>.value` (no longer IDProperties).
- `matrix_world` is not evaluated in `undo_post`: reconcile state only in `depsgraph_update_post`.
- build123d ships with all its dependencies (~220–255 MB per platform), loaded **only in the worker** from a private
  library folder, distributed from GitHub (ADR 0001). A lite build for extensions.blender.org is documented there.
- Extension site-packages precede Blender's in `sys.path`: a bundled wheel of a module Blender ships
  (e.g. `typing_extensions`) overrides it for Blender and all add-ons.
- extensions.blender.org forbids installing packages at runtime and changing Blender's `sys.path`/`sys.modules`.
- build123d `Text` with the OS default font is not reproducible across platforms: always pass a bundled `font_path`.

## Known pitfalls (milestone 1)

- **Script trust (ADR 0004):** a part script is arbitrary Python. Parts of a loaded file run only if
  *Auto Run Python Scripts* is on and the file isn't under `preferences.autoexec_paths` (a `PathCompare`
  collection on `preferences`, not on `filepaths`), or after *Trust Scripts in This File* (session only).
  Scripts created in the session are trusted by `Text.session_uid`. Headless tests run with
  `--factory-startup` (Auto Run off): loaded parts are untrusted there unless a test turns it on.
- **Edit Mode:** a mesh in Edit Mode can't be rebuilt (`Cannot add vertices in edit mode`); check
  `mesh.is_editmode` (covers every object sharing the mesh) before submitting or applying a result.
- **Units (ADR 0003):** scripts are in millimetres; meshes are scaled by `0.001 / scene.unit_settings.scale_length`
  and that factor is part of the mesh tag. Compare volumes in mm³ (`mesh_volume / factor**3`).
- Group parts by ID identity (`session_uid`), never by name: a linked library ID can share a local ID's name.
  Library parts are read-only; look local objects up with `bpy.data.objects.get((name, None))`.
- Add-ons enabled at startup register while `bpy.data` is restricted (no `bpy.data.filepath`): `register()`
  must not read it; `load_post` follows.
- `bpy.data.texts.new()` gives the Text a fake user; clear it or deleted parts leave their scripts in saved files.
- Worker libraries are pinned by `tools/worker-constraints.txt` (`pip -c`); pip evaluates environment markers
  for the build host, not the `--platform` target.

## Known pitfalls (milestone 1.5)

- **Undo in background mode:** call `bpy.ops.ed.undo_push()` once, then run operators as
  `bpy.ops.x.y("EXEC_DEFAULT", True, ...)` (the `True` pushes the undo step); `bpy.ops.ed.undo()`/`redo()` then
  work. Python references to IDs die on undo: look objects up again by name.
- **Headless `matrix_world`:** after moving objects in a test call `bpy.context.view_layer.update()`.
- **build123d 0.13:** `add()` is deprecated, use `insert()`; `Location((x, y, z), (a, b, c))` is intrinsic XYZ =
  Blender `Euler((a, b, c), "ZYX")`; `Wedge` rises along Y and applies `align` before `rotation`; `insert()` inside
  `with Locations(...)` is moved again by those locations.
- **Gizmos:** an arrow with `transform={"CONSTRAIN"}` and no `range=` callback segfaults Blender;
  `Gizmo.use_undo = True` gives one undo step per drag; gizmo groups don't appear in `bpy.types`.
- **`gpu` is not initialized in background mode:** import it inside draw callbacks only.
- `scene.ray_cast` hits wire-display objects (cutters) and returns world-space normals and original objects.
- **Undo restores stale derived data:** an operator's undo step is pushed before the next tick updates data
  derived from the script (the parameter mirror), and memfile undo only reloads IDs that differ between steps.
  Python caches keyed by script tag (`runtime._synced`) must be dropped in `undo_post`/`redo_post`.
  The mesh too: undoing to "add a part" gives an empty mesh; `runtime._meshes` keeps recent results and the
  undo handler puts them back before the redraw (from the tick, the Adjust Last Operation panel still flashed).
- **GUI checks:** `tools/gui_check.py` drives a real window with `--enable-event-simulate`; under WSLg with
  software OpenGL (`WAYLAND_DISPLAY= LIBGL_ALWAYS_SOFTWARE=1 blender --gpu-backend opengl`) simulated events
  ARE delivered (contrary to an earlier finding), but the first simulated press after a pause only focuses the
  window (a throwaway press/Esc must precede the real one there), and a selection made from Python is not an
  undo step (push one, as a click does). The on-screen framebuffer reads back black in that session, so
  screenshots fall back to an offscreen render (`gpu.types.GPUOffScreen`) when `screen.screenshot` comes back
  blank.
- An operator's `self.report({"ERROR"}, ...)` raises `RuntimeError` when the operator is called from Python.
- Blender's zoom-dependent grid step isn't available to Python (`overlay.grid_scale_unit` is only the base cell).
- Part identity is `Text["bs_part_id"]` (part.py): Shift+D copies get a new id, Alt+D/Ctrl+L share it.
- **`matrix_world` is float32:** a rotation passed to OCCT's `gp_Trsf.SetValues` gets a tiny non-unit scale and
  booleans become invalid; the worker re-orthonormalizes rotations (`runner._location`).
- `part.is_local_part(obj)` is None-safe and is the one predicate for "writable local part"
  (`poll()` receives `context.object = None`).
- Headless tests of undo races must call `runtime.tick()` before `ed.undo()` to put a recompute in flight
  (timers don't fire in background mode).
- OCP 8: `Bnd_Box.Get()` can't be called (unregistered return type); use `SquareExtent()`/`CornerMin()`.
- A scratch script named like a stdlib module (`inspect.py`) next to a script breaks numpy imports in Blender's
  Python ("No module named 'bpy'"): name probes `bl_*.py`.
- Blender exposes no modifier-key state outside a modal operator (not on `Window`, not in `Gizmo.test_select`):
  hover feedback that depends on Ctrl can't be done from a tool's gizmo.
- The worker starts in ~0.16 s (blocking) and loads its libraries in ~2 s more (async); `runtime.warm_up()`
  starts it on intent (sidebar panel, Shift+A menu, Draw Solid tool) so the first part doesn't wait.
- **float32 everywhere on the Blender side:** mesh coordinates, `matrix_world`, `mathutils` matrices and Eulers
  (π becomes 180.000005°) and operator Float properties. Anything written into a part script must be computed
  in Python floats: Draw Solid uses the worker's exact face planes (`part.face_plane`, `drawing.LocalPlane`,
  `euler_zyx`) and keeps the exact placement in the hidden `exact` property. Off-by-1e-5 placements leave
  skins and slivers in OCCT booleans.
- `scene.ray_cast` misses exactly on a face's edge or corner (not watertight): pick with a few-pixel ring of
  extra rays (`ops_draw.pick(near=...)`).
- **Scripts write numbers with 6 decimals**, but a face can sit off that grid (a wall at `c ± w/2`): a placement on
  a face's exact plane is written with 10 decimals (`FeatureSpec.exact`), or the feature starts 5e-07 mm off
  the face (past OCCT's 1e-07 tolerance) and leaves a skin.
- `bpy.utils.register_tool(after=<a tool inside a group>, separator=True)` puts a `None` inside that group and
  Blender's own toolbar code raises; pass `group=True` for a button of its own after the group.
- The WSLg offscreen screenshot renders the scene only (no draw handlers or gizmos): to see an overlay, draw it
  into the `GPUOffScreen` after `draw_view3d` with the view/window matrices loaded; on Windows `gui_check`'s
  screenshots are of the real window and include overlays.

## Known pitfalls (milestone 2)

- **Bevel's Clamp Overlap** (on by default) clamps the *whole* bevel to its tightest spot: short chords of a
  triangulated flat cap or of ears along an arc make a 1 mm bevel remove almost nothing. Flat faces are one
  polygon, or convex polygons around holes with collars of radial quads around curved holes (ADR 0008 and its
  addendum); check any new tessellation with clamp on vs off.
- **Picking with modifiers:** `scene.ray_cast` returns polygon indices of the *evaluated* mesh; read attributes
  from `obj.evaluated_get(depsgraph).data`. Modifiers keep `brep_face_id` on new faces (copied from their source
  face), so an Array copy has the id but not the position: check the hit lies on the face's exact plane.
- Custom normals of welded meshes live on the CORNER domain; a mesh saved with the old POINT-domain
  `custom_normal` must have it removed before creating the CORNER one (`part._attribute`).
- OCP 8 ancestor maps: `OCP.collections.IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher`
  (not `TopTools_IndexedDataMapOfShapeListOfShape`); `TopExp.MapShapes` returns `TopoDS_Shape`: cast with
  `TopoDS.Face(...)` before `BRepAdaptor_Surface`.
- build123d 0.13 keeps a `ShapeHistory` (`_history`, with `before`/`brought` inputs) on the part after every
  BuildPart operation: provenance can be read from it without patching build123d (`spike/m2_s01_provenance.py`).
- OCCT's fillet always propagates along tangent chains: filleting one edge of a tangent chain rounds the chain
  (the default part's top-front edge is tangent, through the template fillet's arc, to the -X top edge).
- `context.preferences.system.ui_scale` is 0.0 in background mode: use `ui_scale or 1.0` for pixel thresholds.
- `gui_check.py -- --only 17,18` runs single steps; a step that makes parts from Python must push an undo step
  (`ed.undo_push`) before testing undo, or the undo goes back past the part.
- **Display tessellation (ADR 0005, ADR 0010):** BRepMesh triangulates curved faces with Delaunay in (u, v) space
  and gives fans, slivers and a distorted seam band that no parameter fixes, so every face is meshed from one
  shared edge discretization (`worker/meshing.py`); BRepMesh is only a loud fallback. The tolerance is a scene
  setting (mm, default 1) and part of the tag. OCCT's vertex blends (fillet corner patches) have
  curvature spikes (radius 0.07 mm) and vanishing derivatives: never size a grid from the raw max curvature.
  Any density rule needs a cap (cells per face, intervals per edge, growth while matching sides): an unbounded
  one hung the worker in the GUI. Fuzz random cut+fillet parts (`display_mesh` time, closed mesh) after changes.
- BRepMesh with `Angle = a` turned curves by about a/2 per segment (a 10 mm circle at 0.3 rad: 42 segments):
  ADR 0010 keeps that density (`seg_angle = ang_defl / 2`); tests on normals and fillet volumes depend on it.
- **Any change to the display mesh must bump `part.MESH_FORMAT`** (part of every mesh tag), or saved files keep
  the old mesh (the 10° face-point change missed it at first).

## Known pitfalls (milestone 3a)

- build123d objects (`Rectangle`, `Circle`...) inside `with BuildPart()` raise "BuildPart doesn't have a Rectangle
  object": the `sketch()` context manager clears `build_common._build_scope` for its body.
- `BuildPart().part` is `None` until something solid is added: the provenance hook and the runner accept parts
  that are only sketches (empty mesh; `fill_mesh` must handle 0 polygons).
- build123d's `extrude_until` (`Until.NEXT`) stops at the face the profile lies on ("Extrusion is None"), and its
  `taper` lofts B-spline sides for negative angles, holes or reversed directions: `worker/sketches.py` has its own.
- `BRepAlgoAPI_Splitter` leaves dangling sketch lines inside faces as INTERNAL edges in an extra wire whose
  `edges()` is empty: rebuild region faces from the outer wire and closed inner wires.
- Operator properties persist between calls: options that each call must start without (extrude's taper,
  extent) are `SKIP_SAVE`.
- New WorkSpaceTools after `blendsolid.push_pull_tool` join the Draw Solid group: `separator=True` there puts a
  `None` in the group (test_toolbar_groups_have_no_holes).
- build123d's `sweep()` defaults to `Transition.TRANSFORMED` (invalid solids at sharp path corners) and its
  `normal=` fixes the trihedron (zero-volume solid): grooves call `BRepOffsetAPI_MakePipeShell` with
  `SetMode(gp_Dir(sketch normal))` and RightCorner/RoundCorner; the profile must sit on the path's start point,
  square to the path.
- Sketch curve ends rounded to 6 decimals miss each other by up to 5e-7 mm: the region splitter uses a 1e-5 mm
  fuzzy value; snap points are rounded to 9 decimals (5.000000000000001 -> 5.0).
- gui_check's `warm_up()` clicks at the world origin: steps whose view is elsewhere pass `warm_up(at=...)`.
- Polylines of a wire for display: sample each edge from its own start (`worker/sketches._polyline`); sampling the
  whole wire by length cuts its corners off.
- Blender's keypad digits are `NUMPAD_0`..`NUMPAD_9` (row digits `ZERO`..`NINE`): a wrong event name never matches
  and raises nothing; check key tables against `bpy.types.Event.bl_rna.properties["type"].enum_items`.
- A label from a 3D gizmo's `draw()` needs pixel matrices first (`ops_draw.draw_text_lines(..., pixel_space=True)`).
- **OCCT taper pitfalls (bug sweep 2026-10-04):** `BRepOffsetAPI_DraftAngle.Build()` can hang (a crescent at 5°)
  holding the GIL, so no in-worker watchdog can stop it; a valid-looking draft can be wrong past a vanishing
  section (BRepCheck and `BOPAlgo_ArgumentAnalyzer` don't tell). `BRepOffsetAPI_MakeOffset.Perform` **segfaults**
  on some faces (never call it in the worker without a reason to risk the process) and applies sub-shape
  locations twice.

## Known pitfalls (session 15, 2026-10-04)

- **OCCT's fuse of heavily overlapping solids can return a valid but wrong solid** (BRepCheck passes, volume off
  by up to 99%): sweep pieces are fused only through `sketches._fused`, which verifies the union (`_union_ok`).
  Likewise a one-go `MakePipeShell` sweep whose band overlaps itself passes BRepCheck with a wrong volume.
- Check groove volumes with `spike/m3_bug_sweep/groove_check/oracle.py` (point membership + Monte Carlo,
  independent of OCCT's sweeps), not only BRepCheck; look at meshes with `tools/mesh_shot.py` (shaded + wireframe).
- `pkill -f <pattern>` kills the calling shell when the pattern appears in its own command line (exit 144): use
  `pgrep -f "[r]erun.py"`-style patterns and never relaunch in the same command.
- OCCT/numpy children use many cores each (~900% CPU): pin batch runs with `taskset -c` (rerun.py does).
- build123d `Shape.intersect()` may return a `ShapeList` (use `.solids()`); `shape.edges()` builds new objects on
  every call (identity tests like `e is run.edges()[-1]` are always False).
- On multi-metre parts float32 welding joins the ends of OCCT's micro-edges (6e-5 mm): `tessellate._drop_repeats`.
- BRepMesh can leave a face without triangulation: the display falls back to the lenient recovery, never fails.
