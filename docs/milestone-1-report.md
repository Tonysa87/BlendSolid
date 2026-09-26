# Milestone 1 report — History as code

## Success criterion

From `docs/spec.md`'s milestone table, milestone 1's success criterion, verbatim:

> build123d script saved in the `.blend`; changing a parameter → correct recomputation; worker in a separate process

**Met.** The part's history is a build123d script stored as a Blender text datablock referenced from the object
(`blendsolid/part.py`); every parameter change (panel widgets, undo/redo, or a hand-edited script) is applied by
re-running that script in a persistent worker process (`blendsolid/worker/`, `blendsolid/client.py`,
`blendsolid/runtime.py`) and produces a numerically correct mesh — verified in this task by a headless smoke test
of the *installed extension zip* (Steps 3–4 below) on both Linux and Windows, on top of the existing automated
test suite covering parameter edits, undo/redo, script errors and mirroring (`tests/blender/test_parts.py`,
`tests/blender/test_ui.py`).

## Automated test suite (fresh run, `tools/test.sh`)

```
BL=~/blender/blender-5.2.2-linux-x64/blender tools/test.sh
```

- Unit tests (Blender's Python, no `bpy`): **46 passed** in 14.68 s.
- Blender tests (`blender -b --factory-startup`): **28 passed** in 6.27 s.
- Total: **74 passed**, 0 failed, wall time ~22 s.

## Packaging (Step 1)

`tools/build_extension.py --platform {windows-x64,linux-x64,macos-arm64} --blender <exe> [--out dist]`:

- Copies `blendsolid/` into a staging tree, excluding `__pycache__`, `*.pyc` and any pre-existing `worker_libs/`.
- Rewrites `platforms = [...]` in `blender_manifest.toml` to the single target platform.
- `pip install --target stage/blendsolid/worker_libs --only-binary=:all: --platform <tags> -r tools/worker-requirements.txt`
  (`build123d==0.13.0`, `cadquery-ocp-novtk==8.0.1.0.0`, and their full dependency trees — ADR 0001: bundled, loaded
  only inside the worker process).
- `blender --command extension build --source-dir stage/blendsolid --output-filepath dist/blendsolid-<version>-<platform>.zip`.

## Smoke test (Step 2)

`tools/smoke_installed.py`, run as `blender -b --python tools/smoke_installed.py` (**no** `--factory-startup`, so the
extension enabled in the user's preferences stays enabled): finds the installed `bl_ext.*.blendsolid` module, then
before running anything else, hashes (SHA-256) every `.py` file under the repo's `blendsolid/` (excluding
`__pycache__` and `worker_libs`) and compares each against the file at the same relative path in the installed
package directory (`os.path.dirname` of the module's `__file__`); any missing or differing file makes it print
`SMOKE FAIL: installed extension doesn't match the repository` plus the list of differing files, and exit 1 —
this guards against a false PASS from a stale install (see "Review fix" below). Only once the sources match does
it call `blendsolid.new_part()`, tick the runtime until the worker returns a mesh or an error (180 s timeout),
compute the mesh volume, and compare it to the analytical volume of the default part
(box + boss above the box top − vertical fillet material), printing `SMOKE PASS`/`SMOKE FAIL` and exiting
accordingly.

## Problem found and fixed

Building the Linux zip initially failed with:

```
FATAL_ERROR: Error parsing TOML ".../blender_manifest.toml" key "tagline" invalid: a value no longer than 64
characters expected, found 71
```

`blendsolid/blender_manifest.toml`'s `tagline` ("Exact BRep/NURBS CAD modeling with a parametric history written
as code", 71 characters) exceeds Blender 5.2's 64-character extension manifest limit — a pre-existing bug unrelated
to the worker-libraries packaging (nothing about the bundled binaries was rejected). Fixed by shortening it to
"Exact BRep/NURBS CAD modeling with history written as code" (58 characters). No other manifest or packaging
changes were needed; `blender --command extension build` did **not** warn or refuse the bundled binaries in
`worker_libs`, which validates the ADR 0001 packaging approach as implemented.

Both zips were checked with a script over `zipfile.ZipFile(...).namelist()`: **zero** entries containing
`__pycache__`, ending in `.pyc`, or under the project's own `tests/` or `.dev/` (third-party test subdirectories
bundled *inside* `worker_libs` dependencies, e.g. `worker_libs/numpy/typing/tests/...`, are expected and out of
scope for this check — they ship with the pinned wheels).

## Step 3: Linux build, install, smoke test

```bash
BL=~/blender/blender-5.2.2-linux-x64/blender; PY=~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13
$PY tools/build_extension.py --platform linux-x64 --blender $BL
$BL --command extension install-file -r user_default -e dist/blendsolid-0.1.0-linux-x64.zip
$BL -b --python tools/smoke_installed.py
```

Output:

```
built /home/tony/Projects/BlendSolid/dist/blendsolid-0.1.0-linux-x64.zip (255.1 MB)
STATUS Reinstalled "blendsolid"
first result after 3.7 s, volume 24454.7 (expected 24458.2), error: -
SMOKE PASS
```

- Zip size: **255.1 MB** (matches ADR 0001's "Package size" measurement of ~255 MB for Linux).
- Install replaced the pre-existing 0.0.1 spike extension of the same id ("Reinstalled"), as expected.
- First worker result: **3.7 s**; volume within 0.014% of the analytical expectation (tolerance 1%).
- Build wall time ~1m19s (network wheel downloads dominate; no local wheel cache was reused between the two
  builds in this task).

## Step 4: Windows build, install, smoke test (portable Blender)

```bash
$PY tools/build_extension.py --platform windows-x64 --blender $BL
BW=/mnt/e/blender-5.2.2-windows-x64/blender.exe
"$BW" --command extension install-file -r user_default -e "$(wslpath -w dist/blendsolid-0.1.0-windows-x64.zip)"
"$BW" -b --python "$(wslpath -w tools/smoke_installed.py)"
```

Output:

```
built /home/tony/Projects/BlendSolid/dist/blendsolid-0.1.0-windows-x64.zip (225.8 MB)
STATUS Reinstalled "blendsolid"
=== cold run ===
first result after 13.5 s, volume 24454.7 (expected 24458.2), error: -
SMOKE PASS
=== warm run (second invocation) ===
first result after 1.7 s, volume 24454.7 (expected 24458.2), error: -
SMOKE PASS
```

- Zip size: **225.8 MB** (matches ADR 0001's "Package size" measurement of ~226 MB for Windows).
- Install replaced the pre-existing 0.0.1 spike extension, as expected.
- Cold run (first launch of Windows Blender after install, worker binaries not yet in the OS file cache):
  first worker result after **13.5 s**.
- Warm run (second, immediately following `blender -b` invocation): first worker result after **1.7 s**.
  Each invocation starts a fresh Blender process and worker, so "warm" reflects OS/file-cache warmth for the
  bundled OCP/build123d binaries, not a reused worker process.
- Both runs: volume within 0.014% of the analytical expectation.

Only the portable Windows Blender at `/mnt/e/blender-5.2.2-windows-x64` was used; the maintainer's
`C:\Program Files\Blender Foundation` install was never touched.

## Step 5: Manual GUI test (Windows)

**Pending** — the controller runs this step directly with the maintainer, using the zip installed in Step 4
(`E:\blender-5.2.2-windows-x64\blender.exe`). Not executed as part of this task.

## Review fix: false PASS against a stale install

Code review found that `tools/smoke_installed.py` could report `SMOKE PASS` against a **stale** install: it only
looked for *any* enabled `bl_ext.*.blendsolid` module, so if `extension install-file` silently failed to replace
an already-installed extension, the smoke test would still run against the old code and pass.

Fix: before running anything, the script now hashes (SHA-256) every `.py` file under the repo's `blendsolid/`
(excluding `__pycache__` and `worker_libs`) and requires the file at the same relative path in the installed
package directory to exist and match; on any mismatch it prints which files differ and
`SMOKE FAIL: installed extension doesn't match the repository`, exit 1.

Demonstrated on Linux:

```
BL=~/blender/blender-5.2.2-linux-x64/blender
$BL --command extension install-file -r user_default -e dist/blendsolid-0.1.0-linux-x64.zip   # STATUS Reinstalled "blendsolid"
$BL -b --python tools/smoke_installed.py
```
```
first result after 3.3 s, volume 24454.7 (expected 24458.2), error: -
SMOKE PASS
```

Then, without reinstalling, a comment line was added to the repo's `blendsolid/part.py` docstring and the smoke
test re-run:

```
$BL -b --python tools/smoke_installed.py
```
```
SMOKE FAIL: installed extension doesn't match the repository
  part.py: content differs from the repository
```
(exit code 1, confirmed with `echo $?` after a non-piped run). The edit was then reverted (`git diff blendsolid/part.py`
shows no changes), and the smoke test re-run once more to confirm it returns to `SMOKE PASS` (first result after 1.3 s).

`tools/test.sh` was re-run after the fix: still 46 + 28 = 74 passed.

## Files changed in this task

- `tools/build_extension.py` (new) — per-platform extension zip builder.
- `tools/smoke_installed.py` (new) — headless smoke test of an installed extension; hashes the repo's `.py`
  files against the installed package before running the geometry check (review fix, see above).
- `blendsolid/blender_manifest.toml` — shortened `tagline` to fit Blender's 64-character manifest limit
  (bug found while building, see above).
- `docs/milestone-1-report.md` (new, this file).
- `CLAUDE.md` — added the two new tools to "Useful commands".

`dist/*.zip` and `dist/stage-*` are git-ignored build output, not committed.

## Concerns / follow-ups

- The macOS arm64 zip was not built or smoke-tested (no macOS Blender available in this environment); only
  Linux and Windows were exercised, per the task's scope.
- Zip sizes (255 MB Linux, 226 MB Windows) confirm ADR 0001's estimate and its consequence: these zips cannot be
  hosted on extensions.blender.org (100 MB limit) and must be distributed from GitHub, as already decided.
- The manifest `tagline` fix is a small, low-risk content change; worth a quick look in review since it changes
  user-facing text (still English, still accurate).
