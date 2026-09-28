# BlendSolid

**Exact BRep/NURBS CAD modeling inside Blender, with a parametric history written as code and a 100% native Blender interface.**

> **Status: early development (pre-alpha).** Milestones 0 (feasibility spike), 1 (history as code),
> 1.5 (build without selectors) and 2 (selectors from clicks) are done. A part is a build123d script behind the
> scenes, with draggable parameters, undo and a separate geometry process. Parts are built with parametric
> primitives (Shift+A), the Draw Solid tool, booleans between parts with live cutters, and the **Fillet** and
> **Push/Pull** tools, which click on the part's edges and faces and write readable references
> (`edge_between(face("box_1", "+Z"), face("cut_1", "side"))`) into the script. The display mesh is closed,
> welded and works with Blender's modifiers (Bevel, Array, Solidify, …). It is a developer preview, not ready for
> production work — watch or star the repo to follow progress.

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
- **Blender stays Blender.** Tools live in the toolbar, parameters are native gizmo arrows and sidebar fields,
  undo is Blender's, and a part is an ordinary mesh object: modifiers, materials and rendering work as usual.
- **Freeform starts as SubD** *(planned, milestone 4)*. Shapes modeled with Blender's SubD tools become NURBS
  surfaces and then solids.

**What it is not:** not a replacement for Parasolid/Plasticity for class-A surfacing, and not a production CAD
with drawings and assemblies.

## How it works

```
 Blender (UI, gizmos, display mesh)                 OCCT worker process
┌──────────────────────────────────────┐          ┌──────────────────────────────┐
│ viewport action / gizmo / proxy move │ ──────▶  │ run history script (OCP)     │
│ history script in the .blend         │  params  │ booleans, fillets, surfaces  │
│ mesh with BRep face/edge IDs         │ ◀──────  │ tessellate + face/edge map   │
│ picking: ray_cast → face ID → CAD    │   mesh   │                              │
└──────────────────────────────────────┘          └──────────────────────────────┘
```

Built so far, on top of OCCT (via [OCP](https://pypi.org/project/cadquery-ocp-novtk/)) and
[build123d](https://github.com/gumyr/build123d):

- **History as code.** Each part is a build123d script in the `.blend`; tools add or edit its lines and numeric
  parameters become sidebar fields and gizmo arrows. Scripts from files you open run only if you trust them
  ([ADR 0004](docs/decisions/0004-script-trust.md)).
- **References from clicks.** Every face and edge is named after the feature that made it (`face("box_1", "+Z")`),
  read from build123d's operation history; names survive upstream changes, and a reference that turns doubtful
  (a face split in two) builds with a warning instead of silently picking the wrong face
  ([ADR 0009](docs/decisions/0009-references-to-faces-and-edges.md)).
- **Worker process.** OCCT runs in a separate process (Blender has no Python threads for it): it rebuilds the part
  and returns a display mesh with BRep face/edge ids as mesh attributes, used for picking through modifiers.
- **CAD-style display mesh.** Every BRep edge is discretized once and shared by its faces; fillet bands and trimmed
  cylinders are regular grids, flat faces are a few convex polygons; CAD edges carry sharp and bevel-weight flags
  ([ADR 0008](docs/decisions/0008-modifier-compatible-display-mesh.md),
  [ADR 0010](docs/decisions/0010-edge-first-grid-tessellation.md)).

Planned: **SubD → NURBS** (regular faces converted exactly to bicubic B-splines, extraordinary vertices
approximated, sewn into an OCCT solid), a **variational surface layer** (fairing for G2 blends, N-sided patches,
G2 fillets on top of OCCT's G1 ones) and **automatic verification** (continuity and BRep validity on a corpus of
real models). Full design in [docs/spec.md](docs/spec.md).

## Roadmap

Each milestone has a measurable success criterion.

| # | Milestone | Success criterion | Status |
| --- | --- | --- | --- |
| 0 | Feasibility spike | OCP runs in Blender 5.2; solid visible as mesh; `--split-platforms` build under 100 MB; no DLL conflicts; proxy and GN gizmos tested; undo doesn't corrupt state | ✅ **Done** — see [SPIKE_REPORT.md](SPIKE_REPORT.md) |
| 1 | History as code | History script stored in the `.blend`; changing a parameter recomputes correctly; worker in a separate process | ✅ **Done** — see [docs/milestone-1-report.md](docs/milestone-1-report.md) |
| 1.5 | Build without selectors | Parametric primitives (Shift+A), Draw Solid on a face or the grid (union/cut by drag direction), booleans between parts with live cutters — see [modeling workflows research](docs/research/2026-09-26-modeling-workflows.md) | ✅ **Done** — see [docs/milestone-1.5-report.md](docs/milestone-1.5-report.md) |
| 2 | Selectors from clicks | Face/edge → feature provenance first; 95% of clicked edges and faces on a set of 20 parts produce a unique selector that survives 3 upstream changes | ✅ **Done** — see [docs/milestone-2-report.md](docs/milestone-2-report.md): modifier-compatible mesh, readable references, Fillet and Push/Pull tools, CAD-style tessellation ([ADR 0008](docs/decisions/0008-modifier-compatible-display-mesh.md), [0009](docs/decisions/0009-references-to-faces-and-edges.md), [0010](docs/decisions/0010-edge-first-grid-tessellation.md)) |
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

## Distribution

The spike ([SPIKE_REPORT.md](SPIKE_REPORT.md)) showed that OCP loads inside Blender with no DLL conflicts, and
that build123d with its dependencies weighs ~200 MB per platform — over extensions.blender.org's 100 MB limit.
Decision ([ADR 0001](docs/decisions/0001-shipping-build123d.md)): ship build123d with all its dependencies
(~220–255 MB per platform), loaded only in the worker process, and distribute it from GitHub as a Blender
extension repository; a lighter build for extensions.blender.org is documented as a fallback.

## Supported platforms (planned)

Blender **5.2 LTS** or newer on **Windows x64**, **Linux x64** and **macOS arm64**, installed from a BlendSolid
extension repository hosted on GitHub (Blender 4.2+ supports third-party repositories with automatic updates). Intel Macs are not supported by
Blender 5.x; Windows ARM has no OCP wheel yet.

## Open decisions

Scope-changing choices (settled ones link their decision record; all records are in
[docs/decisions/](docs/decisions/)):

- [x] How to ship build123d: all dependencies, loaded only in the worker, distributed from GitHub — [ADR 0001](docs/decisions/0001-shipping-build123d.md)
- [ ] Whether and how to list on extensions.blender.org (100 MB limit: a lighter build would be needed)
- [ ] Main use: rendering/kitbashing (loose tolerances) or production too (clean STEP, tight tolerances)?
- [x] History script hidden from standard users, available to advanced users ([ADR 0002](docs/decisions/0002-history-script-visibility.md))
- [ ] Constrained sketches: integrate CAD Sketcher or write our own?
- [x] Repository public from the start

## Repository layout

```
blendsolid/         the add-on (Blender side: parts, tools, gizmos, UI, worker client)
  worker/           the geometry process: runs part scripts (build123d/OCCT), tessellates, names faces/edges
tests/unit/         worker tests (Blender's Python, no bpy)
tests/blender/      add-on tests (headless Blender)
tools/              build, test, smoke and GUI-check scripts
docs/spec.md        project spec (vision, architecture, catalog, milestones, risks)
docs/decisions/     architecture decision records (ADRs)
docs/research/      research notes behind the decisions (CAD workflows, selectors, tessellation, fillets)
docs/milestone-*    milestone reports (what was built, how it was verified, known limits)
docs/NEXT.md        current state and next step
SPIKE_REPORT.md     milestone 0 results: PASS/FAIL, timings, issues, proposed spec changes
spike/              throwaway experiments and measurement scripts (not the add-on)
CLAUDE.md           working notes and rules for AI-assisted development
```

## Try it (developer preview)

There are no releases yet: build a per-platform extension zip (~226 MB on Windows, ~255 MB on Linux; build123d
and all its dependencies are bundled for the geometry process, see
[ADR 0001](docs/decisions/0001-shipping-build123d.md)). With Blender 5.2's bundled Python:

```bash
PY=<blender>/5.2/python/bin/python3.13
$PY tools/build_extension.py --platform linux-x64 --blender <blender>/blender     # or windows-x64
<blender>/blender --command extension install-file -r user_default -e dist/blendsolid-0.2.0-linux-x64.zip
```

Then in Blender (parameters are in millimetres, [ADR 0003](docs/decisions/0003-units.md)):

- **Shift+A → BlendSolid** for primitives (box, cylinder, sphere, cone, torus, wedge), or 3D Viewport → `N` →
  **BlendSolid** → **New Part**. The sidebar lists the part's parameters; the arrows on the part drag them.
- **Draw Solid** (toolbar): draw a rectangle or circle on a face or the grid and drag it out (adds) or in (cuts).
  Hold Ctrl to snap, Ctrl+Wheel changes the step.
- **Booleans with live cutters:** select the cutters, then the target, Ctrl+Numpad −/+/*. Cutters are hidden and
  follow the target; *Select Cutter* and the eye in the sidebar bring them back.
- **Fillet** (toolbar): click edges (Shift+click adds, a face takes all its edges), drag the radius; C switches to
  a chamfer.
- **Push/Pull** (toolbar): press on a flat face and drag along its normal.
- Clicking a face shows the arrows of the feature that made it.

Scripts in files you open run only if Blender's *Auto Run Python Scripts* is on or you press *Trust Scripts in
This File*. Developers: `tools/setup_dev.sh` once, then `tools/test.sh` (unit tests with Blender's Python, then
headless Blender tests).

## Contributing

The project is in early development and moves fast. Feedback on the [spec](docs/spec.md), the milestone reports
and the decision records is welcome through GitHub issues — especially from people with experience in OCCT,
NURBS/SubD conversion, surface fairing or Blender add-on development.

## License

[GPL-3.0-or-later](LICENSE), as required for Blender add-ons. Dependencies are GPL-compatible: OCCT (LGPL 2.1 with exception),
OCP (Apache 2.0), build123d (Apache 2.0).

## Acknowledgements

Built on the work of [Open CASCADE Technology](https://dev.opencascade.org/),
[OCP / CadQuery](https://github.com/CadQuery/OCP), [build123d](https://github.com/gumyr/build123d) and
[Blender](https://www.blender.org/). Plasticity and FORGE are sources of inspiration, not models to copy.
