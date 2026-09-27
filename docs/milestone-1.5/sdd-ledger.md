# SDD ledger — plan: docs/superpowers/plans/2026-09-26-milestone-1.5-build-without-selectors.md

Branch milestone-1.5 from main 194d9d4 (working in the main checkout, as for milestone 1, per docs/NEXT.md).
Spec: docs/spec.md + docs/superpowers/plans/m1.5-design-notes.md (binding).

## Preflight scan
Full tables in preflight.md (this directory): no cross-task conflicts, all anchors match except F5. Rulings:
- Ruling F1: fix in Task 5 — tick() gives a fresh bs_part_id to every later Text (by object name) carrying an id already used by another Text (session_uid), + Blender test (text.copy() keeping the id) — a pasted/appended cutter must not silently not cut — if wrong: a bit of extra tick work.
- Ruling F2: a Boolean with N cutters appends N features in ONE script edit, which satisfies the spec ("one undo step and one script edit"); the constraint's parenthesis is read as "new features appended to one part" — if wrong: Boolean would need one feature per call.
- Ruling F3: Task 8's backward-compat test compares with the milestone 1 formula written out (part.source_hash(f"{src}\0unit-factor={f!r}")) — the test must be able to fail — if wrong: none.
- Ruling F4: Task 4 step 2 runs unit and Blender RED stages separately — test.sh stops after the unit stage — if wrong: none.
- Ruling F5: Task 4's ADR edit goes at the end of rule 1 (anchor text is wrapped on disk) — if wrong: none.
- Ruling F6: Task 8 docstring becomes "`groups` comes from part_groups(); `tag_of(obj)` gives the tag a mesh computed from obj's script (placed as obj) would carry." — keeps the groups clause — if wrong: none.
- Ruling F7: de-duplicate production logic: part.is_local_part(obj) added in Task 5 and used by later tasks (gizmo poll, ops_boolean, ops_draw, part_groups if trivially possible); part.scaled_message(obj) added in Task 8 and reused in 9/10; a shared "not editable" message helper added in Task 9 and reused in 10; add_primitive_part gains matrix=None in Task 10 and draw_solid NEW calls it — plan code otherwise verbatim — if wrong: small drift from the scratch-tested code, covered by the same tests.
- Ruling F8: shared Blender test helpers (up_to_date, mm3, select) go to tests/blender/conftest.py from Task 5 on; distinct plate_and_pin helpers get distinct names if they differ; VOLUMES unit/Blender duplication accepted (two separate test runtimes) — if wrong: minor duplication stays.
- Ruling F9: tool refusals for non-canonical scripts show a plain sentence ("<name> was made by an older BlendSolid version or edited by hand: the tools can't add features to it"), with the NotCanonical detail appended only when ui.scripts_visible(context) — ADR 0002 binds — Tasks 9, 10. Worker RefError text reaching the panel: deferred minor for the final review — if wrong: users see a less precise message.
- Ruling F10: Task 9 refuses a scaled target with its own message and calls ensure_part_id only after all checks — if wrong: none.
- Ruling F11: Task 6 fixes the two comments to [(Feature, Arrow)] — if wrong: none.
- Ruling F12: Task 7 drops the unreachable SyntaxError branch and caches shapes after tessellation succeeds — if wrong: none.
- Ruling F13: accepted risk (6-decimal rounding may cause one spurious recompute on reopen; never a wrong result) — noted for the milestone report's concerns.

## Tasks
Task 1: complete (commits 194d9d4..b4ef510, review clean)
Task 1: minor (deferred): _structure vs params._parameter_nodes skip rules differ when an import precedes the docstring (fails safe with a generic NotCanonical)
Task 1: minor (deferred): no test for single-value align=Align.MIN
Task 2: fix round 1/5 (1 addressed, 0 open — RED evidence captured in report; no code diff, so no scoped re-review package: controller confirmed the report section and a clean tree at 5956359)
Task 2: complete (commits b4ef510..5956359, review clean)
Task 3: complete (commits 5956359..4d3c62e, review clean)
Task 3: minor (deferred): tests/blender/test_parts.py:72-73 trailing-comment alignment off after the sed rename
Task 4: Ruling: plan-mandated duplication of the headless-Blender subprocess probe (tests/blender/test_trust.py:117-130 vs test_register.py:10-24) is real; fixed in Task 5 together with the F8 conftest helpers (shared run_probe helper in tests/blender/conftest.py used by both tests, with the Traceback guard) — keeps one dispatch — if wrong: none.
Task 4: complete (commits 4d3c62e..6fb4f3e, review clean apart from the plan-mandated finding carried to Task 5)
Ruling: commit trailers credit the model that actually wrote each commit (Haiku/Sonnet/Opus), not a fixed Opus line — truthful attribution; b4ef510 has no Co-Authored-By trailer (deferred minor, fixable only by rewriting local history before merge) — if wrong: trailers get reworded before merge.
Task 5: minor (deferred): ensure_unique_part_ids ignores linked Texts (link + append same part keeps a local/linked id clash)
Task 5: minor (deferred): part.py:243-244 dead `if text is None` check
Task 5: minor (deferred): ops_add operators have no poll (sidebar buttons in Edit Mode) — plan-mandated code
Task 5: minor (deferred): cone top_radius min=0.001 prevents a pointed cone — plan-mandated code
Task 5: minor (deferred): duplicate-id test covers only one tie-break direction
Task 5: minor (deferred): tests/blender/test_minors.py and test_parts.py still define their own up_to_date (test_parts also mm3)
Task 5: fix round 1/5 (1 addressed, 0 open — up_to_date dedup into conftest; commits 139b4cf..50828d0)
Task 5: complete (commits 6fb4f3e..50828d0, review clean)
Task 6: complete (commits 50828d0..c88377f, review clean)
Task 6: minor (deferred): no test for the wedge top_length clamp to 0 in arrow_set
Task 7: minor (deferred): sys.exit() in a dependency escapes _make_ref's wrapper (reported as the caller's sys.exit, no line)
Task 7: minor (deferred): nested ref errors name the inner id on the outer ref() line
Task 7: minor (deferred): dependency shapes are cached/inserted without the solid/validity check (plan-mandated)
Task 7: minor (deferred): no tests for MAX_DEPTH, malformed matrices, empty matrices, mirrored placement
Task 7: fix round 1/5 (1 addressed, 0 open — float32 rotation re-orthonormalized in _location + test; commits d879001..7d1f434)
Task 7: complete (commits c88377f..7d1f434, review clean)
Task 8: ⚠️ nested deps matrices composed in the dependency's frame — resolved by controller: test_a_cutter_cut_by_another_cutter checks the volumes of both parts and passes (Task 7 worker composes per instance).
Task 8: complete (commits 7d1f434..509dc48, review clean)
Task 8: minor → carried to Task 9: relative_matrix blames the cutter when the TARGET is scaled (fix with F10)
Task 8: minor (deferred): parts with ref( are ast-parsed every tick; no perf test with cutters (consider caching references() by source)
Task 8: minor (deferred): _synced keyed on the dep-including tag re-runs sync_params while a cutter is dragged (harmless)
Task 8: minor (deferred): tag stability relies on 6-decimal rounding (see F13)
Task 9: ⚠️ keymap registration in tests — resolved by controller: test_shortcuts_are_registered reported green in the full run (keyconfigs.addon exists in blender -b).
Task 9: minor (deferred): no test for detail=True branch of not_canonical_message (FORCE_SHOW_SCRIPTS)
Task 9: minor (deferred): cycle check doesn't refuse a cutter whose part_id == target_id (transient after Shift+D; deps reports a loop later)
Task 9: minor (deferred): scale tolerances differ (part.is_scaled 1e-6 vs deps.SCALE_TOLERANCE)
Task 9: fix round 1/5 (2 addressed, 0 open — is_local_part(None) safe + poll test; scaled-target match; commits 474e7b2..d1a9178)
Task 9: complete (commits 509dc48..d1a9178, review clean)
Task 10: complete (commits d1a9178..b0caf36, review clean)
Task 10: ⚠️ non-zero Draw Solid rotations (Euler ZYX ↔ build123d Location) not covered by a volume test → carried to Task 11 (side-face draw test with a volume/position check)
Task 10: minor → carried to Task 11: zero-height / zero-size drags are clamped to 0.001 mm instead of being ignored
Task 10: minor → carried to Task 11: test_millimetre_scene lacks a drawn_properties(drawn, box, factor) assertion with a target
Task 10: minor (deferred): lazy `from . import ui` comment in ops_draw doesn't state the real reason
Task 11: Ruling: the brief's whole-file ops_draw.py is merged into the existing file (additions only) so Task 10's rulings survive — if wrong: none.
Task 11: Ruling: viewport navigation (MMB/wheel/trackpad/NDOF) passes through the Draw Solid modal — reviewer's Minor 1 promoted because the Task 14 GUI test needs to orbit while setting heights — if wrong: small extra change.
Task 11: minor (deferred): height stays 0 when the view is along the face normal (height_along_normal returns 0); cover in manual test/header
Task 11: minor (deferred): test_pull_up_is_a_union_and_ctrl_snaps checks no volume (plan-mandated)
Task 11: fix round 1/5 (3 addressed, 0 open — MIN_MM threshold, zero-size tests, nav pass-through; commits 2c58967..bcda5a0)
Task 11: complete (commits b0caf36..bcda5a0, review clean)
Task 12: Ruling: plan-mandated one_step didn't put a recompute in flight before undo — fixed (runtime.tick() before ed.undo) because Review Focus 1 binds — if wrong: none.
Task 12: ⚠️ BRACKET volume constant 18465.93 not independently verified by the reviewer — the plan states it was checked with build123d; the test passing with the worker's numbers confirms it within tolerance.
Task 12: fix round 1/5 (1 addressed, 0 open — undo races an in-flight recompute, applied tags recorded; commits 3f5c2bd..162ed6a)
Task 12: complete (commits bcda5a0..162ed6a, review clean)
Task 13: complete (commits 162ed6a..1a7d654, review clean)
## Final review (194d9d4..1a7d654, opus): with fixes — I1 Shift+D hands cutter identity to the duplicate (name tie-break); I2 Task 14 steps vs tool behaviour (+ bl_keymap any); I3 worker ref() errors show ref('<id>') to standard users (ADR 0002); minors M1–M7. Task 12 ⚠️ BRACKET constant independently recomputed: matches.
Ruling: one fix wave covers I1, I2 (code: keymap any=True), I3, M1, M2, M3, M4, M5, + rebuild/reinstall 0.2.0 zips and smoke; M6 stays deferred (harmless cache growth); M7 (NEXT.md, trailer rule) handled by the controller in Task 14; the Task 14 step wording (tool switch, Ctrl after drag start if needed, "stale parts recompute", angled view hint) is applied by the controller when guiding the maintainer — if wrong: small follow-ups.
Final fix wave: commits 1a7d654..02546e0 (I1, I2 keymap any, I3, M1–M5); scoped re-review: all addressed, no new Critical/Important.
Final: parked — SyntaxError in a cutter's script still shows the compile filename "<ref <id>>" (runner.py ~447/454) — Ruling: only reachable by users who edit scripts (Show history scripts); fix in milestone 2 — if wrong: a script-editing user sees an opaque id.
Final: parked — group age taken from the name-first object, not min(session_uid) (part.py ~299/329) — Ruling: same result for every real case (a Shift+D copy is always newest); follow-up — if wrong: a rare tie resolves by name.
Final: parked — appending/pasting a target+cutter pair twice makes the second target cut by the first copy's cutter (pre-existing id semantics) — Ruling: milestone 2 follow-up (remap ref ids of incoming groups) — if wrong: surprising result on double append/paste.
Final: deferred — M6 gizmos._layout_cache never pruned (harmless).
Task 14: Ruling: the maintainer is unavailable for the manual GUI test (2026-09-26) — manual test on standby; controller substitutes an automated GUI-session check (tools/gui_check.py, real window, software OpenGL on Linux + the installed 0.2.0 on the portable Windows Blender) covering what can be driven without real mouse events; report marks the manual test as pending; merge to main locally (maintainer authorized the merge), no push until the manual test is done — if wrong: the merge happens before the manual test; any GUI failure is fixed on main before the push.
GUI check (tools/gui_check.py, commits db1171e fix + ecc5d31): PASS Linux WSLg (event-simulate) and Windows portable (installed 0.2.0 rebuilt with the fix); bug found: parameter mirror stale after undo (fixed db1171e). Review: fix correct; Important: stale CLAUDE.md pitfall on event simulation; gui_check minors (drew unchecked, heights non-strict, partial step 4 reported OK, wording).
Ruling: one last dispatch fixes the CLAUDE.md pitfall + gui_check minors (Linux re-run to confirm), then writes the milestone report/README/NEXT.md with the manual test pending for 2026-09-27 — if wrong: docs rework.
