# Research: how OCCT fillets and chamfers fail, and what the Fillet tool should do about it

Date: 2026-09-28. Context: milestone 2, Fillet tool (`ops_fillet.py`, worker wrappers `worker/blends.py`).
The tool writes `fillet(<edge references>, radius=...)` / `chamfer(..., length=...)` into the part script;
build123d 0.13 calls `BRepFilletAPI_MakeFillet` / `BRepFilletAPI_MakeChamfer` of OCCT 8 (OCP 8.0.1).
Goal: know the typical failure cases, turn each into a test, and make every failure give a clear, useful
error (or avoid/fix it).

Legend: **[verified]** = read in the cited page or source code, or measured here on OCP 8.0.1 /
build123d 0.13 with Blender's Python; **[unverified]** = secondary sources or product knowledge that could not
be checked (several vendor help pages returned only navigation chrome or 404 to the fetch tool).

The probe scripts are throwaway (session scratchpad); the numbers below are what they printed.

---

## 1. What OCCT itself says and does

### 1.1 Documentation

- Modeling Algorithms guide, "Fillets and Chamfers": "A fillet description contains an edge and a radius.
  **The edge must be shared by two faces.** The fillet is automatically extended to all edges in a smooth
  continuity with the original edge. It is not an error to add a fillet twice, the last description holds."
  The chapter also claims "Corners and apexes with different radii" and "with different concavity" are
  handled. [verified]
  <https://github.com/Open-Cascade-SAS/OCCT/blob/master/dox/user_guides/modeling_algos/modeling_algos.md>
  (rendered: <https://occt3d.com/dev/doc/overview/html/occt_user_guides__modeling_algos.html>)
- `BRepFilletAPI_MakeFillet::Build()` header comment: "there may be instances where the algorithm fails, for
  example if the data defining the radius of the fillet is not compatible with the geometry of the initial
  shape. **There is no initial analysis of errors** and they only become evident at the construction stage.
  Additionally, in the current software release, the following cases are not handled:
  - the end point of the contour is the point of intersection of **4 or more edges** of the shape, or
  - the intersection of the fillet with a face which limits the contour is **not fully contained in this
    face**." [verified] `src/ModelingAlgorithms/TKFillet/BRepFilletAPI/BRepFilletAPI_MakeFillet.hxx`,
  <https://occt3d.com/dev/doc/refman/html/class_b_rep_fillet_a_p_i___make_fillet.html>
- Chamfer: `Add(dist, E)`, `Add(d1, d2, E, F)` with d1 measured on F, `AddDA(dist, angle, E, F)`.
  "**Nothing is done** if edge E or the face F does not belong to the initial shape" (silent). [verified]
  `BRepFilletAPI_MakeChamfer.hxx`.
- Different radii meeting at a corner leave a gap that OCCT fills with a `GeomFill` patch (guide §2.5.4).
  [verified]

### 1.2 Diagnostic API (MakeFillet only; MakeChamfer has none of it) [verified]

| Method | Meaning (header text) |
|---|---|
| `IsDone()` | result built |
| `NbFaultyContours()`, `FaultyContour(i)` | contours "where the computation of the fillet failed"; `NbEdges(ic)`, `Edge(ic, j)` list their edges |
| `StripeStatus(ic)` → `ChFiDS_ErrorStatus` | `ChFiDS_Ok`, `ChFiDS_Error` (other), `ChFiDS_WalkingFailure` ("problem in the walking"), `ChFiDS_StartsolFailure` ("can't start, **perhaps the radius is too big**"), `ChFiDS_TwistedSurface` |
| `NbFaultyVertices()`, `FaultyVertex(i)` | vertices (corner blends) where the computation failed |
| `HasResult()`, `BadShape()` | "if the filling in a corner failed a shape **with a hole** is returned" (partial result) |
| `NbContours()`, `NbEdges(ic)` | contours after tangent propagation (before Build) |
| `NbComputedSurfaces(ic)`, `ComputedSurface(ic, is)`, `NbSurf`, `Sect`, `Simulate` | inspection of the built stripes |
| `SetParams(Tang, Tesp, T2d, TApp3d, TolApp2d, Fleche)` | tolerances of the walking/approximation |
| `SetContinuity(GeomAbs_C0/C1/C2, AngTol)` | internal continuity of the fillet surfaces (default C1) |
| `SetFilletShape(ChFi3d_Rational / QuasiAngular / Polynomial)` | representation of the circular section |

`MakeChamfer` exposes only `IsDone`, contours and `Simulate`/`Sect` (checked with `dir()` on OCP 8.0.1).

### 1.3 How `ChFi3d_Builder::Compute` fails (source reading) [verified]

`src/ModelingAlgorithms/TKFillet/ChFi3d/ChFi3d_Builder.cxx`:

1. If no contour survived `Add`, `Build()` **throws** `Standard_Failure("There are no suitable edges for
   chamfer or fillet")`. This is the only failure a caller sees as an exception.
2. Each stripe (contour) is computed in a `try`; any `Standard_Failure` inside marks the stripe bad
   (status stays `ChFiDS_Error` unless set earlier). Then each corner (`PerformFilletOnVertex`) in a `try`;
   a failure marks the vertex bad. Then stripes are intersected pairwise (`ChFi3d_StripeEdgeInter`, message
   "fillets have too big radiuses"). **All internal messages are swallowed** (printed only with
   `OCCT_DEBUG`): "OneCorner : fillets have too big radiuses", "IntersectionAtEnd : the max number of faces
   reached", "concavites inverted : fail", "coin mutant non programme" (chamfer), "coin sur plusieurs faces
   non programme", "StartSol : chain is not possible", "PerformSurf : Failed approximation!", ...
3. `IsDone()` false → `Shape()` throws `StdFail_NotDone` ("BRep_API: command not done" is the generic text
   users see in CadQuery/FreeCAD).
4. Nothing checks the final shape: an invalid result is returned with `IsDone() == true`.

`ChFi3d_Builder::PerformElement` (`ChFi3d_Builder_1.cxx`) **silently drops** an added edge when it is
degenerated, has fewer than two distinct faces (free edge, or a seam: same face on both sides), or lies
between **tangent faces** (`ChFi3d::IsTangentFaces`, e.g. the boundary between a fillet and its flat
neighbour). A selection with some such edges fillets the others and says nothing; a selection of only such
edges throws "no suitable edges".

### 1.4 Open OCCT bugs on GitHub (the Mantis tracker moved there) [verified, titles/bodies read]

Search: `gh search issues --repo Open-Cascade-SAS/OCCT fillet`.

| Issue | What | Relevance |
|---|---|---|
| [#172](https://github.com/Open-Cascade-SAS/OCCT/issues/172) (old Mantis 25478) | Fillets that would meet (no flat left between them, e.g. `box 10³`, two opposite edges r=5) fail with "command not done"; other CAD removes the consumed face | our cases 06/07/34 |
| [#1177](https://github.com/Open-Cascade-SAS/OCCT/issues/1177) | Fillet/chamfer cannot reach the opposite edge (box 10, r=10 fails, 9.999 works) or meet another fillet | cases 10/49 |
| [#1371](https://github.com/Open-Cascade-SAS/OCCT/issues/1371) | OCCT 8.0.0p1: fillet of a prism rim made of **one closed rational B-spline edge** returns `IsDone`, 0 faulty contours, but `BRepCheck` invalid and self-intersecting; same oval as 4 edges is fine | "done but invalid" |
| [#1427](https://github.com/Open-Cascade-SAS/OCCT/issues/1427) | fillet on a face tapered 2.9° fails, 2.8° works | draft faces |
| [#736](https://github.com/Open-Cascade-SAS/OCCT/issues/736), [#737](https://github.com/Open-Cascade-SAS/OCCT/issues/737), [#691](https://github.com/Open-Cascade-SAS/OCCT/issues/691)/[#692](https://github.com/Open-Cascade-SAS/OCCT/issues/692)/[#899](https://github.com/Open-Cascade-SAS/OCCT/issues/899)/[#900](https://github.com/Open-Cascade-SAS/OCCT/issues/900) | wrong results: large parts of the shape missing at r=1.0 (fine at 0.99 and 1.01); faulty shapes on sweeps | wrong-but-valid results exist |
| [#1421](https://github.com/Open-Cascade-SAS/OCCT/issues/1421), [#1430](https://github.com/Open-Cascade-SAS/OCCT/issues/1430), [#501](https://github.com/Open-Cascade-SAS/OCCT/issues/501) | **segfaults** with a too-large radius; self-intersections (open) | worker must survive |
| [#725](https://github.com/Open-Cascade-SAS/OCCT/issues/725), [#1163](https://github.com/Open-Cascade-SAS/OCCT/issues/1163) | segfaults near an ellipse edge / after booleans+chamfers (fixed in master; whether OCP 8.0.1 contains the fix is [unverified]) | |
| [#847](https://github.com/Open-Cascade-SAS/OCCT/issues/847), [#1495](https://github.com/Open-Cascade-SAS/OCCT/issues/1495) | **hangs**: `Add()` never returns; `ChFi3d_Builder::StoreData` loops ~forever on a degenerate fillet normal (int overflow) | worker timeout |
| [#1494](https://github.com/Open-Cascade-SAS/OCCT/issues/1494) | `Build()` ignores its `Message_ProgressRange`: no way to cancel a fillet from inside | only killing the process stops it |

An OCCT developer on the forum (2020): ~25 open fillet/chamfer bugs at the time, "different use cases might
result from the same bug". [verified] <https://occt3d.com/dev/content/opencascade-fillet-fiasco/index.html>.
Forum advice: never add seam edges; catch the exception of `Build()`.
[verified] <https://occt3d.com/dev/content/error-control-brepfilletapimakefillet/index.html>

---

## 2. Measurements on OCP 8.0.1 (our kernel)

Each case ran in its own process (60 s timeout; none crashed or hung). "done" = `IsDone()`; "valid" =
`BRepCheck_Analyzer` and `BRepAlgoAPI_Check` (self-intersection, small edges). Box(40,30,20) is centred
(X −20..20, Y −15..15, Z −10..10); the "L" is `Box(40,30,20) - Pos(10,0,5) * Box(20,30,10)` (top-right
quadrant removed: a concave edge along Y at x=0, z=0).

| # | Geometry and operation | OCCT result | Diagnostics | Volume check |
|---|---|---|---|---|
| 01 | Box, one top edge r5 | ok, valid | – | −214.60 = (25−25π/4)·40 ✓ |
| 02 | Box, 3 edges at a corner r5 | ok, valid, 10 faces | – | |
| 03 | same corner, r 2/4/6 | ok, valid | – | |
| 04 | Box, all 12 edges r5 | ok, valid, 26 faces | – | |
| 05 | Box, all 12 edges r9.99 | ok, valid | – | |
| 06 | Box, all 12 edges **r10** (20 mm faces: fillets meet) | **fails** (not done, no exception) | 1 faulty contour, status **`ChFiDS_Ok`** | |
| 07 | Box, two long top edges **r15** (30 mm top: fillets meet) | **fails** | 1 faulty contour, status `ChFiDS_Ok` | |
| 08 | same, r14.9 | ok, valid | – | |
| 09 | same, r16 | **fails** | 0 faulty contours, **2 faulty vertices** (both ends) | |
| 10 | Box, one top edge **r20** (= 20 mm side face) | **fails** | `ChFiDS_StartsolFailure` | |
| 11 | same, r19.99 | ok, valid | – | |
| 12 | same, r25 | **fails** | `ChFiDS_StartsolFailure` | |
| 13 | Pyramid `Solid.make_wedge(20,20,20,10,10,10,10)`, 4 edges at the apex r2 | ok, valid (10 faces) | – | documented "4+ edges" limit **not** hit |
| 37/38 | same apex, 1 or 2 of its 4 edges r2 | ok, valid | – | idem |
| 15 | L, all 18 edges r2 (mixed convex/concave) | ok, valid | – | |
| 52 | L, concave edge r3 | ok, valid | – | +57.94 = (9−9π/4)·30 ✓ |
| 53 | L, concave edge **r12** (10 mm step) | **fails** | `ChFiDS_StartsolFailure` | |
| 54/55 | L, mixed vertex (0,15,0): concave + 2 convex, r2 or r2/4/6 | ok, valid | – | |
| 17 | Box with vertical edges r5, then **one** top edge r2 | ok, valid; **contour has 8 edges** (whole top loop, tangent propagation) | – | |
| 18–20, 40 | same base, top loop r5 / r8 / r9.9 / r12 (bigger than the r5 corner) | ok, valid | – | geometry not checked beyond validity |
| 21 | Cylinder(10,20) top rim r2 | ok, valid | – | |
| 22 | same, r10 = cylinder radius | ok, valid, **3 faces** (top disk vanishes, hemispherical cap) | – | 5235.99 = π·10²·10 + ⅔π·10³ ✓ |
| 23 | Cylinder, **seam** edge r1 | **exception** "There are no suitable edges for chamfer or fillet" | 0 contours | |
| 29 | Box with vertical r5, the 8 vertical edges (**between tangent faces**) r1 | **exception**, same message | 0 contours | |
| 24/25 | Box minus centred Cylinder(5,20), hole rim r2 / r6 | ok, valid | – | |
| 26 | hole 0.5 mm from the +Y face, top +Y edge r2 (fillet runs over the hole) | ok, valid | – | |
| 41 | same hole, rim r1 (fillet breaks through the thin wall) | ok, valid | – | |
| **43** | Box minus `Pos(0,13,0)*Cylinder(1,20)` (small hole inside the fillet band), top +Y edge **r5** | **done, but INVALID** (BRepCheck false; BOP check: 2× SelfIntersect + NotValid) | 0 faulty contours | |
| 43b | same, r = 1, 3, 3.5, 4, 4.5, 5, 6 → invalid; r = 2 → fails; r = 1.5, 1.95 → valid | – | – | **feasible set not an interval** |
| 43c | same, `ChFi3d_Rational/QuasiAngular/Polynomial` | identical invalid result | | fillet shape doesn't matter |
| 43d | same, `ShapeFix_Shape` on the result | BRepCheck **valid**, BOP check invalid, **volume 0** | | ShapeFix is not a repair |
| 42 | Box + 0.005 mm plate on the +X face (sliver faces), top edges r2 | **fails** | `ChFiDS_StartsolFailure` | |
| 27 | prism of a closed interpolated spline (one edge), rim r0.5 | ok, valid | – | #1371 not reproduced |
| 44 | prism of an ellipse converted to a periodic rational B-spline, rim r0.35 | ok, valid | – | #1371 not reproduced |
| 45 | hemisphere (sphere minus box) rim r2 | ok, valid | – | |
| 46/47 | loft Rectangle(20,20) → Circle(6), top/bottom rims r2 (B-spline sides) | ok, valid; one contour of 2 edges | – | |
| 50 | variable radius 2→8 on one edge | ok, valid | – | |
| 30/31 | chamfer one edge 5; asymmetric 5/15 | ok | – | −500 / −1500 ✓ |
| 32 | chamfer asymmetric 5/25 (25 measured on the 30 mm top face) | ok | – | −2500 ✓ (which face gets d1 matters) |
| 48/49 | chamfer one edge **25** / **20** (20 mm side) | **fails**, no diagnostics | – | |
| 34 | chamfer two long top edges 15 (meet) | **fails** | – | |
| 33/35/36 | chamfer corner 3 edges 5; all 12 edges 5; next to a fillet | ok, valid | – | |

Take-aways [verified, measured]:

- A too-large size shows up in **three different ways**: `StartsolFailure` on the contour, a faulty contour
  whose status is still `ChFiDS_Ok`, or no faulty contour at all and faulty *vertices*. The diagnostic API
  locates the problem (contour, vertex) but doesn't explain it reliably.
- **"Fillets meet / face consumed"** (06, 07, 34, 49) fails exactly at the limit and works at limit − ε: the
  limit is plain geometry (the width of the neighbouring flat face) and can be computed.
- **Silent invalid results are real** (43): a hole or other feature inside the fillet band, i.e. the
  documented "intersection of the fillet with a face ... not fully contained in this face". Only a validity
  check catches it; `IsDone`/faulty counts say all is well.
- The set of working radii can be **non-monotonic** (43b): bisection finds *a* working size, not the largest,
  and "too large" can be the wrong explanation.
- Seam and smooth edges are **dropped silently** by `Add`; only when *all* are dropped does anything fail.
- Tangent propagation turns one clicked edge into a contour of many (17: 1 → 8).
- `HasResult()` (partial result) was never true in these cases.
- The "4 or more edges" limitation in the header didn't show on a pyramid apex (OCCT 8), and neither did
  #1371 with our spline profiles; both remain worth a regression test.

### 2.1 build123d 0.13

- `Mixin3D.fillet` adds all edges with one radius, catches `StdFail_NotDone`/`Standard_Failure`, and also
  raises when `not new_shape.is_valid`: "Failed creating a fillet with radius of R, try a smaller value or use
  max_fillet() to find the largest valid fillet radius". The OCCT cause is discarded. [verified,
  `build123d/topology/three_d.py`]
- `Shape.max_fillet(edges, tolerance=0.1, max_iterations=10)` bisects on `[0, 2·bbox diagonal]` with the same
  "done and valid" test. With the defaults it **raises "Failed to find the max value within 0.1 in 10"** for
  Box(20,15,10) and Box(40,30,20) (works for Box(10,10,10)); with `max_iterations=20` it returns 19.997 for
  one edge of Box(40,30,20), 14.988 for the two long top edges, 9.9986 for all 12 edges (0.01–0.13 s).
  [verified, measured]. On case 43 it returned 1.946 (valid) while r=1 is invalid: the non-monotonic set
  again.
- Issue [#1462](https://github.com/gumyr/build123d/issues/1462): a REVERSED solid (outward `offset` with
  openings) makes every fillet produce an inside-out invalid result; fixed by `_forward_solid`. [verified via
  search summary]
- CadQuery: users get the bare "StdFail_NotDone: BRep_API: command not done" and asked for more verbose errors
  ([#876](https://github.com/CadQuery/cadquery/issues/876), no resolution);
  [#346](https://github.com/CadQuery/cadquery/issues/346) chamfer next to a fillet;
  [#1952](https://github.com/CadQuery/cadquery/issues/1952) max fillet fails with multiple faces. [verified]

### 2.2 BlendSolid's current wrapper (`worker/blends.py`)

Measured with the same geometries through `blends.fillet` / `blends.chamfer` inside `BuildPart`:

| Case | Message today | Comment |
|---|---|---|
| 07 two top edges r15 | "too large for these 2 edges: the largest that works is 14.996 mm" | good |
| 06 all edges r10 | "... largest that works is 9.998 mm" | good |
| 48 chamfer 25 | "... largest that works is 19.995 mm" | good |
| 23 seam / 29 smooth edges | "OCCT can't round this edge at any size (try fewer edges at once, or fillet them in separate steps)" | wrong advice: the edge is not a sharp edge at all |
| 42 sliver | "... the largest that works is 0.01 mm" | true but useless: the cause is a 0.005 mm face |
| 43 hole in band r5 | "... the largest that works is 1.987 mm" | misleading: 1 mm fails, 1.5 works; the cause is the hole |
| 43 r1 | "fillet radius 1 mm is too large ... the largest that works is 1 mm" | self-contradictory (0.9998 rounded to 1) |
| 22 cylinder rim r10 | works (hemisphere) | good |

The search costs up to 13 fillets (12 halvings + the first attempt); cheap on these parts (0.01–0.09 s),
but proportional to the part's complexity. The worker already has a job timeout (120 s, `client.py`) and
survives crashes, which covers the segfault/hang bugs above.

---

## 3. How other CAD systems report fillet failures

- **FreeCAD PartDesign** (`FeatureFillet.cpp`): errors "Fillet not possible on selected shapes" (no usable
  edges), "Fillet radius must be greater than zero", "Resulting shape is null", the raw OCCT message, or a
  generic "Fillet operation failed. The selected edges may contain geometry that cannot be filleted together.
  Try filleting edges individually or with a smaller radius." On an **invalid** result it does not fail: it
  calls `ShapeFix_ShapeTolerance::LimitTolerance` and keeps the shape. [verified]
  <https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/PartDesign/App/FeatureFillet.cpp>
  Forum workaround: enable "Refine" on the previous feature (merges coplanar faces, removes seam-like splits).
  [verified, secondary] <https://forum.freecadweb.org/viewtopic.php?p=527337>
- **noBS-CAD** (OCCT-based): for a straight edge between two planes, when OCCT fails because the blend
  consumes a wall, builds the fillet/chamfer as a boolean with a prism of the blend's cross-section, then
  `ShapeUpgrade_UnifySameDomain`; error text names the obstruction: "A 6 mm fillet reaches past the 5 mm wall
  beside the selected edge". [verified] <https://github.com/jackControls/noBS-CAD/pull/160>
- **Onshape** (Parasolid): "Tangent propagation", "**Allow edge overflow**" (let the fillet roll over
  neighbouring edges, deleting them) with "Edges to keep", partial fillets, conic/curvature sections; the
  failing region is shown in the graphics area. [verified, partly]
  <https://cad.onshape.com/help/Content/PartStudio/fillet.htm>
- **SolidWorks**: "Keep features", overflow type (default / keep edge / keep surface); FilletXpert
  "automatically reorder[s] fillets when required or invoke[s] FeatureXpert to resolve fillet errors"; its
  Corner tab lists 3-edge corners with ✓/✗ and alternative corner patches. Help text on failures: the radius
  "may be too large because it cannot fit within a tightly curving face near a selected edge or it would
  inappropriately eliminate an adjacent face". [verified, secondary]
  <https://www.goengineer.com/blog/solidworks-filletxpert-tool-tutorial>,
  <https://www.cati.com/blog/solidworks-feature-mass-filleting/>
- **Fusion**: corner type Rolling Ball vs **Setback**, tangent chain, G2, **Rule Fillet** (all edges of
  faces/features, rounds-only/fillets-only); failures show as "Compute Failed" on the timeline feature.
  [verified, partly] <https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-REF-FILLET.htm>,
  <https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Compute-Failed-message-appears-while-using-pattern-for-Fillets-in-Fusion-360.html>
  Fusion/Inventor highlight the failing edges in red and keep the feature with a warning [unverified].
- **Plasticity** (Parasolid): Fillet Shell with variable points, conic/G2, and a "Y-blend: Attempt" option to
  get better corner topology; error display not documented. [verified, partly]
  <https://doc.plasticity.xyz/solid/fillet-shell>

Common pattern: say **which edges or corner** failed (highlight), keep the feature in the history marked as
failed, give an **actionable number or option** (smaller radius, overflow/keep edges, split into features).
Commercial kernels also *remove consumed faces* (Parasolid/ACIS overflow), which OCCT can't (#172).

---

## 4. Mitigation techniques

1. **Pre-filter the selection** (before OCCT): classify every selected edge with the same tests as
   `PerformElement`: degenerated, fewer than two distinct faces (seam/free), `ChFi3d::IsTangentFaces` /
   `BRep_Tool::Continuity(e, f1, f2) >= GeomAbs_G1` (smooth). Refuse or drop them *with a message*, instead
   of OCCT's silent drop. Cheap and exact.
2. **Geometric upper bound for the common case** (straight edge between two planes; also planes + cylinders):
   for each adjacent planar face, the distance from the edge to the far side of that face along the
   perpendicular in-face direction; the fillet setback is `r / tan(θ/2)` (θ the dihedral turn), which must be
   below that distance, and below half of it when the far edge is filleted in the same operation. This
   explains 06/07/09/10/12/34/48/49/53 exactly ("the 20 mm face beside this edge") and gives the limit
   without bisection.
3. **Always validate the result**: `BRepCheck_Analyzer` (already done) plus, when affordable,
   `BRepAlgoAPI_Check` (self-intersections), one solid, positive volume, and a volume change consistent with
   the operation's sign (fillet of convex edges removes material, of concave edges adds it; for straight
   edges between planes the change is known in closed form, e.g. `(1 − π/4)·r²·L` at 90°).
4. **Locate failures**: on `IsDone() == false` read `NbFaultyContours` → `NbEdges/Edge` (edges to highlight),
   `StripeStatus` (StartsolFailure → "too large for the face next to it"), `NbFaultyVertices` → points (the
   corner to highlight). For an invalid-but-done result, `BRepAlgoAPI_Check::Result()` gives the faulty
   sub-shapes; map them back to the original faces via the builder's `Modified/Generated` history (the
   hole in case 43).
5. **Split by contour**: if a multi-contour fillet fails, run each contour alone (cheap) to find the ones
   that fail by themselves; the rest are interaction failures (fillets meeting). This is also how "partial
   success" can be offered (apply the working contours, report the others) [design idea, see §6].
6. **Order and splitting**: filleting larger radii first, or corners in a different order, is the standard
   manual workaround in SolidWorks/Fusion/FreeCAD forums (FilletXpert automates reordering). For OCCT, one
   `MakeFillet` with all edges is usually better at corners (it builds the vertex blends); sequential fillets
   create fillet-next-to-fillet (tangent propagation) situations. [unverified as a general rule; 17–20 and 36
   show sequential works in simple cases]
7. **Options**: `SetFilletShape` made no difference on the invalid case (43c); `SetParams`/`SetContinuity`
   tune approximation tolerances and are not a fix for topological failures [unverified beyond 43c].
8. **Don't "repair" with ShapeFix**: on case 43, `ShapeFix_Shape` produced a BRepCheck-valid shape with
   volume 0 (43d). FreeCAD's tolerance-limiting just hides invalidity.
9. **Maximum radius search**: bisection (build123d `max_fillet`, our `blends._largest`) assumes that all
   sizes below a working one work. Case 43 disproves it. Mitigate by (a) using the geometric bound (2) when
   it applies, (b) re-checking a couple of sizes below the reported one, (c) wording "the largest size found
   that works" and not claiming "too large" when a smaller size also failed during the search.
10. **Crashes and hangs**: keep OCCT in the worker, keep the job timeout, and give the size search its own
    time budget (it multiplies the fillet's cost by ~13).
11. **Face-consuming fillets** (#172/#1177): out of OCCT's reach; noBS-CAD's prism-boolean fallback for
    straight edges between planes is a possible later feature (it would also make `r = face width` work).
    [design idea]

---

## 5. Test cases

Geometry in build123d terms (Box and Cylinder centred at the origin, as build123d builds them).
"OCCT" = measured behaviour on OCP 8.0.1 (§2). "Ideal" = what the user should see.

| # | Geometry and operation | OCCT (measured) | Ideal user-facing behaviour |
|---|---|---|---|
| T1 | `Box(40,30,20)`, the 3 edges at corner (20,15,10), r=5 | works, valid, 10 faces | works (regression: corner blend) |
| T2 | same 3 edges, r=2, 4, 6 (one per edge; needs per-edge radii in a script) | works, valid | works (regression: unequal radii at a corner) |
| T3 | `Box(40,30,20)`, the two long top edges (along X), r=15 | fails (faulty contour, status Ok) | error on the fillet line: "15 mm is too large: the fillets of these 2 edges would meet across the 30 mm top face; the largest is 14.99 mm"; highlight both edges |
| T4 | same, r=14.9 | works, valid | works |
| T5 | `Box(40,30,20)`, one long top edge, r=20 and r=25 | fails, `StartsolFailure` | "too large for the 20 mm face beside this edge; the largest is 19.99 mm" |
| T6 | `Box(40,30,20)`, all 12 edges, r=10 | fails | as T3, naming the 20 mm faces; largest 9.99 mm |
| T7 | `Cylinder(10,20)`, top rim, r=10 | works, valid (top face vanishes) | works; don't forbid r = face size when OCCT copes |
| T8 | `Cylinder(10,20)`, top rim, r=10.5 | fails | "too large; the largest is 10 mm" |
| T9 | `Cylinder(10,20)`, its seam edge | exception "no suitable edges" | refused at selection time: "this edge is a seam inside one face: there is nothing to round" (no fillet line written) |
| T10 | `Box` with its 4 vertical edges filleted r=5, then those 4 vertical *fillet boundary* edges (between tangent faces), r=1 | exception "no suitable edges" | refused at selection: "these edges are smooth (tangent faces): nothing to round" |
| T11 | T10's base, *one* top edge r=2 | works; contour = 8 edges (whole top loop) | works; preview and message show the propagated loop ("rounds 8 edges, tangent chain") |
| T12 | T10's base, top loop r=8 and r=12 (bigger than the r=5 corners) | works, valid | works; volume sanity check in the test |
| T13 | L = `Box(40,30,20) - Pos(10,0,5)*Box(20,30,10)`, concave edge (along Y through the origin), r=3 | works, volume +57.94 | works (volume sign check: concave adds material) |
| T14 | same concave edge, r=12 (10 mm step) | fails, `StartsolFailure` | "too large for the 10 mm step face; the largest is 9.99 mm" |
| T15 | L, the 3 edges at the mixed vertex (0,15,0) (1 concave + 2 convex), r=2 | works, valid | works (regression: mixed-concavity corner) |
| T16 | `Box(40,30,20) - Pos(0,13,0)*Cylinder(1,20)`, top +Y edge, r=5 | **done but invalid** (self-intersections) | error: "the fillet runs into the hole next to this edge" plus sizes that were checked to work (measured: 0.9998, 1.5 and 1.95 work; 1 and 2 don't), or just "runs into another face: try a smaller radius"; highlight edge and hole. Test must assert the invalid result is **never** accepted |
| T17 | T16 with r=1 | done but invalid (fillet boundary tangent to the hole) | error, not "1 mm is too large; the largest that works is 1 mm" |
| T18 | `Box(40,30,20) + Pos(20.0025,0,-0.005)*Box(0.005,30,19.99)` (0.005 mm sliver), top edges r=2 | fails, `StartsolFailure` | "this edge touches a 0.005 mm face (a sliver from an earlier boolean): fix the earlier feature"; highlight the sliver |
| T19 | `Solid.make_wedge(20,20,20,10,10,10,10)` (pyramid), 4 apex edges r=2; and 1 of them | works, valid | works (regression for the documented 4-edge limitation) |
| T20 | prism of a closed one-edge B-spline profile (interpolated, and a converted ellipse), top rim r=0.35 | works, valid | works (regression for OCCT #1371) |
| T21 | `Box(40,30,20)`, one long top edge, chamfer 25 / 20 | fails, no diagnostics | "chamfer 25 mm is too large for the 20 mm face; the largest is 19.99 mm" |
| T22 | same edge, asymmetric chamfer 5/15 and 5/25 | works; −1500 / −2500 mm³ | works; script says which face gets which length (deterministic reference face), test checks the volume |
| T23 | `Box(40,30,20)`, two long top edges, chamfer 15 (meet) | fails | as T3 |
| T24 | worker: a script whose fillet crashes or hangs (simulate with `os.abort()` / `while True` in a test script) | – | part marked failed with "the geometry worker crashed/timed out while computing the fillet", Blender unaffected, next edit recomputes |

Cases 01, 04, 21, 24/25, 26, 41, 45–47, 50 of §2 are good extra regressions (they work today).

---

## 6. Recommendations for BlendSolid

1. **Classify edges at selection time** (Fillet tool, Blender side via the worker's face/edge map, or worker
   side before `Add`): seam, free, degenerate and smooth edges can't be filleted; say so on click instead of
   writing a line that fails (T9, T10). In `blends.py`, if some selected edges are unfilletable, raise with
   their names rather than letting OCCT drop them silently.
2. **Compute the geometric bound first** for edges between planar (and cylindrical) faces: gives the exact
   limit and a concrete reason ("the 20 mm face beside this edge", "the two fillets would meet across the
   30 mm face"). Use the bisection only when no bound applies.
3. **Keep and strengthen validation**: BRepCheck (as now) + one solid + volume sign/magnitude; add
   `BRepAlgoAPI_Check` if its cost on typical parts is acceptable (measure). T16/T17 must never be accepted.
4. **Use the diagnostic API for location**: faulty contours → edges, faulty vertices → corner points; return
   them with the error so the viewport can highlight them (edge ids are already in the mesh attributes).
5. **Fix the bisection's wording and assumptions** in `blends._largest/_explain`: never print a "largest
   that works" equal (after rounding) to the failing size (T17); re-verify one or two smaller sizes; when a
   smaller probe also failed, say "fails at several sizes (another face is in the way)" instead of "too
   large"; round the reported size *down* to the displayed precision.
6. **Per-contour isolation** when several edges fail together: report which contours fail alone and which
   only together (meeting fillets), so the message can say "these two fillets meet".
7. **Tangent propagation visible**: the preview and the Adjust Last Operation panel should show the
   propagated contour (`NbContours/NbEdges`), since one click may round a whole loop (T11).
8. **No ShapeFix on blend results.**
9. **Time budget** for the size search (e.g. stop after ~2 s and report what's known), separate from the
   120 s job timeout.
10. **Later** (not this milestone): face-consuming fillets on prismatic edges via a prism boolean
    (noBS-CAD approach), "partial success" (apply the working contours), setback/corner options.

## Sources

- OCCT sources (TKFillet: `BRepFilletAPI_MakeFillet.hxx`, `BRepFilletAPI_MakeChamfer.hxx`,
  `ChFi3d_Builder.cxx`, `ChFi3d_Builder_1.cxx`, `ChFiDS_ErrorStatus.hxx`):
  <https://github.com/Open-Cascade-SAS/OCCT/tree/master/src/ModelingAlgorithms/TKFillet>
- OCCT Modeling Algorithms guide:
  <https://github.com/Open-Cascade-SAS/OCCT/blob/master/dox/user_guides/modeling_algos/modeling_algos.md>
- OCCT reference, MakeFillet: <https://occt3d.com/dev/doc/refman/html/class_b_rep_fillet_a_p_i___make_fillet.html>
- OCCT issues: #172, #501, #691, #692, #725, #736, #737, #847, #899, #900, #1163, #1177, #1371, #1421, #1427,
  #1430, #1494, #1495 at <https://github.com/Open-Cascade-SAS/OCCT/issues>
- OCCT forum: <https://occt3d.com/dev/content/opencascade-fillet-fiasco/index.html>,
  <https://occt3d.com/dev/content/error-control-brepfilletapimakefillet/index.html>,
  <https://occt3d.com/dev/content/brepfilletapimakefillet-fillet-failed/index.html>
- build123d 0.13 source (`topology/three_d.py`: `fillet`, `chamfer`, `max_fillet`); issue
  <https://github.com/gumyr/build123d/issues/1462>
- CadQuery issues: <https://github.com/CadQuery/cadquery/issues/876>,
  <https://github.com/CadQuery/cadquery/issues/346>, <https://github.com/CadQuery/cadquery/issues/1952>,
  <https://github.com/dcowden/cadquery/issues/304>
- FreeCAD: <https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/PartDesign/App/FeatureFillet.cpp>,
  <https://github.com/FreeCAD/FreeCAD/issues/18383>, <https://forum.freecadweb.org/viewtopic.php?p=527337>
- noBS-CAD: <https://github.com/jackControls/noBS-CAD/pull/160>
- Onshape: <https://cad.onshape.com/help/Content/PartStudio/fillet.htm>
- SolidWorks: <https://www.goengineer.com/blog/solidworks-filletxpert-tool-tutorial>,
  <https://www.cati.com/blog/solidworks-feature-mass-filleting/>,
  <https://help.solidworks.com/2023/english/SolidWorks/sldworks/HIDD_FILLET_MGR_CORNER.htm>
- Fusion: <https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-REF-FILLET.htm>
- Plasticity: <https://doc.plasticity.xyz/solid/fillet-shell>
