# ADR 0016: STEP / IGES / BREP import and export

- **Status:** accepted (2026-10-04, session 16; from the 3a research, section 7)
- **Date:** 2026-10-04

## Context

Milestone 3a includes STEP/IGES/BREP import and export, needed before the usage checkpoint (real parts to work
on). A part is a history script (ADR 0002) run by the worker; an imported solid has no script that rebuilds it.
The research (`docs/research/2026-09-29-milestone-3a-sketch-extrude-io.md`, sections 3.5 and 7) measured the
maintainer's 18-file STEP corpus: 0.01–1.2 s to read, 1–103 solids per file, assemblies with repeated instances
(a bearing: 16 instances of 3 products), names on every product, colours on most; 3 files hold BRepCheck-invalid
solids that `ShapeFix_Shape` doesn't repair; zlib-compressed binary BRep is 0.2–30% of the STEP size.

Other software: Fusion 360 and Onshape import a STEP as a "base feature" / derived part that later features build
on; Plasticity and MoI import solids as plain bodies. A path reference to the file (FreeCAD's approach for linked
files) breaks when the `.blend` moves to another machine or OS.

## Decision

1. **Import = one part per solid, its shape embedded.** Each solid becomes a part whose script is
   `insert(imported("<blob id>"), clean=False)  # feature: import_1` (the file's faces as they are: build123d's
   `clean()` merged a corpus solid's faces into an invalid solid); later features (fillets, cuts, sketches on its
   faces) are appended as on any part. Face references use the usual roles (`face("import_1", "+Z", near=...)`, ADR 0009):
   stable, because the shape never changes.
2. **The blob** is the solid as a binary BRep (BinTools), zlib-compressed, base64 in 76-character lines, in its
   own Text datablock (named `.<part>.brep`, dot-hidden like part scripts). Its id is the SHA-256 of the
   compressed bytes (32 hex digits): content-addressed, so it is part of every mesh tag through the script text
   itself, identical solids share one blob, and the worker checks the hash before decoding (a damaged blob is an
   error, never a wrong shape).
3. **Ownership:** the part's script Text holds `bs_blobs = {id: <blob Text>}` (an ID-pointer property). The pointer
   is a real user: the blob is saved while the script is, comes along with Append/Link and with Shift+D copies
   (checked in Blender 5.2). The script's `imported("<id>")` stays the source of truth: a blob is found by id in
   the part's own pointers, then in any local blob Text with that id. A missing blob is the part's error
   ("its imported shape's data is missing from this file").
4. **Request:** the reconcile tick resolves the blob ids of a part and of the parts it uses (`ref()`); the run
   request carries `blobs: {id: base64}`. The worker keeps the unpacked bytes and their BRepCheck verdict by id
   (LRU) and reads a new shape from them on every run (~2 ms for the largest corpus solid): build123d's `clean()`
   changes its input in place, so a decoded shape shared between runs was made invalid by the first one.
5. **Assemblies:** read through XDE (`STEPCAFControl_Reader`, `IGESCAFControl_Reader`) with names and colours.
   The tree becomes nested collections under one collection named after the file; each product's solids
   become parts named after the product (instance name if the product has none). Every instance of a product
   is a linked duplicate of the first one (one mesh, one script — Alt+D identity, milestone 1.5), placed by its
   instance location (millimetres → Blender units by ADR 0003). A location with a scale or mirror is baked into
   that instance's blob. Colour: instance, then product, then solid, then its largest face's colour; one
   material per colour (Base Color and Viewport Display colour).
6. **Units:** OCCT converts file units to millimetres on read; files are written in millimetres.
7. **What isn't a solid:** a closed shell is made a solid (`BRepBuilderAPI_MakeSolid` + `ShapeFix_Solid`);
   open shells, loose faces, wires and points are skipped and counted in the import report ("12 surface bodies
   skipped: only solids are imported"). Surface models are milestone 5's business.
8. **Invalid solids are imported anyway** (BRepCheck fails on 3/18 corpus files): the part shows them with a
   warning — "the imported solid is not valid (BRepCheck): booleans and fillets on it may fail" — instead of
   the usual "`result` is not a valid solid" error; a feature that then fails, fails on its own line.
9. **Export** (File > Export > CAD, one operator, format by extension or the Format menu): the selected parts, or
   every visible part that no other part uses as a cutter; each placed by its `matrix_world` in millimetres
   (a scaled object's scale is applied to the exact shape), named after its object, coloured by its first
   material. STEP: XDE, AP214, names and colours; IGES: XDE (`IGESCAFControl_Writer`, MSBO solids); BREP: one
   compound (no names). Written by the worker from the parts' scripts (shape cache hit when recent), never from
   the display mesh, so Blender modifiers are not exported.
10. **Import/export run in the worker**, as blocking operator calls (a wait cursor; 1.2 s for the largest corpus
    file), one undo step for the whole import. Trust (ADR 0004) is unchanged: a blob is data read by BinTools,
    never executed; the script around it is an ordinary part script, trusted because it was created in this
    session.

## Consequences

- A `.blend` with imports is self-contained and grows by the compressed BRep (≤ ~0.4 MB base64 for the 4.2 MB
  board).
- *Reload from file* is not built: the source path and file name are kept on the blob Text (`bs_source`) for it.
- A hand-edited script that drops `imported(...)` leaves the blob pointer behind (dead weight until the part is
  deleted); the tools never do this.
- Per-face colours, layers, PMI and product metadata beyond the name are not imported; materials are one colour
  per part.
- Every recompute sends the blob to the worker again (hundreds of KB, local socket); revisit only if measured slow.
