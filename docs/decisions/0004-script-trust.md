# ADR 0004 — Trusting the scripts of a .blend file

- **Status:** accepted (2026-09-26, controller's ruling after the milestone 1 branch review)
- **Date:** 2026-09-26
- **Context from:** milestone 1 whole-branch review, finding 1 (critical)

## Context

A BlendSolid part is a build123d script stored in the `.blend` (ADR 0002). The reconcile timer submits every
part whose mesh hash differs from its script hash, and the worker `exec`s the script. So opening a `.blend`
whose part has a stale hash ran arbitrary Python from that file, bypassing Blender's own protection against
scripts embedded in files (Preferences › Save & Load › *Auto Run Python Scripts*, with its *Excluded Paths*),
which is **off** by default. The worker runs with the user's privileges, so it is no sandbox.

## Decision

A part's script runs only if one of these holds:

1. **The file is trusted by Blender's rule:** `context.preferences.filepaths.use_scripts_auto_execute` is on
   and the file path is not matched by an entry of `context.preferences.autoexec_paths` (a `PathCompare`
   collection with `path` and `use_glob`; matched like Blender's `BKE_autoexec_match()`: a glob is an
   `fnmatch` pattern, otherwise the entry is a prefix of the path; case-insensitive on Windows). An unsaved
   file (e.g. the startup file) only needs the switch.
2. **The user pressed "Trust Scripts in This File"** in the BlendSolid panel. This lasts for the session
   only: it is never saved, and it is forgotten when another file (or the same one again) is loaded.
3. **The script was created in this session:** *New Part* creates a trusted script; a copy of a trusted script
   (Shift+D) is trusted too. Trust is tracked per `Text` datablock by `session_uid`, which is stable across
   undo/redo and renames.

The rule is evaluated when a file is loaded (`load_post`) and when the add-on is enabled with a file open.

An **untrusted** part:

- keeps showing the mesh saved in the file (the cached tessellation), never submitted to the worker —
  including after parameter or script edits (the script text is still rewritten; it is just not run);
- still has its parameters mirrored into the panel (parsing with `ast` doesn't execute anything);
- shows a notice in the panel ("Scripts in this file are not trusted") with the trust button.

An object that adopts an untrusted script (e.g. *Link Object Data* onto a loaded part) becomes untrusted:
trust follows the script, not the object.

## Consequences

- Opening a file from an unknown source is as safe with BlendSolid as without it, under Blender's default
  settings. Users who enabled *Auto Run* get the same behaviour as for drivers and registered text blocks.
- Blender's command-line `--enable-autoexec`/`-y` flag and the "Allow Execution" button of Blender's own
  auto-run warning are not visible to add-ons (only the preference is): after them, BlendSolid parts still
  need the trust button. This errs on the safe side.
- Appended parts follow the file's trust: in a trusted file they run (as Blender runs appended drivers); in
  an untrusted file they need the trust button.
