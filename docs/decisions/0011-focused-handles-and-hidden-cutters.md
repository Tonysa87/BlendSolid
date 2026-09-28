# ADR 0011: Handles of one focused feature; cutters hidden in a collection

- **Status:** accepted (2026-09-28, decided from research; checked by the maintainer in the GUI on 2026-09-28)
- **Date:** 2026-09-28
- **Research:** `docs/research/2026-09-28-handles-and-tool-bodies.md`

## Context

The maintainer found the blue parameter arrows cluttering the view:
- the active part showed arrows for **every** primitive feature of its script: the base box, and every box or
  cylinder added or cut with Draw Solid, so after a few cuts arrows float inside and around the solid;
- the arrows stayed while the part was active but deselected (or hidden with H);
- cutters of live booleans (separate parts, shown as wire) stayed visible, and showed their own arrows when
  clicked.

They suggested putting the tool bodies of booleans into a collection that is switched off.

What other software does (research):
- **Handles.** No product shows handles for all features at once. SolidWorks *Instant3D* shows the handles of
  the feature that made the clicked face; Fusion, Onshape, Plasticity and MoI show them only inside an edit
  command; Rhino's Gumball follows the selection. Blender's Geometry Nodes gizmos, the closest precedent, show
  only for an object that is **active and selected**, only for its active modifier and only for inputs in use.
  HardOps' manual calls its per-cutter dots clutter that needs an off switch.
- **Tool bodies.** CAD products consume the tool by default ("Keep Tools" optional). FreeCAD hides the inputs
  and nests them under the result. Blender add-ons (Bool Tool, HardOps/BoxCutter) keep cutters live in a
  cutters collection, wire or bounds display, not rendered, hidden after the cut, parented to the target
  (Bool Tool), and bring them back with Alt+H or by cycling through the booleans.
- **Measured in Blender 5.2.2:** a wire or `hide_select` object is still hit by `scene.ray_cast`; `hide_set()`
  (H, the view layer's eye) and a layer collection's eye keep `matrix_world` updating and parenting working.
  `Object.hide_viewport` and collection *exclude* drop the object from the depsgraph when nothing depends on it:
  its `matrix_world` goes stale. BlendSolid's booleans are computed by the worker, so Blender sees no
  dependency, and `deps.py` would read stale placements.

## Decision

1. **One focused feature per part.** The arrows show only the focused feature's parameters
   (`Object.blendsolid_focus`, a feature name, undoable):
   - clicking a face of the active part (Object Mode, after Blender's own selection click) focuses the feature
     that made that face, read from the face's reference (`face("cut_1", ...)`, ADR 0009): clicking the wall
     of a cut gives the cut's arrows where the cut is;
   - a tool that adds a feature (Draw Solid union/cut, Boolean, Fillet, Push/Pull) focuses it;
   - the sidebar lists the part's features, the focused one highlighted, and a click focuses another;
   - with no focus, or a focus that no longer exists, the first feature is focused (the base solid).
   A feature without arrows (fillet, push/pull, boolean) shows none: focusing it clears the view.
2. **Arrows only for an active, selected, visible part** (the Geometry Nodes rule): deselecting clears them.
3. **Cutters of live booleans** are moved into a `BlendSolid Cutters` collection (created on demand under the
   scene collection, not rendered), parented to their first target keeping their world placement (moving the
   target carries its cuts, as in Bool Tool), kept as wire, and hidden with `hide_set(True)` right after the
   boolean. Never `hide_viewport` or *exclude* (stale placements, measured).
4. **Getting a cutter back:** *Select Cutter* in the sidebar's boolean list (shows and selects it), a
   *Show Cutters* toggle for the active part's cutters, and Blender's own Alt+H or the Outliner's eye.
   *Remove Boolean* on a cutter no other part uses shows it again, solid and rendered, unparents it (world
   placement kept) and moves it back to the target's collection.

## Consequences

- The view shows the arrows of the thing being edited, like Instant3D, and no tool bodies unless asked for.
- The focus click is an Object Mode keymap item that runs after Blender's select click and passes the event
  through; it changes only `blendsolid_focus`, it does not select anything.
- A hidden cutter is out of `scene.ray_cast`: a click can't land on it by mistake (the wire cutter used to take
  Draw Solid's clicks).
- Parenting changes what moving a target does: before, the cut stayed where it was in the world and the target
  was recut; now the cut moves with the target. A cutter already parented (by the user) keeps its parent; a
  cutter used by several targets follows the first.
- Open: drawing a focused boolean's cutter arrows in place without showing the cutter; a scene option to show
  every feature's arrows (for power users).
