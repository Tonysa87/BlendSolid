# SurfacePsycho: what it is, how it works, and what BlendSolid should take from it

- **Date:** 2026-09-27
- **Question (maintainer):** analyse SurfacePsycho (Blender NURBS/CAD add-on) to inform BlendSolid's future NURBS
  surface components: milestone 4 (SubD → NURBS), 5 (G2 surfaces), 6 (G2 fillets and Y-blend).
- **Method:** read the source code (`main` and the release branch `colors-for-real-this-time`, v0.10.4, cloned
  2026-09-27), the GitHub wiki (cloned), the GitHub issues and API metadata, the extensions.blender.org listing
  and version history, and the BlenderArtists thread. The Geometry Nodes assets (`assets/assets.blend`) were
  inspected headless with the Linux portable Blender 5.2.2 (node-group and node-type counts). Videos were **not**
  watched. Claims are tagged with their source ([S1]…, list in section 7); **[inferred]** marks my own reading of
  code or node structure; **[unverified]** marks what I could not check.

---

## 0. Summary

1. **SurfacePsycho (SP) is a freeform surface modeler whose geometry kernel is Geometry Nodes, not OCCT.**
   NURBS/Bezier patches, curves and compounds are plain mesh objects: the mesh is the control geometry and a
   "meshing" GN modifier evaluates and displays the surface. ~580 node groups / ~22 000 nodes do the maths
   (B-spline bases, interpolation by matrix inversion, blends, trims). OCCT (OCP 7.9.3.1, imported **inside
   Blender's process**) is used only for STEP/IGES import and export [S1][S3][S5].
2. **Mature in breadth, alpha in robustness.** v0.10.4 (2026-09-18), Blender 5.2 LTS+, Windows/macOS/Linux,
   16 k downloads, 122 GitHub stars, one developer (629 commits), active since 2023, talk at BCON 2026. The author
   warns of instabilities and breaking changes between versions [S2][S4][S6][S8].
3. **Continuity:** a *Blend Surfaces* modifier builds a Bezier patch between two edges with per-side continuity
   G0–G4 and tension; *Continuity Analysis* plots G0/G1/G2 error along edges. **No surface-surface fillets** (only
   2D fillets of curves, flat patches and trim contours). **SubD → NURBS** exists (*SubD to Compound*) but the
   wiki says it is "not yet accurate and precisely continuous" and it ignores N-gons and triangles [S3][S9][S10].
4. **License:** GPL-3.0-or-later (manifest SPDX, extension listing). BlendSolid is GPL-3.0-or-later too, so code and
   node groups can legally be reused with attribution. Architecturally, almost none of it fits BlendSolid (GN
   kernel, float32, no history as code, OCP in Blender's process); the **ideas and UX** are what transfers.
5. **Recommendation in one line:** take SP's blend UX, its analysis tools and its GN gizmo usage as references for
   milestone 5; use its SubD conversion as the baseline to beat (with numbers) in milestone 4; interoperate only
   through STEP; do not adopt GN as a kernel, and do not couple to SP's internal attribute schema.

---

## 1. What it does

### 1.1 Entities [S3 "Objects"]

| Entity | Definition | Display modifier (GN) |
| --- | --- | --- |
| NURBS Patch | rational B-spline surface, any degree, clamped/periodic, weights, knots | `SP - NURBS Patch Meshing` |
| Bezier Patch | single-span patch; many algorithms are implemented on Bezier first, NURBS later | `SP - Bezier Patch Meshing` |
| Flat Patch | planar face bounded by wires | `SP - FlatPatch Meshing` |
| Analytic faces | cylinder, cone, sphere, torus, surface of revolution, surface of extrusion (mostly from import) | one mesher each |
| Curve / Wire / Segment | wire = chain of segments; segment types Bezier, NURBS, circle (arc), ellipse (arc) | `SP - Curve Meshing` |
| Compound | several shapes in one object as GN instances; used for procedural modeling | `SP - Compound Meshing` |

Source for the type list: `common/enums.py` (`SP_obj_type`, `MesherName`, `SP_segment_type`) [S1].

### 1.2 Operations (≈110 GN modifiers, wiki index) [S3 "Modifiers and Tools"]

- **Blend & fill:** Blend Curve, Blend Surfaces, Coon Patch (4 Bezier sides), Fill Patch (up to 4 target
  segments), Square Fill, Loft, Loft from Internal Curves, Sweep (new in 0.10.4) [S3][S4].
- **Connect:** Connect Bezier Patch / Curve / Flat Patch (continuity to a neighbour), Railed Bezier Surface.
- **Trim / project / intersect:** trim contours in UV (wires drawn in the object's XY plane = UV), Trim Bezier
  Surface from Projected Wires, Project Curve on Surface, UV Curve on Surface, Intersect Bezier Patches, Crop or
  Extend Patch [S3 "Trimming Surfaces"].
- **Rebuild:** Fit Curve/Patch, Interpolate Curve/Patch (chord-length, centripetal, Chebyshev, Foley
  parametrizations — node names in `assets.blend`), Insert/Set Knot, Raise or Lower Degree, NURBS Weighting [S5].
- **Fillets:** *only planar/2D* — Fillet Curve or FlatPatch, Fillet Polyline with Circles, Fillet Trim Contour.
  There is no fillet between two surfaces [S3].
- **Solids:** preset compounds (Cylinder, Slab, Frame, Tubes, Oblong extrusion), Extrude Compound, Pipe Compound,
  Profile Revolution. **No booleans**; closed shells become solids only at export (sewing + `MakeSolid` +
  `BRepCheck_Analyzer`) [S1 `common/utils.py: shells_to_solids`].
- **Analysis:** Curvature Analysis (vertex-colour map), curvature combs, Continuity Analysis (G0/G1/G2 error plot),
  Plot Curve Torsion, Plot Distance Between Curves / from Mesh, Compare Mesh, Curvature Probe, "Psycho matcaps"
  (zebra-like matcaps) [S3][S1 `__init__.py`].
- **Mirror/symmetry:** Blender's own Mirror modifier is supported (must be last; bisect not supported) [S3].
- **SubD → NURBS:** `SP - SubD to Compound`: any mesh inside a compound is subdivided and converted to Bezier
  patches; supports creases; ignores N-gons and triangles; "not yet accurate and precisely continuous" [S9].
  Open issues: #24 (N-gons, 2026-06-16), #23 (merge patches across edges without n-poles, i.e. *packing*; closed
  2026-09-02 with "The method just fails") [S6].
- **I/O:** STEP (AP203) and IGES export with optional sewing (default tolerance 0.1 mm); STEP/IGES import with
  names/colours (`STEPCAFControl_Reader`) into **editable** SP objects ("importing a .STEP gives you direct editing
  access to the shapes"); SVG export of 2D shapes; import is "in progress, expect variable quality" [S1][S3].
- **Other:** conversion to/from Blender's internal (legacy) NURBS surface objects, asset library, SP Mode Tool
  (segment hover/selection overlay, Ctrl+click), dedicated keymap, pie menu, Exact Normals toggle [S1][S3].

### 1.3 Continuity

- *Blend Surfaces* operator/modifier: inputs `Target 1/2`, `Segment 1/2` (or auto), `Continuity 1/2` in
  {G0, G1, G2, G3, G4}, `Tension 1/2`, `Invert`, `Portion 1/2`, `Offset parallel 1/2`, `Bias Angle`,
  `2nd Target From Symmetry` + mirror axis/object, `Ignore Target Trim Contour 1/2`, `Prolongate if Straight`
  [S1 `tools/macros.py: SP_OT_blend_surfaces`; S5 node-group interface]. The result is a **Bezier patch** (the
  operator stacks `SP - Blend Surfaces` + `SP - Bezier Patch Meshing`).
- Continuity is imposed by construction on control points (rows of control points derived from derivatives of the
  target along the segment) **[inferred** from subgroups such as `SP - Bezier Patch Partial Derivative CP`,
  `SP - Continuity Case`, `SP - B-Spline Derivatives Basis [Up to 5th]`**]**. No evidence of a fairing/variational
  solver. How G2 is achieved against a *trimmed* target edge (whose boundary is not an isoparametric line) is not
  documented **[unverified]**.
- Verification is visual/plotted (Continuity Analysis, curvature combs); I found no numeric acceptance thresholds
  or automated continuity tests [S1 `.testing/`: 5 scripts on import/export/macros].

### 1.4 Maturity and activity

| Item | Value | Source |
| --- | --- | --- |
| Latest version | 0.10.4, 2026-09-18 (0.10.x since 2026-07-23) | [S4] |
| Blender | 5.2 LTS+ (0.10.x); 5.1+ (0.9.5–0.9.7); 5.0+ (0.9.0–0.9.4); 4.3+ (0.8.x) | [S4] |
| Platforms | windows-x64, macos-x64, macos-arm64, linux-x64; zips 51–71 MB | [S2][S1 manifest] |
| Status | "Still in Alpha. Expect instabilities, breaking changes and modifier incompatibilities when mixing versions" | [S2][S1 README] |
| Adoption | 16 106 downloads, 5.0/5 (9 reviews); GitHub 122 stars, 6 forks, 6 open issues | [S2][S6], 2026-09-27 |
| Team | single developer (Romain Guimbal, 629 commits); issues say "No AI work accepted" | [S6] |
| History | README: "actively developed since May 2023"; BlenderArtists announcement 2023-10-14; repo created 2023-11-02 | [S1][S7][S6] |
| Visibility | BCON 2026 talk "NURBS of NODES – SurfacePsycho Adventure" (2026-09-25) | [S8] |
| Commercial | also sold on Superhive ($63, GPL; that listing's page is stale, Blender 4.1) | [S11] |

Commit cadence on `main` (last 100 commits): 10–23 per month from 2025-11 to 2026-05, then work moved to release
branches (`colors-for-real-this-time` holds v0.10.4) [S6].

---

## 2. How it works

### 2.1 Kernel

- **Geometry Nodes is the kernel.** The author, 2026-01-20: *"SurfacePsycho is based on GeometryNodes. It is a pure
  geometry nodes kernel bringing a huge benefit of realtime feedback, blender vanilla total compatibility and very
  fast development. The downsides being of course lack of scalability, no external libraries, no code, limited
  performances. Open Cascade kernel is used purely for import and export of cad files"* [S6 issue #17].
- `assets.blend` (65 MB) holds 582 node groups / 21 978 nodes. Sizes: `SP - Blend Surfaces` 6 209 nodes across 162
  nested groups; `SP - Fill Patch` 4 313; `SP - Bezier Patch Meshing` 3 941; `SP - NURBS Patch Meshing` 3 270;
  `SP - SubD to Compound` 2 152 (one `Subdivision Surface` node, then Bezier/NURBS interpolation groups) [S5].
- Linear algebra is done in nodes: matrix inversion by LU/Gaussian elimination in node groups, `Invert Matrix`,
  `Matrix SVD`, repeat zones, and since 0.10.4 **list** nodes and closures ("Use lists for matrix inversion (x3.4
  speedup)") [S4][S5]. Open issue #25 (2026-07-29): B-spline interpolation still inverts one global collocation
  matrix, to be decomposed for speed [S6].
- **Precision [inferred]:** control points live in mesh attributes (`FLOAT_VECTOR`, i.e. float32) and GN float
  sockets are 32-bit, so all SP geometry and its solvers run in single precision; the exporter only widens to
  float64 when building OCCT objects (`read_attribute_by_name` → numpy float64) [S1 `common/utils.py`]. This is
  the same float32 trap BlendSolid documented in CLAUDE.md for milestone 1.5.
- Long-term, the author plans "a proper system in C++ directly as part of Blender", starting from a STEP-based data
  model; Blender developers "are positive", resources are the open question [S6 issue #17, 2026-01-20].

### 2.2 Data model in Blender

- An SP object is a **mesh object whose vertices are the control geometry** plus a stack of GN modifiers; the last
  one (the *mesher*) evaluates the surface and **stores the attributes the exporter reads** on the evaluated mesh:
  `CP_NURBS_surf` / `CP_any_order_surf` (control points), `CP_count`, `Degrees`, `IsClamped`, `IsPeriodic`,
  `Weights`, knot/multiplicity attributes, `CP_trim_contour_UV` + counts for trims [S1
  `exporter/export_final_shapes.py`]. The object type is recognised from the node-group name of the last visible
  mesher modifier (`sp_type_of_object`) [S1].
- Modifiers above the mesher act on the control geometry; Blender deform modifiers work there too [S3].
- **Files are "Blender-vanilla":** they open and display without the add-on, which is only needed for I/O and UX
  [S1 README][S3 "Compatibility"]. Versioning of node groups is manual (`Replace Node Group`, a versioning module) and
  old objects "might not export properly" [S3][S1 `common/versioning.py`].
- **No parametric history outside the modifier stack**: the modifier stack *is* the history; destructive edits use
  a "duplicate modifier, apply one, disable the other" pattern [S3 "Workflow Tips"].

### 2.3 Tessellation and display

- Display meshes are produced by the GN meshers (grid per patch, `Resolution U/V`, per-segment resolution in 0.10);
  trimmed patches use a "Dense Mesh from Contour" subgroup [S4][S5]. Normals are approximate by default; *Exact
  Normals* computes them from derivatives at a performance cost [S3 "Exact Normals"].
- OCCT's `BRepMesh` is not used for display [inferred: no `BRepMesh` in the source; S1].

### 2.4 UI

- Native Blender only: Shift+A entries, asset browser drag-and-drop of modifiers, N-panel, operators with Adjust
  Last Operation, a `WorkSpaceTool` ("SP Mode Tool") that draws a segment-hover overlay and switches a keymap,
  pie menu (Shift+F) [S1 `tools/`][S3].
- **Control-point editing is ordinary mesh Edit Mode** on the control grid (plus attributes such as endpoints and
  segment types set by operators) [S3 "Editing Wires"].
- **Geometry Nodes gizmos are used in production:** 29 `GizmoLinear` and 3 `GizmoDial` nodes in the assets, e.g.
  `SP - Continuity Selctor Gizmo` (a dial to pick G0–G4) [S5]. No Python `Gizmo`/`GizmoGroup` classes in the
  source [S1].

### 2.5 Dependencies and shipping

- One dependency: `cadquery_ocp_novtk` **7.9.3.1** wheels (cp313) listed in `blender_manifest.toml`, installed by
  Blender into the shared extensions site-packages and **imported in Blender's own process** [S1 manifest].
  Everything else is node groups in `assets.blend`. Heavy operations run synchronously in Blender; no worker
  process [S1: no `subprocess`/`multiprocessing`].

---

## 3. License and reuse

- **License:** `license = ["SPDX:GPL-3.0-or-later"]`, `copyright = ["2026 Romain Guimbal"]` in the manifest, and
  "GNU General Public License v3.0 or later" on the extension listing [S1][S2]. The repository has **no LICENSE
  file** (GitHub API reports `license: null`) and only `__init__.py` of 33 Python files carries the GPL header [S6];
  the manifest statement by the copyright holder is still a clear grant, but anyone copying files should keep the
  copyright line and add a header.
- **Compatibility with BlendSolid:** BlendSolid is GPL-3.0-or-later (`blendsolid/blender_manifest.toml`, `LICENSE`).
  Same license, so SP code **and** its node groups (part of the distributed work) may be copied or adapted into
  BlendSolid, provided BlendSolid stays GPL-3.0-or-later, keeps SP's copyright notice on copied parts and states
  changes (GPLv3 §5). No incompatibility with OCCT (LGPL-2.1 with exception) or build123d (Apache-2.0) is introduced.
  (Not legal advice.)
- **Practical limits:**
  - SP's Python is Blender-side OCP code; BlendSolid never imports OCP in Blender (ADR 0001), so any reused
    function has to move into the worker and be ported from OCP 7.9 to 8 (e.g. `TopoDS.Shell_s` → `TopoDS.Shell`,
    see SP issue #13 [S6]).
  - Node groups can't be diffed or reviewed as text (the author: "no version control system exists for nodes yet"
    [S6 #23]); reusing them means owning opaque binary assets.
  - Contributing back: SP's issues state "No AI work accepted" [S6 #23, #24]; BlendSolid is developed with an AI
    agent, so upstream contributions from this project are not appropriate without the maintainer writing them.

---

## 4. Overlap, complementarity, interoperability, risks

### 4.1 Where they differ

| | SurfacePsycho | BlendSolid (spec) |
| --- | --- | --- |
| Focus | freeform surfaces, control-point first, industrial design | solids + history as code; freeform via SubD → NURBS |
| Kernel | Geometry Nodes (float32), OCCT only for I/O | OCCT everywhere (float64), in a worker process |
| History | GN modifier stack; destructive steps by applying | build123d script, semantic selectors |
| Solids / booleans / 3D fillets | no booleans, no surface fillets; solids only at export | MVP (booleans, fillets, shell…) |
| Blends / fills | Blend Surfaces G0–G4, Coon, Fill, Loft, Sweep | milestone 5 (G2 blend, Greiner fairing), `BRepOffsetAPI_MakeFilling` |
| SubD → NURBS | interpolation after GN subdivision; approximate; no N-gons; packing failed | milestone 4: exact regular faces, OpenSubdiv Bfr, packing |
| Files without add-on | yes (vanilla) | display meshes persist; recompute needs the add-on + worker |
| Performance model | real-time on small models; "lack of scalability" by the author's own words | worker latency; OCCT multi-core |

### 4.2 Competition

They compete directly on milestones 4–5: an SP user can already do SubD → patches, G2 blends, curvature analysis
and STEP export today. BlendSolid's differentiators are exactness (float64, OCCT validity), solids and booleans,
3D fillets, script history, and numerically verified continuity. For pure class-A-ish surfacing with instant
feedback SP will stay ahead unless BlendSolid's blend loop is interactive.

### 4.3 Interoperability

- **STEP is the right seam.** Both write/read STEP through OCCT; SP imports STEP into editable patches, BlendSolid
  imports STEP into a part. Round-trip (BlendSolid → STEP → SP → STEP → BlendSolid) is a realistic user workflow
  and a free test corpus of freeform NURBS for milestones 4–5.
- **Do not read SP attributes directly.** The schema is internal, versioned by hand and declared unstable [S2][S3].
- **Coexistence in one Blender:** SP loads OCP 7.9.3.1 into Blender's process; BlendSolid loads OCP 8.0.1 only in
  its worker, started with `python -I` and its own library folder first in `sys.path`
  (`blendsolid/client.py`, `blendsolid/worker/server.py`). By reading the code there is no shared-module or DLL
  clash **[inferred, not tested]**: to be verified with both extensions enabled.

### 4.4 Risks

- If the author's native C++ NURBS system for Blender materialises [S6 #17], Blender itself may gain a NURBS data
  type that users expect add-ons to use; BlendSolid should track it (opportunity for display/interop, risk of
  overlap). No public design document found **[unverified]**.
- User expectations: SP sets the bar for interactive feedback (real-time GN) and analysis visuals in Blender;
  BlendSolid's worker round-trip must feel comparable during blend parameter drags.
- Porting SP node groups would import float32 numerics and unreviewable binary logic into BlendSolid.

---

## 5. Recommendations

| # | Action | Verdict | Milestone | Why / how |
| --- | --- | --- | --- | --- |
| 1 | Use SP's *Blend Surfaces* parameter set as the UX spec for BlendSolid's blend: per-side continuity (G0/G1/G2), per-side tension, edge portion/range, invert, blend to mirror image, offset | **Adopt** | 5 | Proven, compact parameter set users already know; map each to a script argument + Adjust Last Operation + native gizmos |
| 2 | Continuity analysis *along an edge* (plot G0 gap, G1 angle, G2 curvature jump, with tolerance) | **Adopt** | 5 | SP's Continuity Analysis is exactly the metric of BlendSolid's milestone-5 criterion; BlendSolid computes it in the worker in float64 and shows it with `gpu` |
| 3 | Curvature combs and curvature colour map; zebra via matcap as a cheap first zebra | **Adopt** | 5 (catalog: Analysis) | Low cost, expected by SP users; matcap zebra needs no shader work |
| 4 | GN gizmos (`GizmoLinear`, `GizmoDial`) for blend parameters, e.g. a dial to choose continuity | **Study further** | 5 | SP proves they work on 5.2 in shipping assets; the spec already lists GN gizmos as an option; compare with the Python gizmos BlendSolid uses today |
| 5 | Treat SP's *SubD to Compound* as the baseline: build a comparison on the same cages (deviation from the limit surface, G1/G2 across patch edges, patch count after packing, N-gons, creases) | **Adopt (as benchmark)** | 4 | Gives milestone 4 a concrete "better than existing" target; SP itself says it is not accurate |
| 6 | Packing criterion from SP issue #23 (merge patches across edges whose ends are regular valence-4 interior vertices) | **Study further** | 4 | Same idea as the spec's "faces packed into larger surfaces"; SP reports its GN method fails, so do it in the worker on B-spline knot vectors and measure |
| 7 | Support creases and N-gons in SubD → NURBS from the start (one extra subdivision level turns N-gons into quads, SP issue #24) | **Adopt** | 4 | Users will compare with SP; the N-gon trick is standard Catmull-Clark behaviour |
| 8 | Interpolation parametrization choices (chord-length, centripetal, Foley, Chebyshev) exposed for fit/interpolate operations | **Study further** | 4–5 | SP ships them; OCCT `GeomAPI_Interpolate`/`GeomAPI_PointsToBSplineSurface` offer parametrization options — check coverage |
| 9 | STEP round-trip tests with SP-exported files as a freeform NURBS corpus, and a coexistence smoke test with both extensions enabled | **Adopt** | 3 (I/O), reused in 4–5 | Cheap interop evidence; catches DLL/`sys.path` issues early |
| 10 | Reuse SP's STEP/IGES reader code (names, colours, hierarchy via `STEPCAFControl_Reader`) | **Study further** | 3 | GPL-compatible, but check first what build123d's importer already gives; any reuse moves to the worker, ports to OCP 8, keeps SP's copyright |
| 11 | Geometry Nodes as a geometry kernel, or porting SP node groups | **Avoid** | 4–6 | float32, performance limits admitted by the author, binary/unreviewable logic; conflicts with the spec's OCCT + numeric verification rules |
| 12 | Reading SP's internal mesh attributes to convert SP objects in place | **Avoid** | — | Unstable alpha schema; use STEP |
| 13 | Expecting SP to inform G2 3D fillets / Y-blends | **Avoid** | 6 | SP has no surface fillets; milestone 6 needs other references (OCCT G1 fillet + two-pass G2, literature in the spec) |
| 14 | "Files open without the add-on" as a design value: make sure BlendSolid parts keep their last display mesh and read-only state when the add-on is missing | **Study further** | 3 | Users coming from SP will expect it; BlendSolid already stores meshes, check the add-on-less behaviour explicitly |

---

## 6. Open points

- Watch the BCON 2026 talk [S8 video] for the author's roadmap and any numbers on performance/precision
  **[not watched]**.
- Whether SP's G2 blend is exact G2 or approximate (sampled derivatives) was not measured; if useful, export an SP
  blend to STEP and measure the curvature jump with OCCT in the worker.

---

## 7. Sources (accessed 2026-09-27)

- [S1] SurfacePsycho source, GitHub: https://github.com/RomainGuimbal/SurfacePsycho (branch `main`, last commit
  2026-07-30; branch `colors-for-real-this-time`, v0.10.4, 2026-09-18). Files cited: `blender_manifest.toml`,
  `README.md`, `__init__.py`, `common/enums.py`, `common/utils.py`, `common/asset_list.py`, `tools/macros.py`,
  `exporter/export_final_shapes.py`, `exporter/export_operator.py`, `exporter/export_process_cad.py`,
  `importer/import_reader.py`, `importer/import_shape_to_blender_object.py`, `.testing/`.
- [S2] Extension listing: https://extensions.blender.org/add-ons/surfacepsycho/
- [S3] Wiki: https://github.com/RomainGuimbal/SurfacePsycho/wiki (pages Objects, Modifiers and Tools, Import and
  Export, Compatibility/Data safety, Exact Normals, SP Mode Tool, Editing Wires, Trimming Surfaces, Workflow Tips,
  Procedural modeling with SP, SP – Blend Surfaces, SP – Coon Patch, SP – Continuity Analysis).
- [S4] Version history: https://extensions.blender.org/add-ons/surfacepsycho/versions/
- [S5] `assets/assets.blend` of v0.10.4 inspected headless with Blender 5.2.2 (Linux portable): node-group counts,
  node types, group interfaces.
- [S6] GitHub issues and API: https://github.com/RomainGuimbal/SurfacePsycho/issues — #13, #17 (author's comment
  2026-01-20), #23 (closed 2026-09-02), #24, #25; repository metadata via `gh api`.
- [S7] BlenderArtists thread: https://blenderartists.org/t/surfacepsycho-addon-project/1487629
- [S8] Blender Conference 2026 schedule: https://conference.blender.org/2026/schedule/ ; talk video
  https://www.youtube.com/watch?v=9z1MwYy3Mkw
- [S9] Wiki page SP – SubD to Compound: https://github.com/RomainGuimbal/SurfacePsycho/wiki/SP---SubD-to-Compound
- [S10] Tutorials playlist: https://youtube.com/playlist?list=PLsTbL26zgwpI6m0qrpZZFmrgf3PaFzuiq (not watched)
- [S11] Superhive listing: https://superhivemarket.com/products/surfacepsycho
