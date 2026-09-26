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
  Face/edge references are semantic selectors; fallback to OCCT Generated/Modified history + geometric matching.
- **100% native Blender UI:** standard transform gizmo via Empty proxies, native gizmos bound to parameters,
  Geometry Nodes gizmos, `WorkSpaceTool`, picking via BRep IDs stored as mesh attributes + `ray_cast`.
- **Separate process** for OCCT computation (Blender doesn't support Python threads): the worker returns the
  tessellated mesh + face/edge map.
- Distribution: GitHub-hosted Blender extension repository, one zip per platform (~220–255 MB, ADR 0001);
  extensions.blender.org (max 100 MB per zip) only with a lighter build, still to be decided.
- Milestones: 0 spike → 1 history as code → 2 selectors from clicks → 3 publishable MVP → 4 SubD→NURBS
  → 5 G2 surfaces → 6 G2 fillets.

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
spike/s08_build_extension.sh                                               # per-platform zips in dist/
"$BW" -c extension install-file -r user_default -e "$(wslpath -w dist/<zip>)"
```

## Layout

- `docs/spec.md` — spec draft.
- `spike/` — throwaway code for milestone 0.
- `SPIKE_REPORT.md` — spike results (PASS/FAIL, evidence, timings, proposed spec changes).
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
- **GUI checks:** `tools/gui_check.py` drives a real window with `--enable-event-simulate`; the first simulated
  press only focuses the window, and a selection made from Python is not an undo step (push one, as a click does).
- An operator's `self.report({"ERROR"}, ...)` raises `RuntimeError` when the operator is called from Python.
- Blender's zoom-dependent grid step isn't available to Python (`overlay.grid_scale_unit` is only the base cell).
- Part identity is `Text["bs_part_id"]` (part.py): Shift+D copies get a new id, Alt+D/Ctrl+L share it.
- GUI automation: `--enable-event-simulate` events were not delivered in a WSLg session with software OpenGL
  (`WAYLAND_DISPLAY= LIBGL_ALWAYS_SOFTWARE=1 blender --gpu-backend opengl` does run the GUI, e.g. to smoke-test
  draw callbacks and gizmo `draw_prepare`).
- **`matrix_world` is float32:** a rotation passed to OCCT's `gp_Trsf.SetValues` gets a tiny non-unit scale and
  booleans become invalid; the worker re-orthonormalizes rotations (`runner._location`).
- `part.is_local_part(obj)` is None-safe and is the one predicate for "writable local part"
  (`poll()` receives `context.object = None`).
- Headless tests of undo races must call `runtime.tick()` before `ed.undo()` to put a recompute in flight
  (timers don't fire in background mode).
