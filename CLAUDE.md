# BlendSolid

Open source (GPL) CAD/NURBS add-on for **Blender 5.2 LTS** (Python 3.13).
Extension id and Python package: `blendsolid`. Full spec: `docs/spec.md` — read it before working.

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
