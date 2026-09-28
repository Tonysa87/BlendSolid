# BlendSolid — spec draft

Sep 26, 2026 · @Antonio Sartini

## Vision and goals

BlendSolid is an open source (GPL) add-on that brings exact BRep/NURBS modeling to Blender, with a parametric history written as code and a 100% native Blender interface. FORGE is only an inspiration: the goal is not to copy it.

- **Who it's for:** Blender users who want CAD precision (hard surface, kitbashing of real parts, product renders) without leaving Blender.
- **What sets it apart:** the history is a build123d script, readable and editable, including by Claude via MCP; freeform shapes start as SubD and become NURBS; the gizmos are Blender's own.
- **What it is not:** it is not a replacement for Parasolid/Plasticity for class-A surfaces, nor a production CAD with drawings and assemblies.
- **Distribution:** extensions.blender.org, GPL license.

## Verified technical constraints

All distribution constraints appear to be surmountable; only DLL coexistence remains to be tested.

| Constraint | Status | Note |
| --- | --- | --- |
| Target Blender | 5.2 LTS | Python 3.13 from Blender 5.1 onward |
| Kernel | OCP (`cadquery-ocp-novtk` 8.0.1) | cp313 wheels: Windows \~48 MB, Linux/macOS \~61–68 MB |
| extensions.blender.org limit | 100 MB per package | One zip per platform with `--split-platforms` |
| License | GPL | OCCT LGPL and build123d Apache 2.0 are compatible |
| Python threads | Not supported by Blender | Heavy OCCT computations in a separate process |
| DLL conflicts (TBB, freetype) | To be verified | First test of the spike |

## Architecture

Four pillars on top of OCCT, plus a computation process separate from Blender.

1. **History = build123d code.** Every action in the viewport writes or edits lines of a script saved in the `.blend`; the solid is recomputed from it.
   - References to faces and edges as semantic selectors generated from the click (e.g. "circular edges of the topmost face, largest radius"), verified to be unique.
   - Fallback: OCCT Generated/Modified history, then geometric matching.
   - State cache after every step, so the whole script is not recomputed.
2. **Freeform: SubD → NURBS.** Regular faces converted exactly into bicubic B-splines; extraordinary vertices approximated (G1 first, G2 later); faces packed into larger surfaces; sewing into an OCCT solid.
3. **Variational surface layer.** Fairing solver (Greiner) for G2 blend and match, 4-sided fill, N-sided patches with `transfinite` + constrained fitting; "two-pass" G2 fillet on top of the OCCT G1 fillet.
4. **Automatic verification.** Numeric continuity and BRep validity metrics on a corpus of real models.

**Processes.** Blender (UI, gizmos, display mesh) talks to an OCCT worker in a separate process; the worker returns the tessellated mesh + face/edge map.

**Performance (note, 2026-09-26).** OCCT runs on the CPU: use its multi-core options (parallel booleans and meshing) first. GPU acceleration (e.g. CUDA) is not planned for the kernel; it is an **R&D item to evaluate later** for the fairing solver and SubD → NURBS fitting on dense meshes, only if profiling shows them as the bottleneck, and always with a CPU fallback (CUDA is NVIDIA-only and its libraries weigh hundreds of MB). Viewport analysis (zebra, curvature) uses Blender's vendor-neutral `gpu` module.

## UX and Blender integration

The interface uses only native Blender 5.2 components; no modes in the mode drop-down menu, which Python cannot add.

- **Standard transform gizmo via proxy.** When a face or CAD part is selected, an invisible Empty is placed on it; moving it with the gizmo or with `G Z 5` becomes a CAD operation. Native constraints, numeric input, pivot and snapping included.
- **Native gizmos bound to parameters.** Blender arrows, dials and cages bound to depths, radii and angles in the script.
- **Geometry Nodes gizmos** (`GizmoLinear`, `GizmoDial`, `GizmoTransform`) for the parameters of library elements: to be evaluated in the spike.
- **Toolbar** with `WorkSpaceTool` in a "CAD" workspace; the interactive loop starts from a key, not from the tool.
- **Picking:** BRep face/edge IDs stored as mesh attributes; `ray_cast` from the mouse traces back to the CAD entity.
- **Exact snapping** (hole centers, midpoints): "service" vertices in the display mesh.
- **Previews and HUD** only where native components are not enough, with `gpu` and `blf`.
- **Undo:** how Blender's undo combines with handler-triggered recomputation is still to be defined.

## Feature catalog by phase

MVP = OCCT already does it; v2 = real work with no unknowns; R&D = needs research.

Full comparison with Plasticity commands: Plasticity command by command

| Area | MVP | v2 | R&D |
| --- | --- | --- | --- |
| 2D sketch | Line, arc, circle, ellipse, rectangle, polygon, spiral, spline, trim/split/join, offset, slot, extend, curve fillet/chamfer | Constraints and dimensions (CAD Sketcher/SolveSpace), G1/G2 bridge curve, rebuild curve, CV editing | — |
| Projections | Curve on body, body-body intersection, projection onto the construction plane | Outline, 3D curve from two views | — |
| Solids | Primitives, extrude, revolve, loft, pipe, sweep, shell, thicken, mirror with merge, array, cut | Sweep with mitre/round corners, loft with tangency | — |
| Booleans | Union, difference, intersection with fuzzy tolerance | Ghost preview | — |
| Fillets | Constant fillet, chamfer | Variable and partial fillet, fillet removal (OCCT defeaturing) | Conic/chordal/G2/full fillet, Y-blend |
| Direct editing | Imprint, topology cleanup | Delete face, offset face, draft face, offset edge/face loop, isoparam | — |
| Surfaces | Surface from 4 edges, square, join/unjoin sheet, untrim, reverse, open edges | Patch, bridge surface, G1 and G2 blend/match on untrimmed edges, extend sheet, constrained surface, rebuild face | G2 match on trimmed edges, G2 N-sided patch |
| SubD → NURBS | — | Exact regular faces, packing | G2 extraordinary vertices |
| Analysis | Zebra (shader), distance and radius measurements | Curvature color map, continuity measurement, dimensions, sections | — |
| Interface | Native Blender: transforms, F3 palette, pie menus, outliner, Asset Browser, materials | Construction planes, exact snapping with service vertices, place on face | — |
| Blender output | Adjustable tessellation, hard edges, UV seams | Quad mesh for simple faces | Quads on trimmed faces (QuiltMesher) |
| I/O | STEP, IGES, BREP | Hidden line SVG | — |

## Milestones

Decisions of 2026-09-28 (maintainer): publication on extensions.blender.org only at the end of everything;
mirror, array and shell are CAD features (Blender's own modifiers keep working on parts for visual-only results,
ADR 0008, but a fillet across a mirror seam, a boolean on array copies, an exact shell or a STEP export need the
geometry in the kernel).

We start with a 1–2 day spike; every milestone has a measurable criterion.

| # | Milestone | Success criterion |
| --- | --- | --- |
| 0 | Spike | OCP runs in Blender 5.2 on Windows; box + cylinder + boolean + fillet visible as a mesh; `--split-platforms` build under 100 MB; no DLL conflicts; proxy gizmo and GN gizmo tested; undo does not corrupt the state |
| 1 | History as code | build123d script saved in the `.blend`; changing a parameter → correct recomputation; worker in a separate process |
| 1.5 | Build without selectors (added 2026-09-26) | A user builds the milestone 1 default part and a bracket with 3 holes using only parametric primitives (Shift+A), the Draw Solid tool (on a face or the grid; union/cut by drag direction) and booleans between parts with live cutters; every step is one undo step and one script edit |
| 2 | Selectors from clicks | Starts with face/edge → feature provenance from the worker. 95% of the edges **and faces** clicked on a set of 20 parts produce a unique selector that survives 3 upstream changes |
| 3 | Complete hard-surface modeling (redefined 2026-09-28) | All in the CAD kernel (exact, filletable, STEP-exportable), one sub-milestone at a time: **3a** 2D sketch on a face or plane + extrude/revolve; **3b** chamfer with two distances or distance + angle (side choice) and variable fillet; mirror, linear/polar array, shell/thicken as CAD features with Blender-modifier-like UI; **3c** direct editing: offset face, delete face with healing, draft face; split body/imprint, cut by sketch; **3d** loft, sweep, pipe; **3e** zebra and measurements, STEP/IGES/BREP I/O, convert to quads. Each sub-milestone gets its measurable criterion when planned. Distributed from the GitHub extension repository (ADR 0001) |
| 4 | SubD → NURBS | Regular faces converted with deviation ≤ tolerance; solid valid for OCCT |
| 5 | G2 surfaces | G2 blend between untrimmed edges with curvature jump below threshold |
| 6 | G2 fillets and Y-blend | To be defined after milestone 5 |
| — | extensions.blender.org | Decided at the very end (2026-09-28): development and distribution from GitHub until then |

## Test strategy

Every geometric result is verified with numbers, not by eye; the human eye is needed only for the final zebra checks.

- **Metrics:** BRep validity (`BRepCheck`), closed and manifold solid, angular deviation along edges (G1), curvature jump (G2), deviation from the source SubD.
- **Corpus:** real STEP parts from the kitbash, NIST cases, a sample of the ABC dataset.
- **Regression tests** on selectors: same script, upstream parameters changed, same edge selected.
- **Adversarial critics** with fresh context looking for the cases that break solvers and selectors.
- **Tests in Blender** headless (`blender -b`) for the non-interactive part; manual tests only for gizmos and UX.

## Main risks

The highest risk is selector synthesis; it must be validated before building on top of it.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Ambiguous selectors (symmetric or similar edges) | Broken history | Fallback to OCCT history + geometric matching; regression tests from milestone 2 |
| Blender undo vs handler-driven recomputation | Inconsistent states | Decided in the spike; history in the script as the single source of truth |
| DLL conflicts between OCCT and Blender | Crash at startup | Test on day 1 of the spike |
| Robustness of OCCT fillets and booleans | Failing operations | Fuzzy tolerance, clear messages, regression corpus |
| Quality at SubD extraordinary vertices | Defective zebras | G1 as default, G2 as an R&D option |
| Future OCP/Python updates in Blender | Missing wheels | Version pinning, per-platform CI |

## Open decisions

These choices change the scope; they are needed before milestone 1.

- [ ] **Main use:** rendering and kitbashing (loose tolerances, mesh first) or production too (clean STEP, tight tolerances)?
- [ ] **Platforms:** Windows only at first, or Windows + Linux + macOS right away?
- [x] **History:** hidden from standard users, shown to advanced users via a preference (decided 2026-09-26, [ADR 0002](decisions/0002-history-script-visibility.md)).
- [ ] **Constrained sketches:** integrate CAD Sketcher or write our own sketcher?
- [x] **Repository:** public from the start (decided 2026-09-26): https://github.com/Tonysa87/BlendSolid
- [ ] **Available time** per week, to calibrate the milestones.

## References

- [cadquery-ocp-novtk on PyPI](https://pypi.org/project/cadquery-ocp-novtk/)
- [build123d – Selector Tutorial](https://build123d.readthedocs.io/en/latest/tutorial_selectors.html)
- [build123d-mcp](https://pypi.org/project/build123d-mcp/0.3.69/)
- [OCCT BRepAlgoAPI\_Defeaturing](https://dev.opencascade.org/doc/refman/html/class_b_rep_algo_a_p_i___defeaturing.html)
- [OCCT BRepOffsetAPI\_MakeFilling](https://dev.opencascade.org/doc/refman/html/class_b_rep_offset_a_p_i___make_filling.html)
- [OpenSubdiv – Bfr](https://opensubdiv.org/docs/bfr_overview.html)
- [Rhino ToNURBS](https://docs.mcneel.com/rhino/8/help/en-us/commands/tonurbs.htm)
- [salvipeter/transfinite](https://github.com/salvipeter/transfinite)
- [Survey of multi-sided patches (2024)](https://www.sciencedirect.com/science/article/pii/S0167839624000207)
- [Greiner 1994 – Variational Design and Fairing](https://www.semanticscholar.org/paper/Variational-Design-and-Fairing-of-Spline-Surfaces-Greiner/daa09ef79becfc2f38adc468d9ed8c7e926a4b9d)
- [Blender 5.2 API – Gizmo](https://docs.blender.org/api/5.2/bpy.types.Gizmo.html)
- [meshStep (ABC dataset)](https://github.com/CNCKitchen/meshStep)
