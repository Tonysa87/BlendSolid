# ADR 0007 — Live cutters: deleting keeps them restorable

- **Status:** accepted (2026-09-27, maintainer's request in the milestone 1.5 manual GUI test)
- **Date:** 2026-09-27
- **Context from:** manual GUI test, step 14; research on Fusion 360, HardOps/BoxCutter, Onshape, SolidWorks,
  Plasticity and Blender's Boolean modifier

## Context

A part's boolean with a live cutter is an `insert(ref("<cutter id>"))` feature of its script. Deleting the
cutter made the part show an error ("undo the deletion or delete this part") and keep its last mesh, and the
cutter's script was purged on the next save: a cutter deleted by mistake, or found wrong later, couldn't be
brought back, and a cut couldn't be removed without editing the (hidden) script. Other tools: Blender's
Boolean modifier silently loses the cut; HardOps/BoxCutter hide cutters instead of deleting them; Fusion 360,
Onshape and SolidWorks keep the cut in the part's history where it can be edited, suppressed or removed.

## Decision

- The scripts of parts other parts use get a fake user (`part.keep_used_scripts`, marked so only those fake
  users are ever cleared), and each part remembers where its cutters were, in its own frame
  (`part.remember_cutters`). A deleted cutter goes on cutting from its kept script and placement: no error,
  no recompute, across save and reload (`deps._deleted_cutter`).
- The BlendSolid panel lists a part's booleans (`deps.booleans`): Select Cutter (shown if hidden), Restore
  Cutter for a deleted one (recreated where it was, wire, editable) and Remove (the boolean is dropped from the
  history with `script_model.remove_feature`; a cutter no other part uses is shown and rendered again).
- Only a cutter whose script is really lost is still an error, pointing at Remove.
- Not now (NEXT.md): per-boolean suppress, "Apply" (inline a cutter into the part's history), cycling
  through a part's cutters.

## Consequences

- Deleting a cutter is never destructive; its script stays in the file while any part uses it and is released
  once no part does.
- A deleted cutter that itself uses other parts can't be used from its script alone: the part asks to restore it.
- Tests: `tests/blender/test_removed_cutters.py`, `tests/unit/test_script_model.py`.
