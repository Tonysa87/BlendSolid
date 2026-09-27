# BlendSolid

**Exact BRep/NURBS CAD modeling inside Blender, with a parametric history written as code and a 100% native Blender interface.**

> **Status: early development (pre-alpha).** Milestones 0 (feasibility spike) and 1 (history as code) are done;
> 1.5 (build without selectors) is implemented, with its manual GUI test pending. A part is a build123d script
> behind the scenes, with draggable parameters, undo and a separate geometry process; parts can now be built
> with parametric primitives (Shift+A), the interactive Draw Solid tool and booleans between parts with live
> cutters, no clicking on faces or edges yet. It is a developer preview, not ready for production work — watch
> or star the repo to follow progress.

BlendSolid is an open source (GPL) add-on for **Blender 5.2 LTS** built on the **OpenCASCADE (OCCT)** kernel.
It aims to give Blender users CAD precision — fillets, booleans, shells, exact surfaces, clean STEP output —
without leaving Blender or learning a second application.

## Why

Blender is excellent at meshes, SubD, shading and rendering, but it has no exact geometry kernel: a mesh fillet
is an approximation, a boolean on meshes is fragile, and there is no parametric history to go back and change a
dimension. Hard-surface artists, kitbashers and product-render people end up round-tripping through a separate
CAD package. BlendSolid wants to close that gap.

**Who it's for:** Blender users who want CAD precision (hard surface, kitbashing of real parts, product renders)
without leaving Blender.

**What sets it apart**

- **The history is code.** Every viewport action writes or edits lines of a readable Python script stored in the
  `.blend`; the solid is recomputed from it. You can read it, edit it, version it — and an AI assistant (e.g.
  Claude via MCP) can edit it too.
- **Freeform starts as SubD.** Shapes modeled with Blender's SubD tools become NURBS surfaces and then solids.
- **The gizmos are Blender's own.** Moving a face is `G Z 5` with the standard transform gizmo, snapping,
  numeric input and pivots included — no parallel UI to learn.

**What it is not:** not a replacement for Parasolid/Plasticity for class-A surfacing, and not a production CAD
with drawings and assemblies.

## How it works (planned architecture)

```
 Blender (UI, gizmos, display mesh)                 OCCT worker process
┌──────────────────────────────────────┐          ┌──────────────────────────────┐
│ viewport action / gizmo / proxy move │ ──────▶  │ run history script (OCP)     │
│ history script in the .blend         │  params  │ booleans, fillets, surfaces  │
│ mesh with BRep face/edge IDs         │ ◀──────  │ tessellate + face/edge map   │
│ picking: ray_cast → face ID → CAD    │   mesh   │                              │
└──────────────────────────────────────┘          └──────────────────────────────┘
```

Four pillars on top of OCCT (via [OCP](https://pypi.org/project/cadquery-ocp-novtk/)):

1. **History as code.** Face and edge references are *semantic selectors* generated from clicks
   (e.g. "circular edges of the topmost face, largest radius"), checked for uniqueness; fallback to OCCT's
   Generated/Modified history and geometric matching. The state after each step is cached.
2. **Freeform: SubD → NURBS.** Regular faces converted exactly to bicubic B-splines; extraordinary vertices
   approximated (G1 first, G2 later); faces packed into larger surfaces and sewn into an OCCT solid.
3. **Variational surface layer.** Fairing solver for G2 blends and matches, 4-sided fills, N-sided patches,
   "two-pass" G2 fillets on top of OCCT's G1 fillets.
4. **Automatic verification.** Numeric continuity and BRep validity metrics on a corpus of real models.

**Native Blender UX:** invisible Empty proxies turn standard transforms into CAD operations; native and
Geometry Nodes gizmos (arrows, dials, cages) bound to depths, radii and angles; a "CAD" workspace with
`WorkSpaceTool`s; BRep IDs stored as mesh attributes for picking; service vertices for exact snapping;
`gpu`/`blf` overlays only where native widgets aren't enough.

## Roadmap

Each milestone has a measurable success criterion.

| # | Milestone | Success criterion | Status |
| --- | --- | --- | --- |
| 0 | Feasibility spike | OCP runs in Blender 5.2; solid visible as mesh; `--split-platforms` build under 100 MB; no DLL conflicts; proxy and GN gizmos tested; undo doesn't corrupt state | ✅ **Done** — see [SPIKE_REPORT.md](SPIKE_REPORT.md) |
| 1 | History as code | History script stored in the `.blend`; changing a parameter recomputes correctly; worker in a separate process | ✅ **Done** — see [docs/milestone-1-report.md](docs/milestone-1-report.md) |
| 1.5 | Build without selectors | Parametric primitives (Shift+A), Draw Solid on a face or the grid (union/cut by drag direction), booleans between parts with live cutters — see [modeling workflows research](docs/research/2026-09-26-modeling-workflows.md) | ⚠️ **Implemented** — manual GUI test passed, sign-off pending, see [docs/milestone-1.5-report.md](docs/milestone-1.5-report.md) |
| 2 | Selectors from clicks | Face/edge → feature provenance first; 95% of clicked edges and faces on a set of 20 parts produce a unique selector that survives 3 upstream changes | Planned |
| 3 | Publishable MVP | MVP column of the feature catalog complete; published on extensions.blender.org | Planned |
| 4 | SubD → NURBS | Regular faces converted within tolerance; solid valid for OCCT | Planned |
| 5 | G2 surfaces | G2 blend between untrimmed edges with curvature jump below threshold | Planned |
| 6 | G2 fillets and Y-blends | To be defined after milestone 5 | Planned |

### Feature catalog (summary)

MVP = OCCT already does it · v2 = real work, no unknowns · R&D = needs research. Full table in [docs/spec.md](docs/spec.md).

| Area | MVP | v2 | R&D |
| --- | --- | --- | --- |
| 2D sketch | Lines, arcs, circles, splines, offset, trim, fillet/chamfer | Constraints and dimensions, G1/G2 bridge curves | — |
| Solids | Primitives, extrude, revolve, loft, sweep, shell, thicken, mirror, array | Mitred sweeps, loft with tangency | — |
| Booleans | Union, difference, intersection (fuzzy tolerance) | Ghost preview | — |
| Fillets | Constant fillet, chamfer | Variable/partial fillet, fillet removal | Conic/G2 fillets, Y-blend |
| Direct editing | Imprint, topology cleanup | Delete/offset/draft face | — |
| Surfaces | 4-edge surface, join/unjoin, untrim | Patch, G1/G2 blend and match | G2 on trimmed edges, N-sided G2 patch |
| SubD → NURBS | — | Exact regular faces | G2 extraordinary vertices |
| Analysis | Zebra, distance/radius | Curvature map, continuity measures, sections | — |
| I/O | STEP, IGES, BREP | Hidden-line SVG | — |

## Milestone 0 results

The spike ran on Blender 5.2.2 LTS (Windows portable + Linux) with `cadquery-ocp-novtk` 8.0.1. All 8 goals passed:

- **OCP loads inside Blender with no DLL conflicts** — OCP's DLLs are hash-renamed and coexist with Blender's;
  OCP doesn't use TBB.
- **Box + cylinder + boolean + fillet → Blender mesh** with the BRep volume matching the analytical value.
- **Picking** from a click to the right BRep face via a face attribute and `ray_cast`.
- **Push face with a proxy Empty** and the standard gizmo / `G Z 5`, recomputed live in ~10 ms.
- **Undo** stays consistent, with two caveats that shape the milestone-1 design.
- **Geometry Nodes `GizmoLinear`** driving an OCCT recompute.
- **Worker process**: ~1–8 ms overhead per recompute, ~0.5 s cold start → it must be persistent.
- **Package size**: Windows zip 47.7 MB, Linux 66.8 MB, macOS arm64 63.0 MB (limit 100 MB).

**Main open issue:** build123d with its dependencies weighs ~200 MB per platform and does not fit the 100 MB
extensions.blender.org limit. Decision ([ADR 0001](docs/decisions/0001-shipping-build123d.md)): ship
build123d with all its dependencies (~220–255 MB per platform), loaded only in the worker process, and distribute
it from GitHub as a Blender extension repository; a lighter build for extensions.blender.org is researched and
documented as a fallback.

## Supported platforms (planned)

Blender **5.2 LTS** or newer on **Windows x64**, **Linux x64** and **macOS arm64**, installed from a BlendSolid
extension repository hosted on GitHub (Blender 4.2+ supports third-party repositories with automatic updates). Intel Macs are not supported by
Blender 5.x; Windows ARM has no OCP wheel yet.

## Open decisions

Scope-changing choices still to be made before milestone 1:

- [x] How to ship build123d: all dependencies, loaded only in the worker, distributed from GitHub — [ADR 0001](docs/decisions/0001-shipping-build123d.md)
- [ ] Whether and how to list on extensions.blender.org (100 MB limit: a lighter build would be needed)
- [ ] Main use: rendering/kitbashing (loose tolerances) or production too (clean STEP, tight tolerances)?
- [x] History script hidden from standard users, available to advanced users ([ADR 0002](docs/decisions/0002-history-script-visibility.md))
- [ ] Constrained sketches: integrate CAD Sketcher or write our own?
- [x] Repository public from the start

## Repository layout

```
docs/spec.md        project spec draft (vision, architecture, catalog, milestones, risks)
docs/decisions/     architecture decision records (ADRs)
SPIKE_REPORT.md     milestone 0 results: PASS/FAIL, timings, issues, proposed spec changes
spike/              throwaway milestone-0 code (not the add-on)
  occ_model.py      OCP-only geometry: model, push face, tessellation
  bl_bridge.py      tessellated arrays → Blender mesh with brep_face_id attribute
  gui_session.py    interactive session: picking, proxy push, GN gizmo, undo logging
  worker.py         OCCT worker process + s07_worker_bench.py benchmark
  extension/        minimal extension manifest used for the packaging test
  build123d_lite/   research for ADR 0001: build123d with stubbed heavy dependencies, in the worker
  logs/             raw test output (in Italian: recorded before the code was translated)
CLAUDE.md           working notes and rules for AI-assisted development
```

## Try it (developer preview)

Milestone 1.5 builds a per-platform extension zip (~226 MB on Windows, ~255 MB on Linux: build123d and all its
dependencies are bundled for the geometry process, see [ADR 0001](docs/decisions/0001-shipping-build123d.md)).
With Blender 5.2's bundled Python:

```bash
PY=<blender>/5.2/python/bin/python3.13
$PY tools/build_extension.py --platform linux-x64 --blender <blender>/blender     # or windows-x64
<blender>/blender --command extension install-file -r user_default -e dist/blendsolid-0.2.0-linux-x64.zip
```

Then in Blender: 3D Viewport → `N` → **BlendSolid** → **New Part**. Parameters are in millimetres
([ADR 0003](docs/decisions/0003-units.md)). Scripts in files you open are only run if Blender's *Auto Run Python
Scripts* is on or you press *Trust Scripts in This File* ([ADR 0004](docs/decisions/0004-script-trust.md)).
Then Shift+A → BlendSolid for primitives, the *Draw Solid* tool in the toolbar (hold Ctrl to snap to the grid
it shows, Ctrl+Wheel to change the step), and Ctrl+Numpad −/+/* for booleans with live cutters (select the
cutters, then the target). Developers: `tools/setup_dev.sh` then
`tools/test.sh`.

## Running the spike

The spike is for developers only. You need Blender 5.2 and OCP installed next to it:

```bash
# install OCP into a folder next to Blender (Windows: use the bundled python.exe)
<blender>/5.2/python/bin/python3.13 -m pip install --target <blender>/spike_site cadquery-ocp-novtk==8.0.1

# headless checks
<blender>/blender -b --factory-startup --python spike/s01_import_ocp.py
<blender>/blender -b --factory-startup --python spike/s02_s03_mesh_pick.py
<blender>/blender -b --factory-startup --python spike/s07_worker_bench.py

# interactive session (picking, proxy push, GN gizmo, undo)
<blender>/blender --factory-startup --python spike/gui_session.py

# build the per-platform extension zips (wheels downloaded into ./wheels first)
spike/s08_build_extension.sh
```

The scripts look for OCP in a `spike_site` folder next to the Blender executable, or in `$BLENDSOLID_SITE`.

## Contributing

The project is at the design stage and the code is still throwaway. Feedback on the [spec](docs/spec.md) and the
[spike report](SPIKE_REPORT.md) is welcome through GitHub issues — especially from people with experience in
OCCT, NURBS/SubD conversion, surface fairing or Blender add-on development.

## License

[GPL-3.0-or-later](LICENSE), as required for Blender add-ons. Dependencies are GPL-compatible: OCCT (LGPL 2.1 with exception),
OCP (Apache 2.0), build123d (Apache 2.0).

## Acknowledgements

Built on the work of [Open CASCADE Technology](https://dev.opencascade.org/),
[OCP / CadQuery](https://github.com/CadQuery/OCP), [build123d](https://github.com/gumyr/build123d) and
[Blender](https://www.blender.org/). Plasticity and FORGE are sources of inspiration, not models to copy.
