# Chamfer options: what CAD tools offer

- **Date:** 2026-09-29
- **Question:** the Fillet tool's chamfer has one length. Which options do CAD tools give, and how is the side of
  an asymmetric chamfer chosen?

## Products

- **Fusion 360** — chamfer types *Equal distance*, *Two distances*, *Distance and angle*; *Flip* swaps the first
  and second sides of a two-distance chamfer (users have asked for a per-edge flip of distance-and-angle).
  <https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-CHAMFER-SOLID.htm>,
  <https://forums.autodesk.com/t5/fusion-360-ideastation-archived/flip-distance-direction-for-chamfer-feature/idi-p/9269604>
- **Onshape** — *Equal distance*, *Two distances*, *Distance and angle*; an arrow flips the direction of all edges,
  *Direction overrides* flips single edges. <https://cad.onshape.com/help/Content/PartStudio/chamfer.htm>
- **Plasticity** — chamfer distance and angle set by moving the cursor or typing the two distances (keys: A angle,
  C chamfer distance, D fillet distance). <https://doc.plasticity.xyz/solid/fillet-shell>

## Kernel

build123d `chamfer(objects, length, length2=None, angle=None, reference=None)`: `angle` makes
`length2 = length · tan(angle)`, i.e. the chamfer's angle to the face `length` is measured on; `reference` (a
Face holding every edge) picks that face, otherwise OCCT takes each edge's first face (`BRepFilletAPI_MakeChamfer`).
One reference face for the whole call.

## Decision for BlendSolid

The operator's Adjust Last Operation panel gets Fusion/Onshape's three types and a Flip. The first length is
measured on a face every selected edge lies on, read from the reference texts (`edge_between(A, B)` → A, B;
`edges_of(F)` → F; the mesh can't be used: at the drag's release it still shows the preview). Default: the
first reference's first face; Flip: its other face, or, when the edges share only one face (a face's edges),
the two distances swapped (a distance and an angle can't be flipped that way: an error says so). Edges with no
common face: an error asks to chamfer them one face at a time (Onshape's per-edge overrides would need one
chamfer call per edge; not now). The drag keeps setting the (first) length; the type, second length or angle
and Flip are set in the panel after the release.
