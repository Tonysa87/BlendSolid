# Bug sweep tools (session 14, 2026-10-04)

The headless searches behind `docs/research/2026-10-04-bug-sweep.md` (the ledger: every finding and its status),
kept so the next sessions can rerun them after a fix. Scripts run with Blender's own Python (worker code) or
`blender -b` (Blender side); **at most 2 processes at a time** (the maintainer's PC must stay usable).

- `rerun.py grooves|tapers` — reruns the groove sweep's 3000 cases (`groove_cases.json.gz`: source, category at
  the sweep, independent 2D-band volume `exp`, volume at the sweep) or the 895 tapers that passed at the sweep
  (`taper_cases.json.gz`) against the current worker; writes `changed_<kind>.json` and prints a summary. A "same
  volume" or "exact" case is fine; anything else is a regression or a fix to check against `exp`.
- `sweep_grooves/` — the groove/rib fuzzer (`fuzz.py`, `harness.py`, `analyze.py`; `final.txt` holds the
  ledger's G repros).
- `sweep_regions/` — the regions/extrude/revolve fuzzer (`fuzz.py`, `child.py`, `drive.py`; `final.py` the R
  repros).
- `sweep_mesh/` — the display mesh checker (`check.py`: closed, orientation, slivers, deviation, fallbacks;
  `gen.py`/`case.py` the case generator; `case_<seed>.py` the M repros).
- `sweep_blender/` — Blender-side scenarios driven headless (`h.py` harness, `fakeview.py` fake view/events for
  modals; `run.sh sNN_x.py`).
- `taper_check/` — the taper ground-truth experiments (offset-section integral, self-intersection test): why the
  volume check was dropped (`BRepOffsetAPI_MakeOffset` segfaults on some faces).

The original result files (~100 MB) stayed in the session's scratchpad; paths in the scripts were rewritten to
this folder, so some scripts expect result files that are no longer here: rerun them to regenerate.
