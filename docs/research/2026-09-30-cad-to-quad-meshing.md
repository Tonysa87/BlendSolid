# Research: from a CAD solid to a quad (and triangle) mesh

Date: 2026-09-30 (evening). Context: the spec's "Blender output" row (v2: quad mesh for simple faces; R&D: quads on
trimmed faces) and the maintainer's "Convert to quads" idea (`docs/NEXT.md`). The 2026-09-28 notes
(`cad-display-tessellation-products.md`, `trimmed-face-tessellation-algorithms.md`) cover how CAD products
tessellate for display and list Gmsh's quad options; this note covers the **quad** side: technique families, the
literature, what each gives, and what fits BlendSolid.

Legend: **[verified]** = read (abstract, README or licence file); **[title]** = title/venue only;
**[unverified]** = general knowledge not checked here.

---

## 1. Why quads are hard on CAD solids

A B-rep face is a patch of a surface (u, v) **trimmed** by curves; a solid is many faces meeting along edges. A
triangle mesh can follow any trim; a quad mesh wants **4-sided regions and edge loops that run across faces**. CAD
faces rarely are 4-sided (a plate with holes, a face cut by a boss), and CAD topology says nothing about loops.
So every technique trades three things: **exactness** (vertices on the true surface, edges on the true edges),
**quad purity** (all-quad vs quad-dominant), and **edge flow** (few irregular vertices, loops along features).

## 2. Four families

### A. Per-face (u, v) grids — what CAD products do for display
- Quads where the face is untrimmed, n-gons or triangles along trims; exact vertices; not conforming across faces
  unless the edges are discretized once and shared (BlendSolid does this, ADR 0010). MoI: "quads in untrimmed
  areas … n-gons formed at trims"; Rhino: watertight quads only for a single untrimmed surface; Plasticity's OBJ
  export offers Tris / Quads / Ngons. [verified in the 2026-09-28 note]
- Gives: exact, fast, **quad-dominant, no edge flow across faces**. Fine for rendering and Bevel-by-weight; poor for
  SubD, deformation, sculpting.

### B. Triangles → quads by pairing (recombination)
- Pair adjacent triangles into quads, choosing the pairing that makes the best quads: **Blossom-Quad** (Remacle et
  al., IJNME 2012) solves it as a minimum-cost perfect matching; a midpoint subdivision then makes the mesh
  all-quad. In Gmsh as `Mesh.RecombinationAlgorithm` (blossom / blossom full-quad). [title; Gmsh option verified in
  the 2026-09-28 note] <https://onlinelibrary.wiley.com/doi/abs/10.1002/nme.3279>
- More recent: *Quadrilateral surface mesh generation with improved quality by combination of triangles* (IJNME
  2024). [title] <https://onlinelibrary.wiley.com/doi/10.1002/nme.7539>
- Gives: keeps the triangle mesh's vertices (exact), quads everywhere or almost, **edge flow inherited from the
  triangulation** — on a grid-based tessellation that is decent inside faces, irregular at trims. Fast, local.

### C. Field-aligned remeshing (the "retopology" family)
A **cross field** (4 directions per point) is computed to follow curvature and sharp features; the surface is
parametrized or traced along it; the result is quantized to integers so that quads come out. Singularities of the
field become the irregular vertices.
- **Instant Meshes** (Jakob, Tarini, Panozzo, Sorkine-Hornung, SIGGRAPH Asia 2015): local, very fast, quad-dominant.
  Licence: BSD-style. [verified licence] <https://github.com/wjakob/instant-meshes>
- **QuadriFlow** (Huang et al., 2018): scalable, few singularities; it is Blender's *Quad remesh*. Licence: BSD-style.
  [verified licence] <https://github.com/hjwdzh/QuadriFlow>
- **QuadWild** (Pietroni et al., *Reliable feature-line driven quad-remeshing*, SIGGRAPH 2021): feature lines
  (sharp edges) drive a patch layout, then patches are quadrangulated; robust on CAD-like models. Licence GPL-3.0.
  [verified licence] <https://dl.acm.org/doi/10.1145/3450626.3459941>, <https://github.com/nicopietroni/quadwild>
- **Bi-MDF** (Heistermann et al., *Min-Deviation-Flow in Bi-directed Graphs for T-Mesh Quantization*, SIGGRAPH
  2023): a better quantization step for QuadWild; `quadwild-bimdf` is GPL-3.0. [verified licence]
  <https://dl.acm.org/doi/abs/10.1145/3592437>, <https://github.com/cgg-bern/quadwild-bimdf>
- **Gmsh quasi-structured quad meshing** (Reberol, Georgiadis, Remacle, 2021) — **the one written for CAD
  models**: quad-dominant mesh by frontal insertion guided by a cross field and a size map; all-quad by
  combination + midpoint subdivision; irregular vertices kept only where the cross field has singularities,
  others removed by local disk quadrangulations or patch remeshing with predefined patterns; validity guaranteed by
  monitoring element quality; "strict respect of the CAD features" and user size constraints; in Gmsh. [verified,
  abstract] <https://arxiv.org/abs/2103.04652>
- Neural cross fields: **NeurCross** (Dong et al., SIGGRAPH 2025), licence **AGPL-3.0** [verified licence]
  <https://dl.acm.org/doi/10.1145/3731159>; **CrossGen** (2025): cross fields "in milliseconds", within a second,
  comparable to NeurCross, from point samples of any surface, CAD included [verified, abstract]
  <https://arxiv.org/html/2506.07020>.
- Products: Rhino **QuadRemesh** (surfaces, solids, meshes or SubD in; target count, hard-edge detection, adaptive
  size, symmetry, guide curves; quad mesh or SubD out) [verified] <https://www.rhino3d.com/features/quadremesh/>;
  Blender add-on **QRemeshify** wraps QuadWild + Bi-MDF (GPL-3.0; triangulated input; detect sharp; symmetry)
  [verified README] <https://github.com/ksami/QRemeshify>.
- Gives: **clean edge flow, few irregular vertices, loops around fillets and holes**; vertices are re-sampled, so the
  mesh **approximates** the solid (small deviation, controlled by density); slower (seconds to minutes); can fail on
  thin or complex parts. Best for SubD, animation, sculpting, UVs.

### D. Coarse quad layouts (patches) — towards SubD cages
- Partition the surface into a few big quadrilateral patches, then grid each patch: Campen, *Partitioning surfaces
  into quadrilateral patches: a survey* (CGF 2017) [title] <https://onlinelibrary.wiley.com/doi/10.1111/cgf.13153>;
  *Quad layouts via constrained T-mesh quantization* (Lyon et al., CGF 2021) [title]
  <https://onlinelibrary.wiley.com/doi/abs/10.1111/cgf.142634>; *Robust motorcycle graph construction and
  simplification for semi-structured quad mesh generation* (Computers & Graphics 2025) [title]
  <https://www.sciencedirect.com/science/article/abs/pii/S0097849325000123>; **SQuadGen** (Kong et al., arXiv
  2026-04): diffusion model trained on 230,000+ simple quad layouts, "artist-friendly" layouts from any shape
  [verified, abstract] <https://arxiv.org/html/2604.27329>.
- Gives: the coarse cage a modeller would draw — the natural input for **SubD** and the reverse of milestone 4
  (SubD → NURBS).

### Triangles, for completeness
- Robust triangle meshes of whole B-reps: *Topology-first B-rep meshing* (Zhou et al., arXiv 2604.02141): 10,000+
  ABC/Fusion 360 models, better than OCCT, Gmsh, NetGen [verified abstract; see
  `2026-09-30-occt-fillets-upstream-and-literature.md` §4]. BlendSolid's own edge-first grids (ADR 0010) already give
  clean, conforming triangles for display.

## 3. What each gives (expected results)

| Family | Quads | Exact on the solid | Edge flow | Speed | Good for |
| --- | --- | --- | --- | --- | --- |
| A per-face grids | dominant (n-gons/tris at trims) | yes | none across faces | instant | display, render, Bevel by weight |
| B pairing | dominant or all (subdivided) | yes | inherited, messy at trims | fast | "more quads" cheaply |
| C field-aligned | all or nearly | approximate (density-bound) | good | seconds–minutes | SubD, deform, sculpt, UVs |
| D coarse layout | all | approximate | best (few, big patches) | slow / research | SubD cages, round trip |

## 4. What a CAD kernel knows that a mesh remesher doesn't

BlendSolid has the B-rep, not just triangles — each face has its **type and role** (ADR 0009: planes, cylinders,
`blend` fillet faces, feature names). That allows a hybrid a pure remesher can't do:
- **Fillet bands and cylinders are natural quad strips**: a rolling-ball fillet is parametrized along the edge and
  across the arc; a cylinder along its axis and around it. Structured quads there, exact, with loops that follow the
  fillet — exactly where a modeller wants loops.
- **4-sided faces** (most fillet faces, many side walls): structured grid, matching counts on shared edges.
- **Trimmed planar faces with holes** (the hard case): collars of quads around holes already exist in the display
  mesh (ADR 0008 addendum); the rest needs a field-aligned fill (C) or patterns (Gmsh's disk quadrangulations).
- **Sharp BRep edges** are the feature lines C needs: pass them to QuadWild/Gmsh instead of detecting them by angle.

## 5. Options for BlendSolid's "Convert to quads" (by cost)

1. **Pair the current display triangles** (family B) — the grid-based tessellation pairs back into quads inside
   faces; hours of work; result "mostly quads", exact, messy at trims.
2. **Structured faces first** (A done properly): fillet bands, cylinders and 4-sided faces meshed as grids with
   matching edge counts (a small integer problem on shared edges), triangles/n-gons elsewhere.
3. **Field-aligned with CAD features** (C): feed the display mesh plus the BRep sharp edges to QuadWild-BiMDF
   (GPL-3.0, compatible) or Gmsh's quasi-structured algorithm (Gmsh is GPL-2.0-or-later [unverified here]); an
   approximate but clean quad mesh, as a **copy** (the part stays exact). The maintainer's own QuiltMesher project
   (quad remeshing on QuadWild-BiMDF and NeurCross, aimed at Blender) is the natural engine to reuse — note
   NeurCross is AGPL-3.0.
4. **Hybrid** (4 + 3): structured quads on fillets/cylinders/4-sided faces, field-aligned only on the remaining
   faces, stitched on shared edges. The research-grade version; the one that uses what a CAD kernel knows.
5. **Coarse layout → SubD cage** (D): the reverse of milestone 4; R&D.

Measures for any of them: share of quads, irregular vertex count, minimum scaled Jacobian / angle, Hausdorff distance
to the exact solid (the worker can compute it), time, and whether Blender's Subdivision modifier on the result stays
close to the solid.

## 6. Maintainer's decision (2026-09-30, evening)

**Start with the classic methods, as Rhino and Plasticity do (families A and B); evaluate the others (C field-aligned,
D coarse layouts, external engines) afterwards.** Concretely, what "classic" means here:

- **A topology choice like Plasticity's export (*Tris / Quads / Ngons*)**: the same exact vertices, three ways of
  grouping them. *Quads*: grid cells stay quads (fillet bands, cylinders, untrimmed and 4-sided faces), the trim
  band next to trim curves is paired into quads where the pair is good and left as triangles elsewhere (family B,
  e.g. Blossom-style matching or a greedy best-pair pass). *Ngons*: flat faces as one polygon or a few convex ones
  (what the display mesh already does for Bevel, ADR 0008). *Tris*: everything triangulated.
- **Rhino's rules as the reference for quality**: watertight quads come only from untrimmed faces; the refinement
  keeps quads where it can ("the mesher tries to start with quads, but will triangulate in places where
  necessary"); an aspect-ratio limit splits long thin cells (see the 2026-09-28 products note).
- Exactness kept: no vertex moves, no vertex added (the pairing only removes diagonals), shared edge discretization
  unchanged (ADR 0010), so the result stays conforming and the BRep ids and sharp/bevel-weight flags still apply.

To settle when planned (Claude Code, with the maintainer): whether the topology is a **display setting** of the
part (the Blender mesh itself is Tris/Quads/Ngons) or an **export/convert command** producing a copy; how it
interacts with the Catmull–Clark rule of ADR 0008's addendum (`docs/NEXT.md`: reconsider it once convert-to-quads
exists); the measures of section 5 (share of quads, worst angles, time) on the test parts. Scheduled in the spec at
3e ("convert to quads") unless the maintainer moves it.
