# Modeling feature survey: what Plasticity, FORGE and other tools offer beyond our catalog

Date: 2026-09-28. Scope: find modeling commands in hard-surface and CAD tools that are **not** yet in
BlendSolid's "Feature catalog by phase" or in the milestone 3a–3e plan (`docs/spec.md`), and rank them.

Already in the catalog (not repeated below unless an option is missing): primitives, 2D sketch (incl. slot,
spiral, offset, curve fillet), projections and outline, extrude/revolve/loft/sweep/pipe, shell/thicken,
mirror/array, cut, booleans with ghost preview, constant/variable/partial fillet, asymmetric chamfer, fillet
removal, conic/chordal/G2/full fillet (R&D), imprint, topology cleanup, delete/offset/draft face, offset
edge/face loop, isoparam, the surface set (4 edges, patch, bridge, blend, extend, constrained, rebuild, untrim),
zebra/curvature/continuity/sections/measurements, construction planes, place on face, quads, STEP/IGES/BREP,
hidden-line SVG, SubD→NURBS, G2 surfaces and fillets.

Legend: **[unverified]** = could not be confirmed from a primary source; *(own assessment)* = my engineering
judgement, not a quote.

---

## 1. What "FORGE" is

Already researched on 2026-09-26 (`docs/research/2026-09-26-modeling-workflows.md`, section 1); re-checked today.
Several products share the name; in the hard-surface context it is:

**FORGE: CAD Precision Modelling in Blender**, by RenderCraft Studio. A commercial (GPL-licensed) Blender add-on,
V1.0 released end of June 2026, Blender 4.2–5.0, $49/$149/$299, "200+" sales on Superhive.
Sources: [Gumroad page](https://rendercraftstudio01.gumroad.com/l/forge),
[Superhive listing](https://superhivemarket.com/products/forge-cad-precision-modelling-in-blender),
[product site](https://forgewebsite.netlify.app/) (503 / "usage exceeded" on both 2026-09-26 and today).

- Pitch: "Professional NURBS & BRep CAD modeling inside Blender … flawless fillets, live booleans, and instant
  zero-retopology quad mesh conversion. Includes STEP & IGES I/O." A "Forge Mode" workspace "just like Edit Mode".
- Tools named on the Gumroad page (V1.0): Line, Spline, Cylinder, Sphere, Boolean (with "real-time ghost
  preview"), Fillet and Chamfer, **Split** ("slice bodies and faces … using planes or sketched lines"), Trim,
  Loft, Sweep, Revolve, Pipe ("hollow or solid"), Mirror ("auto-fusing"), **Auto-Retopology** (all-quad mesh);
  "and so much more: Extrude, Offset, **Inset**, Imprint, Shell, Thicken, Array, **Auto-Regions**,
  **Quad-Remesh**, Project". A **Performance Mode** toggle with "Viewport Curve Quality".
- Roadmap: Phase 1 "history tree … live dimension editing … sketch constraints"; Phase 2 "N-sided patching,
  SubD-to-CAD bridging, G2/G3"; Phase 3 "Mechanical Assemblies: joints, hinges, **interference detection**, 2D
  dimensioned blueprint exports". No newer version than V1.0 found today.
- Kernel: not stated by the vendor. A search-engine snippet says "geometry is calculated by OpenCascade through
  Replicad, in a background worker", but it appears to come from an unrelated web app repository
  ("TheForgefinal", now 404). **[unverified]** — do not rely on it.

Other "Forge" products, not relevant: ForgeCAD (code-first JS/TS CAD in the browser,
[GitHub](https://github.com/ForgeCAD/forgecad-public-kit)); Autodesk Forge (now Autodesk Platform Services);
Kenney Asset Forge; FrameForge and other unrelated Blender add-ons.

**Features FORGE has that our catalog lacks:** Inset, Auto-Regions (Plasticity-style: closed curve areas become
faces automatically), auto quad remesh of the whole part (our catalog has "quad mesh for simple faces" and
QuiltMesher R&D, so we are covered in intent), interference detection (roadmap), performance-mode viewport
quality (we have the tessellation tolerance setting).

---

## 2. Per program: notable commands not in our catalog

One line each; sources in brackets. Items already in the catalog are omitted.

### 2.1 Plasticity 2026.1 (manual: [doc.plasticity.xyz](https://doc.plasticity.xyz), source
[github.com/nkallen/plasticity-document](https://github.com/nkallen/plasticity-document))

- **Fillet Shell options**: "conic, G2 continuous, or constant width profiles … variable distance and range
  limiting" — constant width (chord) is in our R&D row; nothing new except the *range limiting* UI
  ([fillet-shell](https://doc.plasticity.xyz/solid/fillet-shell)).
- **Full Round Fillet** (2024.1) — a fillet that replaces a middle face between two side faces
  ([2024.1 notes](https://doc.plasticity.xyz/release-notes/whats-new-2024.1)); in our R&D row as "full".
- **Remove Fillets From Shell** "with possible restrictions on max radius and convexity" — catalog has fillet
  removal; the *filter by radius/convexity* is new ([page](https://doc.plasticity.xyz/solid/remove-fillets-from-shell)).
- **Hollow**: on a face "creates an open void"; on a solid "turns it into a closed hollow form" (closed-cavity
  shell) ([hollow](https://doc.plasticity.xyz/solid/hollow)).
- **Match Face**: "Replace the selected Face with another Face" (= Fusion Replace Face)
  ([match-face](https://doc.plasticity.xyz/solid/match-face)).
- **Deform Solid and Sheet**: "Wrap existing solid and sheet objects onto a regular and irregular surface"
  ([page](https://doc.plasticity.xyz/solid/deform-solid-and-sheet)).
- **Unwrap Face**: flatten a face ([unwrap-face](https://doc.plasticity.xyz/solid/unwrap-face)).
- **Curve Array**: copies along a curve with twist, scale, alignment, instances
  ([curve-array](https://doc.plasticity.xyz/common/curve-array)).
- **Radial Array** with instances ([radial-array](https://doc.plasticity.xyz/common/radial-array)) — array is
  in 3b; *instances* (linked copies) are the new part.
- **Text** → curves (built-in fonts) ([text](https://doc.plasticity.xyz/sketch/text)).
- **Offset Region**: offset a whole closed region (face-like 2D area) ([offset-region](https://doc.plasticity.xyz/sketch/offset-region)).
- **Cut** with a curve: "the cut is made based on a surface generated from that Curve"
  ([cut](https://doc.plasticity.xyz/solid/cut)) — covered by 3c "cut by sketch".
- **Complete Edge**: extend an edge until it meets another ([complete-edge](https://doc.plasticity.xyz/common/complete-edge)).
- **Section Analysis**: live clipping plane ([section-analysis](https://doc.plasticity.xyz/common/section-analysis)).
- **Copy/Paste with Placement**, **Place** (duplicate to a picked point with scale/rotate/flip)
  ([place](https://doc.plasticity.xyz/common/place)) — place on face is in the catalog.
- **Create/Realize Instance** (2025.3) ([notes](https://doc.plasticity.xyz/release-notes/whats-new-2025.3)).
- **Export Hidden Line**, **PolySplines** (mesh → G2 NURBS, Studio), **Slot** (2026.1)
  ([2026.1 notes](https://doc.plasticity.xyz/release-notes/whats-new-2026.1)) — all three already in the catalog/M4.
- **XNurbs / Align Surface** (Studio): N-sided and G0/G1/G2 edge matching
  ([xnurbs](https://doc.plasticity.xyz/solid/xnurbs)) — our M5/M6.

### 2.2 FORGE — see section 1 (Inset, Auto-Regions, interference detection on roadmap).

### 2.3 Autodesk Fusion
Sources: [glossary](https://productdesignonline.com/tips-and-tricks/autodesk-fusion-360-glossary/),
[Fusion help](https://help.autodesk.com/view/fusion360/ENU/).

- **Rib** (thin feature from an open sketch curve, parallel to the sketch plane) and **Web** (normal to it)
  ([rib help](https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-RIB)).
- **Emboss**: wrap sketch profiles/text onto a face, emboss or deboss, depth, tangent chain
  ([emboss help](https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-EMBOSS.htm)).
- **Hole** (simple/counterbore/countersink, tapped) and **Thread** (cosmetic or modeled) (glossary).
- **Coil** (helical spring/solid) and **Pipe** (glossary).
- **Pattern on Path** (glossary).
- **Rule Fillet**: fillet all edges of a face or feature by rule, not by edge picks
  ([glossary entry](https://productdesignonline.com/glossary/rule-fillet/)).
- **Replace Face**: remove faces, extend/trim neighbours to a target face
  ([help](https://help.autodesk.com/view/fusion360/ENU/?contextId=MODEL-REPLACE-FACE-CMD)).
- **Boundary Fill**: build solids from cells bounded by intersecting tool bodies/surfaces
  ([help](https://help.autodesk.com/view/fusion360/ENU/?guid=SFC-REF-BOUNDARY-FILL)).
- **Split Face** / **Split Body** / Silhouette Split (glossary) — split is in 3c.
- **Scale** (non-uniform), **Combine** (keep tools), **Interference**, **Center of Mass**, **Draft Analysis**,
  **Curvature Comb** (glossary).
- **Form (T-Splines)** workspace — our SubD→NURBS M4 plays that role.

### 2.4 Shapr3D
- **Wrap & Emboss** (v26.30, 2026-03-03; gizmo in 26.50) — cylindrical and conical faces
  ([help](https://support.shapr3d.com/hc/en-us/articles/25620612815260-Wrap-Emboss),
  [release](https://support.shapr3d.com/hc/en-us/articles/25704787506460-26-30-Wrap-Emboss-tool-is-here)).
- **Replace Face** ([help](https://support.shapr3d.com/hc/en-us/articles/7874457242268-Replace-Face)).
- **Offset Edge (3D)** ([help](https://support.shapr3d.com/hc/en-us/articles/7874464169244-Offset-Edge-3D)) — in catalog.
- **Extrude with draft angle** ([help](https://support.shapr3d.com/hc/en-us/articles/7874453786908-Extrude)).
- **Variables and expressions** shared across features
  ([help](https://support.shapr3d.com/hc/en-us/articles/18763796906396-Parametric-design-with-variables-and-expressions)).
- Help center pages returned HTTP 403 to the fetcher; details are from search snippets. **[partly unverified]**

### 2.5 MoI 3D ([command reference](http://moi3d.com/2.0/docs/moi_command_reference7.htm))
- **Inset**: "Generates either a depressed or raised panel that follows the outline of faces"; localized, unlike
  Shell ([forum, M. Gibson](http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=3295.3)). Pieces must be bounded
  by sharp corners.
- **Boolean Merge**: "Combines objects together and extracts all volumes" (all cells, like Boundary Fill).
- **Rail Revolve**, **Network** (surface from a 2-direction curve network), **Silhouette** curves.
- **Flow** (with a "Projective" decal-like option) and **Twist** deformers (V5)
  ([MoI forum/wiki](http://moi3d.com/wiki/V3Beta)) **[version details unverified]**.

### 2.6 Onshape ([help](https://cad.onshape.com/help/Content/PartStudio/part_studios.htm))
- **Fillet** cross sections Circular / **Conic (rho)** / **Curvature (magnitude)**, variable, partial,
  asymmetric, **"Allow edge overflow"**, smooth corners, full round
  ([fillet](https://cad.onshape.com/help/Content/PartStudio/fillet.htm)).
- **Enclose**: solid from any set of bounding surfaces/solids/planes
  ([enclose](https://cad.onshape.com/help/Content/PartStudio/enclose.htm)).
- **Move Face** (translate/rotate/offset), **Replace Face**, **Move Boundary** (extend/trim sheet edge)
  ([move face](https://cad.onshape.com/help/Content/PartStudio/move_face.htm)).
- **Fill** (N-sided surface with G0/G1/G2) ([fill](https://cad.onshape.com/help/Content/PartStudio/fill.htm)) — our Patch.
- Hole, Rib, Wrap, Thread (FeatureScript), Sheet metal exist in Onshape (my knowledge) **[not re-verified today]**.

### 2.7 Rhino 8 ([Solid Tools toolbar](http://docs.mcneel.com/rhino/8/help/en-us/toolbarmap/solid_tools_toolbar.htm),
[New in Rhino 8](https://docs.mcneel.com/rhino/8/help/en-us/commandlist/newinrhino8.htm))
- **BooleanSplit** ("split and close solids at intersections"), **Boolean2Objects** (cycle through results).
- **Cap** (fill planar holes), **CreateSolid** (closed polysurface from surfaces).
- **MergeCoplanarFace(s)** — our topology cleanup.
- **BlendEdge** (variable G2 edge blend) ([help](http://docs.mcneel.com/rhino/8/help/en-us/commands/blendedge.htm)),
  **ChamferEdge** with varying distances, **FilletEdge edit** — in catalog/M6.
- **WireCut**: "trim a polysurface with a curve similar to cutting foam with a heated wire".
- **MoveFace / MoveEdge / FoldFace** (rotate faces about an axis), **SolidPtOn** (pseudo control points on a solid).
- **Inset** (offset face edges inward) — also for polysurfaces.
- **Hole family**: RoundHole, MakeHole/PlaceHole, RevolvedHole (profile-revolved hole), MoveHole, RotateHole,
  ArrayHole(Polar), UntrimHoles.
- **PushPull** (new in 8), **ShrinkWrap** (mesh), **DimVolume**.

### 2.8 SolidWorks
- **Hole Wizard** / Hole Series (standard fastener holes incl. tapped, cosmetic threads)
  ([overview](https://help.solidworks.com/2026/English/SolidWorks/sldworks/c_Hole_Wizard_Overview.htm)).
- **Wrap**: emboss / deboss / **scribe** (split the face along the wrapped sketch)
  ([help](https://help.solidworks.com/2025/english/SolidWorks/sldworks/hidd_dve_surf_wrapping_sketch.htm)).
- **Flex**: bend, twist, taper, stretch a body
  ([overview](https://help.solidworks.com/2023/english/solidworks/sldworks/c_Flex_Overview.htm)).
- **Indent**: offset pocket/protrusion shaped by a tool body with thickness and clearance
  ([overview](https://help.solidworks.com/2025/english/solidworks/sldworks/c_Indent_Overview.htm)).
- **Fastening features**: Vent (grille from a sketch), Mounting Boss, Snap Hook, Lip/Groove
  ([overview](https://help.solidworks.com/2025/english/SolidWorks/sldworks/c_Fastening_Features_Overview.htm),
  [vent](https://help.solidworks.com/2022/English/SolidWorks/sldworks/hidd_dve_vent.htm)).
- **Dome**, **Rib**, **Draft**, **Thread**, **Scale**, **Freeform** (search-result feature lists)
  **[details not re-verified]**.

### 2.9 nTop
Implicit/field modeling (lattices, variable-thickness shells, field-driven blends). Not applicable to an exact
BRep kernel; skipped as requested.

### 2.10 Blender hard-surface add-ons (workflow ideas, mesh-level today)
- **BoxCutter/HardOps** modes: Cut, **Slice** ("duplicates the mesh using difference on the primary and
  intersect on the secondary"), **Inset** (for curved simple shapes, slice + solidify), Join, **Knife** (cut
  edges only), **Extract** (turn existing booleans into a reusable cutter), Make
  ([boxDocs modes](https://boxcutter-manual.readthedocs.io/en/latest/modes/)). HardOps: sharpen/"Csharp",
  "Step" (bake bevels and add a new level) ([masterxeon1001](https://masterxeon1001.com/hard-ops-007-csharp-ssharp/)).
- **Fluent 4 / Power Trip**: cut, slice, inset, bevel/chamfer, array/mirror/taper, **grid** (turn any cut
  into a grille, 14 styles), **plate**, wire, pipe, **screw head scattering**, cloth panel
  ([Superhive](https://superhivemarket.com/products/fluent), [docs](https://cgthoughts.com/fluent/doc/)).
- **MESHmachine**: Fuse/Unfuse/Change Width/Unchamfer/Unbevel (edit or remove existing bevels), Plugs (detail
  inserts), Stash, Real Mirror, Offset Cut ([docs](https://machin3.io/MESHmachine/docs/)).
- **DECALmachine**: simple/subset/**panel**/info decals; panel decals "sliced" into meshes as panel lines,
  trim sheets, projection/shrinkwrap on curved surfaces ([docs](https://machin3.io/DECALmachine/docs/)).

---

## 3. Consolidated candidate table (features NOT in our catalog)

Value = value for hard-surface modeling in Blender. Feasibility names the OCCT/build123d path (all OCCT classes
listed were checked to exist in our OCP 8 build today). Effort: S ≤ 3 days, M ≈ 1–2 weeks, L > 2 weeks
*(own assessment)*.

| # | Feature | Programs | What it does | Value | OCCT / build123d feasibility | Effort | Milestone |
|---|---|---|---|---|---|---|---|
| 1 | Extrude options: taper (draft) angle, up-to-next/last/face, both sides | Fusion, Shapr3D, Onshape, SolidWorks | Tapered extrusion; extrude until the next face | High | build123d `extrude(taper=, until=Until.NEXT/LAST, target=, both=)`; `BRepFeat_MakeDPrism` | S | 3a |
| 2 | Inset panel (raised/recessed, follows face outline) | MoI, Rhino, FORGE, BoxCutter, Fluent | Offset a face's outline inward, then push the inner area in or out | High | Planar faces: `BRepOffsetAPI_MakeOffset` on the face wire + prism/cut. Curved faces: offset curves on surface are hard (MoI limits it to sharp-bounded faces) | M (planar S) | 3c |
| 3 | Panel lines / grooves along a curve on a face | DECALmachine, Fluent, (SolidWorks Wrap scribe) | Cut a small V/U/square groove along an imprinted curve | High | Imprint curve (`BRepFeat_SplitShape`), sweep a small profile (`BRepOffsetAPI_MakePipeShell`) along it, boolean cut; fillet the groove edges | M | 3c/3d |
| 4 | Rule fillet (by face / feature / convex-concave / all) | Fusion, Plasticity (range), Onshape | Fillet all edges of a face or feature, filtered by convexity | High | Selection rule only; edges from our semantic selectors + dihedral sign; same `BRepFilletAPI_MakeFillet` | S | 3b |
| 5 | Hole feature (simple, counterbore, countersink, tapped cosmetic; on a face, patterned) | Fusion, SolidWorks Hole Wizard, Rhino hole family, Onshape | Standard holes placed by click, with ISO sizes | High | build123d `Hole`, `CounterBoreHole`, `CounterSinkHole`; `BRepFeat_MakeCylindricalHole`; ISO table in data | S | 3b |
| 6 | Modeled thread / helix / coil / spring | Fusion Thread + Coil, SolidWorks Thread, Onshape (FS) | Helical solid thread or spring | Med | `Wire.make_helix` + `sweep` (pipe shell, auxiliary spine); bd_warehouse `Thread` (Apache-2.0, not bundled). Booleans of helicoids are slow and fragile — cosmetic thread (metadata + texture) is the cheap variant | M | 3d |
| 7 | Emboss / deboss / wrap text and sketches onto curved faces | Fusion Emboss, Shapr3D Wrap & Emboss, SolidWorks Wrap, Plasticity Deform | Raised or engraved logos/labels following a face | High (labels, grips, details) | build123d `Face.wrap(planar_shape, loc)` (length-preserving, approximated), then thicken/extrude along normals + boolean. Exact for cylinders/cones by building pcurves in (u,v) (developable). Text needs a bundled font (known pitfall) | M (cyl/cone), L (freeform) | 3c (cyl/cone), later (freeform) |
| 8 | Text tool (sketch text) | Plasticity, Fusion, Onshape, SolidWorks | Curves from text for extrude/emboss | Med | build123d `Text(font_path=…)` | S | 3a |
| 9 | Rib / web | Fusion, SolidWorks, Onshape | Thin wall from an open curve that grows until it meets the body | Med-High (brackets, housings) | `BRepFeat_MakeLinearForm` (made for ribs), or thicken the open wire to a face, extrude `until`, intersect with the body's hull, fuse | M | 3b/3c |
| 10 | Boundary fill / Enclose / Boolean Merge / BooleanSplit (cells) | Fusion, Onshape, MoI, Rhino | Intersect several bodies/surfaces, pick which cells to keep | High (fast complex forms from simple cutters) | `BOPAlgo_MakerVolume` (solids from surfaces), `BOPAlgo_CellsBuilder` (pick cells), `BRepAlgoAPI_Splitter` | M | 3c |
| 11 | Replace face / Match face / Move face (translate + rotate) | Fusion, Shapr3D, Onshape, Plasticity, Rhino MoveFace/FoldFace | Swap a face for another surface, or move/tilt a face with neighbours extending | Med-High (edit imported STEP, tilt a wall) | No single API. Offset/draft are covered (`BRepOffset_MakeOffset`, `BRepOffsetAPI_DraftAngle`); general move/replace = remove face (`BRepAlgoAPI_Defeaturing`) + rebuild with extended target surface + `Splitter`; fragile **[feasibility unverified]** | L | 3c (tilt via draft), later (general) |
| 12 | Modify existing fillet (change radius/remove by radius filter) on imported or history-less solids | Onshape, Plasticity Remove Fillets (radius/convexity filter), MESHmachine Change Width/Unfuse | Recognize fillet faces, remove, refillet | Med (STEP import users) | `BRepAlgoAPI_Defeaturing` + fillet recognition (cylindrical/toroidal faces between tangent neighbours) + refillet | M | 3e (with STEP import) |
| 13 | Slice (split and keep both parts as separate objects, optional gap) | BoxCutter, Fluent, FORGE Split, Rhino BooleanSplit | Cut a part into two editable parts along a sketch/cutter | High | `BRepAlgoAPI_Splitter`, build123d `split(keep=Keep.BOTH)`; gap = offset the tool. Needs the part system to spawn a second part script | S-M | 3c |
| 14 | Knife (imprint only, no removal) from a drawn line | BoxCutter Knife, Rhino SplitFace | Split faces along a drawn polyline for later push/pull | Med | `BRepFeat_SplitShape` / projection (`BRepProj_Projection`) — the catalog's imprint, but as a draw-in-viewport tool | S | 3c |
| 15 | Pattern on path / curve array (with instances) | Fusion, Plasticity Curve Array, SolidWorks | Copies along a curve with alignment/twist/scale | Med | Locations from `Edge.location_at(t)`; fuse or keep as instances | S | 3d (needs curves) |
| 16 | Instances (linked copies inside a part's patterns) | Plasticity 2025.3, Rhino blocks | Array copies share one computed body | Med (performance) | Compute once, place copies with `TopLoc_Location`; Blender side = linked data or GN instances | M | 3b |
| 17 | Grille / vent generator | SolidWorks Vent, Fluent grid | Pattern of slots/holes inside a boundary with ribs/border | High (hard-surface signature detail) | Sketch pattern (slots/hex) clipped to a region + cut; plus optional border offset | M | 3b/3c (after sketch + array) |
| 18 | Hardware library (screws, bolts, nuts, inserts) placed by click | Fluent screw scatter, Fusion McMaster insert, SolidWorks Toolbox | Drop standard fasteners onto holes | Med | bd_warehouse fasteners (Apache-2.0) or own simplified heads; Blender Asset Browser | M | later (after 3b holes) |
| 19 | Hollow closed (internal cavity) | Plasticity Hollow, Fusion shell with no removed faces | Closed shell with an inner void | Low-Med | `BRepOffsetAPI_MakeThickSolid` with empty face list / offset shape + cut | S | 3b (shell option) |
| 20 | Non-uniform scale of a body | Fusion Scale, SolidWorks Scale | Scale by X/Y/Z factors | Low-Med | `BRepBuilderAPI_GTransform` (converts to NURBS; circles become B-splines) | S | 3b |
| 21 | Indent (pocket shaped like a tool body with clearance/thickness) | SolidWorks | Emboss one body's shape into another | Low-Med | Offset tool (`BRepOffsetAPI_MakeOffsetShape`) + booleans | M | later |
| 22 | Interference check, mass properties / center of mass, volume dimension | Fusion, Rhino DimVolume, FORGE roadmap | Numbers for fit and weight | Med | `BRepAlgoAPI_Common` + `GProp_GProps`; `BRepExtrema_DistShapeShape` | S | 3e |
| 23 | Draft analysis, minimum radius analysis | Fusion, SolidWorks | Color faces by angle to a pull direction / flag radii below a threshold | Low-Med (moldability, printability) | Shader on normals (draft); curvature from `BRepLProp` (min radius) | S | 3e |
| 24 | Live section / clipping plane | Plasticity Section Analysis, Fusion | Temporary cutaway | Med | Blender side only (clip planes / a boolean on the display mesh); exact section via `BRepAlgoAPI_Section` for curves | S | 3e ("sections" is in the catalog; the live cutaway is the new part) |
| 25 | Global variables / expressions across features and parts | Shapr3D, Fusion, Onshape | Named parameters driving many features | Med | Pure history-side: shared Python constants in scripts; UI for them | M | later (fits "history as code") |
| 26 | Flex / Deform / Flow / Twist (bend, twist, taper a solid; wrap solid onto surface) | SolidWorks Flex, Plasticity Deform, MoI Flow/Twist | Freeform deformation of a BRep | Low (Blender's own deform modifiers already do this on the mesh) | No exact OCCT operator; NURBS-convert + move poles = approximation, fillets degrade | L | never (keep Blender modifiers) |
| 27 | Dome | SolidWorks | Cap a face with a dome | Low | `BRepOffsetAPI_MakeFilling` or revolve/loft | S-M | never / later |
| 28 | Unwrap face (flatten) | Plasticity | Flat pattern of a face | Low | Developable faces only; general = approximation | M | never (sheet metal out of scope) |
| 29 | Extract cutter from an existing boolean | BoxCutter Extract | Turn a cut back into a reusable cutter | Low for us | Already natural: our cutters are parts in the history | — | never (covered by design) |
| 30 | Custom bevel profiles on edges (Blender bevel "custom profile") | Blender Bevel, HardOps | Non-circular edge profile | Low-Med | Not in `BRepFilletAPI` (only circular sections; `ChFi3d_FilletShape` is a parametrization choice, not a conic). Would need sweep of profile along edge + trim: L. Conic is already R&D | L | later (with conic fillets) |
| 31 | Complete edge / extend edge to intersection | Plasticity | Extend an edge until it meets another | Low | 2D sketch extend covers most uses | S | 3a (sketch extend) |

Notes on the table:
- `BRepFilletAPI_MakeFillet` in OCP 8 exposes `SetLaw`/`SetRadius` with ranges (variable fillet, 3b) and
  `SetFilletShape` with `ChFi3d_Rational/QuasiAngular/Polynomial` — these only change the surface
  parametrization; conic or curvature-continuous sections are not available in OCCT out of the box *(own
  assessment, consistent with our R&D row)*.
- `BRepAlgoAPI_Defeaturing` exists (items 11–12); it removes faces and heals by extending neighbours, which is
  also the basis for "delete face with healing" in 3c.

---

## 4. Top 10 recommendations

1. **Extrude taper and "up to next/last/face" (3a).** Nearly free in build123d, standard in every CAD tool,
   and it removes a whole class of "extrude, then draft, then boolean" workarounds. Add to the 3a success
   criterion.
2. **Slice into two parts (3c).** The single most used BoxCutter/Fluent operation after cut; our splitter
   already exists in OCCT (`BRepAlgoAPI_Splitter`). The real work is spawning a second part whose script
   references the first — decide the part-to-part relation early.
3. **Inset panel (3c, planar first).** A hard-surface signature (MoI, Rhino, FORGE, BoxCutter, Fluent all have
   it). Planar faces are an in-plane wire offset plus push/pull — small on top of 3a/3c.
4. **Rule fillet: all edges of a face/feature, convex-only/concave-only (3b).** Hard-surface parts get dozens of
   fillets; picking edges one by one does not scale. It reuses our semantic selectors (a rule is itself a
   selector, which survives upstream changes better than edge lists).
5. **Hole feature with ISO presets (3b).** build123d has Hole/CounterBore/CounterSink; the UX is click a face,
   pick a size. Also patterned holes via 3b arrays. Cosmetic thread (tag + optional texture) now; modeled thread
   later.
6. **Boundary fill / cells (3c).** `BOPAlgo_CellsBuilder` lets users intersect a few simple bodies and click the
   cells to keep — fast to build complex forms, and a natural fit for Blender where users already place several
   objects. Also covers Rhino BooleanSplit and MoI Boolean Merge.
7. **Panel lines / grooves along a curve (3c/3d).** What DECALmachine fakes with decals and Fluent with cuts,
   done exactly and filletable: imprint + small swept profile + cut. Depends on imprint (3c) and sweep (3d).
8. **Emboss/deboss on cylinders and cones, with Text (3a text, 3c emboss).** Shapr3D shipped it in 2026, Fusion
   and SolidWorks have it; labels, grips and logos are common hard-surface details. Exact on developable faces;
   freeform wrap (`Face.wrap`) later.
9. **Rib/web (3b/3c).** Standard for brackets and housings; `BRepFeat_MakeLinearForm` targets exactly this.
   Medium value for pure art, high for printable/functional parts.
10. **Measurements++: interference, mass/volume, center of mass, live section (3e).** Cheap (`GProp`,
    `BRepAlgoAPI_Common`), and on FORGE's roadmap; makes BlendSolid credible for printed/functional parts.

Honourable mentions: grille/vent generator (high visual value, after sketch + array), modify/remove fillets by
radius filter on imported STEP (with 3e STEP import), helix/coil (3d, with sweep), global variables across
parts (later; a natural extension of "history as code").

Not recommended: Flex/Deform/Twist/Flow and Dome (Blender modifiers already do deformation on the mesh; exact
versions are approximations), unwrap/sheet metal, BoxCutter Extract (our cutters are already history).

## 5. What I could not verify

- FORGE's kernel (Replicad/OpenCascade claim traced to an unrelated repository) and any release after V1.0.
- Shapr3D help pages (HTTP 403 to the fetcher): feature details come from search snippets.
- Onshape Rib/Wrap/Thread/Hole and SolidWorks Dome/Freeform details were not re-read from primary pages today.
- MoI V5 Flow "Projective" and Twist: from forum/search snippets.
- Effort estimates and feasibility of general Replace/Move Face are my own assessment.
