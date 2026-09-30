# Research: OCCT fillet problems — what changed upstream, what the literature offers

Date: 2026-09-30. Context: the maintainer asked (morning session, no coding) for known OCCT fillet problems and how
to address them, including the scientific literature. **This note extends
`docs/research/2026-09-28-fillet-edge-cases.md`** (OCCT's documentation and diagnostic API, how
`ChFi3d_Builder::Compute` fails, open issues, measurements on OCP 8.0.1, mitigations, recommendations) and does
not repeat it. New here: upstream fixes after OCCT 8.0.1, the literature behind each failure class, and another
open-source kernel's work on the same problems.

Legend: **[verified]** = read in the cited source (OCCT commit messages read from a clone of its history);
**[title/abstract]** = only the title or abstract could be read; **[unverified]** = not checked.

---

## 1. Upstream OCCT: fixes after 8.0.1

BlendSolid runs `cadquery-ocp-novtk` 8.0.1. OCCT 8.0.1 was tagged 2026-07-30 (`V8_0_1`). Commits on OCCT's
default branch touching fillets and chamfers, and whether 8.0.1 contains them [verified, `git log` on
<https://github.com/Open-Cascade-SAS/OCCT>, history since 2024-06]:

| Date | Commit | In 8.0.1? | What the message says |
| --- | --- | --- | --- |
| 2026-08-09 | **Enhance fillet and chamfer handling, Part 2 (#1449)** | **no** | detect complete coincidence between fillet and chamfer intersection curves; reuse existing restriction edges instead of duplicating topology; merge coincident curve endpoints into shared vertices; **"Exclude fully consumed faces and their obsolete boundary edges during reconstruction"**; mark edges collapsed to a point as degenerated; accept tangential contacts, reject transversal ones; preserve generated/modified history; GTests for "convex, concave, **opposing-edge**, chamfer, and history cases" (27 files, +1523 lines) |
| 2026-08-09 | Enhance fillet and chamfer handling, Part 1 (#1293) | no | retain coincident segments only when no regular hatching domain exists; tests for limiting and partial boundary overlaps |
| 2026-08-23 | Remove obsolete ChFi3d debug instrumentation (#1490) | no | cleanup |
| 2026-07-29 | Prevent crashes in `ChFi3d_Builder::StartSol` (#1407) | yes | an oversized or invalid chamfer ends with `IsDone() == false` instead of crashing |
| 2026-07-29 | Fillet solid reconstruction reentrant across threads (#1374) | yes | the fillet rebuilds its solid through the legacy `TopOpeBRepBuild` engine with file-scope statics: concurrent fillets gave "wrong-but-plausible" solids failing BRepCheck (~15–20% in a stress test); now `thread_local` |
| 2026-04-04 | Fix segfault in `IntersectMoreCorner` (#1163) | yes | (issue #1163 in the 2026-09-28 note) |
| 2025-11-27 | `MakeFillet::Add` hangs on adding edge (#859) | yes | (hang class, #847 in the 2026-09-28 note) |
| 2025-12-07, 2025-10 | periodic curves in ChFi3d (#892); chamfer crash (#743); ellipse segfault (#738) | yes | |

What it means for BlendSolid:
- **#1449 aims at the class the 2026-09-28 note left "out of OCCT's reach"**: fillets that consume a face or meet
  across it (issues #172, #1177; our cases 06/07/10/34/49). Whether it fixes exactly those cases is
  [unverified]: the commit doesn't cite the issues. It is **not in 8.0.1**, so it reaches us only with the next
  OCCT release and an OCP wheel built on it.
- #1374 matters only if the worker ever runs fillets on several threads (it doesn't today): keep one fillet at a
  time per process until OCP ≥ a build with #1374 is confirmed.
- Consequence for the planned fillet benchmark: **it must be re-runnable per OCCT/OCP version**, so an upgrade is
  judged by numbers (same corpus, failure rate before/after), not by release notes.

## 2. The literature behind each failure class

OCCT's `ChFi3d` is a *rolling-ball, marching* ("walking") algorithm: it traces the ball's contact curves along the
edge, fits the blend surface, then fills corners and rebuilds the solid. Each failure class of the 2026-09-28 note
has its own literature.

### 2.1 The rolling ball and its walking (StartsolFailure, WalkingFailure, twisted surfaces)
- Rossignac & Requicha, *Constant-radius blending in solid modelling* (1984): blends of solids as the result of
  rolling a ball (offset-based definition). [title/abstract]
  <https://www.semanticscholar.org/paper/CONSTANT-RADIUS-BLENDING-IN-SOLID-MODELLING-Rossignac-Requicha/553014d71e15e44f3585377bc9fd017d4f823b3d>
- Choi & Ju, *Constant-radius blending in surface modelling*, CAD 21(4), 1989: the marching method for the
  rolling-ball blend — the family `ChFi3d`'s walking belongs to. [title/abstract]
  <https://www.sciencedirect.com/science/article/abs/pii/0010448589900468>
- Vida, Martin & Várady, *A survey of blending methods that use parametric surfaces*, CAD 26(5), 1994: the
  standard taxonomy (rolling ball, variable radius, cross-sections, trimlines) and open problems. [title only;
  full text not in the repository that indexes it] <https://eprints.sztaki.hu/682/>

Practical reading: walking fails where the ball can't start (radius larger than the room on a face →
`StartsolFailure`) or loses contact (a face ends, curvature radius below the ball's → `WalkingFailure`,
`TwistedSurface`). The 2026-09-28 note's **geometric bound before calling OCCT** is the classic answer: for planar
and cylindrical neighbours the room is known in closed form.

### 2.2 Blends that run off their faces: non-local blending (fillets that meet, consumed faces, overflow)
- Braid, *Non-local blending of boundary models*, CAD 29(2), 1997 (Braid co-created the ROMULUS/Parasolid/ACIS
  lineage): blends whose extent crosses beyond the two faces they join, consuming or overflowing neighbours —
  the #172/#1177 class. [title/abstract] <https://www.sciencedirect.com/science/article/abs/pii/S0010448596000383>
- Commercial kernels expose it as options: Onshape's **Allow edge overflow** (research of 2026-09-30 on the Fillet
  tool) and SOLIDWORKS' overflow types. OCCT has no such option; #1449 (above) is its first step.
- *Topological considerations in joining and terminating blends* (Springer, 2025): **not read** — the publisher
  page refused the request (rate limit). <https://link.springer.com/chapter/10.1007/978-981-96-6235-7_15>

### 2.3 Corners: vertex blends (NbFaultyVertices, holes in the result, curvature spikes)
- Várady & Rockwood, *Geometric construction for setback vertex blending*, CAD 29(6), 1997: edge blends are
  widened ("set back") at a distance from the vertex and the corner is a **2n-sided patch**, built from a control
  frame obtained by repeated chamfering, G1 to its neighbours. [title/abstract]
  <https://www.sciencedirect.com/science/article/abs/pii/S001044859600070X>
- Várady et al., *Setback vertex blends in digital shape reconstruction* (2009). [title only]
  <https://link.springer.com/chapter/10.1007/978-3-642-03596-8_21>
- OCCT fills corners with `GeomFill` patches (guide §2.5.4); the 2026-09-28 measurements found curvature spikes
  (radius 0.07 mm) there. Setback vertex blends are what commercial kernels offer as "setback" corner options,
  and the multi-sided patch work already in the spec (Salvi–Várady transfinite surfaces, milestone 5) is the
  modern form of the same construction.

### 2.4 Smoother blends (G2) — for milestones 5–6, not for robustness
- *Analytical C2 continuous surface blending*, Mathematics 12(19), 2024. [title only]
  <https://www.mdpi.com/2227-7390/12/19/3096>
- Variable-radius blending of parametric surfaces (The Visual Computer). [title only]
  <https://link.springer.com/content/pdf/10.1007/BF02434038.pdf>

## 3. Another open-source kernel working on the same problems: brepkit

- **brepkit** (Rust, compiled to WebAssembly; engine of brepjs): "Walking-based fillet and chamfer with constant,
  variable, and custom radius laws" (`brepkit-blend`), marked Stable; benchmarks with every row
  "output-verified before timing" (fillet volume agreement 0.004% against closed form or another kernel).
  **License: AGPL-3.0-only or commercial.** [verified, README]
  <https://github.com/andymai/brepkit>
- Its PR #1679 (2026) fixed 15 corner defects: adjoining equal-radius fillets rebuilt with a **G1-constrained
  rational setback patch**; mixed radii at a corner by generalising that patch (equal radii as the correctness
  oracle); sharp mitred corners from the exact crease ellipse; **dedicated exact constructions at the limits
  r = S (two edges) and r = S/2 (four edges)** — exactly the "fillets meet across the face" limit. [verified, PR
  page] <https://github.com/andymai/brepkit/pull/1679>
- Use for BlendSolid: a **reference to read** (algorithms, test cases, limit cases) — AGPL code can't be copied
  into a GPL-3.0 add-on without taking on AGPL terms for it, so ideas and test cases only. Also a kernel to watch
  alongside Fornjot and Truck.

## 4. Adjacent: meshing B-reps robustly

- Zhou, Zint, Izadyar, Tao, Panozzo, Schneider, *Topology-first B-rep meshing* (arXiv 2604.02141): keeps the B-rep
  topology as an invariant (curves sampled and snapped to vertices, loops embedded by 3D tracing instead of 2D
  trimming curves, patches stitched along shared edges, topology-preserving remeshing); meshed 10,000+ ABC and
  Fusion 360 models, better than OCCT's mesher, Gmsh, NetGen and Mefisto. [abstract read]
  <https://arxiv.org/abs/2604.02141> — relevant to ADR 0010's display tessellation more than to fillets.

## 5. How this maps onto the options discussed with the maintainer

From cheapest to hardest (levels as in the morning conversation):

1. **Upgrade OCCT** when a release with #1293/#1449 is out and OCP publishes wheels on it; judge it with the
   fillet benchmark (before/after on the same corpus). Cost: packaging. Watch: OCCT releases, OCP wheels.
2. **Above OCCT, in Python** (the 2026-09-28 recommendations, still valid): classify edges before `Add`,
   closed-form radius bounds, per-contour isolation, the diagnostic API to locate failures, validation of "done"
   results, time budget. These turn most failures into clear messages and some into successes.
3. **Own corner patches**: replace OCCT's corner fill with setback vertex blends / multi-sided patches
   (Várady–Rockwood; Salvi–Várady transfinite; brepkit's rational setback patch as a worked example), sewn into
   the solid. This is where the curvature spikes and many `NbFaultyVertices` failures live.
4. **Non-local blending** (consumed faces, fillets that meet): first see what #1449 solves; for straight edges
   between planes the prism-boolean construction (noBS-CAD, 2026-09-28 note) remains a fallback.
5. **Upstream contributions**: each failure the benchmark isolates, reduced to a minimal case, becomes an OCCT
   issue or a test for a fix — OCCT now takes pull requests on GitHub and the 2026 fixes above show the fillet
   code is being worked on.

**Next step proposed:** the fillet benchmark (corpus, classification by the failure classes above, per-version
re-runs), designed here and run with Claude Code.
