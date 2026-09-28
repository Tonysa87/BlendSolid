# Research: when to show parameter handles, and what to do with boolean tool bodies

Date: 2026-09-28. Context: milestone 2. The active part shows arrow gizmos for the dimensions of *every*
primitive feature in its script (base box plus every Draw Solid union/cut), and keeps them while the part is
active but deselected. Separate cutter parts of live booleans stay as wire objects and show their own handles
when active. The view fills with arrows, many inside or floating around the solid. The maintainer proposed a
dedicated hidden collection for all boolean tool bodies. This note looks at how other software handles both
problems before deciding.

Legend: **[verified]** = read in the cited page or source code, or measured here; **[unverified]** = from
general product knowledge or secondary sources that could not be fetched (several vendor help pages returned
403/404 or only navigation chrome to the fetch tool).

---

## 1. When are parameter handles shown?

### SolidWorks (Instant3D)
- Handles appear **when a face or edge is selected**: "Click and drag the arrows that appear when a face or edge
  is selected. The appropriate dimensions will be modified and the model will update."
  [verified] <https://hawkridgesys.com/blog/solidworks-instant3d-instant2d>
- The handles/dimensions shown are those of **the feature that created the clicked face** (and its sketch):
  "the dimensions which appear will be the dimensions associated with whatever feature (and underlying sketch)
  the selected face is related to." [verified, secondary]
  <https://knowledge.cadimensions.com/knowledge/what-is-solidworks-instant-3d>
- Double-clicking a feature (in the tree or on the model) shows all its dimensions.
  [verified, secondary] <https://www.javelin-tech.com/blog/2016/04/show-feature-dimensions-solidworks/>
- Net effect: **one feature at a time, chosen by clicking one of its faces**. Nothing is shown for a part that is
  merely active. Cut features get handles exactly like boss features: click the cut's wall.

### Fusion 360
- Manipulators (arrows, rotation rings) exist **only inside a command dialog** (Extrude, Press Pull, Move,
  Fillet…). After OK they vanish. [unverified: general knowledge, consistent with the help results below]
- To change a feature later: right-click it in the **timeline** → *Edit Feature*, which reopens the dialog with
  its manipulators; move/copy features can be re-edited from the timeline and "adjust the manipulator handles in
  the canvas". [verified, secondary] search result summary of
  <https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/How-to-edit-existing-features-in-Fusion-360.html>
  (403 to the fetch tool) and <https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-USE-MOVE-COPY>.
- Right-clicking a face in the canvas offers *Edit Feature* / *Find in Timeline* for the feature that made the
  face. [unverified]

### Onshape
- Same model as Fusion: manipulator arrows live in the **feature dialog** ("use the manipulator arrow to add
  depth"). [verified] <https://cad.onshape.com/help/Content/PartStudio/extrude.htm>
- Editing = double-click the feature in the Feature list, or right-click a face → *Edit <feature>*.
  [unverified] <https://cad.onshape.com/help/Content/PartStudio/feature_basics.htm>

### Shapr3D
- Direct gizmos appear on the **current selection** (select a face → offset arrow). With history on, selecting a
  history item opens it for editing, with its handles; changes propagate. [verified, secondary]
  <https://support.shapr3d.com/hc/en-us/articles/7874400678428-Offset-Face>,
  <https://support.shapr3d.com/hc/en-us/articles/13444210101788-5-590-History-Based-Parametric-Modeling-is-here>
  (help center returned 403 to the fetch tool; details [unverified]).

### Plasticity
- Gizmos exist **only while a command runs** (Move, Extrude, Push Face, Fillet, Thicken…; Tab types a value).
  [verified, secondary] <https://yelzkizi.org/plasticity-2026-1-adds-new-commands-improves-old-ones/>,
  <https://doc.plasticity.xyz/common/move.en>
- Plasticity is a direct modeler: "no parametric editing, no design history". [verified]
  <https://digitalproduction.com/2023/10/04/plasticity-3d-cad-for-artists/>. Later versions added
  "constraints"/limited history [unverified]. So there is no "handles of an old feature" at all.

### MoI 3D
- Command-scoped handles; only limited history (edit the curve → the extrusion updates, broken by later
  booleans). [verified] <http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=7365.2>

### Rhino (Gumball)
- The Gumball "appears on selected objects" (or sub-object selections such as a face), at the selection's
  bounding-box center; widgets depend on what is selected. [verified, secondary]
  <https://www.rhino3d.com/en/docs/guides/general/gumball-basics/> (404 at fetch time; search summary),
  <https://docs.mcneel.com/rhino/8/help/en-us/options/modeling_aids_gumball.htm>. One gumball for the
  selection, not one per construction parameter.

### FreeCAD
- No persistent handles on parametric features. Parameters are edited in the property editor or in the feature's
  task panel (double-click in the tree). Some objects offer draggers only in edit mode (Transform).
  [unverified: general knowledge; wiki.freecad.org blocked the fetch tool]

### Blender's own gizmos (read from source, `main` branch)
- Light, camera and empty-image gizmos: the poll takes the **active base** and requires
  `BASE_SELECTABLE(v3d, base)` (visible and selectable), **not** `BASE_SELECTED`. So they show for an active but
  deselected object, and hide as soon as it is hidden. [verified]
  `source/blender/editors/space_view3d/view3d_gizmo_light.cc` (lines ~193, 363, 511, 609),
  `view3d_gizmo_camera.cc` (~68), `view3d_gizmo_empty.cc` (~113) at
  <https://projects.blender.org/blender/blender/src/branch/main/source/blender/editors/space_view3d>
- Viewport header: *Gizmos ▸ Active Object* toggles all of them. [verified]
  <https://docs.blender.org/manual/en/latest/editors/3dview/display/gizmo.html>

### Blender Geometry Nodes gizmos (4.3+)
- Manual: a node's gizmos are shown **if the node is selected** in an open node editor; the pin icon keeps them
  visible; gizmos propagated to the modifier "always show when the modifier is active". [verified]
  <https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/gizmos.html>
- Source (`nodes/intern/geometry_nodes_gizmos.cc`, `foreach_active_gizmo`): modifier gizmos are shown only for
  the **active object, if it is also selected** (`active_base->flag & BASE_SELECTED`), only for its **active
  modifier**, only if that modifier is enabled in the viewport, and only for **group inputs that are actually
  used** (socket usage inference). [verified]
  <https://projects.blender.org/blender/blender/src/branch/main/source/blender/nodes/intern/geometry_nodes_gizmos.cc>
- Bug fixed upstream: GN gizmos stayed interactive with *Show Gizmos* off (poll lacked the `V3D_GIZMO_HIDE`
  check). [verified] <https://projects.blender.org/blender/blender/pulls/152529>
- This is the closest analogue to BlendSolid (parameters of a procedural object): Blender deliberately narrows to
  **one object × one modifier**, the one the user focused.

### HardOps / BoxCutter
- No dimension handles on cutters after the cut; the cutter itself is the "handle" (select it, move it, or use
  modifier/bool scroll). hopsTool's *boolean dots* are drawn on demand (select 2 objects + hold Ctrl), and the
  manual itself warns "Boolshapes also get their own dot which is where the view can get cluttered quickly",
  offering a fade distance and an off switch. [verified] <https://hardops-manual.readthedocs.io/en/latest/hopsTool/>

---

## 2. What happens to tool bodies after a boolean?

| Software | Default after boolean | Option | Where the tool lives |
|---|---|---|---|
| Fusion 360 Combine | Tool bodies **removed** (consumed) | *Keep Tools* keeps a copy (then the user hides it in the Browser) [verified] <https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-COMBINE.htm> | Still exists earlier in the timeline; roll the marker back or edit the Combine [unverified] |
| Onshape Boolean | Tools **removed** from the Part Studio | *Keep tools* ("keep the original part and surface entities, or uncheck to remove them") [verified] <https://cad.onshape.com/help/Content/PartStudio/boolean.htm> | Earlier in the feature list (roll back) [unverified] |
| SolidWorks Combine (Subtract) | Tool bodies **consumed**, drop out of the *Solid Bodies* folder [verified, secondary] <https://help.solidworks.com/2023/English/SolidWorks/sldworks/t_combining_bodies_subtract.htm> | — | In the features before Combine (roll back / edit feature) [unverified] |
| Plasticity Boolean | Tools **consumed** | *Keep Tools* [verified] <https://doc.plasticity.xyz/solid/boolean> | Nowhere (no history) |
| FreeCAD Part Cut/Fuse/Common | Base and Tool **kept, hidden**, and **nested under the result** in the tree | Deleting the result asks whether to delete or re-show the inputs | Source: `ViewProviderBoolean::claimChildren()` returns Base+Tool; `hideViewProvider(...)` on link change; `onDelete` shows them again [verified] <https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Part/Gui/ViewProviderBoolean.cpp> |
| Blender Bool Tool (brush boolean) | Cutter **kept**: `hide_render`, `display_type` **BOUNDS** (pref, or WIRE), camera/shadow/… ray visibility off, Line Art excluded, **linked into a `boolean_cutters` collection** (render-hidden, red tag), **parented to the first canvas** (pref, default on) | Auto boolean applies and deletes | Source `functions/cutter.py::make_cutter`, `functions/scene.py::ensure_collection`, `preferences.py` [verified] <https://github.com/nickberckley/bool_tool> (commit a5635e5, 2026-07-15); intro <https://nickberckley.github.io/bool_tool/introduction.html> |
| HardOps / BoxCutter | Cutter kept as a wire "boolshape", put in a **Cutters collection**, **hidden** after the cut (BoxCutter "show shape" off by default = auto-hide) | show shape; wire/bounds display | Alt+H in the collection, Q-menu object scroll, modifier/bool scroll cycles and reveals cutters [verified] <https://hardops-manual.readthedocs.io/en/latest/faq/> |
| Rhino BooleanDifference | Inputs **deleted** (DeleteInput=Yes) | DeleteInput=No keeps them [unverified] | — |

Two families: **feature-based CAD consumes the tool** (it survives in history), **mesh/add-on booleans keep the
tool as a hidden or bounds/wire object** grouped in one collection and usually parented to the target.

## 3. Editing a consumed/hidden tool later

- **SolidWorks:** click a face produced by the cut → that feature's Instant3D handles; or double-click in the
  FeatureManager; or edit feature/roll back. [verified, see §1]
- **Fusion / Onshape:** timeline/feature list → *Edit Feature*; right-click a face → edit the feature that made
  it [partly unverified]. Selecting the result shows only the body; no tool handles.
- **FreeCAD:** expand the result in the tree, select the child (Base/Tool), Space toggles its visibility, edit its
  properties; the result is recomputed. [verified from source for hiding/nesting; workflow unverified]
- **HardOps:** bool/modifier scroll steps through cutters and shows the current one; hopsTool dots; Alt+H.
- **Bool Tool:** utility operators to select, toggle and remove cutters from the canvas; cutters are children of
  the canvas in the Outliner. [verified, intro page + source]

Common thread: **selecting the result never shows the tools' parameters**; the user reaches a tool either by
clicking *its* face/feature (CAD) or through a list/scroll on the target (add-ons, FreeCAD tree).

---

## 4. Comparison table (handles)

| Software | Handles shown for | Trigger | Object state required |
|---|---|---|---|
| SolidWorks Instant3D | one feature | click a face/edge of it | face selected |
| Fusion 360 / Onshape | one feature | inside its command/edit dialog | in command |
| Shapr3D | selection / edited history step | select face or history item | selected / editing |
| Plasticity, MoI | current command | command running | in command |
| Rhino Gumball | whole selection (transform only) | selection | selected |
| FreeCAD | none (property editor / task panel) | double-click in tree | editing |
| Blender light/camera/empty | the active object | always | active + visible/selectable (not selected) |
| Blender GN modifier gizmos | active modifier's *used* inputs | active modifier | active **and** selected |
| HardOps booldots | all boolshapes (known to clutter) | Ctrl held | on demand |
| **BlendSolid today** | **every primitive feature of the part** | always | active (even deselected) |

BlendSolid is the only one showing all features at once, and nobody shows handles for tool bodies of a finished
boolean.

---

## 5. Blender facts measured for this note (Linux Blender 5.2.2, `-b --factory-startup`)

Scene: a 2 m target cube, a 1 m cutter in a "Cutters" collection, `scene.ray_cast` straight down through the
cutter. Script in the session scratchpad (`bl_vis*.py`, not committed).

| Cutter state | `scene.ray_cast` hits cutter | in `selectable_objects` | Boolean modifier still cuts | matrix_world updates, no depsgraph relation | parented child follows parent |
|---|---|---|---|---|---|
| visible, `display_type` WIRE/BOUNDS | **yes** | yes | yes | yes | — |
| `hide_select = True` | **yes** | no | yes | — | — |
| `hide_set(True)` (view-layer hide, H) | no | no | yes | **yes** | **yes** |
| layer collection eye (`LayerCollection.hide_viewport`) | no | no | yes | **yes** | **yes** |
| `Object.hide_viewport = True` (monitor, global) | no | no | yes | **no** (stale) | **no** |
| collection monitor (`Collection.hide_viewport`) | no | no | yes | — | — |
| `LayerCollection.exclude = True` | no | no | yes (the modifier pulls it into the depsgraph) | **no** (stale) | **no** |

Consequences:
- A wire cutter is hit by `scene.ray_cast` (already known), and `hide_select` does **not** make it click-through.
- `hide_viewport` (object or collection monitor) and collection **exclude** drop the object from the depsgraph
  unless something depends on it; BlendSolid's live booleans are computed by the worker, not by a Blender
  modifier, so there is no such relation: `deps.py` would read a **stale `matrix_world`** and a parented cutter
  would not follow its target. Use `hide_set()` or the layer-collection eye instead.
- `hide_set` is per view layer (Outliner eye), saved in the file and undoable; Alt+H reveals everything in the
  view layer, which users know.
- BlendSolid's gizmo poll (`gizmos.py`) checks only `context.object`: after H the hidden part stays
  `context.object` and its handles would still draw. Blender's own polls require `BASE_SELECTABLE`
  (visible, selectable); add `obj.visible_get()` (and, if following GN, `obj.select_get()`).
- Blender 5.2 has `Object.visible_raycast` (Bool Tool sets it off on cutters). It sits with the render ray
  visibility flags; whether it affects `scene.ray_cast` was **not** tested [unverified].

---

## 6. Recommendation for BlendSolid

### 6.1 Handles: one focused feature, like SolidWorks + GN's "active modifier"
1. **Show handles for one feature per part, the *focused* feature**, not all primitive features.
   - Clicking a face of the active part (Select/Tweak click, already picked through `brep_face_id`) focuses the
     feature that **created** that face (worker provenance from build123d's `ShapeHistory`, M2 step 1). Clicking
     a cut's wall focuses the cut: this is Instant3D, and it gives cut features handles *where the cut is*.
   - A new feature (Draw Solid, Add) becomes the focus when created (like Fusion's dialog).
   - Default when nothing was focused yet: the base (first) primitive feature.
   - The sidebar feature list gets an "active feature" highlight, clickable, exactly as the modifier stack's
     active modifier drives GN gizmos. Store the focus per part (e.g. a property on the part object or its Text)
     so undo restores it; resolve it by feature id, falling back to the base feature when the id is gone.
2. **Active *and* selected**, as GN gizmos: deselecting (click in empty space, Alt+A) clears the clutter. Blender's
   light/camera gizmos only need active, but they are single fixed handles; GN is the procedural precedent.
   Also require `obj.visible_get()`.
3. Optional later: a scene toggle "Show all feature handles" (off by default) for power users, the HardOps dots
   lesson being that "all at once" needs an off switch.

### 6.2 Separate cutter parts: keep them live, hide them like Bool Tool/HardOps/FreeCAD
Cutters are real parts with their own script, so the CAD "consume" model would lose their independence;
the Blender add-on and FreeCAD model fits:
1. After a boolean, **link the cutter into a `BlendSolid Cutters` collection** (one per scene, created on demand,
   `hide_render = True`, a color tag), unlinking it from its old collections (Bool Tool only *adds* a link; a
   single home keeps the Outliner clean).
2. **Parent it to the target** keeping its world transform (`matrix_parent_inverse`), so moving the target
   carries its cutters (Bool Tool default). `deps.py` already works in target-relative coordinates.
3. `display_type = "WIRE"` (keep; BOUNDS hides the shape, bad for CAD), `hide_render = True`, and
   **`hide_set(True)`** right after the operation (HardOps/BoxCutter auto-hide, FreeCAD hides inputs).
   Never `hide_viewport` or `exclude` (stale `matrix_world`, measured). A hidden cutter is also out of
   `ray_cast`, which removes today's "wire cutter steals the click" problem.
4. **Getting it back:**
   - Click a face of the target that the cutter produced → focus that boolean feature (6.1). Its handles would be
     the cutter's own parameters; simplest first step: the focus shows a *Select Cutter* affordance (the existing
     `blendsolid.select_cutter`, which already unhides and selects), later drawing the cutter's handles in place.
   - Sidebar boolean list (exists): *Select Cutter* per row, plus a "Show Cutters" toggle for the active target
     (`hide_set(False)` on its cutters only).
   - Standard Blender: Alt+H, Outliner eye, the collection's layer eye for all cutters at once.
   - When a cutter is deselected/deactivated after editing, re-hide it only if it is still used as a cutter
     (optional; HardOps re-hides on scroll-away). Do not auto-hide something the user unhid deliberately without
     a clear rule: start with "hide once, at boolean time".
5. *Remove Boolean* on the last use restores display (already done) and should also unparent and move the part
   back to the target's collection (Bool Tool's `restore_cutter`).

### 6.3 Pitfalls to design around
- Hidden objects are not ray-cast, selectable or in `selectable_objects`; picking a hidden cutter must go through
  the target's face provenance, not through the cutter.
- `hide_set` is per view layer; other view layers see the cutter. Acceptable (same as H).
- Excluded or monitor-hidden cutters freeze `matrix_world` and break parenting without a depsgraph relation.
- `context.object` can be a hidden object: gizmo polls must check visibility.
- Linked-library cutters are read-only: don't try to reparent/relink them (keep `part.is_local_part`).
- The cutters collection must not be created inside `register()` (restricted `bpy.data`); create it in the
  boolean operator.

## Sources
- SolidWorks Instant3D: <https://hawkridgesys.com/blog/solidworks-instant3d-instant2d>,
  <https://knowledge.cadimensions.com/knowledge/what-is-solidworks-instant-3d>,
  <https://www.javelin-tech.com/blog/2016/04/show-feature-dimensions-solidworks/>,
  <https://help.solidworks.com/2023/English/SolidWorks/sldworks/t_combining_bodies_subtract.htm>
- Fusion: <https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-COMBINE.htm>,
  <https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-USE-MOVE-COPY>,
  <https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/How-to-edit-existing-features-in-Fusion-360.html>
- Onshape: <https://cad.onshape.com/help/Content/PartStudio/boolean.htm>,
  <https://cad.onshape.com/help/Content/PartStudio/extrude.htm>
- Shapr3D: <https://support.shapr3d.com/hc/en-us/articles/7874400678428-Offset-Face>,
  <https://support.shapr3d.com/hc/en-us/articles/13444210101788-5-590-History-Based-Parametric-Modeling-is-here>
- Plasticity: <https://doc.plasticity.xyz/solid/boolean>, <https://doc.plasticity.xyz/common/move.en>,
  <https://digitalproduction.com/2023/10/04/plasticity-3d-cad-for-artists/>
- MoI: <http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=7365.2>
- Rhino: <https://www.rhino3d.com/en/docs/guides/general/gumball-basics/>,
  <https://docs.mcneel.com/rhino/8/help/en-us/options/modeling_aids_gumball.htm>
- FreeCAD: <https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Part/Gui/ViewProviderBoolean.cpp>
- Blender: <https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/gizmos.html>,
  <https://docs.blender.org/manual/en/latest/editors/3dview/display/gizmo.html>,
  <https://projects.blender.org/blender/blender/src/branch/main/source/blender/nodes/intern/geometry_nodes_gizmos.cc>,
  <https://projects.blender.org/blender/blender/src/branch/main/source/blender/editors/space_view3d>,
  <https://projects.blender.org/blender/blender/pulls/152529>
- Bool Tool: <https://github.com/nickberckley/bool_tool>, <https://nickberckley.github.io/bool_tool/introduction.html>
- HardOps/BoxCutter: <https://hardops-manual.readthedocs.io/en/latest/faq/>,
  <https://hardops-manual.readthedocs.io/en/latest/hopsTool/>
