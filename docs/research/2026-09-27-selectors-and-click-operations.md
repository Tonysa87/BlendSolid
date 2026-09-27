# Selectors from clicks: first consumer operations and persistent naming of faces and edges

- **Date:** 2026-09-27
- **Question (for milestone 2 design):** from how comparable software does it, (a) which operations should be the
  first consumers of clicked faces/edges, and (b) how should BlendSolid name/reference faces and edges persistently,
  given that the history is a *readable* build123d script (a reference must be a line of Python a user can read).
- **Builds on:** `docs/research/2026-09-26-modeling-workflows.md` (tool list, push/pull stages, provenance idea).
  That document is not repeated here; it already covers Press Pull, Instant3D, Shapr3D's history and Plasticity's
  selection-implies-command model at the level of *creation*. This one is about *references*.
- **Spec criterion (M2):** "Starts with face/edge → feature provenance from the worker. 95% of the edges **and
  faces** clicked on a set of 20 parts produce a unique selector that survives 3 upstream changes."
- **Method:** web research on official manuals, help centres, API docs, forum answers by vendor staff, papers; plus
  a read of the vendored build123d 0.13.0 (`.dev/worker_libs/build123d`). Pages that blocked automated fetches
  (Autodesk University, SOLIDWORKS help, Shapr3D help, ScienceDirect) are summarized from search-engine snippets
  and marked **[snippet]**. My own inferences are marked **[inference]**; anything I could not confirm is marked
  **[unverified]**. All sources accessed 2026-09-27 unless a date is given.

---

## 0. Summary

**First consumers (in order):**

1. **Fillet / chamfer on clicked edges** (Ctrl+B, radius drag). Every reference tool makes it the default edge
   action (Plasticity runs Fillet as soon as edges are selected), all of them propagate along tangent edges by
   default, and all accept *faces* (→ their edges) and *features* (→ all their edges) as well as edges. It is also
   the hardest reference case: Fusion notes a fillet consumes the edge, so a lost edge cannot be recovered from a
   cache. It exercises edge selectors, face selectors (face → its edges) and chains in one tool.
2. **Push/pull a clicked face**: first the M1.5-style "edit the owning feature's parameter" (provenance only, no
   selector), then "new extrude/offset from this face" (face selector). Onshape's Move Face (offset / translate /
   rotate) is the direct-editing reference.
3. **Re-attach Draw Solid to the clicked face** (the M1.5 placement becomes face-relative). This is the most
   TNP-prone reference in every tool (FreeCAD's own docs tell users not to sketch on solid faces), so it should come
   *after* fillet and push/pull have proven the face selectors, and stay opt-in until it does.
4. **Shell with clicked faces removed** is a cheap fourth (faces only, one OCCT call); draft and move-face
   translate/rotate are v2.

**Naming strategy: "select on the feature, map forward by history, disambiguate by geometry, verify by count".**

- **Layer 0 — no selector:** a click on a feature's cap edits that feature's parameter (provenance only).
- **Layer 1 — feature-scoped, role-based selectors.** A face is named by the feature that made it and its role on
  that feature (the Onshape `qCreatedBy`/cap/swept model, Kripac's face-based naming, Bidarra's feature-based
  naming), written as readable Python: `face(boss_1, "top")`. The worker maps the feature's own face forward to the
  current part through OCCT history (`BRepTools_History`, which build123d 0.13 already wraps as `ShapeHistory`).
- **Edges are named through faces:** `edge_between(face(boss_1, "side"), face(box_1, "top"))`, the same idea as
  KCL's `getCommonEdge` and Fusion's "Rule Fillet → Between Faces/Features". Every manifold edge bounds two faces, so
  edge naming reduces to face naming plus a tie-break when two faces share several edges.
- **Layer 2 — geometric disambiguation** only inside the (small) provenance set: `filter_by(GeomType…)`,
  `sort_by(Axis.Z)[-1]`, `sort_by_distance(point)`; never bare list indices (the build123d tutorial's own warning;
  Zoo's `edgeId(index=…)` is the counter-example).
- **Layer 3 — fallback for geometry with no provenance** (STEP imports): a whole-part build123d selector chain, and
  as the last resort `nearest(point)`, which is always unique and always readable but follows no design intent.
- **Detection:** every reference states its expected count; 0 matches or a different count is a broken reference.
  A geometric signature of the last good match (type, radius/length, centroid, normal) is kept *outside* the script
  and compared after each recompute to catch silent re-binding.
- **Presentation:** Fusion's warning/error split (partial loss = warning, the feature still computes; total loss =
  error), Onshape's "last healthy state" side view, SolidWorks' "Missing" list plus "Repair All Missing References",
  FreeCAD 1.0's automatic repair only when confident. In Blender: keep the last good mesh, mark the feature in the
  panel, draw the lost entities as a ghost overlay, and offer *Reselect* and *Accept suggested repair*.
- **Use history as oracle and repair engine, not as the stored name.** Onshape's robust queries are unreadable by
  design (staff: UI queries are "pretty complicated" because of robustness tricks); BlendSolid chooses readability,
  so it compensates with detection plus history-driven repair, and uses full-history tracking as the ground truth in
  the M2 regression tests.

---

## 1. Click-driven operations and selection UX

### 1.1 Plasticity (main UX reference)

- **Selection implies the command.** From the previous research: "When one or more Edges are selected, the default
  command, Fillet, is automatically executed"; a selected face runs Push Face; a region runs Extrude.
- **Fillet Shell options** (manual): positive distance = fillet, negative = chamfer; shapes Conic, Chordal, G2,
  Full; Y-blend "Attempt"; **"Add tangent Edges" toggle (T)** "to limit fillets to selected edges only"; **Ctrl adds or
  removes edges** from the selection while the command runs; V variable point, L limit point (up to two).
- **Selection tools** (manual, *Selecting Objects*): **Alt+click** is contextual — "edge loops, … related faces";
  **Ctrl+Alt+click** selects "edge rings, parallel faces, or parallel cylindrical faces"; Ctrl+Shift+= selects
  adjacent; Ctrl+1…5 converts the selection between points/edges/faces/solids/groups; **Ctrl+T "selects source
  objects from the previous operation"** (a history-aware selection in a history-less tool).
- **No parametric history**, so no persistent naming at all: references live only for the running command.
- **Lesson:** the Blender-adjacent audience expects edge-click → fillet, Alt+click loops (also Blender's own Edit
  Mode convention), tangent propagation on by default with a one-key toggle, and adding/removing edges during the
  command.

### 1.2 Autodesk Fusion

- **Fillet accepts "edges, faces, or features"**; Ctrl/Cmd modifies the selection after changing values.
- **Tangent Chain** is a checkbox, "checked by default", "so that … the selection set automatically includes
  tangentially connected edges" ([snippet] of the Tangent chain reference).
- **Rule Fillet:** "All Edges" (all edges of selected faces or features) or "Between Faces/Features" (edges where two
  selection sets meet), with topology filters Rounds and Fillets / Rounds Only / Fillets Only. This is a *semantic*
  edge selection, recorded as the rule, not as the resulting edge list.
- **Press Pull** switches by selection (profile → extrude, edge → fillet, face → offset face); its *Automatic / Edit
  Feature* modes edit the feature that made the face (previous research, [snippet]).
- **References and failure states** ([snippet] of Strater & Eichmiller, *Debugging your Fusion 360 design*, AU 2021,
  and Autodesk's *Resolving timeline warning or errors* article): "A failure in a Geometry reference will result in
  a Warning, while a failure in a Topology reference will result in an Error." A geometry reference "automatically
  caches the geometry on each successful compute", so a matching failure can fall back to the cache; Fusion "cannot
  cache a Topology reference, and you need the edge itself to compute a Fillet". But a fillet whose references only
  *partly* fail still computes the matched edges and reports a **Warning**. Repair: right-click the timeline feature →
  *Review Warning*, reselect; *Compute All* (Ctrl+B) before saving reveals latent errors.
- **API entity tokens** (`entityToken` / `Design.findEntityByToken`): the token string for an entity may differ over
  time but resolves to the same entity; after a split "it will match to both (or more) split pieces" ([snippet] of
  the API help and forum). So Fusion's persistent names bind to *all* descendants on a split.
- Practitioners on Hacker News (2026, thread on FreeCAD's TNP page) credit commercial tools with "a mapping
  algorithm that remaps the new features to the old features after a topological restructure using a combination
  of topological id systems and heuristics"; one says Fusion's heuristics are good enough that they "rarely run into
  these problems" (anecdotal).

### 1.3 Onshape

- **Fillet accepts "edges or faces of the part"**; "Tangent propagation" is on by default; options Circular / Conic
  (rho) / Curvature, partial fillet, variable fillet, "Allow edge overflow".
- **Selection refinement** (*Create Selection* help): Tangent connected, Loop/Chain connected ("select a face … and all
  edges that form a connected loop on that face"), Equal length/radius, Parallel, Select pattern.
- **Direct editing:** *Move Face* (Offset — "most often used with non-planar faces to increase or decrease a radius",
  Translate, Rotate), *Delete Face* (heal / cap / leave open), *Replace Face*. The help pages pitch them for imported
  parts without history.
- **References and repair:** failing references show red in the feature dialog; the **Repair tool** (blog,
  2026-01-29) is "a dual-screen debug console": left the current broken Part Studio, right a read-only snapshot "when
  it was last healthy"; *Edit healthy moment* finds the most recent state where that feature worked; hovering a
  missing reference highlights it; *Replace reference* with "Propagate changes" fixes dependent features too.
  Naming internals are in §2.1.

### 1.4 SOLIDWORKS

- **Items to Fillet** accepts faces, edges, features and loops; **Tangent propagation** fillets every edge tangent to
  the selected one ([snippet] of Engineers Rule and SOLIDWORKS help).
- **Missing references:** in *Edit Feature*, lost items are listed as **Missing** at the top of *Items to Fillet*;
  SOLIDWORKS 2020 added right-click → **Repair All Missing References**, which fillets the new edges "if they replace
  an old filleted edge" ([snippet] of the 2020 What's New and Javelin blog; both pages refused automated fetches).
  How the replacement edge is chosen is not documented publicly **[unverified]**.
- The Korean persistent-naming literature classifies SOLIDWORKS as "geometry based basic naming" versus
  topology-based naming in CATIA/NX ([snippet], secondary; **[unverified]** against any vendor source).

### 1.5 Shapr3D

- Chamfer/Fillet: select an edge and drag the arrows; "Include Tangent Edges" option ([snippet]; help page blocked).
- Community threads ask for **edge-loop selection** (2023–2025 feature requests), which suggests it is still
  missing **[unverified]**.
- Direct edits are recorded as history steps (previous research).

### 1.6 MoI3D

- Fillet runs on selected edges; the v5 ACIS-based fillet "will automatically extend" to tangent edges; *select loop*
  only follows the trim boundary of one surface and "does not know how to cross over edges that belong to multiple
  separate faces"; an older *chain* command picks the first and last edge of a chain (MoI forum answers by the
  author). Partial history only (previous research): no persistent naming of edges.

### 1.7 FreeCAD PartDesign

- Fillet/chamfer are "dress-up" features on edges; for a tangent chain "only a single edge needs to be selected".
- **"Use All Edges"** (0.20+): "there is some protection from topological naming issues … there is no dependence on
  individual edge names" (wiki).
- The wiki's standing advice is to "finish the main design work … before applying features like fillets and
  chamfers, otherwise edges could change names"; broken dress-ups report "Invalid edge link" / "missing element
  reference" (GitHub issues #14194, #25760).

### 1.8 Zoo Design Studio / KCL (the closest analogue: clicks write code)

- "Every CAD function in Zoo Design Studio generates KCL"; you can "fillet an edge by clicking, adjust a dimension in
  code, or re-prompt" (Zoo v1 blog, [snippet]).
- **References in code** (KCL book, std lib, issue #12755):
  - **Tags** declared on sketch segments (`$line1`) become names of the swept faces/edges after extrude;
    `getOppositeEdge(tag)`, `getNextAdjacentEdge(tag)`, `getPreviousAdjacentEdge(tag)` navigate from them;
  - `getCommonEdge(faces = [a, b])` — "the edge that is shared between them";
  - for edges with no tag (booleans, imports, shells) the GUI writes `edge005 = edgeId(solid002, index = 54)`;
    `edgeId` doc: "In general, you should prefer tagging edges to using this function"; `index` is claimed to be "a
    stable ordering of edges"; `closestTo = [x, y, z]` is the alternative.
- **Lesson:** Zoo made the same bet as BlendSolid (readable code as history) and ended with a two-tier system:
  meaningful names where the creating feature can name the entity, opaque indices elsewhere. BlendSolid should get
  the first tier from OCCT history for *all* features (not only sketch segments) and avoid indices in the second.

### 1.9 Summary table

| Tool | Edge op on click | Face accepted as edge set | Feature accepted | Tangent propagation | Loop / chain select | Face ops on click |
| --- | --- | --- | --- | --- | --- | --- |
| Plasticity | Fillet auto on edge selection | via Alt+click related | — | On, T toggles | Alt+click loop, Ctrl+Alt ring | Push Face auto |
| Fusion | Fillet/Chamfer, Press Pull | Yes | Yes (+ Rule Fillet) | On by default | via tangent chain / rule | Press Pull offset face, edit feature |
| Onshape | Fillet/Chamfer | Yes | via selection tools | On by default | Loop/chain, tangent, equal radius, parallel | Move/Delete/Replace Face, sketch on face |
| SOLIDWORKS | Fillet/Chamfer, FilletXpert | Yes | Yes | On | Loops | Instant3D, Move/Delete Face |
| Shapr3D | Chamfer/Fillet with arrows | [unverified] | — | Option | Requested by users | Push/pull, offset face |
| MoI3D | Fillet | — | — | Auto (ACIS) | Loop on one surface, chain | — |
| FreeCAD | Fillet/Chamfer dress-up | Yes | Use All Edges | On | — | Sketch on face (discouraged) |
| Zoo | Fillet/Chamfer writes KCL | — | — | [unverified] | — | Sketch on face, extrude |

**Frequency of use.** I found no published usage statistics per operation. Dataset papers built from Onshape public
documents state that extrude is the most frequent feature and that fillet and chamfer are the operations "human
engineers use a lot" (WHUCAD, [snippet]); DeepCAD dropped every design using fillet/chamfer/revolve/sweep/loft/shell,
which "cut 82% of the corpus" (CADFS, 2026), i.e. those operations are ubiquitous. This supports fillet/chamfer as the
first consumer but is indirect evidence **[inference]**.

---

## 2. Persistent naming (the topological naming problem)

### 2.1 Onshape: queries resolved against the feature history

- Queries "do not contain a list of entities … they contain criteria"; `evaluateQuery` returns *transient* queries,
  which "become invalid … if anything is changed" (FeatureScript docs; staff answers).
- **Robust queries** "evaluate the input query to get the transient ID [and] get the ID of the last operation used
  [then] put them into a query that says 'At the time of this Operation ID what was the entity?'" (forum, 2025).
- **Identity** is a *single lineage*: a face keeps identity through modifications, but "If the block is cut so that
  the top face is split, its identity disappears"; `startTracking` then captures the split pieces (staff, forum).
- **Operation ids are hierarchical paths** rooted at the feature id; *unstable id components* (loop indices) act as
  wildcards, and *external disambiguation* pins them to a user selection so that deselecting an item doesn't shift
  every later reference (staff, forum).
- **What the Part Studio stores** for UI clicks: per CADFS (arXiv, 2026-05-03), references are
  `makeQuery(operationId, queryType, entityType, disambiguation)`, e.g. `makeQuery(F5, SWEPT_EDGE, edge, [F4])`; the
  query type "encodes the topological role of the target entity within that operation" (cap, swept…), and "the most
  common mechanisms are original set disambiguation and topology disambiguation, which specify either the entity's
  ancestors or its neighbors". Staff: UI queries use "a number of different tricks to make downstream feature robust
  … and this ends up making ui queries pretty complicated" — they are stored compressed, not meant for humans.
- **Lesson:** this is the layered design BlendSolid wants — *creating operation + role + disambiguation by ancestors
  or neighbours* — but Onshape pays for robustness with unreadable references.

### 2.2 Fusion, Parasolid, SOLIDWORKS: kernel identifiers and attributes

- **Parasolid** gives each entity a session *tag* and a persistent *identifier* (`PK_ENTITY_ask_identifier`), and
  user **attributes** whose class defines how they behave on split, merge, move, etc., overridable with callbacks
  (Parasolid docs mirrored on q-solid.com, v12–v35). Host applications can hang their own names on faces and let the
  kernel carry them through operations. How Fusion (ASM/Parasolid-derived kernel **[unverified]**) and SOLIDWORKS map
  them to references is not public.
- **Fusion** exposes the result: topology references bind by identity, split pieces all match, failures become
  warnings or errors (§1.2). Geometry references fall back to cached geometry.
- **Takeaway [inference]:** commercial systems combine kernel-carried identity with heuristics, and design the *UI*
  around the fact that matching sometimes fails (warning vs error, cached geometry, repair tools).

### 2.3 FreeCAD 1.0: realthunder's element maps

- Plain FreeCAD names are type + index (`Face6`), assigned by OCCT order, so they shift after edits (wiki).
- The algorithm (realthunder's wiki) builds **mapped names from OCCT's `BRepBuilderAPI_MakeShape` history** in four
  steps: copy names of unchanged elements; name Modified/Generated elements from their sources
  (`Face6;:M2;FUS;:T1:5:F`, `Edge2;:G1;XTR;:T1:4:E`, multiple sources `Face6;:M(Face2;:T2:5:F);FUS;…`); name leftovers
  from their parent (`F1;:U1`); name higher elements from their lower ones (`(edge1,edge2,edge3);:L`).
- **Known limits (same page):** index order on splits "relies on what OCCT reports to us"; guessing a lost name "works
  fine when … caused by changes in the previous model step. It works poorly when the change happens several steps
  into the history"; a lost fillet edge still reports "invalid edge link" and the guess "requires user attention";
  cost ~30% recompute time and ~27% file size in realthunder's benchmark.
- **FreeCAD 1.0 behaviour (wiki):** identify broken references and show an error; suggest "a likely fix" during manual
  repair; repair automatically only when "enough information … is stored to have high confidence". Structural edits
  (inserting/deleting features mid-history) make auto-repair "less likely". Ondsel (2025-05-22): "TNP mitigation
  helps only for a specific kind of model breakage."
- **Lesson:** history-derived names work, but only with (a) confident auto-repair, (b) visible errors, (c) a repair UI.

### 2.4 OCCT: what the kernel gives BlendSolid

- **`BRepTools_History`** records, for vertices, edges, faces and solids only, `Generated(S)`, `Modified(S)` and
  `IsRemoved(S)`; a shape can't be both removed and modified, nor both generated and modified from the same input;
  histories of consecutive operations can be **merged**; it can be built from any algorithm exposing
  `Generated/Modified/IsDeleted` (OCCT reference manual).
- **OCAF `TNaming`** (`TNaming_NamedShape` with PRIMITIVE / GENERATED / MODIFY / DELETE / SELECTED evolutions,
  `TNaming_Selector` to re-solve a selection after recompute) is OCCT's full persistent-naming framework; it
  "cannot resolve selections if required topological evolution data is missing". It requires the OCAF document
  model, which BlendSolid does not use **[inference: too heavy to adopt; useful as a design reference]**.
- **Local finding — build123d 0.13.0 already carries history.** `build123d/topology/history.py` (dated 2026-09-10)
  wraps `BRepTools_History` as `ShapeHistory` with `from_boolean`, `from_unify` (the `clean()` step that merges
  coplanar faces), `from_algorithm`, `from_sewing`, `from_relocation`, `merge`, and a `Trace` with
  `is_untouched / is_modified / is_generated / is_descendant`. Builders use it for `Select.LAST` / `Select.NEW` of the
  *last* operation only. BlendSolid needs the chain across *all* operations; merging each operation's record is
  exactly what `BRepTools_History::Merge` is for. **Needs a spike:** hooking every builder operation from the worker
  (e.g. around `_made_by(record)`) without patching build123d.

### 2.5 Code-CAD selectors: build123d and CadQuery

- **build123d:** `faces()/edges()` return `ShapeList`s filtered and ordered with `filter_by(GeomType|Axis|Plane|
  lambda)`, `filter_by_position`, `group_by`, `sort_by(Axis|SortBy)`, `sort_by_distance`, then slicing. Its tutorial
  warns to avoid static indices because "the order within the list is not guaranteed to remain the same", and says
  selectors are what avoids the TNP. `Select.LAST/NEW` scope a query to the last operation.
- **CadQuery:** string selectors (`">Z"`, `"|Z"`, `"#Z"`, `"%CIRCLE"`, `">Z[-2]"`, `and/or/not/exc`), with the caveats
  that non-planar faces are evaluated "at the center of mass of the face. This can lead to results that are quite
  unexpected" and non-linear edges are ignored by most string selectors; plus `tag()` / `workplaneFromTagged()` for
  named intermediate states ([inference] from CadQuery API; the selector page doesn't cover tags).
- **Where geometric selectors fail [inference, consistent with Wang & Nnaji 2005's critique]:**
  - *symmetric or repeated entities* (two identical bosses; four vertical box edges): `sort_by` picks one
    deterministically, but a parameter change can reorder them;
  - *extremal selectors change meaning* when a new feature becomes the new "top";
  - *splits* turn one entity into several and a `[0]` silently picks one;
  - *merges* (`clean()`/UnifySameDomain) make one face out of several;
  - selectors over the *whole part* grow long and unreadable as the part grows.
  They work well on *small, fixed-topology sets* — which is what feature scoping gives them.

### 2.6 Academic references

- **Capoyleas, Chen & Hoffmann 1996**, *Generic naming in generative, constraint-based design* (CAD 28): names
  entities by the generating operation plus disambiguation, the foundation of history-based naming.
- **Kripac 1997**, *A mechanism for persistently naming topological entities in history-based parametric solid
  models* (CAD 29(2):113–122): the Topological ID System assigns IDs and maps old IDs to new ones after re-evaluation;
  face-based basic naming (edges and vertices named through faces), with name matching to resolve ambiguity.
- **Marcheix & Pierra 2002**, *A survey of the persistent naming problem* (ACM SMA '02, 13–22): five common concepts
  and two orthogonal classification criteria.
- **Bidarra & Bronsvoort 2002**, *Persistent naming through persistent entities* (GMP 2002); **Bidarra, Nyirenda &
  Bronsvoort 2005**, *A feature-based solution to the persistent naming problem* (CAD&A 2(1–4):517–526): reference
  the faces of *features* in the feature model rather than the boundary entities of the final BRep (paraphrase from
  the paper's PDF; the automated summary was thin).
- **Wang & Nnaji 2005**, *Geometry-based semantic ID for persistent and interoperable reference in feature-based
  parametric modeling* (CAD 37:1081–1093): names from persistent geometry with hierarchical namespaces; discusses
  splits/merges and symmetric entities as failure cases of topology-based naming.
- **Farjana & Han 2018**, *Mechanisms of persistent identification of topological entities in CAD systems: a review*
  (Alexandria Eng. J.): survey of topology-, geometry- and hybrid approaches (read via [snippet] only).
- **Pyatov et al. 2026**, *CADFS* (arXiv 2605.01925): Onshape reference structure as used in 451k designs (§2.1).

### 2.7 What works, what fails

| Approach | Works for | Fails on | Readable? |
| --- | --- | --- | --- |
| Type + index (`Face6`, Zoo `edgeId(index)`) | nothing persistent | any upstream edit | No meaning |
| Whole-part geometric selector (build123d/CadQuery) | simple parts, extremal entities | symmetry, new extremes, splits, long chains | Yes |
| Creating feature + role (Onshape `qCreatedBy`/cap, KCL tags, Kripac) | most entities of history-built parts | splits (lineage ends), entities with no creator (imports) | Yes, if the role vocabulary is small |
| Kernel history chain (FreeCAD element maps, OCCT `BRepTools_History`, Parasolid attributes) | modifications, booleans, fillets | splits order, changes several steps back, algorithms with no history | No (as stored names) |
| Edge = common edge of two named faces (Kripac, KCL `getCommonEdge`, Fusion Rule Fillet) | most edges, and it survives face modifications | faces sharing several edges, edges on seams / degenerate | Yes |
| Proximity (`closestTo` point) | always unique, imports | anything that moves | Yes, but no intent |
| Cached geometry fallback (Fusion) | geometry references (sketch planes, extents) | topology references (fillets) | n/a |

Every production system layers several of these and **plans for failure in the UI** (§1.2–1.4, §2.3).

---

## 3. Recommendation for BlendSolid milestone 2

### 3.1 First consumer operations

| Order | Operation | Reference needed | Why first |
| --- | --- | --- | --- |
| 1 | **Fillet / chamfer on clicked edges** (Ctrl+B modal radius; negative = chamfer as in Plasticity; tangent propagation on, T toggles; Alt+click adds the loop; clicking a face adds its edges) | edges, faces as edge sets, chains | The default edge action everywhere; M2's criterion was written on edges; fillet consumes its edges, so it is the hardest reference case (Fusion). build123d `fillet()`/`chamfer()` and OCCT history for them exist. |
| 2a | **Push/pull a face that is a feature cap** (G / arrow) | none (provenance) | M1.5's research recommended it; needs only the face → (feature, role) map, which M2 builds anyway. |
| 2b | **Push/pull any planar face → new feature** (extrude from face, `Mode.ADD/SUBTRACT`) | one face | First face selector; Onshape Move Face / Fusion Press Pull equivalent. Offset of non-planar faces is v2. |
| 3 | **Draw Solid attached to a face** (upgrade of the M1.5 fixed placement, opt-in "Attach to face") | one face + a local frame | Fixes the M1.5 follow-up "placements don't follow upstream changes", but face-attached sketches are the most fragile reference class in FreeCAD/Onshape; do it once 1 and 2b pass the corpus. |
| 4 | **Shell with clicked faces as openings** | face set | Faces only; one call (`offset(…, openings=…)`); in the MVP catalog. |
| later | Draft, move face translate/rotate, delete face | faces | Catalog v2 (direct editing). |

**Record the intent, not the expanded set** (Fusion Rule Fillet, FreeCAD Use All Edges): "all edges of face X",
"the tangent chain from edge E" and "all edges of feature F" are each *one* selector that stays valid when the number
of edges changes. OCCT's fillet builder propagates along tangent-continuous edges by itself **[unverified in OCP 8;
spike]**, so a tangent chain can often be stored as its seed edge.

### 3.2 Naming: the reference grammar

A small BlendSolid helper module, injected into the part script namespace like `ref()` already is, gives
readable, feature-scoped references. Proposal (names to be settled in an ADR):

```python
fillet(edge_between(face(boss_1, "side"), face(box_1, "top")), radius=fillet_1_radius)  # feature: fillet_1
chamfer(edges_of(face(box_1, "+X")), length=chamfer_1_length)                             # feature: chamfer_1
extrude(face(cut_1, "floor"), amount=push_1_amount, mode=Mode.ADD)                        # feature: push_1
fillet(edges_of(feature(boss_1)).filter_by(GeomType.CIRCLE), radius=fillet_2_radius)     # feature: fillet_2
fillet(part.edges().filter_by(Axis.Z).sort_by_distance((40, 0, 0))[0], radius=r)  # layer 3 (no provenance)
```

- `feature(name)` names a feature by the `# feature:` id the script already carries (M1). The feature object must
  be reachable by name, so M2 should assign each feature's result (`boss_1 = Cylinder(...)`) or record it by id in the
  worker **[design choice for the ADR]**.
- `face(feature, role)` → faces of the **current** part that descend (untouched / modified) from that feature's own
  face with that role. Roles are per feature type and small: Box `±X ±Y ±Z`; Cylinder `top`, `bottom`, `side`;
  extrude `start`, `end`, `side` (+ which profile edge it was swept from, like KCL tags); fillet faces generated by an
  edge; boolean results keep the inputs' roles because boolean faces are *Modified* from input faces.
  Selecting on the **feature's own small, fixed-topology shape** makes the geometric part trivial and stable (Bidarra's
  point), and the history chain maps it forward (Kripac/FreeCAD's mechanism).
- `edge_between(a, b)` → edges shared by the faces matched by `a` and `b` (KCL `getCommonEdge`, Fusion "between
  faces"). Ambiguity (several shared edges) is resolved by an extra `.sort_by(...)`/`near=` term.
- `edges_of(x)` → all edges of faces/features (Fusion "All Edges", FreeCAD "Use All Edges").
- Splits: a role that maps to several pieces returns all of them (Fusion's token behaviour); consumers that need one
  (push/pull) disambiguate with `near=` in the feature's local frame, not in world coordinates.
- Plain build123d selectors remain valid everywhere; the synthesizer emits them only when there is no provenance.

### 3.3 Synthesis from a click

1. The worker returns, per BRep face and edge, its provenance: `(feature id, role, descendant kind)`, alongside the
   existing `brep_face_id`. **Edges are not in the display mesh map today** (`part.FACE_ATTR` only), so M2 starts by
   adding an edge-id attribute and edge picking.
2. Generate candidates in order of preference: role reference → `edge_between` of the two adjacent faces' role
   references → provenance set + one geometric filter/sort → whole-part geometric chain → `nearest`.
3. Keep the first candidate that (a) evaluates to exactly the clicked set and (b) **still picks the same entity when
   the worker re-runs the script with upstream parameters perturbed** (e.g. ±10% on each numeric parameter before
   the feature), using full-history tracking as ground truth. This builds M2's "survives 3 upstream changes" test
   into synthesis **[inference: cost to be measured; perturbation runs can be capped or done in the background]**.
4. Show the chosen reference in plain words on hover and in the feature panel ("edge between Boss 1 side and Box 1
   top"), so users see what the click means (Onshape highlights; Plasticity labels).

### 3.4 Detecting and presenting broken references

- **Count contract:** each reference carries its expected count (`face(..., expect=1)` or the consumer's own check);
  0 or a different count → broken. build123d selectors that return an empty list silently must be wrapped.
- **Silent re-binding check:** the worker stores a signature of the last good match (entity type, radius/length,
  centroid, normal, area) in the part's sidecar data (not in the script) and flags a warning when the new match moves
  beyond tolerance or changes type.
- **States (Fusion model):** *warning* when some references of a multi-entity feature are lost and the feature still
  computes on the rest; *error* when nothing is left or the operation fails. Keep the last good mesh visible (as
  Onshape's "last healthy" view and Fusion's cached geometry do) and show the state in the BlendSolid panel and the
  part's name/icon.
- **Repair (SOLIDWORKS/Onshape/FreeCAD):**
  - *Reselect*: enter the edge/face picking tool with the lost entities drawn as a ghost overlay (from the stored
    last-good polylines), the new click rewrites only that reference;
  - *Suggested repair*: use the history chain and the stored signature to propose a replacement (the descendant of
    the lost entity, or the nearest entity of the same type and size); apply automatically only when unique and
    within tolerance (FreeCAD's "high confidence" rule), otherwise ask;
  - one *Repair all* action per part (SOLIDWORKS 2020).
- Script-editing users see a Python exception pointing at the reference line, as with any build123d error.

### 3.5 Test plan for the M2 criterion

- Corpus of 20 parts built with M1.5 tools plus fillets/pushes (default part, bracket with 3 holes, symmetric parts
  with patterned bosses, a part with a split face, a STEP import).
- For every face and edge: synthesize, then apply 3 scripted upstream changes (dimension change, feature
  insertion, boolean that splits a face). Oracle = full-history tracking in the worker, independent of the
  selector. Metric = share of entities whose selector still resolves to the oracle's entity (target ≥ 95%), and
  **zero silent wrong bindings** (a wrong pick must be detected, per §3.4).
- Numbers only (counts, BRepCheck, volumes), per project rules; adversarial critics hunt symmetric cases.

### 3.6 Spikes before the ADR

1. Accumulate `BRepTools_History` across every operation of a build123d 0.13 script from the worker (via
   `ShapeHistory.merge`), including `clean()`, fillet and `Locations`, without patching build123d.
2. Role extraction for primitives and `extrude` (cap/side, which profile edge) from the operation's history.
3. Whether OCCT's fillet propagates tangent chains from one seed edge in OCP 8.0.1.
4. Cost of perturbation re-runs per click on the corpus parts.

---

## 4. What I could not verify

- Fusion's AU 2021 debugging article, Autodesk support articles, SOLIDWORKS help, Shapr3D help and ScienceDirect
  returned HTTP 403: their statements come from search-engine snippets.
- How SOLIDWORKS' "Repair All Missing References" chooses a replacement edge, and whether SOLIDWORKS naming is really
  "geometry based" (only secondary academic sources).
- Which kernel identifiers Fusion uses internally for topology references.
- Whether Shapr3D has edge-loop selection today; Zoo's default for tangent propagation.
- Any quantitative data on how often users run each operation (only indirect dataset evidence).
- OCCT fillet tangent propagation in OCP 8.0.1 (spike item 3).

---

## 5. Sources

**Plasticity**
- [Fillet Shell — Plasticity Manual](https://doc.plasticity.xyz/solid/fillet-shell)
- [Fillet — Plasticity Manual](https://doc.plasticity.xyz/solid/fillet)
- [Selecting Objects — Plasticity Manual](https://doc.plasticity.xyz/plasticity-essentials/selecting-objects)

**Fusion**
- [Fillet reference](https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-REF-FILLET.htm)
- [Tangent chain reference](https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/SLD-REF-TANGENT-CHAIN.htm) [snippet]
- [Debugging Your Fusion 360 Design (Strater, Eichmiller, AU 2021)](https://www.autodesk.com/autodesk-university/article/Debugging-Your-Fusion-360-Design-2021) [snippet]
- [Resolving timeline warning or errors in Autodesk Fusion](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Resolving-Timeline-Warning-or-Errors-in-Fusion-360.html) [snippet]
- [Design.findEntityByToken (API)](https://help.autodesk.com/view/fusion360/ENU/?guid=GUID-63F88589-9865-4866-A2F9-2FEEFED725D6) and [forum thread](https://forums.autodesk.com/t5/fusion-api-and-scripts-forum/a-question-about-design-findentitybytoken-method/td-p/9757489) [snippet]

**Onshape**
- [Fillet help](https://cad.onshape.com/help/Content/PartStudio/fillet.htm)
- [Create Selection help](https://cad.onshape.com/help/Content/Home/create_selection.htm)
- [Move Face help](https://cad.onshape.com/help/Content/PartStudio/move_face.htm), [Replace Face](https://cad.onshape.com/help/Content/PartStudio/replace_face.htm) [snippet]
- [How Onshape's Repair Tool Fixes Broken References (2026-01-29)](https://www.onshape.com/en/blog/cad-repair-tool-fix-broken-references)
- [Repairing (help)](https://cad.onshape.com/help/Content/Document/repairing.htm) [snippet]
- [FeatureScript Standard Library](https://cad.onshape.com/FsDoc/library.html) [snippet]
- [Forum: How does the identity tracking/robustness system work?](https://forum.onshape.com/discussion/16911/how-does-the-identity-tracking-rebustness-system-work)
- [Forum: transient / robust / tracked / unstable ids (2025)](https://forum.onshape.com/discussion/28627/please-explain-externally-disambiguated-transient-robust-tracked-unstable-id-039-s-etc)
- [Forum: extrude's entities queries (UI queries are complicated)](https://forum.onshape.com/discussion/9544/feature-script-extrude-s-entities-queries)

**SOLIDWORKS**
- [Repairing Missing References for Fillets (2025 help)](https://help.solidworks.com/2025/English/SolidWorks/sldworks/t_reparing_missing_references_fillets.htm) [snippet]
- [Repairing Missing References for Fillets and Chamfers (What's New 2020)](https://help.solidworks.com/2020/English/WhatsNew/t_repair_missing_references.htm) [snippet]
- [Javelin: Repair All Missing References for Fillets (2019-09)](https://www.javelin-tech.com/blog/2019/09/solidworks-fillet-repair-tool/) [snippet]
- [Engineers Rule: Advanced breakdown of the SOLIDWORKS fillet tool](https://www.engineersrule.com/advanced-breakdown-solidworks-fillet-featuretool/) [snippet]

**Shapr3D, MoI3D**
- [Shapr3D Chamfer/Fillet](https://support.shapr3d.com/hc/en-us/articles/7874402399900-Chamfer-Fillet) [snippet]
- [Shapr3D community: Edge Loop Selection](https://discourse.shapr3d.com/t/edge-loop-selection/32355) [snippet]
- [MoI forum: Tangent Edges — Chain Select](https://moi3d.com/forum/lmessages.php?webtag=MOI&msg=11506.0), [Looped edge selection](http://moi3d.com/forum/lmessages.php?webtag=MOI&msg=3112.4) [snippet]

**FreeCAD**
- [Topological naming problem (wiki source)](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Topological_naming_problem.md)
- [realthunder: Topological Naming Algorithm](https://github.com/realthunder/FreeCAD_assembly3/wiki/Topological-Naming-Algorithm)
- [Ondsel: FreeCAD's topological naming problem is (officially) history (2025-05-22)](https://www.ondsel.com/blog/toponaming-problem-is-history/)
- [PartDesign Fillet (wiki source)](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_Fillet.md) [snippet]
- [Issue #25760: fillet edges disappear after a toponame change](https://github.com/FreeCAD/FreeCAD/issues/25760), [Issue #14194](https://github.com/FreeCAD/FreeCAD/issues/14194) [snippet]
- [Hacker News discussion of the TNP page (2026)](https://news.ycombinator.com/item?id=47097446)

**Zoo / KCL**
- [Fillets, Chamfers and Edges — Modeling with KCL](https://zoo.dev/docs/kcl-book/fillets.html)
- [edgeId — KCL std](https://zoo.dev/docs/kcl-std/functions/std-edgeId)
- [What's New With Zoo, March 2026](https://zoo.dev/blog/whats-new-mar-2026)
- [Zoo Design Studio v1 blog](https://zoo.dev/blog/zoo-design-studio-v1) [snippet]
- [modeling-app issue #12755 (generated KCL for point-and-click fillets)](https://github.com/KittyCAD/modeling-app/issues/12755)

**OCCT, build123d, CadQuery**
- [BRepTools_History (OCCT reference)](https://occt3d.com/dev/doc/refman/html/class_b_rep_tools___history.html)
- [OCAF user guide — Topological naming](https://occt3d.com/dev/doc/overview/html/occt_user_guides__ocaf.html)
- [build123d Selector Tutorial](https://build123d.readthedocs.io/en/latest/tutorial_selectors.html)
- build123d 0.13.0 source, vendored: `.dev/worker_libs/build123d/topology/history.py`, `build_common.py`, `build_enums.py`
- [CadQuery selectors](https://cadquery.readthedocs.io/en/latest/selectors.html)

**Parasolid**
- [Parasolid attribute definitions (q-solid mirror, v12)](http://www.q-solid.com/Parasolid_Docs/chapters/fd_chap.47.html), [attribute callbacks example](http://www.q-solid.com/Parasolid_Examples/Application_Support/Attribute_Processing/Callbacks.html) [snippet]

**Academic**
- [Capoyleas, Chen, Hoffmann 1996 — Generic naming in generative, constraint-based design](https://www.sciencedirect.com/science/article/pii/0010448595000143)
- [Kripac 1997 — A mechanism for persistently naming topological entities…](https://www.sciencedirect.com/science/article/abs/pii/S0010448596000401)
- [Marcheix & Pierra 2002 — A survey of the persistent naming problem](https://www.researchgate.net/publication/221115805_A_survey_of_the_persistent_naming_problem)
- [Bidarra & Bronsvoort 2002 — Persistent naming through persistent entities](https://ieeexplore.ieee.org/document/1027515)
- [Bidarra, Nyirenda, Bronsvoort 2005 — A feature-based solution to the persistent naming problem](https://www.cad-journal.net/files/vol_2/CAD_2(1-4)_2005_517-526.pdf)
- [Wang & Nnaji 2005 — Geometry-based semantic ID…](https://www.sciencedirect.com/science/article/abs/pii/S0010448504002301) ([PDF](https://msse.gatech.edu/publication/JCAD_PID_wang.pdf))
- [Farjana & Han 2018 — Mechanisms of persistent identification of topological entities in CAD systems: a review](https://www.sciencedirect.com/science/article/pii/S1110016818300814) [snippet]
- [Pyatov et al. 2026 — CADFS (arXiv 2605.01925)](https://arxiv.org/html/2605.01925)
- [WHUCAD dataset paper (Fan et al. 2025)](https://journals.sagepub.com/doi/10.3233/ICA-240744) [snippet]
