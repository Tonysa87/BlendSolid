# How users build solids: modeling workflows in reference tools, and a creation workflow for BlendSolid

- **Date:** 2026-09-26
- **Question (maintainer):** how should users actually *build* geometry in BlendSolid: parametric primitives,
  sketch-and-extrude, direct drawing on faces, push/pull? Base the answer on how the reference programs work.
- **Scope addition (maintainer, same day):** find the existing Blender add-on(s) that make the Shift+A primitives
  parametric after creation, and decide what BlendSolid should copy from them (section 4).
- **Method:** web research on official manuals, help centers, release notes, product pages, source repositories
  and dated reviews. Every source is listed in section 9 with its date (publication or last update when the page
  shows one; otherwise "accessed 2026-09-26"). Where a claim comes from a search-engine snippet rather than a page
  I could read, or from my own knowledge, it is marked as such.
- **Constraints taken from the spec:** every viewport action writes or edits lines of the part's build123d
  script; native Blender UI only (operators, Adjust Last Operation, `WorkSpaceTool`, gizmos, snapping); Python
  cannot add entries to the mode menu; OCCT runs in a separate worker process; the script is hidden from standard
  users (ADR 0002); scripts are in millimetres (ADR 0003).

---

## 0. Summary of the recommendation

1. **Start with parametric primitives, not with sketches.** Shift+A → BlendSolid → Box/Cylinder/…, with the
   Adjust Last Operation panel and then persistent parameters and arrow gizmos. This is what Blender users expect;
   Modern Primitive (78k downloads, it also runs on 5.2) shows the UX conventions to copy. It needs no selectors.
2. **Add an interactive "draw a solid on a face or on the grid" tool.** It follows Blender's own Add Cube tool and
   the BoxCutter/QBlocker pattern: drag a base, then a height. The direction of the drag picks the boolean
   (outward = union, inward = cut), the rule Shapr3D, MoI and CAD Sketcher use. The placement is written into the
   script as a fixed `Location`, so it needs no selectors either.
3. **Add booleans between parts with live cutters.** Moving a cutter with the native G gizmo is already a CAD
   operation. No selectors needed.
4. **Fillet/chamfer on clicked edges is the first tool that needs milestone 2.** Use it as the driving case for
   M2, which is defined on edges anyway.
5. **Push/pull a face in two stages.** (a) If the face is the cap of a feature, edit that feature's parameter
   (SolidWorks Instant3D / Fusion "Automatic" offset). This needs *face → feature provenance* from the worker,
   not selectors. (b) Otherwise add a new extrude/offset feature, which needs **face** selectors.
6. **Sketch-on-face + extrude comes after that**, Plasticity/Shapr3D style: simple profiles drawn on a face or on
   the 3D-cursor plane, closed profiles detected as regions automatically, E to extrude with an arrow gizmo, and
   the boolean inferred from direction. Constrained sketches stay v2, probably through CAD Sketcher interop.
7. **Recommended change to the plan:** insert a short "M1.5: build tools without selectors" (items 1–3), and
   extend M2's criterion from edges to **edges and faces**, plus face → feature provenance.

---

## 1. What "FORGE" is

Several products share the name. The one the spec means is clearly the first.

| Product | What it is | Fits the spec? |
| --- | --- | --- |
| **FORGE: CAD Precision Modelling in Blender** (RenderCraft Studio, author listed as Ogunsola Omololu) | Commercial Blender add-on: "Professional NURBS & BRep CAD modeling inside Blender". V1.0 released at the end of June 2026 | **Yes** |
| ForgeCAD (github.com/ForgeCAD, forks) | Code-first parametric CAD in JavaScript/TypeScript, used in the browser/CLI, BSL 1.1 license | No, but it is a code-first reference (section 2.7) |
| Autodesk Forge | Autodesk's cloud API platform, renamed Autodesk Platform Services in 2022 (my own knowledge) | No |
| Asset Forge (Kenney) | Block-based asset kit-bashing tool (alternativeto listing) | No |

**FORGE facts (Gumroad page for V1.0, Superhive listing, YouTube channel "Rendercraft Studio"):**

- Teaser video "True CAD in Blender? (FORGE Add-on Teaser)", **2026-06-08**: "pushing the live sketch, extrude,
  and internal fillet features to the limit". Launch video "Real-Time CAD Modeling in Blender is HERE",
  **2026-06-20**: "From a 2D sketch to a flawless all-quad mesh in seconds… V1.0 officially releases NEXT WEEK".
- Superhive (accessed 2026-09-26): published "3 months ago", 200+ sales, Blender **4.2–5.0**, license GPL,
  $49 / $149 / $299 tiers. A third-party mirror lists "last updated July 15, 2026" (low reliability).
- **Interaction model:** "FORGE MODE. Forge doesn't just sit on top of Blender; it is a fully dedicated
  workspace. Just like Edit Mode, enter Forge Mode to access a unified CAD environment". Python cannot add a real
  mode, so this is very likely a workspace plus a modal state, but that is unverified.
- **Tool list:** Line ("exact numeric input"), Spline, Cylinder, Sphere ("full parametric control over radius and
  depth"), Boolean ("non-destructive cuts, unions, and intersections with a real-time ghost preview"), Fillet and
  Chamfer, Split, Trim, Loft, Sweep, Revolve, Pipe, Mirror ("auto-fusing"), Auto-Retopology to an all-quad mesh,
  plus "Extrude, Offset, Inset, Imprint, Shell, Thicken, Array, **Auto-Regions**, Quad-Remesh, Project". The set
  of tools, and "Auto-Regions" in particular, is Plasticity's vocabulary. A community post (Skool, 1 July)
  describes it as "plasticity type of modelling directly in Blender".
- **History:** V1.0 has none. The roadmap's "Phase 1: Parametric Foundation" promises "a dedicated history tree
  logging every operation, live dimension editing, and mathematically locked sketch constraints". Phase 2 is
  "N-sided patching, SubD-to-CAD bridging… G2/G3". Phase 3 is assemblies and 2D drawings.
- **Kernel:** not disclosed. No public documentation beyond the sales page could be retrieved: the Superhive
  docs tab renders client-side and the product website returned 503.

**Takeaway:** FORGE is today's closest competitor, and it is Plasticity-inside-Blender (curves → regions →
extrude, direct modeling, no history yet). BlendSolid's differentiators stay intact: an open-source, readable
code history that Claude can edit via MCP, native gizmos, and SubD→NURBS. FORGE's roadmap ("history tree",
"SubD-to-CAD") targets the same space, so the history story has to show up in the UX early, not only in the
architecture.

---

## 2. How the reference tools let users create and edit solids

### 2.1 Plasticity (Nick Kallen / Plastic Software), current version 2026.1 (2026-04-16)

Kernel: Parasolid (Wikipedia). It is pitched as "CAD for artists".

**Creation, click by click:**
1. **Pick a construction plane.** Numpad 7/1/3 give the XY/XZ/YZ planes. To draw on a face, select the face and
   press **Space**: "Create CPlane and align view". Shift+Space creates the plane without moving the view,
   Ctrl+Space aligns it to the view, and Ctrl+Shift+Space puts it through a point. 2026.1 added "Construction
   Plane 2D Snapping", which projects all picked points onto the active plane.
2. **Draw curves** (Line, Spline, Circle, Rectangle, Polygon, Spiral…). For a line, click the start, click the
   next points and **right-click to confirm**. **Tab** "enables direct input of dimensions", and X/Y/Z constrain
   a segment to an axis.
3. **Regions appear on their own.** "An area enclosed by Curves is called a Region." Regions render dark blue.
4. **Extrude.** "Selecting a Region automatically activates the Extrude command". Plasticity does *selection
   first, command implied*. You can also press **E** on faces, regions or curves. You "move the yellow dot to
   specify the distance", and Tab types the value (gizmo distance input, 2026.1). D is distance mode, F is
   freestyle (start/end points), A is taper angle, S is symmetric, and I toggles direct/individual normals.
5. **Booleans while extruding:** Q union, W difference, Shift+Q slice, Shift+E intersect, B new body. The
   standalone Boolean command uses the same keys, plus T for "Keep Tools" and G/R/S to move the tool *during*
   the boolean.
6. **Push/pull:** "When a Face is selected, the default command, Push Face, is automatically executed". You drag
   the yellow dot or type a distance, and Tab cycles grow modes (Moving / Fixed / None).
7. **Fillet:** "When one or more Edges are selected, the default command, Fillet, is automatically executed". You
   drag the dot; a negative distance gives a chamfer. V adds variable-radius points and L adds limit points.
8. **Everything else is a command search on F**, keyboard driven. Navigation presets imitate Blender, Maya,
   Rhino and others (Digital Production, 2023-10-04).

**History philosophy:** "no parametric editing, no design history, no editable sketches with dimensions". Kallen
treats parametrics as a low priority because of the artist focus (Digital Production, 2023-10-04). The 2025.1
(2025-02-25) and 2026.1 release notes add no history or associative features. They add direct-modeling features
(Slide, instances, PolySplines, hidden-line SVG). A search snippet claims "Constraints" are "essentially Alias's
History", but I could not verify it on any Plasticity page, so treat it as **unverified**.

**How it differs from history-based CAD:** there is no feature tree to maintain. Every command acts on the
current geometry, and the selection decides the command (region → extrude, face → push, edge → fillet). The price
is that you cannot change a dimension from earlier and have it propagate. The Blender Bridge exists because
people finish their models in Blender.

### 2.2 Shapr3D: direct modeling first, history since 2024

- **Touch/pencil first:** on the iPad you select a face and push or pull it with the Apple Pencil while the other
  hand steers the view (shapr3d.com iPad page, Digital Engineering review). The "adaptive UI" offers tools based on
  the selection.
- **Sketching:** "Select a sketch plane or face to draw on", then use Line/Circle/Spline, "apply constraints and
  dimensions" (Sketching in Shapr3D, created 2025-03-04, updated 2026-09-21). Closed sketches are profiles.
  Colors show the state: green means fully defined, blue means under-defined. Hovering over a construction plane
  updates the grid, and clicking a plane or face rotates the view to it (Create sketches tutorial, 2024-02-02).
- **Extrude = push/pull:** select a face or sketch profile, "use the gizmo to extrude", optionally pick a boolean
  from the **Boolean badge**, then Done. **Automatic booleans** (Extrude article, 2023-02-24, updated 2026-08-26):
  - *New Body* when the new geometry touches no body.
  - *Union* when a face of a body is extruded, or a profile connected to a body is pulled away from it.
  - *Subtract* when a profile or face is pushed into the body.
  - *Intersect* is never automatic.
- **History:** History-Based Parametric Modeling went out of beta in 5.590 (2024-04-08). The History panel lists
  the steps; selecting a step shows its parameters (Profile, Sides, Extent: Distance / To Object / Through All,
  Draft, Start) and a gizmo. Sketches drive bodies: "your sketches are now connected to your bodies". Direct
  edits (move/offset face) remain "a core experience" and are *recorded as steps* ("combine direct geometry edits
  with adjusting design history leveraging the same adaptive user interface", shapr3d.com).
- **Lesson for BlendSolid:** Shapr3D proves a direct-modeling UX can sit on top of a recorded history without
  forcing users to think in features. That is the stance ADR 0002 already takes (history hidden by default).

### 2.3 Autodesk Fusion

- **Classic flow:** Create Sketch → pick a plane or planar face (the view aligns to it) → draw → constraints and
  dimensions → Finish Sketch → **Extrude (E)**: select the profiles, drag the arrow manipulator or type the
  distance, and pick Operation = Join / Cut / Intersect / New Body / New Component. Direction can be One Side,
  Two Sides or Symmetric (Extrude help). In my experience the operation defaults to Join or Cut from the drag
  direction when the profile lies on a body, but the help page lists it as a user choice.
- **Parametric primitives:** Box, Cylinder, Sphere, Torus, Coil, Pipe. For Box you pick a plane, draw the base,
  then "drag the Length, Width, and Height manipulator handles… or specify exact values", then choose an Operation.
- **Press Pull (Q):** one command that switches on the selection. Profile → Extrude, **edge → Fillet, face →
  Offset Face**. From a support-article snippet I could not open directly: with Offset Type set to *Automatic* or
  *Edit Feature*, pushing a face **edits the existing feature** that made it and adds no timeline entry; with *New
  Offset* it adds a feature.
- **Timeline:** in parametric mode every feature is captured in the bottom timeline, where you can roll back,
  reorder, suppress or edit. "Do not capture Design History" switches to Direct Modeling mode. A **Base Feature**
  is "a Direct Modeling session within the parametric design".

### 2.4 Onshape

- The Part Studio's feature list: sketch → Extrude (Shift+E) with **New / Add / Remove / Intersect** and a merge
  scope. "If the geometry touches or intersects with only one part then that part is automatically added to the
  merge scope." Depth comes from the manipulator arrow or a typed value.
- **The feature list *is* code:** "A feature in the feature tree is a function call… A Part Studio defines a
  build function, containing a function call for every feature". Right-click the tab → "Show code"
  (FeatureScript intro). References are **queries by creation history**: `qCreatedBy(id + "startingCube",
  EntityType.EDGE)`, cap/non-cap entity queries and so on. That is Onshape's answer to topological naming, and it
  is the closest analogue to what BlendSolid's selectors have to do.
- **Lesson:** "GUI writes code" works at industrial scale (Onshape). References there are expressed relative to
  the *feature that created* an entity, not by geometry alone. build123d's `Select.LAST` / `Select.NEW` (entities
  created by the last operation; present in the vendored build123d 0.13.0 `build_enums.py`) are the build123d
  equivalent of `qCreatedBy`.

### 2.5 MoI3D and Rhino: curve first, partial history

**MoI (Moment of Inspiration)** (v4 command reference; page footer © 2014, so it describes long-standing
behavior):
- Draw curves (Line: "specifying the 2 end points… Distance constraint or Angle constraint"; freeform curves by
  control points). Then **Extrude** "works on selected curves or faces. Closed curves may contain other closed
  curves inside them to form holes". Options include Set dir, Set path, Tapered and to-point.
- **Push/pull via auto-boolean:** "If you select a face sub-object of a solid as the input for extrude, the result
  of the extrusion will get automatically booleaned with the base object… outward direction makes a Boolean
  Union…, inwards does a Boolean Difference." A solid can also be cut **directly by 2D curves** (Boolean
  difference with curves, no extrude needed).
- **Limited history:** "Some commands have history updates enabled by default. For example, the Loft command will
  update the lofted surface if you edit one of the original curves"; a boolean afterwards "will break the history
  chain" (forum answer).

**Rhino 8:**
- **Record History:** the output updates when its inputs change, and over 100 commands support it. The link "is
  easily broken": deleting parents, editing children directly, joining, and so on.
- **Gumball:** the "Extrude handle (a dot on the Z arrow)… Drag… to extrude", "Click on the Extrude handle to type
  the extruding distance", Ctrl-drag makes a closed extrude, and Alt toggles copy. In Rhino 8 **PushPull** can
  "grab a face and push or pull it, extruding or extending", together with Auto CPlanes.
- **Grasshopper** is Rhino's full parametric layer: a separate node graph (my own knowledge, not re-verified here).
- **Lesson:** the curve-first workflow plus a gumball extrude dot is the precedent for "native transform gizmo as
  a CAD operation". Rhino's history breaks when the model is edited directly. That is the failure mode BlendSolid
  avoids by writing *every* edit into the script.

### 2.6 Inside Blender

**Native expectations** (Blender 5.2 LTS manual):
- **Add primitive, then Adjust Last Operation.** "You can tweak the parameters of an operator after running it… a
  'head-up display' panel in the bottom left… Alternatively… F9". The parameters are lost after the next
  operation, which is exactly the gap the add-ons in section 4 fill.
- **The interactive Add Cube / Add Cylinder… tools in the toolbar:** "first defining the base through dragging
  with LMB, then releasing LMB and moving the mouse to define the height, and finally clicking LMB". Options cover
  base from corner or center, fixed or free aspect, height from base or center, "start placing on the surface
  under the mouse cursor, or if no surface exists, use a cursor plane", and global snapping.
- **Extrude (E) in Edit Mode:** faces follow the normal and are confirmed with LMB/Enter. X/Y/Z lock the axis,
  numbers can be typed, and options appear in Adjust Last Operation afterwards.
- Blender users expect **G/R/S + axis + number**, snapping from the header magnet, **Ctrl+B** for bevel,
  **Ctrl+Numpad −/+/*** for booleans (Bool Tool, my own knowledge), pie menus and F3 search.

**CAD Sketcher** (hlorus, GPL-3.0; **v0.32.0 released 2026-09-25**; docs in its repository):
- Add Sketch picks an origin plane or a face, then you draw with WorkSpaceTools (P point, L line, C circle, A arc,
  R rectangle…). The tools are *stateful* and accept "Select → Invoke" and "Invoke → Select" as well as mixed
  order. **Numeric input** starts with digits, Tab moves to the next sub-value, and units such as "5cm" are
  accepted. Snapping reuses Blender's own snap settings. "Live Project Snaps" keep a reference to the snapped
  source.
- Constraints are solved with SolveSpace (keys: Shift+C coincident, Shift+H horizontal, Alt+D distance…).
- **New in 2026:** modeling tools that act on objects. **Extrude (Ctrl+Shift+E), Revolve, Array and Boolean**
  (Ctrl+Shift+B) are added as **Geometry Nodes modifiers** on the sketch's mesh "body". **"A new Extrude or
  Revolve that overlaps existing bodies is booleaned into them right away, so a pocket drawn on a face cuts what it
  sits on without a second step"**, with the operation chosen in the redo panel. There are Parts and Assemblies
  built from object parenting. The result is a **tessellated mesh** ("a meshed circle is a polygon"), not BRep.
- **Relevance:** CAD Sketcher is both a model for Blender-native CAD interaction (it already solved many of
  BlendSolid's UX questions within Blender's limits) and a possible input source. Its solved sketch entities
  (lines, arcs, circles) could become exact build123d profiles. That bears on the spec's open decision
  "integrate CAD Sketcher or write our own sketcher".

**Hard Ops / BoxCutter** (BoxCutter 26 "Stiletto", Superhive; boxDocs):
- Activate the tool and **click-drag a shape on the surface**, then move the mouse to set the depth. Modes are
  **Cut, Slice, Inset, Join, Knife, Extract, Make**. Shapes are box, circle, ngon and custom. The result is a live
  mesh Boolean modifier with a cutter object, and "Tab to live" gives editable dots ("shapes be kept live until
  you decide to apply them").
- Hard Ops is the companion menu (Q menu, bevel/sharpen helpers, boolean shortcuts). Its public manual has almost
  no content, so these details come from my own knowledge.
- **Relevance:** "draw on the face, drag the depth, the mode picks the boolean, the cutter stays live" is the
  hard-surface Blender user's muscle memory. BlendSolid can reproduce it exactly, with exact BRep results.

**Existing OCCT/code-CAD bridges in Blender:**
- **BlendQuery** (uki-dev; last push 2024-07-13): runs a CadQuery/build123d script from Object Properties and
  imports every top-level shape. Code only, with no viewport authoring. It is the closest prior art to BlendSolid's
  M1 and does *less*: no worker process, no parameters UI, no picking.
- **STEPper NEXT** (Peak-Design, GPL-3.0, pushed 2026-09-18), **step2blend** and **blender2step**: OCCT-based
  STEP/IGES import and export only.
- **Bonsai (formerly BlenderBIM)** (IfcOpenShell, OCCT among its geometry backends): "IFC data becomes the source of
  truth… There is no such thing as an import or export". Blender meshes are regenerated from IFC and authoring
  uses WorkSpaceTools. It is architecturally the closest analogue to BlendSolid (an external source of truth, with
  Blender as view and editor).
- **KittyCAD text-to-cad Blender add-on** (MIT): generates CAD from text prompts through Zoo's API.
- **Serpentine3D** (MIT, 2026): a stand-alone Rhino-style OCCT NURBS modeler with MCP integration. Not Blender,
  but shows the same "OCCT + MCP" idea.

### 2.7 Code-first tools

- **build123d** (Apache-2.0; the vendored copy is 0.13.0): builder mode (`with BuildPart():`, `with
  BuildSketch(face):`, `Mode.ADD/SUBTRACT/INTERSECT`) and algebra mode. It selects geometry with chained,
  **geometric** selectors: `part.faces().sort_by(Axis.Z)[-1]`, `.filter_by(GeomType.CIRCLE)`, `.group_by(...)`.
  `Select.LAST/NEW` give entities by creation. A sketch placed on a face uses that face's plane
  (`BuildSketch(example.faces().sort_by(Axis.Z)[-1])`). `extrude(..., until=Until.NEXT/LAST, target=...)` covers
  "up to next face".
- **CadQuery:** the same kernel, with a fluent `Workplane` API and string selectors (`">Z"`, `"|Z"`). CQ-editor
  gives code, then a viewer. There is no GUI authoring (my own knowledge).
- **OpenSCAD:** CSG only (no fillet on arbitrary edges). Its **Customizer** turns annotated top-level variables into
  GUI widgets. That is the same idea as BlendSolid's M1 parameter block, which confirms the convention (my own
  knowledge; OpenSCAD manual).
- **Zoo Design Studio (KittyCAD)** (v1 on 2025-05-21; new sketch mode and ezpz solver on 2026-05-28): models
  are stored as **KCL code**. "The point-and-click interface generates human-readable code". Clicking a feature
  highlights its code lines. Since November 2025 you can "pick any face on any solid and extrude the sketch to
  meet that face" from the GUI (What's New, November). The sketch mode is rough-then-constrain, with colors going
  from blue (under-constrained) to white (fully constrained). Zookeeper AI edits the same code.
- **ForgeCAD** (JS/TS, BSL): code-first, with "named shapes, face/edge references, fillet/chamfer helpers" and
  built for coding agents.
- **Lesson:** Zoo is the direct precedent for "every click writes a code line, and code and GUI stay in sync".
  BlendSolid does this with build123d and Blender instead of KCL and a custom app. Zoo, like Onshape, uses
  explicit **tags** on sketch segments to name faces (my own knowledge of KCL's `tag: $name` syntax, not
  re-verified here). That argues for BlendSolid emitting *named features* as well.

### 2.8 Other tools with a distinct interaction idea

- **SketchUp Push/Pull** (help.sketchup.com): hover over a face and drag, or type a distance in the Measurements
  box while the tool is active. "Double-click another face" repeats the last distance, and Ctrl/Option +
  double-click stacks another one. Inference tells you when two faces become parallel. **Idea:** repeat the last
  push/pull distance with a double-click, and use inference against other faces.
- **SOLIDWORKS Instant3D** (help 2021–2024, via search snippets): select a sketch contour or a face and **a drag
  handle and a ruler appear**. Dragging a face "modifies" the feature that created it: "You can also drag the
  dimension handles to resize features". **Idea:** push/pull on a cap face *edits the existing parameter* instead
  of adding a feature (the same as Fusion's "Edit Feature" offset type). This is the key idea for BlendSolid's
  push/pull (section 6, tool 5).
- **Bonsai**: see 2.6. The idea is a regenerated Blender view of an external source of truth, with WorkSpaceTools
  for authoring.

---

## 3. Comparison table

| Tool | Entry point | Editing model | Constraints | Booleans triggered by | Precise input | Gizmo use |
| --- | --- | --- | --- | --- | --- | --- |
| **FORGE** (V1.0, 2026) | Curves, then auto-regions, then extrude; Cylinder/Sphere primitives | Direct (history tree on the roadmap) | None yet (roadmap) | Boolean tool with ghost preview; "live booleans" | "Exact numeric input" on Line | Not documented |
| **Plasticity** 2026.1 | Curves on a construction plane or face (Space) | Direct, no history | None (only snaps and axis locks) | Keys during Extrude (Q/W/Shift+Q/Shift+E/B), or the Boolean command | Tab for typed values in commands and gizmos | Yellow dot handles; selection implies the command |
| **Shapr3D** | Sketch on a plane or face, or a face of a body | Both: direct edits recorded as history steps | Yes (green/blue state) | **Automatic** from geometry (new body / union / subtract); Boolean badge to override | Dimension labels, typed values | Push/pull gizmo, dimension labels |
| **Fusion** | Sketch → Extrude; Box/Cylinder primitives; Press Pull | Timeline (parametric), Direct mode, or Base Feature | Full sketch constraints | Operation dropdown (Join/Cut/Intersect/New Body) | Dialog fields plus manipulators | Arrow and length manipulators |
| **Onshape** | Sketch → Extrude | Feature list = FeatureScript code; direct-edit features (move/replace face) | Full | Result type (New/Add/Remove/Intersect) plus auto merge scope | Dialog fields | Manipulator arrows |
| **MoI** | Curves | Direct; history only on some commands (loft, extrude from curves) | None (snaps, construction lines) | Face-extrude auto-union/difference by direction; explicit Boolean command, which also accepts curves | Typed distances and angles | Minimal |
| **Rhino 8** | Curves; Gumball extrude; PushPull | Direct, plus Record History (fragile), plus Grasshopper | None in core (Grasshopper for logic) | Explicit Boolean commands; PushPull | Command line, click the handle to type | **Gumball extrude dot** |
| **Blender native** | Shift+A primitive; the Add Cube/Cylinder tool (base drag, then height) | Destructive mesh plus modifier stack | None | Boolean modifier / Bool Tool | Adjust Last Operation, typed values during modal ops | Transform gizmo, tool gizmos |
| **CAD Sketcher** 0.32 | Sketch on a plane or face (WorkSpaceTools) | Sketch plus GN modifier stack (tessellated) | Full (SolveSpace) | **Automatic** when an extrude overlaps; redo panel | Digits + Tab, units ("5cm"), redo panel | Tool previews |
| **BoxCutter / Hard Ops** | Drag a shape on a face, then depth | Live mesh Boolean modifiers ("Tab to live") | None | **Mode chosen before drawing** (Cut/Join/Slice…) | Modal keys, grid snapping | Live dots |
| **Zoo Design Studio** | Sketch (rough, then constrain) → Extrude | Code (KCL) = history; GUI writes code | Yes (ezpz solver) | Feature options | Code and dialogs | Standard CAD |
| **build123d / CadQuery** | Code: primitives or sketches | Code | Via code only | `mode=` argument | Code | None |
| **SketchUp** | Draw a face, then Push/Pull | Direct (mesh-like) | Inference only | Implicit (push into = hole) | Measurements box, double-click to repeat | Tool cursor |
| **SOLIDWORKS Instant3D** | Sketch contour or face drag | Feature tree; the drag **edits the owning feature** | Full | Feature options | Ruler snapping, typed values | Drag handle plus ruler |

---

## 4. Parametric primitive add-ons for Blender ("don't reinvent the wheel")

The add-on the maintainer remembers is most likely **Modern Primitive**. It is the only one of these that
supports Blender 5.2, is on extensions.blender.org, covers most of the Shift+A mesh primitives, and is widely
used. ND Primitives and Better Primitives are the close competitors.

| Add-on | Author, license, price | Blender | Technique | Where the parameters live after creation | Notes |
| --- | --- | --- | --- | --- | --- |
| **Modern Primitive** (extensions.blender.org, GitHub degarashi/ModernPrimitive) | Degarashi, GPL-3.0+, free; 78,685 downloads; published 2024-12-18, v0.0.57 on 2026-07-28, repo pushed 2026-09-17 | **4.3+, including 5.2** | Each primitive is a **Geometry Nodes modifier** loaded from bundled `.blend` node groups. The **gizmos are GN gizmo nodes** (`GeometryNodeGizmoDial` and others, confirmed by inspecting `assets/cube.blend`). A Python depsgraph handler reads "Gizmo Position/Type/Normal/Color" attributes from the evaluated mesh to draw a **HUD** of values | Modifier panel; N-panel tab **[MPR]**; viewport gizmos; **Modal Edit (Ctrl+Shift+C)** with key letters (S size, H height, W smooth), typed numbers and the mouse wheel; **Focus Modifier (Ctrl+Alt+X)** | 13 primitives (Cube, Deformable Cube, UV/Ico/Quad Sphere, Cylinder, Cone, Capsule, Tube, Torus, Gear, Spring, Grid). Shift+A → Mesh → Modern Primitive. "Convert to Primitive" (an existing mesh becomes a parametric primitive, keeping the object, booleans, materials and modifiers). "Extract to Primitive" from Edit Mode faces. "Apply Mesh". "Apply Scale" to keep gizmos in sync with a non-uniform scale. The primitive is placed at the 3D cursor and takes its rotation. Warns when the user tries to edit the mesh |
| **ND Primitives** ("Non-Destructive Primitives", extensions.blender.org, BlenderArtists) | Dan-Gry (Dangry), GPL-3.0+, free; 33,394 downloads; v0.2.4 announced 2024-12-17, last update about 2025-01 | **4.2 LTS; listed "Unsupported 5.2 and above"** | GN modifier plus gizmos. "Simply enter Edit Mode and begin modeling! No need to apply any Modifiers": the modifier is disabled to model on the base mesh and re-enabled to tweak | Modifier panel, gizmos, pie menu (Shift+A) | 13 primitives. Users reported handles blocking the translate gizmo and scale-apply quirks |
| **Better Primitives** (Superhive) | CGMatter, GPL, $10; V2.7 (2025-01-07) | 4.3–4.4 | GN modifier with **GN gizmos** (the feature introduced in 4.3) | Gizmos plus modifier properties | 12 primitives, including Plane, Circle, Line, Gear, Helix |
| **QBlocker** (Gumroad/Superhive; docs 0.2.x) | Balazs Szeleczki (my own knowledge), paid 0.22 / free 0.17 | 3.6–5.0 | Custom modal creation tool; parameters kept on the object | Post-creation parameter editing (size, radius, segments) | **3ds Max-style interactive placement**: draw the base, then the height, on the grid or **on object surfaces**, with a working plane and custom snapping |
| **RePrimitive** (GitHub eXzacT/RePrimitive, Gumroad, Blender Market) | eXzacT, MIT (repo); last push 2024-05-12 | Older | **Infers the parameters back from the mesh** (radius and segment counts from vertex positions, detects applied rotation), then **re-invokes a primitive operator with `REGISTER\|UNDO\|PRESET`**, so the Adjust Last Operation panel is prefilled. It rebuilds the object and copies modifiers and children | Adjust Last Operation panel (Ctrl+Alt+A) | Works even on plain Blender primitives created earlier |
| **Paramix** (Superhive) | 3Z Axis, GPL, $2 | 3.0–4.5 | Keeps the operator parameters and regenerates the mesh | Custom panel in Properties → Object | Only Torus, Sphere, Cylinder, Cone, Circle |
| gen_ParametricPrimitives, Wonder Mesh, Live Meshes, Blender Super Primitives | Various | Old or unmaintained (for example gen_ParametricPrimitives, last push 2021) | Custom properties plus regeneration | N-panel | Historical; not relevant for 5.2 |

Blender itself still has no persistent primitive parameters in 5.2. The 5.2 release notes add an Add Primitive tool
in Sculpt Mode and **Geometry Nodes modifiers on Empty objects** ("a good choice… for fully generated objects that
don't have original data"). The second item matters for the spec's "Empty proxy + GN gizmo" idea.

### What BlendSolid should copy

- **Menu placement and naming:** Shift+A → **BlendSolid** submenu (Box, Cylinder, Sphere, Cone, Torus, Wedge,
  plus later "Tube", "Capsule"), mirroring Shift+A → Mesh → Modern Primitive. Also a Create panel in the N-panel.
- **Place at the 3D cursor, taking the cursor's rotation.** Free and native, and it gives users a "construction
  plane" through the 3D cursor with no new concept.
- **Three places for the same parameters:** the Adjust Last Operation panel right after creation (native), then
  a persistent panel (M1 already has one), then gizmos in the viewport. Add a **modal edit** with letter keys
  (S/H/R) and typed numbers, the Modern Primitive way, which is ideal for keyboard users.
- **Focus/HUD conventions:** a small value HUD next to the gizmo while dragging (`blf`), and a "focus" shortcut
  that opens the part's parameters.
- **"Convert to BlendSolid" from existing primitives.** Read Modern Primitive's modifier inputs, or infer
  parameters from a plain Blender cylinder or cube mesh as RePrimitive does, and write the equivalent exact
  `Box`/`Cylinder` script. This gives interoperability for free and a migration path for users' blockouts.
- **"Apply Mesh" (bake).** Freeze the part into an ordinary mesh, optionally keeping the script, as Modern
  Primitive does.
- **Warn when users try to Edit-Mode the display mesh.** The mesh is derived, as Modern Primitive warns for its
  own primitives.
- **Gizmo lessons:** handles must not hide the transform gizmo (ND users' complaint). Gizmos must follow a
  non-uniform object scale, or scale must be locked or applied (Modern Primitive has a whole "Apply Scale"
  feature for this). BlendSolid should keep part scale at 1: a scaled BRep is a different part, and scale
  belongs in the script.

### What must differ

- **The geometry comes from build123d in the worker, not from Geometry Nodes.** Parameters live in the script's
  parameter block, not in modifier inputs. So a GN modifier can at most host *gizmo nodes*, and Python has to
  mirror its inputs into the script. That is a two-way sync with undo and feedback-loop risks. **Recommendation:**
  use **Python `GizmoGroup`s with `target_set_handler`** writing straight to the script parameter, and keep GN
  gizmos as the spike item the spec already lists. Modern Primitive shows GN gizmos work in 5.2, but in their
  case the GN graph owns the geometry.
- **Latency:** GN recomputes in-process and instantly, while a BRep recompute is a round-trip to the worker.
  During a gizmo drag BlendSolid needs a "latest value wins" request queue, plus either a throttled live
  recompute or a cheap preview (a scaled copy of the last mesh or a `gpu` ghost), then a final recompute on
  release.
- **No segment counts or UV options per primitive.** Tessellation is a per-part display setting (the spec's
  "adjustable tessellation"), not a shape parameter.
- **No "Edit Mode on the base mesh" trick** (ND Primitives). The only path back to mesh modeling is Apply Mesh,
  which is one-way. SubD → NURBS comes later from the other direction.
- **Primitives are the first feature of a part.** They must also be addable *into* an existing part as union or
  cut features (section 6, tool 2). No GN-primitive add-on has that concept.

---

## 5. Which interaction patterns fit BlendSolid

Criteria: (a) every action must become a script edit; (b) native Blender UI only, with no custom modes; (c) the
worker adds latency; (d) whether the pattern needs selectors (M2) or only placements.

**Patterns that fit well**

| Pattern | Source | Why it fits | Needs M2? |
| --- | --- | --- | --- |
| Shift+A primitive, then Adjust Last Operation | Blender, Fusion Box | 1:1 with an operator with `REGISTER\|UNDO` whose `execute` writes a parameter block plus one feature line | No |
| Draw base, then height, on a face or grid | Blender Add Cube tool, QBlocker, BoxCutter, Fusion Box | A WorkSpaceTool plus a modal operator; the result is a primitive at a fixed `Location` computed from the clicked face's plane | No (fixed placement) |
| Boolean by drag direction (outward = union, inward = cut, no contact = new part) | Shapr3D, MoI, CAD Sketcher | Removes a step; maps to `mode=Mode.ADD/SUBTRACT` | No |
| Live cutter objects moved with G/R/S | BoxCutter, Hard Ops, Plasticity "Keep Tools" | The native transform gizmo becomes the CAD operation, which is exactly the spec's proxy idea | No |
| Selection implies the command (face → push, edge → fillet, region → extrude) | Plasticity, Fusion Press Pull | Can be done with one "smart" operator on a key (for example Q, like Fusion) that dispatches on what the picked BRep entity is. It is not automatic on selection, which would be un-Blender-like | Yes (edges and faces) |
| Push/pull edits the owning feature's parameter | SOLIDWORKS Instant3D, Fusion "Edit Feature" | No new script line and no selector: only face → feature provenance. Very robust | No selectors; needs provenance |
| GUI writes readable code, and code lines highlight on selection | Zoo, Onshape "Show code" | This *is* BlendSolid's architecture. For advanced users (ADR 0002) the Text Editor can jump to the feature line | – |
| Typed values during modal drags, then the redo panel | Blender, CAD Sketcher, Plasticity (Tab) | Native; units via ADR 0003 | – |
| 3D cursor as the construction plane | Blender, Modern Primitive, Plasticity's cplane | Native concept; no new "construction plane" object needed for the MVP | – |

**Patterns that don't fit (now)**

| Pattern | Why not |
| --- | --- |
| Plasticity-style **pure direct modeling without history** | Contradicts "history = script". But we can *present* direct modeling (as Shapr3D does) while recording steps. |
| A **dedicated CAD mode** ("Forge Mode", Plasticity's command context) | Python cannot add modes. Use a "CAD" workspace plus WorkSpaceTools plus tool-scoped keymaps instead. |
| **Full constrained sketcher** in the MVP (Fusion, Onshape, Shapr3D, Zoo) | A large project (solver, UI). CAD Sketcher already exists (GPL, SolveSpace, very active). This is v2 per the spec; prefer interop (import solved sketches as exact profiles) over rewriting. |
| **Curves as free-standing objects that later become solids** (Plasticity, MoI, Rhino) | In BlendSolid a curve that isn't part of a part's script has no history. Keep profiles *inside* a part's script (sketch features). Free-standing BlendSolid curves are v2 at best. |
| **Timeline UI with rollback/reorder** (Fusion, Onshape) | Needs a custom editor, which native UI can't provide nicely. A *feature list* panel (UIList) is feasible later, but it is not part of the creation workflow. |
| **Automatic command on selection** (Plasticity) | Blender users select constantly with no intent to act. Use explicit keys or tools. |
| **Touch/pencil-first** (Shapr3D) | Not Blender's input model. |

---

## 6. Recommended creation workflow for the MVP

### 6.1 Principles

1. **Every tool is a Blender operator with `bl_options = {'REGISTER', 'UNDO'}`.** Its `execute()` does exactly one
   thing: rewrite the part's script (add a parameter block entry plus a feature statement, or change a parameter).
   The worker recompute follows as in M1. This gives the Adjust Last Operation panel and Blender undo for free, as
   one undo step per tool. Interactive versions are modal (`invoke`/`modal`) operators that *end* by calling the
   same `execute()`.
2. **Named features, named parameters.** Each tool emits parameters prefixed with the feature name
   (`boss_1_radius = 6.0`) and a marker on the feature statement (`# feature: boss_1`). This keeps M1's parameter
   block convention and gives the UI a line ↔ feature map (Zoo-style highlighting). It also gives the worker a
   hook for provenance (6.3).
3. **Two kinds of references, chosen explicitly:**
   - *Fixed placement:* the click's plane is written as numbers (`Location`, `Plane(origin=…, z_dir=…)`).
     It is always robust but not associative: if an upstream parameter moves the face, the feature stays where it
     was.
   - *Associative reference:* an M2 selector (`part.faces()…`) or provenance (`Select.LAST` of a named feature).
     It follows upstream changes but can become ambiguous.
   The MVP can ship tools with fixed placement first and upgrade them when M2 lands, without changing the UX.
4. **Tools live in a "CAD" workspace as WorkSpaceTools**, with tool-scoped keymaps so they don't steal E/Q/Ctrl+B
   from Object Mode. Shift+A and F3 work everywhere.
5. **Precise input everywhere, in the same three layers:** typed numbers during the modal drag (Blender
   convention; CAD Sketcher's "digits, then Tab to the next value, units accepted"), then the Adjust Last
   Operation panel, then the persistent parameter panel and gizmos.

### 6.2 The first 8 tools, in order

| # | Tool | Blender-native UI | build123d written | Needs selectors? |
| --- | --- | --- | --- | --- |
| **1** | **Parametric primitives** (Box, Cylinder, Sphere, Cone, Torus, Wedge) as new parts | Shift+A → BlendSolid → …; operator with `REGISTER\|UNDO`, so the Adjust Last Operation panel shows size and alignment; placed at the 3D cursor with its rotation (object transform, not script); then the M1 panel plus **arrow/dial gizmos** (Python `GizmoGroup`) on each dimension, a HUD, and modal edit (letter keys) | `box_1_length = 40.0` … then `Box(box_1_length, box_1_width, box_1_height, align=Align.MIN)  # feature: box_1` | No |
| **2** | **Interactive "Draw Solid" tool** (box/cylinder/polygon prism drawn on a face or the grid; BoxCutter/QBlocker/Add Cube style) | WorkSpaceTool with a modal operator: hover shows the face plane (from `ray_cast` plus BRep face ID, or the 3D-cursor plane when over empty space). LMB drag draws the base (Ctrl snaps via Blender's snap settings; digits type values), release, move the mouse for height, click to confirm. **The direction picks the boolean** (outward union, inward cut); Alt cycles New part / Union / Cut / Intersect, like Plasticity's keys; afterwards the redo panel | Inside the target part: `with Locations(Location((x, y, z), (rx, ry, rz))): Box(cut_1_w, cut_1_d, cut_1_h, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)  # feature: cut_1`. Over empty space: a new part, as in tool 1 | **No** (fixed placement); upgrade to a face-relative location after M2 |
| **3** | **Booleans between parts with live cutters** | Select the cutter(s), then the target, then **Ctrl+Numpad −/+/*** (Bool Tool convention) or the header menu. The cutter stays a visible part in wire display (BoxCutter convention); moving it with G/R/S or the transform gizmo re-cuts. "Apply" inlines the cutter's script into the target, making the history self-contained | `add(ref("Cutter"), mode=Mode.SUBTRACT)  # feature: cut_2`. `ref()` is a BlendSolid helper that the worker resolves to the other part's result in the target's local frame. Parts form a DAG and the worker orders recomputes | No |
| **4** | **Fillet / chamfer on clicked edges** | Edge-picking WorkSpaceTool (BRep edge IDs in mesh attributes, per the spec), then **Ctrl+B** (Blender's bevel key) as a modal drag of the radius, typed digits and Adjust Last Operation; afterwards an arrow gizmo on the radius | `fillet(<selector from M2>, radius=fillet_1_radius)  # feature: fillet_1` | **Yes: the M2 driving case.** Without M2, only "fillet all edges of feature X" via `Select.LAST` provenance |
| **5a** | **Push/pull a cap face → edit its parameter** (Instant3D / Fusion "Edit Feature") | Click a face and press **G** (proxy Empty per the spec), or drag the face's arrow gizmo. If provenance says "this face is the +Z cap of `box_1`" or "the end face of `extrude_1`", the drag changes `box_1_height` / `extrude_1_depth` | Changes one number; adds no line | **No selectors.** Needs face → (feature, role) provenance from the worker |
| **5b** | **Push/pull any planar face → new feature** | Same gesture when the face has no editable owner (after booleans, fillets, STEP imports). Outward adds material, inward removes it | `extrude(<face selector>, amount=push_1, mode=Mode.ADD)` (or `Mode.SUBTRACT` with a negative amount); non-planar faces need OCCT offset-face, which is v2 in the catalog ("offset face") | **Yes: face selectors** |
| **6** | **Sketch on face + Extrude** (rectangle, circle, polygon, slot, polyline/arc chain; closed profiles become regions automatically) | "Sketch" WorkSpaceTool: hover a face (or use the 3D-cursor plane), click to start; profile tools draw with typed values; closed loops are detected as regions (Plasticity/FORGE "auto-regions"); **E** extrudes the selected region with an arrow gizmo, the boolean follows the drag direction (Shapr3D rules), plus the redo panel. Revolve (tool 7) takes the same regions | `with BuildSketch(<plane>): with Locations((sk_1_x, sk_1_y)): Rectangle(sk_1_w, sk_1_h)` then `extrude(amount=extrude_1_depth, mode=Mode.ADD)  # feature: extrude_1`. `<plane>` is a fixed `Plane(...)` before M2 and `part.faces()…` (a face selector) after | Fixed plane without M2; associative with M2 |
| **7** | **Revolve, mirror, linear/polar pattern** of features | Operators with redo panels; the axis comes from a picked straight edge, a part axis or the 3D-cursor axis; gizmos for angle and count | `revolve(axis=…, revolution_arc=rev_1_angle)`, `mirror(about=Plane.YZ)`, `with PolarLocations(r, n): …` | Axis by pick needs an edge selector; axes from the cursor or part don't |
| **8** | **STEP import as base feature**, then direct edits (tools 4 and 5b) | File → Import → STEP (BlendSolid) creates a part whose first line imports the file (stored in the .blend or linked) | `import_step("…")  # feature: base` followed by features | Edits need M2 selectors; this is the "kitbash of real parts" use case from the spec's vision |

Shell, thicken, loft, sweep and pipe (the rest of the MVP catalog) follow the same operator-writes-a-line pattern
after tool 8. They mostly need profile or face references that tools 4–6 will have built.

### 6.3 Relation to milestone 2 (selectors from clicks)

- **Tools 1–3 need no selectors.** They give users a real, useful modeling loop (blockout, cut, add, move
  cutters) *before* M2 and should come first. Suggestion: a short **M1.5 "Build without selectors"** with the
  measurable criterion "a user can build the M1 default part and a bracket with 3 holes using only tools 1–3,
  and every step is one undo step and one script edit".
- **Face → feature provenance is a smaller, separate piece of infrastructure than selectors.** After each named
  feature the worker records which faces and edges are `Select.LAST`/`Select.NEW` and tags them in the face/edge
  map it already returns (feature name plus role such as "cap", "side" or "end"). It makes tool 5a possible, and
  it gives M2's selector synthesis a strong first strategy: "faces created by `extrude_1`, then disambiguated
  geometrically". This is the Onshape `qCreatedBy` approach. **Recommend building it at the start of M2.**
- **Tools 4, 5b, 6 (associative) and 8 need M2.** Tool 4 (fillet on clicked edges) is the natural driver, because
  M2's success criterion is written on edges. **But tools 5b and 6 need face selectors**, so M2's criterion should
  be extended to "…95% of clicked **edges and faces**…".
- **Is push/pull blocked on selectors?** Only partly. On a face that belongs to a feature's parameter (the common
  case right after tools 1, 2 and 6) it is not: it needs provenance only. On a face with no editable owner it is.

### 6.4 Keymap proposal (tool-scoped where it could clash)

| Key | Action | Precedent |
| --- | --- | --- |
| Shift+A → BlendSolid | Add parametric primitive | Blender, Modern Primitive |
| (tool) LMB drag | Draw a solid on the face or grid | Add Cube tool, BoxCutter, QBlocker |
| G / R / S on a part or cutter | Move the part, or re-cut with the cutter | Blender, BoxCutter |
| G on a picked face (proxy) or drag its arrow | Push/pull (5a/5b) | Spec, Rhino gumball, SketchUp |
| Ctrl+B | Fillet/chamfer the picked edges | Blender bevel |
| Ctrl+Numpad − / + / * | Difference / union / intersect parts | Bool Tool, Hard Ops |
| E (in the Sketch tool) | Extrude the region | Plasticity, Fusion, Blender |
| Alt (during a draw or extrude) | Cycle the boolean mode | Plasticity Q/W/…, Shapr3D badge |
| Digits, Tab | Typed values, next field | Blender, CAD Sketcher, Plasticity |
| F9 | Adjust Last Operation | Blender |
| Ctrl+Shift+C | Modal parameter edit on the active part | Modern Primitive |

---

## 7. Risks and open questions

1. **Latency during drags.** Worker round-trips make gizmo and push/pull drags laggy on complex parts. This needs
   the spec's per-step state cache (recompute only from the edited feature onward), "latest value wins" requests,
   and a cheap preview. It should be measured early on tool 1's gizmos.
2. **Fixed placements drift.** Before M2, a cut drawn on a face stays put when the face moves upstream. That can
   surprise users. Mitigation: show a "not attached" state in the feature panel, and make "re-attach to face" the
   first thing M2 upgrades.
3. **Face ambiguity is worse than edge ambiguity in symmetric parts** (the top faces of two identical bosses).
   Provenance-first selectors (created by feature X) reduce this. The spec's fallbacks (OCCT history, then
   geometric matching) still apply.
4. **Cross-part references** (live cutters, `ref()`) turn parts into a DAG. Open questions: cycles, deleting a
   cutter, linking and appending parts between .blend files, and recompute order in the worker. Alternative: make
   "Apply" (inline the cutter) the default and keep live cutters optional.
5. **Undo with modal tools.** One undo step per tool is fine. Gizmo drags that write the script on every event
   would flood undo, so only the release should push an undo step. This ties into the spec's undo question.
6. **Keymap collisions** (E, Q, Ctrl+B, Ctrl+Numpad) with the user's add-ons (Hard Ops, Bool Tool). Scope keys to
   BlendSolid tools where possible, and document the conflicts.
7. **GN gizmos vs Python gizmos.** Modern Primitive proves GN gizmos in 5.2, but syncing GN modifier inputs with
   the script adds a second source of truth. The spike item stays open. Blender 5.2's "GN modifiers on Empty
   objects" makes a GN-gizmo proxy Empty plausible.
8. **Sketcher strategy** (open decision in the spec). CAD Sketcher now also does parts, extrude and auto-boolean
   on *meshes*, so it partly overlaps with BlendSolid's UX. Option A: consume its solved entities as exact
   build123d profiles (interop). Option B: minimal own profile tools (tool 6) with no constraints in the MVP.
   Recommendation: B for the MVP, A for v2 constraints. Contact the CAD Sketcher maintainer early.
9. **Competition and perception.** FORGE ships a Plasticity-like tool set today and promises history. BlendSolid's
   open code history needs to be *visible* in the UX: a feature list, "show code" for advanced users, and
   Claude/MCP editing.
10. **Multi-body parts vs one solid per part.** Tool 2's "no contact = new part" vs "new body in the same part" is
    a product decision. Shapr3D and Plasticity allow multiple bodies, while M1 has `result = part.part`.
11. **Verification.** Every tool needs headless tests that check volumes and BRep validity (project rule), plus
    manual steps for the modal/gizmo parts.

---

## 8. What I could not verify

- FORGE's kernel, docs and exact interaction: only marketing text and video descriptions were reachable.
- The Plasticity "Constraints ≈ Alias History" claim (search snippet only; not in the 2025.1 or 2026.1 release
  notes).
- The text of Fusion's Press Pull "Offset Type" options and SOLIDWORKS Instant3D's steps. Both pages blocked
  automated fetches, so they are summarized from search-engine snippets of the official pages.
- QBlocker's detailed docs (404 on subpages) and Hard Ops' manual (placeholder content).

---

## 9. Sources (with dates)

**FORGE and namesakes**
- FORGE product page, Gumroad (V1.0 text, roadmap), accessed 2026-09-26: https://rendercraftstudio01.gumroad.com/l/forge
- FORGE on Superhive ("Published 3 months ago", Blender 4.2–5.0, GPL), accessed 2026-09-26: https://superhivemarket.com/products/forge-cad-precision-modelling-in-blender
- "Real-Time CAD Modeling in Blender is HERE (FORGE Add-on)", Rendercraft Studio, YouTube, 2026-06-20: https://www.youtube.com/watch?v=Vrv8sL2tHek
- "True CAD in Blender? (FORGE Add-on Teaser)", YouTube Shorts, 2026-06-08: https://www.youtube.com/shorts/LE1cXxQj0yY
- Skool community post "Forge Addon Blender", 1 July (year not shown, context 2026): https://www.skool.com/ultimate-3d-membership-7140/forge-addon-blender?p=79d81c7e
- anyplugins mirror ("last updated July 15, 2026"; low reliability): https://anyplugins.com/plugin/forge-cad-precision-modelling-in-blender
- ForgeCAD public kit (code-first JS CAD), accessed 2026-09-26: https://github.com/ForgeCAD/forgecad-public-kit

**Plasticity**
- Manual home (current 2026.1): https://doc.plasticity.xyz/
- Extrude: https://doc.plasticity.xyz/solid/extrude · Offset Face: https://doc.plasticity.xyz/solid/offset-face · Boolean: https://doc.plasticity.xyz/solid/boolean · Fillet Shell: https://doc.plasticity.xyz/solid/fillet-shell · Line: https://doc.plasticity.xyz/tool/line · Construction plane: https://doc.plasticity.xyz/plasticity-essentials/plasticity-interface/construction-plane · Object types (regions): https://doc.plasticity.xyz/plasticity-essentials/object-types (all accessed 2026-09-26)
- Release notes 2026.1, 2026-04-16: https://doc.plasticity.xyz/whats-new
- Release notes 25.1, 2025-02-25: https://doc.plasticity.xyz/release-notes/whats-new-2025.1
- R. Gliffe, "Plasticity 3D – CAD for Artists", Digital Production, 2023-10-04: https://digitalproduction.com/2023/10/04/plasticity-3d-cad-for-artists/
- Wikipedia, Plasticity (software), accessed 2026-09-26: https://en.wikipedia.org/wiki/Plasticity_(software)

**Shapr3D**
- Extrude (created 2023-02-24, updated 2026-08-26): https://support.shapr3d.com/hc/en-us/articles/7874453786908-Extrude
- 5.590 – History-Based Parametric Modeling is here (2024-04-08): https://support.shapr3d.com/hc/en-us/articles/13444210101788-5-590-History-Based-Parametric-Modeling-is-here
- Sketching in Shapr3D (2025-03-04, updated 2026-09-21): https://support.shapr3d.com/hc/en-us/articles/18816009328284-Sketching-in-Shapr3D
- Create sketches (2024-02-02): https://support.shapr3d.com/hc/en-us/articles/12469688911516-Create-sketches
- Using History and Extrude (2024-04-30): https://support.shapr3d.com/hc/en-us/articles/13778812916636-Using-History-and-Extrude
- Building parametric models with driving sketches (2025-04-23): https://support.shapr3d.com/hc/en-us/articles/19704555060508-Building-parametric-models-with-driving-sketches
- Adaptive Parametric Modeling (undated product page): https://www.shapr3d.com/content-library/shapr3d-history-based-parametric-modeling
- Shapr3D on iPad (undated): https://www.shapr3d.com/download/ipad · Digital Engineering review (undated): https://www.digitalengineering247.com/article/shapr3d-unites-modeling-rigor-with-sketching-simplicity/design

**Fusion**
- Create solids with Press Pull (accessed 2026-09-26): https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/GUID-02F9ADA3-7556-42A9-8AD1-552728D537AB.htm
- Press Pull does not create a timeline feature (support article; snippet only): https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Press-Pull-does-not-create-a-timeline-feature-in-Fusion-360.html
- Modeling modes in Fusion: https://help.autodesk.com/view/fusion360/ENU/?contextId=ASM-DESIGN-MODELING-MODES
- Extrude a solid body: https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-EXTRUDE-SOLID.htm
- Create a solid box: https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-BOX-SOLID.htm

**Onshape**
- FeatureScript introduction ("Show code"): https://cad.onshape.com/FsDoc/intro.html
- FeatureScript standard library, queries: https://cad.onshape.com/FsDoc/library.html#module-query.fs
- Extrude help: https://cad.onshape.com/help/Content/PartStudio/extrude.htm (all accessed 2026-09-26)

**MoI and Rhino**
- MoI v4 command reference, Construct (Extrude, Booleans): http://moi3d.com/4.0/docs/moi_command_reference7.htm · Edit (History): http://moi3d.com/4.0/docs/moi_command_reference4.htm · Draw curve: http://moi3d.com/4.0/docs/moi_command_reference2.htm (page footer © 2014)
- MoI forum, extrusion history: http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=7365.2
- Rhino 8 History: https://docs.mcneel.com/rhino/8/help/en-us/commands/history.htm · Gumball: https://docs.mcneel.com/rhino/8/help/en-us/commands/gumball.htm · PushPull: https://docs.mcneel.com/rhino/8/help/en-us/commands/pushpull.htm · Push-Pull feature page: https://www.rhino3d.com/features/push-pull/ (accessed 2026-09-26)

**Blender native**
- Undo & Redo, Adjust Last Operation (5.2 LTS manual): https://docs.blender.org/manual/en/latest/interface/undo_redo.html
- Add Cube tool (5.2 LTS manual): https://docs.blender.org/manual/en/latest/editors/3dview/toolbar/add_cube.html
- Extrude Faces (5.2 LTS manual): https://docs.blender.org/manual/en/latest/modeling/meshes/editing/face/extrude_faces.html
- Blender 5.2 LTS Geometry Nodes release notes (GN modifiers on empties): https://developer.blender.org/docs/release_notes/5.2/geometry_nodes/
- Blender 5.2 LTS release notes: https://developer.blender.org/docs/release_notes/5.2/

**Blender add-ons**
- CAD Sketcher docs (tools, interaction system, modeling, parts, integration), repo docs at v0.32.0 (2026-09-25): https://github.com/hlorus/CAD_Sketcher/tree/main/docs/content · site: https://www.cadsketcher.com/
- BoxCutter manual, modes: https://boxcutter-manual.readthedocs.io/en/latest/modes/ · BoxCutter 26 on Superhive: https://superhivemarket.com/products/boxcutter
- Hard Ops manual: https://hardops-manual.readthedocs.io/en/latest/
- BlendQuery (last push 2024-07-13): https://github.com/uki-dev/blendquery
- STEPper NEXT (pushed 2026-09-18): https://github.com/Peak-Design/STEPper_NEXT · step2blend: https://github.com/BlueLazyFish/step2blend · blender2step: https://github.com/langhua/blender2step
- Bonsai docs 0.8.5: https://docs.bonsaibim.org/ · extension page: https://extensions.blender.org/add-ons/bonsai/
- KittyCAD text-to-cad Blender add-on: https://github.com/KittyCAD/text-to-cad-blender-addon
- Serpentine3D (2026): https://github.com/eoneruw/Serpentine3D

**Parametric primitive add-ons**
- Modern Primitive, extensions.blender.org (published 2024-12-18, updated about 2026-08, 4.3+): https://extensions.blender.org/add-ons/modern-primitive/ · repo (v0.0.57 on 2026-07-28; code inspected 2026-09-26): https://github.com/degarashi/ModernPrimitive
- ND Primitives, extensions.blender.org (published 2024-12-17; "Unsupported 5.2 and above"): https://extensions.blender.org/add-ons/non-destructive-primitives/ · BlenderArtists thread (2024-12-17): https://blenderartists.org/t/non-destructive-primitives-add-on-v0-2-4/1563192
- Better Primitives (CGMatter), V2.7 2025-01-07: https://superhivemarket.com/products/better-primitives
- Paramix: https://superhivemarket.com/products/paramix-
- QBlocker docs: https://qblockerdocs.readthedocs.io/ · Superhive: https://superhivemarket.com/products/qblocker
- RePrimitive (last push 2024-05-12; code inspected 2026-09-26): https://github.com/eXzacT/RePrimitive
- gen_ParametricPrimitives (last push 2021-09-23): https://github.com/g3ntile/gen_ParametricPrimitives

**Code-first**
- build123d selector tutorial: https://build123d.readthedocs.io/en/latest/tutorial_selectors.html · build123d 0.13.0 source (`Select`, `extrude`, `Until`), vendored copy inspected 2026-09-26
- Zoo Design Studio v1, 2025-05-21: https://zoo.dev/blog/zoo-design-studio-v1
- "We redesigned Zoo's sketch mode", 2026-05-28: https://zoo.dev/blog/announcing-solver
- "What's New With Zoo, November Edition" (2025): https://zoo.dev/blog/whats-new-november
- OpenSCAD Customizer (manual): https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/Customizer

**Other tools**
- SketchUp, Pushing and Pulling Shapes into 3D: https://help.sketchup.com/en/sketchup/pushing-and-pulling-shapes-3d
- SOLIDWORKS 2024 help, Creating Features in Instant3D: https://help.solidworks.com/2024/English/SolidWorks/sldworks/t_creating_and_modifying_instant3d.htm (content from search snippets)
