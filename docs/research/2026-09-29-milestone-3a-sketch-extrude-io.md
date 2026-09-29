# Milestone 3a research: 2D sketch, extrude/revolve, STEP/IGES/BREP I/O

Date: 2026-09-29 (session 11). Input for planning milestone 3a (spec, Milestones: "2D sketch on a face or plane +
extrude (with taper angle and up-to-face/next/last) / revolve, and STEP/IGES/BREP import/export").
Builds on `2026-09-26-modeling-workflows.md` (sections 2.1–2.8: Plasticity, Shapr3D, Fusion, Onshape, MoI, Rhino,
CAD Sketcher, Zoo) and `2026-09-28-modeling-feature-survey.md` (row 1: taper/up-to; row 8: text), which are not
repeated here. Two questions added by the maintainer during the research are answered in sections 5 and 6.

Every API claim about build123d 0.13 / OCP 8 below was checked on the installed copy in `.dev/worker_libs`
(grep, then a probe run with Blender's Python). Probe scripts are throwaway (session scratchpad), numbers quoted.

---

## 1. How products handle sketches

| Product | Where a sketch lives | Entities | Constraints | Profiles |
| --- | --- | --- | --- | --- |
| **Fusion** | One plane or planar face per sketch; the view aligns to it | full set + text, project/include | Full, dimensions | Closed areas are auto-detected **profiles**, picked by clicking inside |
| **Onshape** | One plane/face per sketch | full set | Full | Every bounded area is a **region** ("3 regions for two overlapping circles"); FeatureScript picks one with `qContainsPoint(qSketchRegion(id), point)` |
| **SolidWorks** | One plane/face; the sketch origin shown in red is the part origin projected | full set | Full | Whole sketch must be non-intersecting, or regions picked with Contour Select |
| **Shapr3D** | Pick a plane or face (Space over a face while hovering; the grid follows the hovered plane) | line/arc/circle/rect/spline… | Optional (green = fully defined, blue = under-defined) | Closed sketches are profiles, extruded with the push/pull gizmo |
| **Plasticity** | Curves on the construction plane; Space on a face makes a CPlane there | line, arc, circle, rect, polygon, spline, spiral, text | **None** (snaps, axis locks, Tab for typed values) | "An area enclosed by Curves is called a Region", auto, selecting it implies Extrude |
| **MoI** | Curves on the construction plane / on faces | lines, arcs, curves by control points | None (snaps, construction lines, typed distances) | Extrude takes closed curves; "closed curves may contain other closed curves inside them to form holes" |
| **FreeCAD Sketcher** | Sketch *attached* to a face/plane (Map Mode) | full set | Full (planegcs) | Closed non-intersecting wires, nested = holes. Its own docs recommend attaching sketches to origin/datum planes, not faces, because of TNP; 1.0 detects broken references and auto-fixes only "with high confidence" |
| **CAD Sketcher** (Blender, 0.32) | Workplane on an origin plane or a mesh face (anchor survives reload since 0.32) | point, line, arc, circle, rectangle… as WorkSpaceTools | Full (SolveSpace) | Extrude/Revolve modifiers on the converted mesh; new solids auto-boolean into overlapping bodies (switchable in 0.32) |
| **Blender native** | 3D cursor plane / surface under the mouse (Add Cube tool) | curves (Bézier), mesh | none | none (mesh Fill) |

Common ground: **one plane per sketch** everywhere; regions detected automatically in every modern tool (Fusion,
Onshape, Plasticity, Shapr3D); the region is identified by a point inside it (Onshape's query is literally that).
Constraints are the dividing line: history CAD has them, direct-modeling tools (Plasticity, MoI) replace them
with snaps + typed input and still produce exact geometry.

**Fit with BlendSolid.** The script is already the parametric layer: a rectangle written as
`Rectangle(sketch_1_rect_1_width, ...)` gets named parameters, the sidebar fields and arrows (M1/M1.5) for free.
Constraints would add a solver, a second source of truth next to the script, and a UI Blender has no native
component for. A Plasticity/MoI-style direct sketch (exact snaps, axis locks, typed values) fits "100% native
Blender UI + history as script"; constraints stay v2 (spec), where the open spec decision "integrate CAD
Sketcher or write our own" can be taken (SolveSpace is GPL-3, compatible; CAD Sketcher's solved entities could be
imported as exact build123d curves).

## 2. How products handle extrude/revolve

| | Fusion | Onshape | SolidWorks | Shapr3D | Plasticity |
| --- | --- | --- | --- | --- | --- |
| Handle | Arrow manipulator + field | Manipulator arrow | Instant3D drag handle + ruler | Push/pull gizmo | Yellow dot, Tab to type |
| Extents | Distance, **To Object** (body/face/plane), All | Blind, **Up to next**, **Up to face** ("the infinite face underlying the selected face"), Up to part, Up to vertex, Through all; offset on the up-to types | Blind, Up To Next, Up To Surface (extends an analytic face if the profile overhangs), Offset From Surface, Through All | Distance, To Object, Through All | Distance or freestyle points; no up-to |
| Two sides | One side / Two sides / Symmetric | Symmetric or second end position | Direction 2 | Sides | S symmetric |
| Taper | Taper angle | Draft, sketch plane = neutral plane | Draft | Draft | A: angle |
| Booleans | Join / Cut / Intersect / New Body / New Component | New / Add / Remove / Intersect, auto merge scope when one part is touched | Merge result | **Automatic** (new/union/subtract from geometry), badge to override | Q/W/Shift+E/B + **Keep Tools** |
| Failure | — | "If it doesn't completely terminate, then the Extrude fails" | — | — | — |

Revolve is the same everywhere: profile + axis (a sketch line, an edge or an origin axis) + angle, one or two
sides; same boolean choices.

Takeaways for BlendSolid: the boolean by drag direction (already Draw Solid's rule, ADR 0006) + a redo-panel
override is the Shapr3D/CAD Sketcher pattern; "up to face" means the **extended** surface of the face (Onshape,
SolidWorks); an up-to that does not terminate is an **error**, never a partial solid.

## 3. build123d 0.13 / OCCT: what exists and what it really does (verified)

### 3.1 Sketch on a face

- `BuildSketch(plane)` draws in local XY and places the result (`sketch_local` vs `sketch`); `mode=Mode.PRIVATE`
  keeps it out of the part's pending faces. `Plane(face)` needs a single `Face` (`face()` returns a ShapeList:
  `Plane(face(...)[0])`; the list itself raises "Expected three VectorLike points").
- **`Plane(face)`'s origin is the face's centre**: a 40→60 mm box moved the top face's plane origin from x=20 to
  x=30. A sketch written in those coordinates drifts when an upstream change resizes the face. Fusion, Onshape
  and SolidWorks use the part origin projected onto the face (SolidWorks' red sketch origin), which is Draw
  Solid's convention too (ADR 0006). Its x axis comes from the surface parametrisation (side faces got x = +Z).
  → A helper is needed: the face's exact plane, origin = part origin projected, x axis by ADR 0006's rule.
- Probe (`runner.run_script` on a canonical script): sketch on `face("box_1", "+Z")`, extrude, then a second
  sketch on `face("extrude_1", "+Z")` and `extrude(..., until=Until.LAST, mode=Mode.SUBTRACT)`: builds, valid,
  the provenance hook labels everything. Extruded side faces get today's roles: a 4-segment polyline gave `+X`,
  `-Y` and two `slope` faces with `near=`; with a 3° taper **all four became `slope` + `near=`**. Onshape names
  cap faces (`qCapEntity` START/END) and side faces by the sketch entity that swept them; BlendSolid needs the
  same (`start`/`end`, and side faces by entity name) for references on extrudes to be stable.

### 3.2 Regions from overlapping curves

build123d has no region helper (`make_face()` only closes one wire; `BuildSketch` fuses overlapping faces and
loses their inner edges). OCCT's General Fuse does it: `BRepAlgoAPI_Splitter` of a large planar face by all the
sketch edges, keeping the faces that don't touch the big face's border. Probe: rectangle 20×10 + a circle r=4
overlapping its edge + a line across → 4 regions, areas 25.133 / 25.133 / 75.0 / 99.867 (sum = 200 + half
circle outside, exact), **1.4 ms**. (OCP 8: the list type is `OCP.collections.List_TopoDS_Shape`, not
`TopTools_ListOfShape`.)

### 3.3 Extrude, taper, up-to

`extrude(to_extrude, amount, dir, until, target, both, taper, clean, mode)`; `Until.NEXT/LAST/PREVIOUS/FIRST`.

- **Taper is inconsistent** (`Solid.extrude_taper`): OCCT's `LocOpe_DPrism` only when the direction is the face
  normal, taper > 0 and no holes; otherwise a **loft** to a 2D-offset wire. Measured (20×10 rect, 10 mm, 5°):

  | Profile | taper +5 (DPrism) | taper −5 / holes / negative direction (loft) |
  | --- | --- | --- |
  | rectangle | 6 PLANE | 4 **BSPLINE** sides |
  | rectangle with hole | — (loft) | 4 BSPLINE + cone |
  | L shape | 8 PLANE + **1 CONE** (DPrism rounds the reflex corner) | 6 BSPLINE |

  B-spline "planes" have no exact plane (no `face_planes`, no sketch on them, Draw Solid treats them as curved).
  **Straight extrude + `Solid.draft(sides, sketch plane, angle)`** (`BRepOffsetAPI_DraftAngle`) gave PLANE/CONE
  faces in every case, sharp corners, volumes exact (rect +5°: 1747.7397 mm³ = ∫(20−2kz)(10−2kz)dz), valid.
  Draft only accepts PLANE/CYLINDER/CONE faces: splines can't be tapered this way (loft fallback or refuse).
- **Up to next / last** (`Solid.extrude_until`: long prism, `BRepAlgoAPI_Common` with the target, sew the hit
  faces, split the prism by the nearest/farthest): exact (slanted roof: 1149.6542 mm³ = analytic). Target
  defaults to the part so far.
- **Up to a face** via `target=<face>`: exact when the face covers the profile and faces the extrusion; a face
  whose normal points the other way kept the part **beyond** the face (4519 mm³, z 30.7→122); a face that
  covers the profile only partly returned a **valid but wrong** solid (1340 mm³). build123d's docstring says
  "partial overlaps may yield open or invalid solids". → Up-to-face must split by the face's untrimmed surface
  (Onshape/SolidWorks semantics) with an orientation test, and fail when the profile's prism misses it.
- `both=True` + `until` raises "Extrusion is None"; `taper` + `until` **silently ignores the taper**.
- `revolve(profiles, axis, revolution_arc)` exact (rect 4×10 at r=15: 3769.9112 mm³ = 2π·15·40).

### 3.4 Projection and wrap (for section 5)

0.13 has `project(objects, workplane, target)` (onto a plane), `Face.project_to_shape(target, direction)` (a
face projected onto a solid: returns faces on every surface hit), `Face.wrap(planar_shape, surface_loc)` /
`wrap_faces` (conform a 2D shape to one non-planar face; approximated, tolerance 1e-3), and generic `split`.
A newer build123d PR (#1465, not in 0.13) writes shapes into a face's (u, v) space exactly for planes, cylinders
and cones.

### 3.5 STEP / IGES / BREP

- `import_step(path)` (STEPCAFControl + XDE): assembly tree as `Compound.children`, `label` (names) and `color`
  (instance → referred → largest-face fallback), locations applied. Path only (OCP has
  `STEPCAFControl_Reader.ReadStream` for bytes). `export_step(shape, path, unit=MM, ...)` writes labels/colors
  via XDE; round trip kept label "ring", colour red, volume exact; an assembly kept child names and colours.
- **Pitfall:** `export_step(unit=)` is the unit *of the model*, not of the file: `unit=Unit.IN` on a 10 mm box
  wrote a 254 mm box tagged millimetres. BlendSolid scripts are mm: never pass it. On read OCCT converts file
  units to `xstep.cascade.unit` (mm by default).
- `import_brep` / `export_brep` (text, also to a BytesIO); `persistence.serialize_shape` (BinTools, binary).
- **No IGES in build123d**: OCP's `IGESControl_Writer("MM", 1)` (mode 1 = MSBO solids) + `IGESControl_Reader`
  round-tripped a revolved ring as 1 solid, exact volume; `IGESCAFControl_Reader` (names/colours) exists in OCP.
  With the default face mode IGES gives loose faces that need sewing.
- **Corpus measurement** (the maintainer's 18 STEP files, `/mnt/e/bs_debug/step_corpus`, 10 KB–4.2 MB):
  import 0.01–1.18 s; 1–150 solids per file, 1–54 leaves; names on every leaf, colours on some.
  BRep text is 0.2–1.2× the STEP size; **zlib-compressed binary BRep is 0.2–30% of the STEP** (max 303 KB for the
  4.2 MB board). **3 of 18 files contain BRepCheck-invalid solids** (1, 3 and 2 solids), and `ShapeFix_Shape`
  did not repair any: today's runner would refuse them ("`result` is not a valid solid").

## 4. Sketches in the history script, and surviving upstream changes

Options for writing a sketch:
1. `with BuildSketch(plane, mode=Mode.PRIVATE) as sketch_1:` + objects — idiomatic, verified with the hook, but
   BuildSketch fuses overlapping objects: overlap regions (Plasticity/Fusion behaviour) are lost.
2. Curves only (`BuildLine`) + `make_face()` — one closed wire per face, no overlaps either.
3. **A sketch value built from named build123d objects + a `regions()` query** (proposed):

```python
    sketch_1 = sketch(on_face(face("box_1", "+Z")),  # feature: sketch_1
        rect_1=Pos(sketch_1_rect_1_x, sketch_1_rect_1_y) * Rectangle(sketch_1_rect_1_width, sketch_1_rect_1_height),
        circle_1=Pos(30.0, 8.0) * Circle(sketch_1_circle_1_radius),
        line_1=Line((0.0, 0.0), (40.0, 16.0)),
    )
    extrude(regions(sketch_1, (12.0, 8.0)), amount=extrude_1_amount, taper=extrude_1_taper)  # feature: extrude_1
    revolve(regions(sketch_2, (15.0, 5.0)), axis=sketch_2.axis("line_1"), revolution_arc=revolve_1_angle)  # feature: revolve_1
```

   - The entities are plain build123d objects in sketch-local mm (faces contribute their edges), keyword-named so
     tools and references can name them; parameters follow the existing `<feature>_<param>` block.
   - `on_face(face(...))`: the face's exact plane, origin = the part origin projected, x axis by ADR 0006;
     follows the face when upstream changes move it (associative, like Fusion), which also answers NEXT.md item 3
     for sketches. On the 3D-cursor plane / origin planes a literal `Plane(origin=, x_dir=, z_dir=)` is written
     (10 decimals for the component that must lie on a face, ADR 0006).
   - `regions(sketch, *points)`: the arrangement faces containing the seed points (Onshape's `qContainsPoint`);
     no point = every outer region with its holes (FreeCAD/whole-sketch behaviour). A seed in no region is a
     `BrokenReference` error; a seed within tolerance of a region boundary, or regions that changed count around
     it, a warning (ADR 0009 policy: never silent re-binding). Tools that edit an entity's parameter move the
     seeds they own with it.
   - Up-to extents and taper go through BlendSolid's own `extrude` (namespace override, like `fillet`/`chamfer`
     in `provenance.namespace`) so the script reads as build123d but gets draft-based taper, extended-surface
     up-to-face and clear errors for unsupported combinations: `extrude(r, until=Until.NEXT)`,
     `extrude(r, until=face("box_1", "-Z"))`, `extrude(r, amount=..., both=True)`.
   - Provenance roles for extrude/revolve (ADR 0009 addendum needed): `start`, `end`, and side faces named by the
     entity that swept them (`face("extrude_1", "rect_1")`, several faces → `near=`), found by matching each side
     face to its generating sketch edge. These survive a taper and a parameter change; the frame roles don't.
- The hook runs after `sketch_1 = ...` like after any feature (it adds no faces); `face()` on a sketch name is an
  error with a clear message.

## 5. Drawing across adjacent faces (maintainer question 1)

- **Every product keeps one plane per sketch.** Shapr3D and Plasticity let the *hover* choose the plane before
  drawing (Shapr3D: the grid follows the hovered plane, Space starts the sketch; Plasticity: Space on a face makes
  a CPlane); Fusion/Onshape/SolidWorks pick the face explicitly. None moves the plane mid-curve.
- **Curves across an edge onto several faces** are a separate family of commands working on existing curves:
  Fusion *Project to Surface* (and Emboss for wrap), SolidWorks *Wrap* / *Projected Curve* / *Split Line*,
  Shapr3D *Wrap & Emboss*, Plasticity *Imprint Curve Body* (Normal or Vector projection, bidirectional, "Hide
  occlusion", completion to edges). In build123d: `Face.project_to_shape`, `Face.wrap`/`wrap_faces`, `split`;
  in OCCT `BRepFeat_SplitShape` / `BRepAlgoAPI_Splitter` for the imprint.
- **Fit:** 3a = one sketch per planar face or plane. Before the first click the plane follows the face under the
  cursor (Draw Solid's hover, ADR 0006); the first click fixes it; points outside the face stay on the same
  infinite plane (Plasticity 2026.1's "Construction Plane 2D Snapping" projects picked points onto the plane).
  A click on another face while no entity is in progress starts a new sketch there. Projecting/wrapping a sketch
  onto several faces is imprint/"cut by sketch"/emboss: **3c** (already scheduled there), cylinders/cones exact
  first.

## 6. Extruded sketch as a cutter (maintainer question 2)

- Products: Fusion *Cut* vs *New Body* then *Combine* with *Keep Tools*; Onshape *Remove* vs *New* then a Boolean;
  Plasticity's extrude booleans include **Keep Tools**; CAD Sketcher 0.32 auto-booleans overlapping solids with an
  option to keep them separate; HardOps/BoxCutter keep a live cutter object (ADR 0011).
- BlendSolid has both mechanisms already: a `mode=Mode.SUBTRACT` feature in the part's own script (Draw Solid,
  Push/Pull) and live cutters = separate parts used through `insert(ref(id))`, hidden in *BlendSolid Cutters*
  (ADR 0007, 0011).
- **Fit:** the extrude's *Operation* in Adjust Last Operation: **Auto** (default: by drag direction and contact,
  as Draw Solid) / Join / Cut / Intersect / **New Part** / **Cutter**.
  - Cut (in-part) is the default: one script, the sketch stays associative to the face (`on_face(face(...))`),
    references to the pocket's faces are provenance references.
  - Cutter = the sketch + extrude become a **new part's** script (its plane written as a literal placement in
    its own frame; a part can't `face()` into another part's history) and the target gets
    `insert(ref(id), mode=Mode.SUBTRACT)`, cutter hidden and parented as ADR 0011. For tools reused on several
    parts or moved with G/R. Trade-off stated in the tooltip: it no longer follows the face it was drawn on.
  - New Part = the same without the boolean. Converting a Cut into a Cutter later ("extract to cutter") and
    the reverse ("Apply", already a NEXT follow-up) are follow-ups, not 3a.

## 7. Import/export in a history-as-script model

- **Path reference** (`import_step("C:/…")`): tiny and readable, but breaks when the file moves, differs per
  machine/OS, and re-reads the file on every rebuild. **Embedded blob**: self-contained `.blend`, sizes measured
  above (≤ ~0.4 MB base64 for the largest corpus file).
- Proposed: each imported solid is a part whose script is
  `insert(imported("<blob id>"))  # feature: import_1` (+ features added later), the blob a compressed binary BRep
  (BinTools, zlib, base64) in its own Text datablock (`bs_blob_id`, fake user while used, like cutter scripts),
  sent to the worker with the request like `ref()` deps and part of the mesh tag by hash. The source path and
  the STEP name are kept as metadata for a *Reload from file* button. A blob is data read by BinTools, not code,
  so it adds nothing to the trust model (ADR 0004); the part script around it stays under ADR 0004.
- Invalid solids (3/18 corpus files): import them anyway, show them, and report "imported solid is not valid
  (BRepCheck): booleans and fillets on it may fail" as a part warning; features on them fail on their own line.
- Assemblies: one part per leaf solid, the tree mirrored as Blender collections or parenting, names from STEP
  labels, colours to the viewport colour/material; repeated instances of one product → linked duplicates sharing
  one script (Alt+D identity, M1.5). Units: OCCT converts to mm; the mesh is scaled per ADR 0003.
- Face references on an import: roles computed as for primitives (`face("import_1", "+Z", near=...)`); stable
  because the blob never changes except on explicit reload.
- Export (File > Export, `ExportHelper`): selected parts, placed by their `matrix_world` in mm (scene scale
  applied), names from objects, colours from materials; STEP (XDE, AP214), IGES (`IGESControl_Writer("MM", 1)`),
  BREP; written by the worker. Import/export run in the worker process (the 4 MB file: 1.2 s import).

---

## Recommendation for 3a

**Scope.** Sketch on a planar face, an origin plane or the 3D-cursor plane; auto regions; extrude (distance,
symmetric, two sides, taper, up to next / last / face, through all) and revolve (angle, full, symmetric), with
Operation Auto/Join/Cut/Intersect/New Part/Cutter; STEP/IGES/BREP import and export. Out of 3a: constraints,
projection/wrap/imprint across faces (3c), splines, ellipse, offset, text, curve fillet (after the usage
checkpoint).

**Entity set.** Line/polyline (chained clicks), arc (3-point and tangent continuation), circle (centre-radius),
rectangle (2-corner, centre), regular polygon, slot; plus delete of an entity. Exact snaps: grid (ADR 0006 step
ladder), endpoints, midpoints, centres, intersections, the part's edges/vertices projected on the plane,
horizontal/vertical/axis locks; typed values with Tab (as Plasticity/CAD Sketcher).

**Constraint approach.** None in 3a (Plasticity/MoI model): each entity's dimensions are named script parameters,
editable from the sidebar and arrows like primitives. Constraints stay v2 (SolveSpace or CAD Sketcher interop).

**Data model.** Section 4, option 3: `sketch_1 = sketch(on_face(face(...)) | Plane(...), name=<build123d object>,
...)`; profiles `regions(sketch_1, (u, v), ...)` by seed points; BlendSolid's `extrude`/`revolve` overrides for
draft-based taper and extended-surface up-to-face; new roles `start`/`end`/side-by-entity (ADR 0009 addendum);
one ADR for the sketch grammar, one for import blobs.

**UX flow.** *Sketch* WorkSpaceTool (entity tools as its variants): hover shows the plane of the face under the
cursor; first click fixes it and writes the sketch feature; entities drawn with snaps, one undo step each;
regions tinted on a wire+face mesh object parented to the part (pickable through a region attribute, as
`brep_face_id`); Enter/Esc leaves the sketch. Select a region → **E** (or the arrow) → drag: out of the part =
join, into it = cut, no contact = new part (Draw Solid's rule); during the drag, a key snaps the extent to the
face under the cursor (up to face); Adjust Last Operation: Operation, Extent, Distance, Symmetric/Two sides,
Taper. Revolve: region + axis (a sketch line, a part edge, or a sketch axis) + angle dial. The sketch hides after
use (Fusion), stays editable from the sidebar's feature list (focus, ADR 0011).

**I/O approach.** Section 7: embedded compressed BRep blobs (no file paths), one part per leaf solid, invalid
solids imported with a warning, names/colours/instances kept; export of selected parts to STEP/IGES/BREP from the
worker; Blender's File > Import/Export menus.

**Acceptance criteria (proposals).**
1. Geometry: a corpus of ≥ 30 scripted sketch/extrude/revolve cases (each entity, overlaps, holes, taper ±,
   every extent, both booleans) on the M2 test parts: all BRepCheck-valid, volumes = analytic within 1e-6
   relative, tapered line/arc profiles give only PLANE/CONE/CYLINDER faces (no BSPLINE).
2. Regions: ≥ 10 overlap configurations give the analytic region count and areas (1e-9 relative).
3. Associativity (M2-style criterion): sketches on faces, their region seeds and the references to extrude faces
   survive 3 upstream changes each for ≥ 95% of cases, with **0 silent wrong bindings** (seed or side face).
4. Up-to: next/last/face exact on ≥ 5 targets (plane, slanted plane, cylinder, stepped part); a profile that the
   face doesn't fully stop gives an error, never a partial solid.
5. Usage: the maintainer models 2–3 objects of their choice (e.g. a tapered-boss bracket, a revolved knob with a
   pocket up to next) with the sketch tools only; each action is one undo step and one script edit.
6. I/O: every test part round-trips STEP, IGES and BREP (same volume within 1e-6 relative, same face count, names
   kept); the 18-file corpus imports with names, ≤ 2 s per file, blobs ≤ 0.5× the STEP size, invalid solids
   reported as warnings (not errors).

**Risks.**
- The sketch tool is the largest modal tool so far (snaps, typed input, arcs): budget it like M1.5's Draw Solid;
  float32 must stay out of written numbers (ADR 0006: compute in float64 in plane coordinates).
- Region seeds can land in the wrong region after big parameter changes: the warning rule and criterion 3 measure
  it; fallback plan: identify regions by their bounding entity names.
- build123d taper/up-to behaviours above (loft B-splines, taper ignored with `until`, partial-cover up-to-face)
  force BlendSolid overrides: they must be tested against build123d upgrades.
- Draft fails on some profiles (thin walls, large angles; `DraftAngleError`) — report on the line.
- Invalid imported solids (17% of the corpus files) will fail booleans/fillets; a "heal" command may be needed
  after the usage checkpoint.
- Large imports: many parts at once stress reconcile/tessellation (the 150-solid board); import in the worker
  and measure.
- Sketches on faces are what FreeCAD's docs warn against (TNP): the provenance references + `on_face` projection
  of the part origin are the mitigation; criterion 3 must include face splits.

## Sources

- Fusion Extrude help: https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-EXTRUDE-SOLID
- Fusion Project to Surface / wrap: https://www.autodesk.com/support/technical/article/caas/tsarticles/ts/7iLoGrz03bjnTRY9BUbgsj.html
- Onshape Extrude help: https://cad.onshape.com/help/Content/PartStudio/extrude.htm
- Onshape sketch regions (qSketchRegion, qContainsPoint): https://forum.onshape.com/discussion/11934/ and https://cad.onshape.com/FsDoc/library.html
- SolidWorks end conditions: https://help.solidworks.com/2023/english/SolidWorks/sldworks/c_end_condition_extrude.htm ,
  Up To Surface extension: https://hawkridgesys.com/blog/solidworks-up-to-surface-end-condition ,
  sketch origin: https://forum.solidworks.com/thread/183000
- Shapr3D sketching/planes: https://support.shapr3d.com/hc/en-us/articles/18816009328284-Sketching-in-Shapr3D ,
  https://support.shapr3d.com/hc/en-us/articles/12469688911516-Create-sketches ,
  Wrap & Emboss: https://support.shapr3d.com/hc/en-us/articles/25620612815260-Wrap-Emboss
- Plasticity Extrude: https://doc.plasticity.xyz/solid/extrude ; Imprint Curve Body: https://doc.plasticity.xyz/solid/imprint-curve-body
- FreeCAD TNP: https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Topological_naming_problem.md ;
  MapSketch: https://wiki.freecadweb.org/Sketcher_MapSketch
- CAD Sketcher 0.32.0 release: https://github.com/hlorus/CAD_Sketcher/releases/tag/v0.32.0 ; docs: https://hlorus.github.io/CAD_Sketcher/
- build123d BuildSketch: https://build123d.readthedocs.io/en/latest/build_sketch.html ; wrap PR: https://github.com/gumyr/build123d/pull/1465
- OCCT STEP translator (units, names/colours): https://dev.opencascade.org/doc/occt-7.2.0/overview/html/occt_user_guides__step.html ,
  https://dev.opencascade.org/doc/refman/html/class_s_t_e_p_c_a_f_control___reader.html
- Installed code read: `.dev/worker_libs/build123d/operations_part.py` (extrude, draft, revolve),
  `topology/three_d.py` (extrude_taper, extrude_until, draft), `topology/two_d.py` (project_to_shape, wrap),
  `importers.py`, `exporters3d.py`, `persistence.py`, `build_enums.py` (Until).
