# Where we are / what's next (bookmark)

Updated: 2026-09-26, end of session 1. Read this first when resuming.

## State
- **Milestone 0 (spike):** done — `SPIKE_REPORT.md`.
- **Milestone 1 (history as code):** done, merged to `main` and pushed — `docs/milestone-1-report.md`
  (105 automated tests, smoke tests on Windows + Linux, manual GUI test 8/8 OK).
- **Research:** how reference tools build solids — `docs/research/2026-09-26-modeling-workflows.md`.
- **Spec updated:** milestone 1.5 "Build without selectors" added; milestone 2 extended to edges **and faces**,
  starting with face/edge → feature provenance.
- **Milestone 1.5 plan: written, not started** —
  `docs/superpowers/plans/2026-09-26-milestone-1.5-build-without-selectors.md` (14 tasks), from the design notes
  `docs/superpowers/plans/m1.5-design-notes.md`. The plan author implemented it once in a scratch copy
  (102 unit + 117 Blender tests passing there); the code in the plan is that code. Its "Deviations from the design
  notes" section lists 6 accepted deviations (part id stored on the script Text; `insert(ref(...))`; `-Y` honoured;
  Ctrl = 1 mm snapping; plane picked on mouse-down; primitives centred on the cursor plane).

## Next step
Execute the milestone 1.5 plan with **superpowers:subagent-driven-development**, exactly as milestone 1:
- branch `milestone-1.5` from `main` (local commits only);
- one implementer subagent per task + task review (spec + quality), fix rounds, ledger in
  `.superpowers/sdd/<plan>/progress.md`;
- final whole-branch review on the most capable model, one fix wave, scoped re-review;
- Task 14's manual GUI test is run **with the maintainer**, guided step by step (portable Windows Blender
  `E:\blender-5.2.2-windows-x64`, launched from WSL with the console redirected to a log file);
- then merge to `main` and push (the maintainer's rule: push only at the end of a milestone).

## Working agreement with the maintainer
- Repo content in English; chat in Italian.
- Work autonomously; record non-trivial decisions as ADRs (`docs/decisions/`) or ledger rulings; ask only for
  spec scope changes, publication/licensing/distribution, or anything touching the maintainer's own Blender install.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (+ the session's `Claude-Session:` line
  when the harness provides one).

## Open follow-ups (not blocking)
- Windows worker watchdog blocked while a C call holds the GIL → use a Job object with kill-on-close.
- Windows zip built with the build machine's pip environment markers (no colorama, has pexpect) → fix before any
  public release (milestone 3).
- `PR_SET_PDEATHSIG` is thread-scoped: comment it when the client is next touched.
- Maintainer reported an error on `Ctrl+D` during the milestone 1 GUI test (not a Blender 5.2 default duplicate key;
  nothing in the console) — not investigated.
- Optional GPU acceleration (fairing, SubD → NURBS) is an R&D note in the spec.
