# Research: the Fillet tool's handle and preview

Date: 2026-09-30. Context: after milestone 2 (listed there: "The tools' on-screen feedback (yellow handle,
preview) is to be redesigned (maintainer)"). The maintainer dislikes the yellow arrow of the Fillet tool and the
preview, which "sometimes looks like the right preview and other times gives a wrong visual effect". This note
first reads what the tool draws today and why it can look wrong, then what other products do.

Legend: **[verified]** = read in the cited page or in this repository's code; **[unverified]** = general product
knowledge or a source that could not be read.

---

## 1. What the tool draws today (`blendsolid/ops_fillet.py`, `drawing.py`) [verified, code]

While dragging, **two previews are on screen at once**:

1. **An immediate overlay** (`_draw_drag` → `preview_lines` → `drawing.fillet_preview`): for each segment of each
   selected edge, the two lines where the fillet would meet the faces and one cross-section arc at the segment's
   middle, in the selection orange. `fillet_preview`'s docstring: "Exact for flat faces, an approximation on
   curved ones".
2. **The real result**: every mouse move rewrites the part script with the fillet at the dragged radius and
   submits it (`_preview` → `runtime.kick()`), so the worker's mesh replaces the part's mesh a few tens of
   milliseconds later (edit → mesh 59 ms on the test part, milestone 2 report).

And the handle: `arrow_lines` draws a yellow shaft from the edge's midpoint along the bisector of the two face
normals, stretched to at least 40 px on screen, with a head made of six strokes (a wire cone), plus a label
("R 3.000 mm") at its tip. Before the drag, the same arrow shows on the first selected edge.

### Why the preview can look wrong (each follows from the code)

- **The two previews disagree**, and which one you are looking at changes from frame to frame:
  - *lag*: the overlay follows the mouse at once, the mesh arrives later, so for a moment the orange lines float
    off the surface;
  - *failure*: when the radius is too large the worker returns an error (the header says "can't: … the largest
    that works is 14.996 mm") and the part keeps its **last good mesh** (`runtime.py` only records the error with `part.set_error`; the mesh is not replaced),
    while the overlay keeps drawing the impossible radius;
  - *curved faces and curved edges*: the overlay offsets each straight chord inside its faces' planes, so around
    a cylinder's edge the lines cut chords, cross each other or leave the surface;
  - *corners*: each edge's lines run to its ends and past where neighbouring fillets meet; OCCT's corner patches
    (vertex blends) aren't drawn at all;
  - *tangent chains*: OCCT rounds the whole tangent chain (it can't be turned off), the overlay only the clicked
    edges.
- **It is drawn through the solid**: `_draw_segments` turns the depth test off (`depth_test_set("NONE")`), so the
  preview lines of edges on the far side show through the part, and the arrow too.
- **The arrow**: along the bisector it often points almost straight at the viewer (the code stretches it to 40 px
  for that reason); a wire cone reads as a scribble at small sizes; it is a different object from the blue
  parameter arrows the rest of BlendSolid uses (native gizmos, ADR 0011), and yellow is not a colour Blender uses
  for handles.

## 2. What other products do

### The preview is the real result
- **Fusion:** "Drag the radius manipulator handles in the canvas, or specify exact values"; the preview "displays
  on the body in the canvas, if it can be created". A missing preview *is* the error signal: "If the individual
  edge you select doesn't display a preview, it's likely to be the problem." [verified]
  <https://help.autodesk.com/view/fusion360/ENU/?contextId=SLD-FILLET-SOLID>,
  <https://www.autodesk.com/products/fusion-360/blog/get-smart-with-fusion-360-fillet-best-practices/>
- **Onshape:** an orange drag arrow "to visualize the fillet and approach an estimated value"; when the fillet
  can't be built, "Onshape displays a visualization of the specified fillet to aid in diagnosing the failure",
  with the problem edges and faces in red; tangent propagation is shown in the preview. [verified]
  <https://cad.onshape.com/help/Content/PartStudio/fillet.htm>
- **Shapr3D:** arrows on the edge: drag them **away** from the body for a fillet, **in** toward it for a chamfer;
  live preview; dimension labels to type the value. [verified]
  <https://support.shapr3d.com/hc/en-us/articles/7874402399900-Chamfer-Fillet>
- **Plasticity (Fillet Shell):** a **yellow dot**: "Move the yellow dot to specify the distance"; positive movement
  = fillet, negative = chamfer; keys during the command: D distance, C chamfer, A chamfer angle, V variable point,
  L range limit, **T toggle tangent edges** (limit to the selected edges), Ctrl add/remove edges; shapes Conic,
  Chordal, G2, Full. [verified] <https://doc.plasticity.xyz/solid/fillet-shell>
- **Rhino FilletEdge:** "Displays a dynamic preview. You can change the options and the preview will update";
  radius **handles at the edge ends** (more with AddHandle), shown or hidden with ShowRadius; when a radius is too
  large there, "the handle changes to dark red and displays the edge radius", i.e. the largest allowed. [verified]
  <https://docs.mcneel.com/rhino/8/help/en-us/commands/filletedge.htm>
- **Blender's Bevel tool (Ctrl+B):** no handle at all; the mouse's distance sets the width, the mesh itself is the
  preview, numbers can be typed, Shift for precision. [verified]
  <https://docs.blender.org/manual/en/2.82/modeling/meshes/editing/subdividing/bevel.html>
- MoI: radius typed or given by two clicked points; the forum thread didn't cover live preview. [verified for
  input; preview unverified] <https://moi3d.com/forum/lmessages.php?msg=7178.1&webtag=MOI>

### When the result is expensive
- **SOLIDWORKS** offers **Full preview** (every fillet), **Partial preview** (one fillet) and **No preview** (only
  the selected edges highlighted, the default), recommending Full, and the lighter ones above ~50 edges.
  [verified, secondary] <https://www.engineersrule.com/advanced-breakdown-solidworks-fillet-featuretool/>
- **FreeCAD 1.1** (March 2026) added **transparent previews** in Part Design (the result drawn semi-transparent
  over the model) and interactive draggers for Fillet and Chamfer. [verified, release post]
  <https://blog.freecad.org/2026/03/25/freecad-version-1-1-released/>,
  <https://blog.freecad.org/2024/12/02/new-grants-transparent-preview-in-part-design-interactive-sketcher-tutorials/>
  Its transparent previews had clipping glitches from the renderer's handling of transparency and bounding
  boxes. [verified] <https://github.com/FreeCAD/FreeCAD/issues/23577>

## 3. What this suggests for BlendSolid

1. **One preview, the real one.** Every product above shows the kernel's result, not a drawn approximation;
   BlendSolid already computes it on every move (59 ms). The approximate overlay is the source of most "wrong"
   frames; drop it, or keep it only as a faint, depth-tested placeholder while no result has arrived yet for the
   current radius.
2. **Say when the preview is stale or impossible**, instead of showing the last good mesh silently:
   - computing: the selected edges in a "busy" tint;
   - can't: the edges (or the handle) turn red with the largest working radius as the label, as Rhino does;
     the worker already finds it by bisection (`worker/blends.py`, "the largest that works is …").
3. **One handle style across BlendSolid**: Blender's native arrow gizmo, as for the parameter arrows (ADR 0011),
   or a dot like Plasticity's; drawn with depth so it doesn't float through the part. Direction: out of the solid
   = fillet, into it = chamfer (Shapr3D, Plasticity) could replace the C key.
4. **The drag doesn't need to start on the handle** (Blender's Bevel): distance of the mouse along the handle's
   screen direction, plus typed numbers (Blender's `NumInput`, already a milestone 2 follow-up).
5. **Show the tangent chain before dragging**: the edges OCCT will round with the clicked one, in a lighter tint
   (Onshape shows propagation; Plasticity's T limits it — OCCT can't, so showing it is the honest part).
6. Selection highlights and previews drawn **with the depth test on**, hidden parts faint or not at all.
