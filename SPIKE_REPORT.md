# BlendSolid — Spike report (milestone 0)

Date: 2026-09-26. Environment: Windows 11 + WSL2 (Ubuntu 24.04), Blender 5.2.2 LTS (Windows portable in
`E:\blender-5.2.2-windows-x64`, Linux in `~/blender/blender-5.2.2-linux-x64`), Python 3.13.13,
`cadquery-ocp-novtk` 8.0.1.0.0.

| # | Goal | Result | Verified on |
| --- | --- | --- | --- |
| 1 | Install and import OCP without DLL conflicts | **PASS** | Win headless + GUI, Linux headless |
| 2 | Box + cylinder, boolean, fillet, tessellation → mesh | **PASS** | Win + Linux headless, visual check in GUI |
| 3 | BRep face ID attribute + picking with `ray_cast` | **PASS** | headless (every face) + manual clicks in GUI |
| 4 | Empty proxy → push face (gizmo, `G Z 5`) | **PASS** | manual test, Windows GUI |
| 5 | Undo after push face | **PASS with caveats** | manual test + consistency log |
| 6 | GN gizmo (`GizmoLinear`) + handler → OCCT recompute | **PASS** | manual test, Windows GUI |
| 7 | Worker in a separate process, timings | **PASS** | Win + Linux headless |
| 8 | `--split-platforms` package, Windows zip size | **PASS** (47.7 MB) | built on Linux, installed + tested on Win and Linux |

**Outcome:** the technical constraints in the spec can be met, with **one big unexpected exception**:
build123d with its dependencies weighs ~200 MB per platform and does not fit the 100 MB limit
(see "Issues" and "Spec changes").

The logs in `spike/logs/` are the raw output recorded during the tests, so their messages are in Italian
(the scripts were translated to English afterwards).

## Details per goal

### 1. Installing and importing OCP — PASS

- `pip --target spike_site cadquery-ocp-novtk==8.0.1` with Blender's Python also installs the
  **`cadquery-ocp-proxy`** dependency (not mentioned in the spec). On disk: Windows 168 MB, Linux 382 MB.
- Import OCP + 10×20×30 box: volume 6000, `BRepCheck` valid. Import time 0.33–0.41 s.
- **DLLs:** the wheels are "repaired" with delvewheel/auditwheel, so every DLL carries a hash suffix
  (`freetype-8a5d….dll`, `Imath-9b9c….dll`). Blender loads its own `Imath.dll`/`OpenEXR.dll` from `blender.shared\`
  and OCP loads its own: **they coexist in the same process** with no name collisions (list of loaded modules taken
  with `EnumProcessModules` before and after the import).
  **TBB:** OCP neither ships nor loads TBB (it uses OpenMP, `vcomp140`): no conflict with Blender's `tbb12.dll`.
  **freetype:** Blender links it statically; OCP's copy is loaded under its own name.
- OCP ships its own `msvcp140-<hash>.dll` next to Blender's `MSVCP140.dll`: two C++ runtimes in one process,
  no problems observed (only relevant if C++ objects were ever passed between the two).
- Same result with the GUI running (viewport, fonts) and on Linux.
- Logs: `spike/logs/01_*.log`. Script: `spike/s01_import_ocp.py`.

### 2. Solid → Blender mesh — PASS

- Model (`spike/occ_model.py`): 40×30×20 box ∪ r=6 h=25 cylinder, r=5 fillet on the vertical edge at (0,0).
- `BRepCheck` valid; BRep volume 24458.186 = analytical 24000 + π·36·5 − (1−π/4)·25·20 (error < 1e-6).
  Volume computed from the mesh: 24454.7 (−0.014 %, due to tessellation) → triangles correctly oriented.
- 10 BRep faces, 324 vertices, 308 triangles. Vertices are not shared between faces: smooth inside a face,
  sharp between faces, no split normals needed.
- Visual check in the GUI (maintainer): OK.
- Scripts: `spike/s02_s03_mesh_pick.py`, `spike/bl_bridge.py`. Logs: `spike/logs/02_03_*.log`.

### 3. Picking — PASS

- `brep_face_id` attribute (INT, FACE domain) written with `foreach_set`.
- Headless test: for every BRep face, one `scene.ray_cast` from outside; the ID read from the hit polygon's attribute
  is the expected one on 10/10 faces, also with the object moved and rotated. **Mesh-independent check:**
  the hit point's distance to the BRep face (`BRepExtrema_DistShapeShape`) is 0 on planes and ≤ 0.015 on cylinders
  (linear deflection 0.1).
- Manual test (`BS Pick Face` modal operator, clicks in the viewport): 15 clicks, all with IDs consistent with the
  geometry (x=0 → face 0, top z=20 → 1, cylinder top z=25 → 9, y=0 → 5, y=30 → 3, x=40 → 6).
- UX note: the clicked face is not highlighted in Object Mode (the spike only selects polygons, visible in
  Edit Mode). Milestone 1 needs a `gpu` overlay.

### 4. Proxy and push face — PASS

- Empty `BS_Proxy_Top` on the box's top face. A `depsgraph_update_post` handler projects its motion onto the
  normal and recomputes: prism of the face + fuse/cut + `ShapeUpgrade_UnifySameDomain`.
- Maintainer: `G Z 5` and dragging with the Move gizmo **"all perfect"**. Live recompute on every mouse move:
  750 proxy-driven recomputes in the session, OCCT median 10.0 ms, p95 11.1 ms, max 12.4 ms; mesh update 0.2–0.7 ms.
- Pushing down to −26.7 (past the bottom of the box): OCCT doesn't fail, it just returns the remaining cylinder.
  No error, but results need validation (see spec changes).
- Face IDs are **not stable** across recomputes (the top face goes from ID 1 to 6 after a push): the proxy finds
  its face again with a geometric query (plane with +Z normal at the box height). This directly confirms the
  selector problem (milestone 2).

### 5. Undo — PASS with caveats

Maintainer: `Ctrl+Z` / `Ctrl+Shift+Z` after push and after the GN gizmo: **"all ok"**, no visible inconsistency.
The consistency log (`undo_pre`/`undo_post`/`redo_post` handlers) shows two important facts, though:

1. **Proxy undo:** Blender's memfile undo restores the Empty's position, the custom properties (applied parameters)
   and the mesh **together**. After every undo/redo mesh and parameters match (mesh volume = expected volume)
   and no recompute is needed. **However**, inside `undo_post` `proxy.matrix_world` is not evaluated yet
   (it reads identity → push −20 instead of +3.8). A recompute triggered from `undo_post` reading `matrix_world`
   **would corrupt the state**. The spike only recomputes in `depsgraph_update_post`, where the value is correct.
2. **GN gizmo undo:** the undo step is stored **before** the handler processes the last value change.
   The derived state stored in the step lags by one event (e.g. applied height 24.244 vs GN input 24.359).
   The handler notices and recomputes immediately (~5 ms): on screen everything is consistent, but the derived
   state stored in the undo step can't be trusted.

**Resulting rule:** the controls (proxies, GN inputs) and, later, the script are the single source of truth;
mesh and applied parameters are a cache reconciled in `depsgraph_update_post`. Never make decisions in
`undo_post` based on evaluated data.

### 6. Geometry Nodes gizmo — PASS

- Node group `BS_Params` with `GeometryNodeGizmoLinear`: Value ← "Cylinder Height" input, Position on top of the
  cylinder, Transform joined into the output. The modifier passes the mesh through unchanged.
- The handler reads the value and recomputes with OCCT. Maintainer: dragging and undo **ok**. 416 GN-driven recomputes.
- **API change in 5.2:** modifier inputs are no longer IDProperties (`mod["Socket_1"]` →
  `TypeError: this type doesn't support IDProperties`); use `mod.properties.inputs.Socket_1.value`.
- `GizmoDial` (Value, Position, Up, Screen Space, Radius) and `GizmoTransform` (matrix Value, per-axis flags)
  are also available: suitable for library element parameters.

### 7. Worker in a separate process — PASS

`spike/worker.py`: child process running Blender's own `python`, stdin/stdout pipes, length-prefixed messages,
numpy arrays as raw bytes. Medians over 20–30 recomputes (build + tessellation + Blender mesh):

| Case | Platform | Direct | Warm worker | of which IPC | Overhead | Cold start |
| --- | --- | --- | --- | --- | --- | --- |
| Light (224 tris, 7 KiB) | Windows | 10.6 ms | 12.2 ms | 0.1 ms | +1.6 ms | 502 ms (OCP import 452) |
| Light | Linux | 10.3 ms | 11.2 ms | 0.2 ms | +0.9 ms | 398 ms (OCP import 378) |
| Heavy (6932 tris, 190 KiB) | Windows | 59.6 ms | 67.2 ms | 0.3 ms | +7.6 ms | 486 ms |
| Heavy | Linux | 54.3 ms | 59.3 ms | 0.8 ms | +5.1 ms | 371 ms |

- IPC is negligible. The real cost is the cold start (~0.5 s, almost all of it the OCP import): the worker must be
  **persistent**. The remaining overhead comes from OCCT running slightly slower in the worker, not from the transfer.
- Bug found and fixed: on unbuffered pipes `read(n)` returns partial reads above ~64 KiB → `read_exact` is needed.
- Not tested: crash isolation (an OCCT segfault in the worker must not bring Blender down) and asynchronous
  recompute that doesn't block the UI. To do in milestone 1.
- Logs: `spike/logs/07_*.log`. Script: `spike/s07_worker_bench.py`.

### 8. Package — PASS

`spike/s08_build_extension.sh` → `blender --command extension build --split-platforms`:

| Zip | Size |
| --- | --- |
| `blendsolid-0.0.1-windows_x64.zip` | **47.7 MB** |
| `blendsolid-0.0.1-linux_x64.zip` | 66.8 MB |
| `blendsolid-0.0.1-macos_arm64.zip` | 63.0 MB |

- Each zip contains only its platform's wheel + `cadquery-ocp-proxy`; the manifest is rewritten with that platform
  only. Installed with `blender -c extension install-file` on the Windows portable and on Linux: the test operator
  imports OCP from the extension's site-packages (`portable\extensions\.local\lib\python3.13\site-packages`)
  and rebuilds the solid (correct volume).
- Platforms: `windows-x64`, `linux-x64`, `macos-arm64`. **No Intel macOS** (unsupported by Blender 5.x, although
  the wheel exists) and **no Windows ARM** (no OCP wheel).
- Headroom below 100 MB: ~52 MB on Windows, ~33 MB on Linux, ~37 MB on macOS.

## Issues found

1. **build123d doesn't fit the 100 MB limit.** build123d 0.13.0 (compatible with OCP 8: `cadquery-ocp-novtk>=8.0,<8.1`)
   needs almost all of its dependencies just to import: `threejs_materials` (90 MB), scipy (37 MB),
   scikit-learn, sympy, IPython, pillow, ezdxf, fonttools, etc. Total Windows wheels ≈ 152 MB + 48 MB OCP ≈ **200 MB**
   (with every dependency: 214 MB excluding numpy).
2. **`typing_extensions` conflict:** build123d wants ≥ 4.16 (`typing_extensions.sentinel`), Blender 5.2 bundles
   4.14.1, which takes precedence → `ImportError`. Still to check whether a wheel in the extension can override it.
   *Update:* a bundled wheel does override Blender's module, but for Blender and every add-on (extension
   site-packages precede Blender's in `sys.path`; CLAUDE.md pitfall), so it is not a fix: build123d and its
   dependencies load only in the worker, from a private library folder (ADR 0001).
3. **OCP 8 API differs from OCP 7** (examples and snippets found online don't work):
   `TopTools_IndexedMapOfShape` → `OCP.collections.IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher`;
   `TopoDS.Face_s(x)` → `TopoDS.Face(x)`; `Standard_Version` not exposed.
4. **Blender 5.2 API:** GN modifier inputs via `mod.properties.inputs.<id>.value` (no longer IDProperties).
5. **Undo:** `matrix_world` not evaluated in `undo_post`; undo snapshot one event behind with GN gizmos.
6. Worker protocol bug (partial reads): fixed.
7. Minor: the Linux Blender in WSL is not portable (it installs extensions into `~/.config/blender/5.2`); the Windows
   portable needs a `portable\` folder next to `blender.exe`, otherwise it uses `%APPDATA%`.

## Measured timings (summary)

| What | Time |
| --- | --- |
| OCP import in Blender | 0.33 s (Win), 0.41 s (Linux) |
| Build box+cylinder+fillet | 4–6 ms; with push 8–10 ms |
| Tessellation (defl. 0.1) | 1–8 ms |
| Blender mesh (`foreach_set`) | 0.2–1.3 ms |
| Live recompute in the GUI (1167 events) | OCCT median 10.0 ms, max 12.4 ms |
| Worker: cold start / warm overhead | ~0.4–0.5 s / +1–8 ms |

## Proposed spec changes before milestone 1

1. **build123d (decision needed).** Options:
   - (a) **fork/vendor build123d** (Apache 2.0) with lazy imports of exporters, materials, scipy and sklearn, keeping
     only the core; measure what remains and what it costs to maintain;
   - (b) **our own thin API on top of OCP** with build123d-inspired syntax, so the script stays readable and editable
     by Claude via MCP; no extra dependencies;
   - (c) ask upstream to move the heavy dependencies into extras (`build123d[export]`), plus (a) in the meantime;
   - (d) install build123d into a separate worker environment downloaded on first run: simpler, but probably against
     extensions.blender.org rules (dependencies must be bundled as wheels). To be checked.
   Recommendation: try (a) as the first task of milestone 1, with (b) as fallback, and open (c) in parallel.
   **Update:** decided in [ADR 0001](docs/decisions/0001-shipping-build123d.md): ship build123d with all its
   dependencies, loaded only in the worker, distributed from GitHub; a lite build (+1.9 MB) is documented as the
   fallback for extensions.blender.org; (d) is forbidden by the store guidelines.
2. **Technical constraints:** add `cadquery-ocp-proxy`; pin **OCP 8.0.x** (the API changed from 7);
   `typing_extensions` conflict; platforms = `windows-x64`, `linux-x64`, `macos-arm64`; actual zip sizes
   (47.7 / 66.8 / 63.0 MB). The "DLL conflicts" row can become **verified: no conflict**.
3. **Undo (spike decision):** source of truth = script + controls (proxies, GN inputs), stored in the `.blend` and
   therefore in the memfile undo; mesh and applied parameters = cache. Reconciliation always happens in
   `depsgraph_update_post`; no logic based on evaluated data in `undo_post`. Script changes must be made by
   **operators with `UNDO`** (which create the step after writing the script), not by handlers: with handlers the
   undo step may hold a script one event out of date, as happens here with the GN gizmo.
4. **Worker:** persistent (cold start ~0.5 s), started lazily on first use; protocol without pickle
   (JSON header + raw numpy buffers); timeout and restart on crash. For live dragging: drop intermediate events and
   keep only the latest value when a recompute takes longer than ~30 ms.
5. **Push face:** results need validation (volume, number of solids, `BRepCheck`), because OCCT returns a valid but
   unexpected result when the push goes through the part.
6. **Picking:** add face/edge highlighting with a `gpu` overlay to the MVP.
7. **GN gizmos:** confirmed usable for library parameters (Linear, Dial, Transform). The spec should mention the new
   modifier input API.
