# How CAD/NURBS products tessellate trimmed faces for display and export

Date: 2026-09-28. Research only (web sources, no code). Context: BlendSolid's display mesh of trimmed curved faces
(ADR 0005 and its addendum): Delaunay mosaics on fillet bands, a quarter cylinder trimmed by fillets meshed as one
row of 400 mm triangles fanning between edges with very different node counts, dense slivers on narrow fillet
strips.

**Scope (maintainer, 2026-09-28):** the display mesh should follow CAD conventions (Rhino, Plasticity/Parasolid,
MoI's triangle output): **clean, regular, conforming triangle meshes**. Quad output is a separate, later
"convert to quads" feature; quad findings are only summarised at the end as input for it.

Legend: every claim carries its source. **[unverified]** marks what I could not confirm from a primary source;
**[inference]** marks my own reading of the sources.

---

## 1. MoI3D (Moment of Inspiration)

**Algorithm (Michael Gibson, author).** MoI does not start from a triangulation: it lays a quad mesh on the
surface's (u, v) and cuts the quads with the trim curves into n-gons; triangles, if asked for, come only at the
end by triangulating those n-gons.
- "every single poly edge in the entire output is either along a trim boundary edge, or running along a surface's
  UV directions. There is literally not even a single polygon edge that doesn't belong to one of those categories."
  He calls this "unique to MOI and not available in any commercial geometry library" (26 Dec 2025).
  <http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=11865.65>
- "The meshes that MoI generates will be quads in untrimmed areas of surfaces, but there will be n-gons formed at
  trimming boundaries where any trimming curves slice away regions" (4 Oct 2013); a planar cap becomes "one single
  big n-gon". <http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=6206.1>
- "That quad structure follows the UV layout of each surface, so it isn't typically feasible to get identical quad
  structure between different surfaces that meet along a trimmed edge instead of along a natural surface edge."
  Cylinders or spheres with symmetric cuts can meet at an isoparm; booleaned shapes usually don't (10 Jan 2008).
  <http://moi3d.com/forum/lmessages.php?msg=1244.35&webtag=MOI>
- Joined surfaces get a watertight mesh; unjoined ones are meshed independently with separate vertices
  (2 Dec 2010). <http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=3869.56>

**Export options** (official docs, v4): <https://moi3d.com/4.0/docs/moi_command_reference11.htm>
- Density slider; **Angle**: "the maximum angle allowed between the surface normals at the corners of each polygon".
- **Output**: N-gons (default), Quads & Triangles, Triangles.
- **Weld vertices along edges**: on = polygons on both sides share one point along the edge.
- **Divide larger than**: "force polygons that are larger than this length to be broken down into smaller
  pieces"; can apply to curved, planar or all surfaces.
- **Avoid smaller than**: suppresses refinement below a size (fewer polygons in small areas).
- **Aspect ratio limit**: "force additional subdivisions for quads that are short in one direction but long in
  another. This affects all surfaces, including planar ones." A value of 2 splits any quad with one side more
  than twice the other (per search excerpt of the same page).

**Triangulating the n-gons.** A `moi.ini` switch `CentroidTriangulation`: "an additional point is added to the
centroid of the n-gon and triangles are formed by connecting to that, making a kind of radial triangulation";
it gives "more squat triangles instead of longer skinnier triangles", at the cost of a "poking out" spot on coarse
meshes (6 Mar / 14 Jul 2012). <https://moi3d.com/forum/lmessages.php?msg=4978.23&webtag=MOI>

**Fillets and quality complaints.** A user exporting two perpendicular cylinders with a fillet got long triangles
nearly perpendicular to their neighbours, rendering badly in 3ds Max, and found Plasticity's output cleaner.
Gibson: the artifacts are a vertex-normal problem ("automatically generated topology will render with absolutely
no artifacts ... as long as you don't discard the vertex normals"); averaged normals work better with evenly sized
faces, so use more polygons, clear *Avoid smaller than*, set *Divide larger than* to ~1/10 of the model width.
`CentroidTriangulation=y` "completely fix[ed] the problem" for the user (Aug 2024).
<https://moi3d.com/forum/lmessages.php?webtag=MOI&msg=11521.1>
Users report *Aspect ratio limit* 2 gives tolerable topology but many polygons and still long triangles (search
excerpt of the same thread) **[unverified wording]**.

**Stance on quads.** MoI has "no focus whatsoever ... on making all quad edge flow based model structures"
(Jul 2022). <https://moi3d.com/forum/lmessages.php?webtag=MOI&msg=10747.1> A MoI user: "If it's 'just' a render
mesh, n-gons driven by angle do a perfect job" (Jan 2025).
<https://moi3d.com/forum/lmessages.php?webtag=MOI&msg=11570.69>

---

## 2. Rhino

**Algorithm** (Rhino 8 help, "File Export Mesh Settings"):
<https://docs.mcneel.com/rhino/8/help/en-us/information/polygonmeshsettings.htm>
1. *Initial grid*: a regular rectangular vertex grid on the surface, spacing estimated from the criteria.
2. *Refinement*: quads subdivided until the criteria are met (if *Refine mesh* is on).
3. *Trimming*: the mesh is trimmed along the surface's edges (trimmed surfaces only).
4. *Stitching*: coincident vertices along joined edges are combined (unless *Jagged seams*).

McNeel staff: "The mesher tries to start with quads, but will triangulate in places where necessary"
(Nathan Letwory, 14 Dec 2022). <https://discourse.mcneel.com/t/render-mesh-topology/152082>

**Settings** (same page, and the Mac detailed-options page
<https://docs.mcneel.com/rhino/mac/help/en-us/popup_moreinformation/polygon_mesh_detailed_options.htm>):
- *Density* (0–1), *Maximum angle* (normals at neighbouring vertices), *Maximum aspect ratio* ("approximate
  maximum aspect ratio of the quadrangles"; smaller = "more equilateral and nicely shaped polygons"),
  *Minimum edge length*, *Maximum edge length* ("ensures approximately uniform polygon sizes"),
  *Maximum distance, edge to surface* (midpoint of mesh edge to surface), *Minimum initial grid quads* (per
  surface; keeps flat-ish areas from being too coarse), *Refine mesh*, *Jagged seams*, *Simple planes*
  (planar surfaces: mesh the edges and fill with triangles, as few polygons as possible), *Pack textures*.
- "Rhino does not support watertight quadrangle meshes unless you are meshing a single untrimmed surface. In this
  case, clear Refine mesh and use Jagged seams to generate quadrangle meshes."

**Fillets.** McNeel wiki (mesh FAQ): "Long, skinny surfaces ... are hard for the mesher currently. The longer and
thinner, the harder it is"; typical case: long small-radius fillets. An expert tip: *Maximum aspect ratio* 6.0
"to keep Rhino from meshing long, thin objects with long, skinny triangles".
<https://wiki.mcneel.com/rhino/meshfaqdetails>

**Mesh2 prototype (2017, not shipped).** Jussi Aaltonen's WIP mesher could "mesh multiple objects into compatible
meshes", produced triangles with optional quadrangulation as a post-process; comparing with MoI on a filleted
part he noted the "meshing result seems to depend more on the polysurface than the mesher".
<https://discourse.mcneel.com/t/new-mesher-prototype-in-rhino-wip/47611>

**QuadRemesh (Rhino 7/8)**: remeshes surfaces, solids, meshes or SubD into quads (target count, adaptive size,
hard-edge detection, guide curves, symmetry) — a separate, destructive step, not the render mesh.
<https://www.rhino3d.com/features/quadremesh/>

**Rhino → Blender.** Users describe NURBS exports as "lots and lots of triangles" and use QuadRemesh "to export to
Blender better, since the way mesh works over trimmed surfaces ... doesn't work great sometimes" (search excerpt of
<https://discourse.mcneel.com/t/quad-remesh-issues/105426>) **[wording not verified on the page]**.

---

## 3. Parasolid (Plasticity, Onshape, SolidWorks, Shapr3D, Siemens NX)

**Faceter options** (`PK_TOPOL_facet_mesh_o_t`, Parasolid docs v12 and V35):
<http://www.q-solid.com/Parasolid_Docs/chapters/fd_chap.55.html>,
<http://www.q-solid.com/Parasolid_Docs_V35/chapters/fd_chap.108.html>
- **shape**: convex (default), cut (concave allowed), any (holes allowed).
- **match**: *geometry* (clip facets to a common edge; meshes may leave small triangular gaps), **topology**
  (default: "facets all of the faces of a solid or sheet part as a single mesh ... checks that the boundary
  vertices on a facet mesh always match with vertices on the boundaries of neighboring meshes (possibly splitting
  facets in the neighboring facet mesh in order to meet this condition)"), *trimmed* (clip to edge curves, no
  matching).
- **max_facet_sides** (default 3 — triangles; more sides give planar polygons within *facet_plane_tol*).
- **min_facet_width / max_facet_width** (any side of a facet); curve tolerances **curve_chord_tol,
  curve_chord_max** (maximum chord length on edges), **curve_chord_ang**; surface tolerances
  **surface_plane_tol, surface_plane_ang**; **facet_plane_tol / facet_plane_ang** for >3-sided facets;
  per-face local tolerances; view-dependent density; small-feature ignore; `inflect` (split around inflections);
  `quality` improved; incremental faceting; degeneracy/singularity handling (single vertex or strip-friendly).
- **Algorithm ("Order of constraints")**: "managed first by the initial division of a face into a small number of
  facets. Each facet is then tested ... If the facet does not meet the criteria it is then split into two and
  each resulting facet is again tested ... This process continues until the criteria are satisfied", stopping at
  the minimum width. **This is recursive binary splitting, not a (u, v) grid.** I found no grid/quad mode in the
  Parasolid docs (searched both versions for "grid", "quad") — the brief's "grid-based facetting" for Parasolid is
  **[not confirmed]**. Tabular output can be organised in triangle *strips* (`strip_boundary`, `strip_zigzag`),
  a GPU-friendly ordering, not a structure (V35 ch. 109,
  <http://www.q-solid.com/Parasolid_Docs_V35/chapters/fd_chap.110.html>).

**Plasticity** (Parasolid). Export OBJ options: topology *Tris / Quads / Ngons*; *Density* (the only value that
drives the others); *Min Width* ("prevents tiny polygon clustering in areas like small fillets"); *Max Width*;
*Face/Edge Plane Tolerance*; *Face/Edge Angle Tolerance*; advanced *Curve Max Length*, *Plane Angle ratio*,
*Remove Small Features*, *Inflect*, *Simplify Radial Surfaces*, *Convex Ngons Only*.
<https://doc.plasticity.xyz/plasticity-essentials/export-obj> **[inference]** These are Parasolid's options one
for one (max/min_facet_width, curve_chord_*, surface_plane_*, curve_chord_max, facet_plane_ang, ignore small
features, inflect, shape convex).
Blender Bridge: *Refacet* regenerates the triangulation from the NURBS in Blender with Tri/Ngon, tolerance, angle
and the same advanced widths/tolerances; keeps Plasticity face/edge IDs (select faces/edges, auto mark sharp and
seams). <https://doc.plasticity.xyz/blender/how-to-use>,
<https://doc.plasticity.xyz/blender/introduction-blender-bridge>
Quality: Gibson says Plasticity's n-gon output "will often generate edges that seem to be from an initial
triangular tessellation", with "wonky lines" around holes (Dec 2025, competitor's view).
<http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=11865.65> A MoI user in the fillet thread found Plasticity's
fillet export cleaner than MoI's default (Aug 2024). <https://moi3d.com/forum/lmessages.php?webtag=MOI&msg=11521.1>
Release notes 2025.1–2026.1 (CG Channel) mention no faceting changes; I found no Nick Kallen statement on the
mesher (Discord is not searchable) **[gap]**.

**Onshape** (Parasolid): STL export takes chordal tolerance, angular deviation, minimum facet width; OBJ/glTF/3MF
take distance tolerance, angular tolerance, **maximum chord length**.
<https://cad.onshape.com/help/Content/File/exporting_files.htm>

**SolidWorks** (Parasolid): STL export has *Deviation* (whole-part) and *Angle* (small details) sliders only.
<https://help.solidworks.com/2012/english/solidworks/sldworks/HIDD_STL.htm>

**Shapr3D** (Parasolid): export *Resolution* with custom deviation and angle tolerances.
<https://support.shapr3d.com/hc/en-us/articles/7874524196764-Export> A user complained of over-dense bevel/fillet
tessellation in OBJ; staff: meshes come from a tight-tolerance CAD conversion and "As a CAD software, Shapr3D does
not have many tools to refine or remesh the output. For these purposes please use a mesh editor tool"
(Feb 2022). <https://discourse.shapr3d.com/t/export-quality-bevel-tesselation-obj/17153>

---

## 4. ACIS faceter (Spatial; Autodesk's ASM fork underlies Fusion)

The most explicit published design of a **grid-based trimmed-face mesher**. Sources: ACIS R17 technical article
<http://www.q-solid.com/ACIS_Docs_R17/online/SPAacisuserTechArticles/SPAacisuser_difacetfa.htm> and Faceter R10
manual ch. 1 <http://www-isl.ece.arizona.edu/ACIS-docs/PDF/FCT/01CMP.PDF>.

Phases: *grid spacing determination, edge discretization, face subdivision, triangulation*.
1. A "working edge" per edge takes "the lower of the two values from two adjacent faces" for normal deviation,
   surface tolerance and max edge length; "the edges are discretized to be about the same as the smallest grid
   spacing among connected faces. Thus, it is crucial that the application provide all the faces ... in one step".
2. "a grid in parameter space is laid on each working face". "On planar faces and cylindrical faces, the cells on
   the grid are rectangular in the object space. For spherical, conical, and toroidal faces, the cells are not
   rectangular ... but they are planar. For spline faces ... the grid is laid in an adaptive fashion that puts more
   cells in areas of higher curvature". Iso-lines are equally spaced on analytic surfaces, variably on splines.
   Their number follows normal tolerance, surface tolerance, max facet edge length, max grid lines, min u/v lines.
3. Grid modes: `AF_GRID_NONE`, `AF_GRID_INTERIOR` (grid only inside), `AF_GRID_ONE_DIR`, **`AF_GRID_TO_EDGES`**:
   "the grid intersects the edges and creates facet nodes ... inserting the point list from the working edge into
   the face's uv point set"; "If a facet edge lying on a face's edge is wider than the uv spacing, the facet edges
   are subdivided accordingly"; "the boundary points from the face's uv node set are inserted into the
   corresponding working edge point list"; points from the adjacent faces are checked and inserted too. Without
   it, "faceting will place triangles between the edge and the interior cells".
4. Triangulation: holes get bridge edges, split by the uv grid; "edges are inserted between existing uv nodes on
   opposing edges and are split by the uv grid"; triangulation mode `AF_TRIANG_FRINGE_1/2/…` triangulates only
   the fringe rows next to the boundary (cells stay quads/polygons), `AF_TRIANG_ALL` triangulates the whole grid;
   optional smoothing (`AF_ADJUST_MODE`).
5. **Grid aspect ratio**: "maximum ratio of the long side to the short side of a grid cell in 3D space", default 0
   (ignored); it "does not guarantee that triangles will have a particular aspect ratio" (TurboCAD's ACIS docs,
   <https://turbocaddoc.atlassian.net/wiki/spaces/TC21UG/pages/14320272/ACIS>).
6. Priority when refinements conflict (high to low): max grid lines, max facet edge length, normal tolerance,
   surface tolerance, grid aspect ratio (R10 manual).
- The R10 manual's intro: facets are made "while maintaining edge consistency between adjacent faces ... by
  subdividing the face in parameter space with a grid"; refinements "control ... whether smoothing is used to
  improve the aspect ratios of triangles".

**Fusion** (ASM): *Save as Mesh / 3D Print* refinement = Surface Deviation, Normal Deviation, **Maximum Edge
Length**, **Aspect Ratio** ("ratio between the height and width of each face").
<https://help.autodesk.com/view/fusion360/ENU/?guid=SLD-3D-PRINT> **[inference]** the same four controls as the
ACIS refinement; whether Fusion's display uses grid mode is **[unverified]**.

---

## 5. Open-source and Blender import paths

- **OCCT BRepMesh** (what BlendSolid uses): edges discretized once and shared by adjacent faces; faces meshed by
  Delaunay/sweep-line in 2D parametric space with range splitters for interior nodes and optional deflection
  control; alternative factory Delabella; parameters Deflection/Angle, DeflectionInterior/AngleInterior, MinSize,
  InternalVerticesMode, ControlSurfaceDeflection, AllowQualityDecrease. No structured/grid mode.
  <https://occt3d.com/dev/doc/overview/html/occt_user_guides__mesh.html>
- **FreeCAD** Mesh from shape: meshers Standard (OCCT: surface and angular deviation, relative deviation),
  Mefisto, Netgen, gmsh. <https://wiki.freecad.org/index.php?title=Mesh_MeshFromShape>
- **STEPper NEXT** (Blender, OCCT): triangulation "with smooth normals computed from the analytic shape
  geometry", sharp edges from CAD topology with custom split normals, and "Tris to Quads ... on by default. It
  pairs the tessellation triangles back into quads. No vertex moves and none is added or lost".
  <https://github.com/Peak-Design/STEPper_NEXT>
- **STEP Importer** (extensions.blender.org): presets Draft/Balanced/Fine/Ultra Fine or linear/angular tolerance;
  conversion by Cascadio (STEP → glTF, OCCT-based **[unverified]**), plus a "topology cleanup" operator.
  <https://extensions.blender.org/add-ons/step-importer/>
- **Datasmith (Unreal)**: tessellates CAD surfaces to triangles with import-time settings; re-tessellation per
  mesh later. <https://dev.epicgames.com/documentation/unreal-engine/retessellating-cad-geometry-in-unreal-engine>
  Its CADKernel mesher's algorithm is not documented publicly **[unverified; source needs an Epic account]**.
- Blender users importing CAD meshes fight custom split normals (locked shading) and heavy polycounts:
  <https://blenderartists.org/t/2-8-is-unusable-with-imported-cad-files-1mil-polys-custom-normals/1143103>,
  <https://blenderartists.org/t/maintain-custom-normals-from-cad-file-imported-into-blender/664283>.

## 6. Literature

- Rockwood, Heaton, Davis, *Real-time rendering of trimmed surfaces*, SIGGRAPH 1989 — uniform faceting of trimmed
  surfaces (the classic grid + boundary "coving" approach) **[abstract only]**.
  <https://www.semanticscholar.org/paper/Real-time-rendering-of-trimmed-surfaces-Rockwood-Heaton/aab27824afa6319692d9a8424111d6c3b77dd84a>
- Piegl, Tiller, *Geometry-based triangulation of trimmed NURBS surfaces*, CAD 30(1) 1998: subdivision decided in
  model space, triangulation in parameter space from the subdivision rectangles' vertices **[abstract only]**.
  <https://www.sciencedirect.com/science/article/abs/pii/S001044859700047X>
- Zhou, Zint, Izadyar, Tao, Panozzo, Schneider, *Topology-First B-Rep Meshing*, arXiv 2604.02141 (Apr 2026): edges
  sampled then neighbouring faces made conforming by "inserting any missing vertex"; interiors meshed with MMG in
  the parametric domain with the induced metric, then isotropic remeshing; OCCT failed on 1.56% (ABC) / 8.82%
  (Fusion) of models. Aimed at robustness/isotropy (simulation), not CAD-style display.
  <https://arxiv.org/abs/2604.02141>

---

## 7. Consensus

1. **Structured (u, v) grid vs unstructured.** Rhino, MoI and ACIS start from a grid on the (untrimmed) surface
   and cut it with the trim loops; interior edges follow isoparms, only a boundary band is irregular. Parasolid
   (and so Plasticity, Onshape, SolidWorks, Shapr3D) and OCCT refine/triangulate without a grid, and their
   wireframes look it (Gibson on Plasticity; Shapr3D staff sending users to mesh editors). For a user judging a
   wireframe, the grid family is the reference.
2. **Anisotropy control is universal.** Every product exposes a size cap and/or an aspect cap: Rhino max edge
   length + max aspect ratio, MoI divide larger than + aspect ratio limit, ACIS max edge length + grid aspect
   ratio, Fusion max edge length + aspect ratio, Parasolid max_facet_width + curve_chord_max, Onshape max chord
   length, Plasticity max width. Mostly off by default; the documented fix for long fillets is an aspect cap
   (Rhino ~6, MoI 2).
3. **Conformity** is handled at the edges, not by matching grids: grids of neighbouring faces can't line up
   across a trimmed edge (Gibson). ACIS makes both faces share one edge discretization no coarser than the
   smallest neighbouring grid spacing, and inserts each face's grid-edge crossings into it; Parasolid topology
   matching splits facets on the neighbour so vertices match; Rhino stitches coincident vertices (jagged seams
   off); OCCT shares edge polygons. Different node counts on opposite sides of a face are absorbed by the boundary
   band (ACIS fringe rows, MoI n-gons, Rhino's triangles near trims), not by fans across the whole face.
4. **Normals.** Gibson's point: with exact vertex normals, triangle shape doesn't show in shading. (BlendSolid
   already does this, ADR 0005 §3; but Bevel/Subdivision/Solidify rebuild geometry, so shape still matters.)
5. **Triangles are the norm for CAD display**; quads appear only on untrimmed surfaces (Rhino: watertight quads
   only for a single untrimmed surface) or as n-gons (MoI).

---

## What this means for BlendSolid (ranked by fit)

Goal: clean, regular, conforming **triangle** meshes of trimmed faces, like MoI's triangle output or Rhino's
render mesh.

1. **Grid-to-edges tessellation of trimmed curved faces (ACIS `AF_GRID_TO_EDGES` + fringe triangulation;
   Rhino/MoI "grid then trim").** For each curved face: iso-lines in (u, v) of the face's surface, spacing from
   the tolerance (sag/angle) per direction, capped by a max edge length and a **grid aspect ratio** in 3D (a
   straight generatrix gets rows only because of the cap). Cells fully inside: two triangles on a consistent
   diagonal. Cells cut by the trim loop: clip the cell in (u, v) to the loop (MoI's n-gons), then triangulate each
   piece (ear-clip, or centroid fan like MoI's `CentroidTriangulation` for squat triangles), merging slivers
   smaller than a fraction of a cell into their neighbour (MoI's *avoid smaller than* role). Every interior edge
   is an isoparm and only the band at the trim is irregular — what a Blender user reads as "clean". It
   generalises the full-face grids of ADR 0005 and replaces the Delaunay lattice of the addendum. Fixes the
   fillet torus mosaic and the narrow fillet strips (the strip becomes rows along the fillet, one column band
   across).
2. **Shared, refined edge discretization before face meshing (ACIS working edges; Parasolid topology
   matching).** Discretize each edge once with the finer of its two faces' requirements: tolerance, max edge
   length, and the grid spacing of each adjacent face along it; optionally insert each face's grid-line crossings
   into the edge (full `AF_GRID_TO_EDGES`) so the boundary band has one node per grid line. This is the addendum's
   open item ("30 mm boundary chords against a 6 mm lattice") and the quarter-cylinder case: the cylinder's
   bottom edge gets nodes at the grid spacing, not two. Conformity with neighbours stays by construction (one
   polyline per edge, as BRepMesh does today).
3. **An aspect / max-edge-length cap on every face (Rhino *Maximum aspect ratio* 6, MoI *Aspect ratio limit*,
   Fusion *Aspect Ratio*).** Even a planar face or a cylinder with a straight generatrix gets extra rows when a
   cell would exceed the cap. Keep it internal first (e.g. 4:1 as in the addendum's lattice, or relative to the
   part size); expose it later only if needed. Weigh against ADR 0008 (flat faces stay one polygon/convex
   polygons for Bevel clamp): apply the cap to curved faces, not to flat ones — Rhino's *Simple planes* and MoI's
   single n-gon cap do the same.
4. **Boundary-band quality rules (ACIS fringe rows, MoI n-gon triangulation).** Triangulate only the band between
   trim polyline and the first full grid row; forbid fans by requiring each boundary node to connect to the
   nearest grid nodes (ACIS: "edges are inserted between existing uv nodes on opposing edges and are split by the
   uv grid"). Measurable: minimum angle and max aspect in the band, as the existing tests already do.
5. **Keep exact normals and the fallback.** Exact normals (ADR 0005 §3) remain; keep BRepMesh as fallback when
   clipping fails (degenerate pcurves, seams), as the addendum does now.
6. **Parasolid-style recursive splitting** (split the worst facet in two until criteria hold) is the other
   industry design, cheap to add on top of any triangulation, but it produces the "initial triangular
   tessellation" look Gibson criticises; use only as a refinement pass, not as the base.
7. **Topology-first/isotropic remeshing (arXiv 2604.02141, MMG)**: robust, uniform, but isotropic triangles with
   no isoparm structure — the opposite of the CAD look. Not a fit for display.

**For the future "convert to quads" button (brief):** a grid-based mesh (1) pairs back into quads trivially
inside the grid (STEPper's pairing works on any triangulation; MoI's *Quads & Triangles* output is exactly
grid quads + triangulated trim band); only untrimmed faces give watertight all-quad meshes (Rhino docs, Gibson);
full edge-loop quad topology needs remeshing (Rhino QuadRemesh) or a SubD rebuild — MoI explicitly declines it.
