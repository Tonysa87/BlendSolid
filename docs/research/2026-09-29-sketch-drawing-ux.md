# Sketch drawing UX: what makes a sketch tool useful for hard-surface modeling

Date: 2026-09-29 (session 11). Input for reworking milestone 3a's Sketch tool after the maintainer's first try.
Builds on `2026-09-29-milestone-3a-sketch-extrude-io.md` (sketch/region/extrude model, ADR 0012) and
`2026-09-26-modeling-workflows.md`; neither is repeated here.

**The maintainer's verdict** (session 11, translated): "the sketch function this way doesn't make much sense:
shapes like boxes and circles we can already make with Draw Solid and then extrude or cut; the line today doesn't
seem to do anything. Look at what others do." And then: "What I imagined was: draw a line, then use that line to
drive a cut or union with a profile, a bit like Blender does with a curve and a bevel profile." Later: look at
BoxCutter and Hard Ops closely.

**Diagnosis of today's tool.** It draws one rectangle, circle or single line per drag. Rectangles and circles
duplicate Draw Solid. A line is useful only as a region boundary, and today regions are built from the sketch's
own curves only, so a line across a face bounds nothing and does nothing. There is no chained drawing (polyline,
arcs), and the only thing a sketch feeds is extrude/revolve of closed regions. Every product surveyed below makes
the **open path** a first-class input: it splits faces, it slices bodies, and above all it carries a **profile**
(sweep, pipe, groove, rib).

Every API claim about build123d 0.13 / OCP 8 below was run on the installed copy in `.dev/worker_libs` with
Blender's Python (probe scripts in the session scratchpad; numbers quoted).

---

## 1. Drawing paths: polyline, arcs in the chain, closing, finishing

| Product | Chained drawing | Arc inside the chain | Close / finish | Typed values, locks |
| --- | --- | --- | --- | --- |
| **Fusion** Line | click, click… | "pause over a point, then click and drag to create an arc segment that is tangent to the previous line segment" | click the start point = closed profile; Enter / check icon ends | length and angle fields while drawing; snap glyphs; constraints added automatically |
| **Onshape** Line | click, click… (or click-drag per segment) | hover the endpoint until the icon turns to a tangent arc, or **Shift+A**; arcs can transition back to lines | click the start point; Esc | type the length right after a segment + Enter; inferencing |
| **SolidWorks** Line | click, click… | *Autotransitioning*: move away from the endpoint and back, or press **A** to toggle line/arc | click the start point; double-click / Esc | on-screen numeric input |
| **Shapr3D** Line/Arc | tap/click chain | pen gesture: "wiggle" switches line/arc (Automatic mode); arcs auto-tangent to a line end | closed loops become profiles | numeric input, automatic constraints |
| **Plasticity** Line | click, click… | separate *Tangent Arc* tool (curve + optional second tangent snap) | **right-click** ends; Ctrl+Z undoes the last click | **Tab** numeric input; X/Y/Z axis locks; **Shift** makes temporary snap reference lines; **K** = Knife mode |
| **Rhino** Polyline | click, click… | option **Mode=Arc** / *A* inside the command, *L* back to lines | **Close** option (*C*); Enter; *Undo* removes the last segment | typed distances/angles, Ortho |
| **MoI** Polyline | click, click… | separate arc tools | Done / right-click | typed distance; *straight snap* (90° by default); press-drag from a snap point = temporary **construction line** |
| **Blender** Knife | click, click… | — | double-click closes; Enter/Space confirms; **E**/RMB new cut | **A** angle constraint (30° steps), X/Y/Z axis, Shift midpoints, Ctrl ignore snap, S measurements |
| **BoxCutter** NGon | click-drag to start, click to add points | — | **double-click** ends then extrudes (triple-click = cut through, "lazorcut"); **C** toggles cyclic (closed) vs open | Ctrl angle snap; **Backspace** removes the last point |

Common ground: click-click chaining; **drag from the last point = tangent arc** (Fusion, Onshape, SolidWorks) or
one key to toggle line/arc (SolidWorks A, Onshape Shift+A, Rhino A); clicking the start point closes; one gesture
to finish an open path (Enter, double-click or right-click); the last point can be undone without leaving the tool.

## 2. Do the face's own edges bound sketch regions? (imprint / split face)

- **Onshape**: yes, by default. "When sketching on the face of a part … Onshape will imprint all of the arcs,
  points, and lines"; the *Disable imprinting* checkbox exists to *stop* the face "being broken into distinct
  regions based upon the new sketch". Also *Split* → *Face* with a sketch as the tool.
- **Shapr3D**: yes. Community answer on a sketch that crosses a body edge: "The cube's line going through the circle
  divides it in 2. You must select both halves." Split Body accepts sketch profiles and faces.
- **Fusion**: sketch-on-face projects the face's edges by default ("Auto project edges on reference"), which creates
  profiles bounded by them (Autodesk's own article is about the *unintended* profiles this causes). Explicit
  *Split Face* with a sketch, then *Press Pull* on the piece.
- **Plasticity**: regions are "an area enclosed by Curves" (curves only), but **Knife mode (K)** in Line/Spline
  "cut[s] one or more Faces as you draw a Curve" (points must snap to the target faces), and *Imprint Curve Body*
  projects curves onto a body as new edges (normal/vector projection, completion to edges). The split face pieces
  are then extruded/push-pulled.
- **SketchUp** (the reference for push/pull): "draw a line with starting and ending points on the face's edges,
  creating smaller faces" and "push or pull one part of the face while the other part stays put".
- **Blender**: Knife (click-click across faces, then Extrude); BoxCutter *Knife* mode cuts drawn edges into the mesh.

**Conclusion:** in every push/pull-style product a line drawn from edge to edge of a face gives two pieces that can
be pushed or pulled. BlendSolid's regions ignore the face, which is exactly why "the line doesn't do anything".
Verified (section 6): adding the face's boundary edges to the region split makes a line across a 40×20 face give
two 400 mm² regions; extruding one cuts a clean step or raises a clean block.

## 3. Curve editing and precision tools that matter

| Tool | Fusion | Onshape | Plasticity | MoI/Rhino | CAD Sketcher | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Trim | hover preview, click → trims to next intersection; no intersection → deletes | yes | **T** | yes | "trim segment to its closest intersections" | the most used edit in all tutorials |
| Extend | to next intersection; fails if none | yes | Extend Curve | yes | — | |
| Offset curve | distance, both/one side | yes | Offset Curve | Offset | offset (linked) | turns a path into a closed band = region |
| Corner fillet / chamfer | Fillet, Chamfer | yes | Fillet Curve | Fillet | **Bevel** (radius follows the cursor, clamped) | hard-surface corners |
| Construction geometry | toggle | **Q** toggle | — | MoI press-drag construction lines | toggle | helpers not used by regions |
| Mirror | Mirror | yes | Mirror | Mirror | — | symmetric parts |
| Typed values | fields while drawing | length after segment | **Tab** | typed distance | 0-9 keys | |
| Snaps / inference | grid, geometry, auto constraints | inferencing (h/v/parallel/perpendicular/tangent, coincident with model edges) | snap to curves/vertices, Shift reference lines, X/Y/Z | object snaps, straight snap, construction lines | constraints | model edges/vertices/midpoints everywhere |

Ranking seen across tutorials and docs: snaps to the model (vertices, midpoints, edges, face centres) and angle
locks first; typed length second; trim and corner fillet next; offset, mirror, construction lines after.

## 4. What sketches feed beyond extrude: sweep / pipe first

### 4.1 Sweeping a profile along a drawn path (the maintainer's request)

| Product | Command | Profile choice | Orientation | Corners / ends | Boolean |
| --- | --- | --- | --- | --- | --- |
| **Fusion** | *Pipe* | presets **Circular / Square / Triangular**, size, *Hollow* (wall) | normal to path | *End Types* tab | Join/Cut/Intersect/New Body; **Cut pre-selected** when the path lies on a body |
| | *Sweep* | any sketch profile; path (+ guide rail) | *Perpendicular* (follows path) / *Parallel* (keeps orientation) | — | same |
| **Onshape** | *Sweep* | sketch region/face | *Profile control*: None / Keep profile orientation / **Lock profile faces** (profile oriented by a face's normal along the path) / Lock direction | — | New/Add/Remove/Intersect |
| **SolidWorks** | *Swept Boss / Swept Cut* | sketch, **Circular Profile** (diameter only, "without having to sketch", since 2016), solid profile (tool body) | *Follow path* / *Keep normal constant* / twist | tangency options | cut or boss |
| **Shapr3D** | *Sweep* | sketch profile | *Normal to path* / *Parallel to profile*, twist, scale (26.0) | — | Boolean badge |
| **Plasticity** | *Sweep* (exact), *Pipe* (quick) | Sweep: region/face/curve; Pipe: **circular (vertex count 0) / polygon / custom**, size, wall, rotation angle | Sweep: *normal* or *parallel* alignment, twist, scale, guides | Sweep corners **mitre / round** | union/difference/intersect/slice, keep tools. Manual: Pipe "is *not* intended for creating dimensionally accurate pipes" — use Sweep |
| **Rhino** | *Sweep1*, *Pipe* | Pipe: round with radius at points, *Thick* | Sweep1 *Freeform* / *Roadlike* (fixed up direction) | Pipe **Cap = None / Flat / Round**; kinks kept unless FitRail | via BooleanDifference |
| **MoI** | *Sweep*, *Pipe* (plug-in) | curves | *Maintain height* option | cap ends | booleans |
| **Blender** curve | *Bevel* on a curve object | **Round** (depth, resolution) / **Object** (another curve as profile) / **Profile** (custom profile widget) | *Twist Method* (Minimum / Tangent / Z-Up), tilt | **Fill Caps**; *Taper Object* varies the radius | Boolean modifier with the curve object (common panel-line technique); Hard Ops *Curve Bevel* sets "the 2nd curve as the bevel object" |

Patterns that recur:
- **Preset profiles with 1–2 numbers** cover most uses (Fusion Pipe, SolidWorks Circular Profile, Plasticity Pipe,
  Blender Round bevel): circle, square/rectangle, triangle/V. A custom sketch profile is the advanced path.
- **Orientation for grooves on a face** = profile kept square to the face along the path (Onshape *Lock profile
  faces*, Rhino *Roadlike*, Blender *Z-Up*, OCCT *binormal mode* with the face normal).
- **Corners**: mitre (sharp) or round (Plasticity Sweep); tangent arcs in the path give smooth grooves.
- **Ends**: flat by default, round optional (Rhino Pipe caps; a ball-end groove).
- **Cut vs join**: chosen by context (Fusion pre-selects Cut when the path is on a body).

### 4.2 Other sketch-driven operations

- **Split / slice a body by a line**: Plasticity *Cut* (a curve cutter gets a surface generated from it, *Extend*
  when too short); Shapr3D *Split Body* by sketch profile/plane; Onshape/Fusion *Split* (face or part);
  BoxCutter *Slice*. Verified: a line extruded into a sheet splits a box into two exact halves (section 6).
- **Cut-through with an arbitrary closed profile** (BoxCutter NGon + lazorcut, Fusion extrude Cut *All*): BlendSolid
  has it once polyline regions exist (extrude of regions with `until=Until.LAST`, ADR 0012).
- **Revolve** (exists), **draw on face then cut in one gesture** (BoxCutter: draw, double-click, drag depth; Shapr3D
  push/pull with Boolean badge) — the Extrude Sketch drag already does this for regions.

## 5. BoxCutter and Hard Ops (Blender)

**BoxCutter** (draw-to-boolean tool; sources: boxDocs):
- **Shapes**: Box, Circle (3 sides up to a circle), **NGon** (click points; Ctrl angle snap; Backspace removes the
  last point; **C** toggles *cyclic*; double-click ends and starts the depth drag; triple-click = *lazorcut* through
  everything), **Custom** (any mesh object set with C becomes the cutter; Alt+scroll cycles stored cutters).
- **Modes** (while drawing): **Cut** (difference, live), **Slice** (keeps both sides as separate pieces), **Inset**,
  **Join** (union), **Knife** (cuts edges only, no volume), **Extract** (turns existing booleans into a custom
  cutter), **Make** (shape only, no boolean). X cycles Slice/Intersect/Inset, J join, K knife, A make.
- **Behaviours during the draw**: **E** extrude / **O** offset (depth direction), **T solidify** (thickness of the
  shape's edges: an open NGon *line* + T = a thin panel-line cut; "Cyclic is intended to be used with T"),
  **B bevel** (drag width, scroll segments; Q contour bevel), **V array** (V V radial), **1/2/3 mirror**,
  G/R/S transform, **Tab** = edit the shape's **dots** (handles) before committing, Ctrl = grid/dots on the face
  for the start point, period = centre draw.
- **Live**: bevel, solidify, array and mirror stay as modifiers on the kept cutter ("on by default … to tweak
  afterwards"); *L* keeps the shape live; Shift+confirm keeps the shape as a boolshape.

**Hard Ops** (management of the boolean stack; sources: hopsDocs):
- **Bool Scroll / Object Scroll**: cycle through the live cutters of a mesh to find and tweak one.
- **Curve tools**: *Curve Extrude* (quick presets of a curve's extrusion/bevel resolution), **Curve Bevel** ("use
  the 2nd curve as the bevel object for the primary selection" = sweep a profile curve along a path curve),
  curve-driven *knife project*; newer add-ons (Hardflow) add "panel lines: select edges and get a recessed groove
  seam or raised weld bead in one click … open strips, closed loops, and T/X junctions".
- **sSharpen / cSharpen** (mark sharps, add bevel, apply booleans), **Step** (bake the current bevel and add a new
  bevel modifier: detailing in decreasing widths), **Mirror** and **Array** gizmo operators, Slash/Inset booleans.

**What maps onto an exact kernel with a history script:**

| BoxCutter / Hard Ops idea | Exact BlendSolid equivalent | Status |
| --- | --- | --- |
| NGon click-points, cyclic → cut/join/cut-through | polyline sketch region, Extrude Sketch drag (join/cut, up to last) | needs the polyline; extrude exists |
| NGon open line + **T** solidify → thin panel cut | **groove**: rectangle profile swept along the open path (exact pipe shell), width = T | new, verified |
| Curve + bevel object / Round bevel (Hard Ops Curve Bevel, Blender curve bevel) | **sweep a preset or sketched profile along the path**, cut or join | new, verified |
| Slice | split the body by the path extruded into a sheet (keep both → two parts, or one side) | new, verified |
| Knife (edges only) | imprint: face edges take part in regions, then push/pull the piece | small change, verified |
| B bevel while drawing | per-corner radius of the polyline (`FilletPolyline`) and/or a fillet on the new feature's edges (ADR 0009 roles) | polyline radius verified |
| Mirror / array while drawing | build123d `mirror` / `Locations` around the feature (M3b-e scope) | later |
| Live cutter kept as an object | ADR 0011 cutters (already); Operation *Cutter* in ADR 0012's plan | exists / planned |
| Tab = edit dots before commit | Adjust Last Operation + parameter arrows (M1.5) | exists |
| Bool Scroll | sidebar feature list + focus (ADR 0011) | exists |

## 6. build123d 0.13 / OCCT: verified support

Curves and 2D edits (probe `bl_probe.py`):
- `Line`, `Polyline`, `TangentArc(p0, p1, tangent=)`, `JernArc(start, tangent, radius, arc_size)`,
  `ThreePointArc`, `FilletPolyline(pts, radius=[per vertex], close=)` all exist (`objects_curve.py`).
  Line + TangentArc + lines as one `Wire` → `Face` area 239.269908 = 200 + π·25/2 (exact).
- `Wire.fillet_2d(r, vertices)` and `Wire.chamfer_2d(d, d2, vertices)` work on **closed and open** wires (open L:
  3 edges, the corner a CIRCLE edge).
- `Wire.offset_2d(d, side=Side.LEFT, closed=False)` offsets an open polyline to one side (2 edges, 26.0 mm);
  `side=BOTH` returns the closed band around it (7 edges) — a "thick line" region in one call.
- `Edge.trim_to_other(other)` trims to the nearest intersection (trim tool); `Edge.trim(start, end)`, `mirror`.

Face imprint / split (probes `bl_probe.py`, `bl_probe2.py`):
- **Regions with the face's edges**: today's `_split` fed with the face's boundary edges + one line across a 40×20
  face → **2 regions of 400.0 mm²** (13 ms); the same line alone → 0 regions (today's behaviour). An L polyline
  from one edge to the next + an overshooting line → 4 regions 50/50/150/550 (sum 800). A filleted open polyline
  ending a bit outside the face → 2 regions 321.5664 + 478.4336 = 800.
- Extruding such regions: corner-notch pocket 4 mm → 7600 mm³ (exact), valid; half face pulled 5 mm → 10000 mm³,
  8 faces after clean, valid.
- `BRepFeat_SplitShape(solid).Add(edge, face)` imprints the line on the solid (7 faces, volume unchanged, valid);
  `BRepAlgoAPI_Splitter` with an edge tool does the same (0.9 ms).
- **Slice**: a sheet made by extruding a line through the box → `box.split(sheet, keep=Keep.BOTH)` = 4000 + 4000
  mm³, both valid, 6 ms.

**Sweep along a path** (probes `bl_sweep*.py`; box 40×20×10, path on its top face: line 20 + tangent semicircle
r = 5 + line 20 + **sharp 90° corner** + line 7, centreline 62.707963 mm; profiles in the plane normal to the path
at its start; rectangle 2 wide × 4 high centred on the face → 2 mm deep groove; V 4 wide at +1, apex −2):

| Profile | Transition | Tool valid | Removed mm³ | Expected (analytic) |
| --- | --- | --- | --- | --- |
| rectangle | **RightCorner** (mitre) | yes | 250.8319 | 4·L = 250.8319 |
| rectangle | **RoundCorner** | yes | 250.4026 | 2·(2L − 1 + π/4) = 250.4026 |
| V | RightCorner | yes | 167.2212 | (8/3)·L = 167.2212 |
| V | RoundCorner | yes | 166.9669 | — (valid, cut valid) |
| rectangle / V | **Transformed** (build123d's default) | **no** | 0 or wrong | — |

- Results are identical with OCCT's default corrected-Frenet trihedron and with **binormal mode**
  (`BRepOffsetAPI_MakePipeShell.SetMode(gp_Dir(face normal))`, the profile kept square to the face) on a planar path;
  binormal mode is the one that states the intent and is safe on long curved paths. 7–11 ms per sweep + cut.
- More cases, all valid and exact: L corner, zigzag, arc→line→sharp, sharp→line→arc (removed = 4·L for mitre);
  closed rounded-rectangle path 285.6637 = 4·L; **closed square with sharp corners** 240.0 = 4·L (mitre) and
  238.2832 (round, 4 corners × (π/4 − 1)·2); a straight groove running off both face edges (through) 160.0;
  a round pipe (r = 1.5) half sunk and **joined** (rib/weld bead): union valid; a 3D path in the XZ plane (line +
  tangent arc + line) with a 4×4 profile: 571.3274 = 16·L, union valid.
- **Pitfalls found:**
  1. `sweep()`'s default `transition=Transition.TRANSFORMED` gives **invalid solids at sharp corners**; pass
     `Transition.RIGHT` (mitre) or `Transition.ROUND`.
  2. build123d's `sweep(normal=...)` sets a **fixed trihedron** (`SetMode(gp_Ax2)`), not a binormal: the profile
     does not turn with the path; it returned a zero-volume invalid solid. BlendSolid must call
     `BRepOffsetAPI_MakePipeShell.SetMode(gp_Dir)` itself (or rely on corrected Frenet for planar paths).
  3. The profile must sit **on the path's start point in the plane normal to the path**: a profile placed 5 mm off
     the path (a mistake in the first probe) gave `NotDone` with mitre and invalid solids otherwise.
  4. A path whose groove overlaps itself (a line back across a semicircle's diameter) gives an invalid cut: this
     is a user error to report on the line, not to repair.
  5. Grooves must overshoot the face (profile extending above it, as in the probes) to avoid coplanar boolean faces.

## 7. Why a profile-along-a-path tool is the right primary use

- It is the one thing Draw Solid cannot do (Draw Solid = boxes, cylinders, and later polygons dragged into depth).
- It is what the maintainer asked for, and what the Blender hard-surface ecosystem is built around (panel lines,
  grooves, welds, pipes, rails: BoxCutter line + T, Hard Ops Curve Bevel, Hardflow panel lines, curve bevel +
  Boolean), but here exact and parametric.
- The kernel does it exactly and fast (section 6), with the pitfalls known.
- The same path drawing also feeds split-face regions, slicing and closed-profile extrude, so one drawing tool
  serves four operations.

---

## Recommendation

**Reframe the Sketch tool as "draw a path, then use it".** The primary use is a **profile swept along a drawn
path, cutting (groove) or joining (rib/bead/pipe)**; the same path, closed or crossing a face, also makes regions
for push/pull and cut-through. Rectangle/circle entities stay (they are useful as region shapes and in scripts)
but stop being the point of the tool.

### Ranked first-iteration feature set (value / effort)

1. **Polyline path drawing** — click-click chaining; **drag from the last point = tangent arc** (Fusion/Onshape);
   **A** toggles line/arc for the next segment (SolidWorks/Rhino); click on the first point closes; **Enter,
   double-click or right-click** finishes an open path; **Backspace** removes the last point; one undo step per
   finished path. *Very high / medium* — everything else needs it.
2. **Groove / Rib: sweep a preset profile along the path** — profiles **Rectangle** (width, depth), **Round**
   (U: radius; circle: diameter for pipes/beads), **V** (width, depth or angle); anchored on the face (profile top
   overshooting above it for cuts, centred on the path laterally), kept square to the face (binormal = face
   normal); corners **Mitre / Round**; ends **Flat** (Round later); cut or join chosen by the drag direction like
   Draw Solid (into the face = groove, out = rib) with Operation in Adjust Last Operation; open or closed paths;
   paths may run off the face (through grooves). *Very high / medium* — exact with `MakePipeShell` + RightCorner/
   RoundCorner, verified on sharp and tangent paths.
3. **Face edges take part in regions** (Onshape imprint, SketchUp split) for sketches `on_face`: a line from edge
   to edge splits the face; Extrude Sketch drags either piece (step, raised block, notch). *High / low* — the face's
   edges added to `_split`, verified.
4. **Snaps and precision** — path points snap to the part's vertices, edge midpoints, edges and face centre
   (projected on the sketch plane), to the path's own points, grid with Ctrl (exists), **15° angle lock** and
   horizontal/vertical to the sketch axes; **typed length** (and angle) for the current segment with Tab or digits
   (Plasticity/Fusion/Onshape). *High / medium.*
5. **Corner radius per polyline vertex** — a parameter per corner (`FilletPolyline(pts, radius=[…])`), set in Adjust
   Last Operation or by an arrow on the corner; covers "sketch fillet" for paths and closed profiles. *Medium /
   low.*
6. **Slice by path** — the path extruded normal to the sketch plane into a sheet splits the part (keep both as two
   parts, or one side), BoxCutter Slice / Plasticity Cut / Shapr3D Split Body. *Medium / low.*
7. **Offset to a band** — `offset_2d(side=BOTH)` turns an open path into a closed region of given width (a "thick
   line" to extrude or cut through, BoxCutter NGon line + T with a flat bottom). *Medium / low* (mostly covered by
   the rectangle groove).

After the usage checkpoint: trim/extend, mirror, construction lines (MoI press-drag), custom profile from another
sketch's region, round end caps, paths on several faces (3c projection/wrap), 3D paths in space, hollow pipes.

### Proposed interaction design

- **Sketch tool, Path mode (default)**: hover shows the face plane (as today); click starts the path on that plane
  (or the 3D cursor's plane); clicks add points; press-drag from the last point bends the next segment into a
  tangent arc; A toggles arc/line; snaps as in item 4 with a marker; Tab/digits type the segment length; click
  the first point to close; Enter/double-click/right-click to finish; Backspace undoes the last point; Esc
  cancels the whole path. The finished path is one entity in the sketch (written as a `Wire` of `Line` /
  `TangentArc` or a `FilletPolyline`, points as literals with 6 decimals, ADR 0006/0012 rules).
- **Groove/Rib tool** (next to Extrude Sketch): click a path, then drag off the face: into it = groove (cut), out of
  it = rib (join); the drag sets depth/height, the header shows width/depth; Adjust Last Operation: Profile
  (Rectangle / Round / V / Circle), Width, Depth, Corners (Mitre / Round), Ends (Flat), Operation (Auto / Join /
  Cut / New Part / Cutter). One script line, e.g.
  ```python
  sweep_profile(sketch_1.path_1, profile=Groove.RECT, width=groove_1_width, depth=groove_1_depth,
                corners=Corner.MITRE, mode=Mode.SUBTRACT)  # feature: groove_1
  ```
  (names to be fixed in an ADR); roles for references: `floor`, `wall_left`/`wall_right` by path entity, `end`.
- **Extrude Sketch** keeps working on regions, which now include face pieces cut by paths (item 3) and closed
  paths.
- The grid/snap marker, overlay and undo rules of today's tool carry over; the rectangle/circle entities move to
  the tool's secondary options.

### Risks

- Sweep robustness beyond the probes: self-overlapping paths, profiles wider than a corner's radius (inner side
  folds), very short segments; the worker must report them on the feature line (BRepCheck of the tool before the
  boolean), never return a partial solid.
- Face roles of swept features (walls by path entity, floor, ends) need an ADR 0009 addendum like extrude's.
- Imprinted regions depend on the face's edges: an upstream change can change the region set around a seed; the
  ADR 0009 warning rule applies (criterion 3 of the 3a research must include such cases).
- The modal path tool is the largest interaction so far (chaining, arcs, snaps, typed input): budget like Draw Solid.

## Sources

- Fusion Line (tangent arc by drag, closing, snaps): https://help.autodesk.com/cloudhelp/ENU/Fusion-Sketch/files/SKT-CREATE-LINES.htm ;
  tangent arc tip: https://www.autodesk.com/products/fusion-360/blog/quick-tip-sketching-tangent-arcs/ ;
  Trim/Extend: https://help.autodesk.com/cloudhelp/ENU/Fusion-Sketch/files/SKT-TRIM-EXTEND.htm ;
  sketch Modify tools: https://help.autodesk.com/cloudhelp/ENU/Fusion-Sketch/files/SKT-SKETCH-MODIFY-TOOLS.htm ;
  unintended profiles from face edges: https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Creating-a-sketch-on-a-face-in-Fusion-360-causes-unintended-profiles-to-be-extruded.html ;
  Pipe: https://help.autodesk.com/view/fusion360/ENU/?contextId=MODEL-PIPE-CMD , https://www.autodesk.com/products/fusion-360/blog/tech-tip-pipe-command/ ;
  Sweep orientation: https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-REF-SWEEP ;
  Split Face: https://www.techandespresso.com/blog/fusion-360-split-face-guide
- Onshape Line: https://cad.onshape.com/help/Content/Sketch/line.htm ; auto-transition line/tangent arc:
  https://www.onshape.com/en/resource-center/what-is-new/face-blend-auto-transition-line-tangent-arc-thin-extrude ;
  imprinting: https://www.onshape.com/en/resource-center/tech-tips/disable-imprinting-option-sketching ,
  https://cad.onshape.com/help/Content/Sketch/sketch_basics.htm ; Split: https://cad.onshape.com/help/Content/splitpart.htm ;
  Sweep profile control: https://cad.onshape.com/help/Content/PartStudio/sweep.htm
- SolidWorks autotransitioning: https://help.solidworks.com/2022/english/solidworks/sldworks/t_Autotransitioning.htm ,
  https://www.cati.com/blog/autotransition/ ; Circular Profile sweep:
  https://help.solidworks.com/2024/English/SolidWorks/sldworks/t_create_circular_profile_sweep.htm ;
  orientation (Follow path / Keep normal constant): https://hawkridgesys.com/blog/advanced-sweep-feature-techniques
- Shapr3D Automatic Line/Arc: https://support.shapr3d.com/hc/en-us/articles/7770681244316-Automatic-Line-Arc ;
  Arc: https://support.shapr3d.com/hc/en-us/articles/7874294891804-Arc ; body edges divide sketch regions:
  https://discourse.shapr3d.com/t/sketch-on-body-extends-past-edge/11809 ; Split Body:
  https://support.shapr3d.com/hc/en-us/articles/7874462683036-Split-Body ; Sweep:
  https://support.shapr3d.com/hc/en-us/articles/7874456833948-Sweep ,
  https://discourse.shapr3d.com/t/26-0-scale-orientation-and-twist-controls-for-sweep/40168
- Plasticity: Line https://doc.plasticity.xyz/tool/line ; Sketching Essentials (Tab, Shift reference lines, Knife
  mode) https://doc.plasticity.xyz/tool/sketching-essentials ; Tangent Arc https://doc.plasticity.xyz/tool/tangent-arc ;
  tools list https://doc.plasticity.xyz/all-commands/tool-commands ; Regions https://doc.plasticity.xyz/plasticity-essentials/object-types ;
  Imprint Curve Body https://doc.plasticity.xyz/solid/imprint-curve-body ; Cut https://doc.plasticity.xyz/solid/cut ;
  Extrude https://doc.plasticity.xyz/solid/extrude ; Sweep https://doc.plasticity.xyz/solid/sweep ;
  Pipe https://doc.plasticity.xyz/solid/pipe
- Rhino Polyline: https://docs.mcneel.com/rhino/mac/help/en-us/commands/polyline.htm ; Pipe:
  https://docs.mcneel.com/rhino/8/help/en-us/commands/pipe.htm ; Sweep1: https://docs.mcneel.com/rhino/mac/help/en-us/commands/sweep1.htm
- MoI: https://moi3d.com/3.0/docs/moi_introduction.htm (construction lines, straight snap), help PDF https://moi3d.com/3.0/docs/moi_help.pdf
- SketchUp split face + push/pull: https://help.sketchup.com/en/sketchup/dividing-splitting-and-exploding-lines-and-faces
- Blender Knife: https://docs.blender.org/manual/en/3.1/modeling/meshes/tools/knife.html ; curve Geometry/Bevel:
  https://docs.blender.org/manual/en/latest/modeling/curves/properties/geometry.html ; custom profile bevel for
  curves: https://projects.blender.org/blender/blender/commit/60fa80de0b2c
- CAD Sketcher tools (trim, bevel, offset): https://hlorus.github.io/CAD_Sketcher/tools/
- BoxCutter: shapes https://boxcutter-manual.readthedocs.io/en/latest/shapes/ , NGon https://boxcutter-manual.readthedocs.io/en/latest/shape_ngon/ ,
  Custom https://boxcutter-manual.readthedocs.io/en/latest/shape_custom/ , modes https://boxcutter-manual.readthedocs.io/en/latest/modes/ ,
  hotkeys https://boxcutter-manual.readthedocs.io/en/latest/hotkeys/ , FAQ https://boxcutter-manual.readthedocs.io/en/latest/faq/
- Hard Ops: operations https://hardops-manual.readthedocs.io/en/latest/operations/ , menu (Curve Bevel/Extrude)
  https://hardops-manual.readthedocs.io/en/latest/menu_system/ , Step https://hardops-manual.readthedocs.io/en/latest/step/ ;
  Hardflow panel lines: https://extensions.blender.org/add-ons/hardflow/
- Installed code read: `.dev/worker_libs/build123d/objects_curve.py` (Polyline, TangentArc, JernArc, FilletPolyline),
  `operations_generic.py` (sweep, split, offset, mirror), `topology/one_d.py` (fillet_2d, chamfer_2d, offset_2d,
  trim_to_other), `topology/three_d.py` (Solid.sweep, `_set_sweep_mode`), `topology/shape_core.py` (split).
