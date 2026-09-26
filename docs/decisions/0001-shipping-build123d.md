# ADR 0001 — Shipping build123d within the 100 MB package limit

- **Status:** proposed, awaiting the maintainer's decision
- **Date:** 2026-09-26
- **Context from:** [SPIKE_REPORT.md](../../SPIKE_REPORT.md), issue 1 ("build123d doesn't fit the 100 MB limit")
- **Evidence:** `spike/build123d_lite/`, logs `spike/logs/b123d_lite_*.log`

## Context

The spec makes the parametric history a **build123d script**. The spike found that build123d 0.13.0 needs almost
all of its dependencies just to be imported (`threejs_materials` 90 MB, scipy 37 MB, scikit-learn, sympy, IPython,
pillow, ezdxf, …): ≈ 200 MB of wheels per platform on top of OCP, against a 100 MB limit per zip on
extensions.blender.org. OCP alone already takes 47.7 MB (Windows), 66.8 MB (Linux) and 63.0 MB (macOS arm64).

Two more constraints came out of this research:

- **extensions.blender.org rules** ([add-on guidelines](https://developer.blender.org/docs/handbook/extensions/addon_guidelines/),
  [manual](https://docs.blender.org/manual/en/latest/advanced/extensions/addons.html#bundle-dependencies)):
  "Add-ons must not install Python modules, PIP packages, Python-wheels etc."; dependencies are bundled as wheels
  or *vendorized* as pure-Python sub-modules; and "manipulating Blender's module loading such as changing the module
  search path or inserting modules directly into the global module dictionary is forbidden".
- **`typing_extensions`:** build123d needs ≥ 4.16; Blender 5.2 bundles 4.14.1. The extensions' site-packages comes
  *before* Blender's in `sys.path`, so shipping `typing_extensions` as a wheel would silently upgrade it for Blender
  and every other add-on.

## Options

### (a) Unmodified build123d, trimmed dependencies, loaded only in the worker — **recommended**

build123d and the few light pure-Python dependencies it needs at import time are vendored as a private library
folder inside the extension. They are loaded **only by the OCCT worker process**, which has its own `sys.path`;
Blender's interpreter never imports build123d or OCP. In the worker, a small meta-path finder (`lite_shim.py`)
serves stub modules for the dependencies we don't ship: a stub fails with a clear error only when a feature
actually uses it. build123d's source is not modified.

Shipped with build123d: `anytree`, `webcolors`, `typing_extensions` 4.16, `bd_materials`, `ocp_gordon`,
`trianglesolver`, `fonttools` (pure-Python wheel, for text). Stubbed: scipy, scikit-learn, threejs_materials,
IPython, pillow, ezdxf, lib3mf, ocpsvg, svgpathtools, svgelements, svgwrite, requests, pygltflib,
dataclasses_json, sympy. `compat_scipy.py` gives a real replacement for the one scipy function used by core
modeling code on common paths (`minimize_scalar`, fallback of `Edge.param_at_point`).

**Evidence**

| Check | Result |
| --- | --- |
| Extra package size | **+1.8–1.9 MB per platform** (8.2 MB unpacked): zips 49.5 MB Win, 68.6 MB Linux, 64.9 MB macOS |
| build123d's own test suite (2321 tests pass with all dependencies) | **2174 pass** in lite mode + text (93.7 %); + all 46 `Edge` tests after `compat_scipy` |
| 11 MVP-style history scripts run in the worker, launched from Blender | **identical volumes** to the full install on Linux (11/11) and Windows (10/11: the text script with the OS default font differs, see below; with the same TTF it is identical), all solids valid, no stub hit |
| Blender's interpreter after the run | build123d, OCP, shim: **not loaded** |
| `typing_extensions` | Blender keeps 4.14.1, the worker uses 4.16.0: no conflict |
| Worker cold start (import OCP + build123d, `.pyc` cached) | Windows 1.3–1.5 s (2.0 s without `.pyc`), Linux 0.6–1.0 s |

The scripts cover: box/cylinder/boolean/fillet with a selector (the spike model), sketch + extrude + holes + slot
+ chamfer, revolve, loft, shell, sweep along a spline, mirror + subtract, text engraving, STEP export/import,
`param_at_point`.

What the remaining failing tests need (none of it is in the MVP column of the catalog except where noted):

| Area | Failing tests | Missing dependency |
| --- | --- | --- |
| DXF import / SVG+DXF export | 34 + 26 | ezdxf, svgpathtools |
| 3MF / STL mesh export-import | 22 + 1 | lib3mf |
| Materials / glTF | 33 | threejs_materials |
| SVG import | 13 | ocpsvg, svgpathtools |
| STL → BRep primitive detection | 5 | scikit-learn |
| Convex hull (2D wire, 3D `ConvexPolyhedron`) | 5 | scipy |
| `full_round`, double tangent arc, Gordon surfaces | 1 + 1 + 2 | scipy |
| `str()` of `GroupBy` / `ShapeList` | 2 | IPython (pretty printer) |

One more test fails only because the *test code* uses scipy (`Rotation.from_euler`).

**Costs and risks**

- A stub list and a few compat functions to maintain for each build123d release. Mitigation: pin build123d and run
  its test suite in lite mode in CI, diffing the failures against a full install (what this research did by hand).
- The shim is a meta-path finder. It runs only in our own subprocess, never in Blender's interpreter, so it doesn't
  touch "Blender's module loading"; vendoring pure-Python code is explicitly allowed. **Still worth confirming with
  the extensions moderation team before publishing** (their guidelines say to ask when in doubt).
- The extension folder may be read-only ("system" repositories), so `.pyc` files can't be written there and every
  worker start on Windows would pay ~2 s. Mitigation: `PYTHONPYCACHEPREFIX` pointing to
  `bpy.utils.extension_path_user(__package__)`, and start the worker in the background when the add-on is enabled.
- Features needing scipy (convex hull, `full_round`, Gordon surfaces) need small replacements if we want them.
  scipy itself can't be shipped: OCP + scipy is already 102 MB on Linux.

### (b) Our own thin API on top of OCP — not recommended

Drop build123d and write a build123d-like API ourselves. No dependency problem, but it throws away ~21 000 lines of
tested code, including exactly what milestones 1–2 need: the selector language (`filter_by`, `sort_by`,
`group_by`), `Select.NEW/LAST`, and the new `ShapeHistory` (build123d 0.13, a wrapper of OCCT's
`BRepTools_History`). It also loses a documented syntax that people and language models already know, which
matters for "a script readable and editable by Claude via MCP". Months of work for no user-visible gain.

### (c) Ask upstream to make heavy dependencies optional — recommended in parallel

No issue about dependency weight exists in the build123d tracker yet. Proposal: lazy imports or `extras`
(`build123d[export]`, `build123d[materials]`, …) for threejs_materials, scipy, scikit-learn, ezdxf, SVG libraries,
lib3mf and IPython. If accepted, our stub list shrinks towards zero and (a) becomes plain wheels. It helps other
embedders too (web viewers, FreeCAD/Blender add-ons, serverless builds).

### (d) Install build123d at first run — rejected

Forbidden on extensions.blender.org ("Add-ons must not install Python modules, PIP packages, Python-wheels etc."),
and it would need network access and a writable environment.

## Decision (proposed)

**(a) now, (c) in parallel.** Keep build123d unmodified, vendor it with its light dependencies as a private worker
library, stub the heavy optional ones, and propose optional extras upstream.

## Consequences for milestone 1

- **Blender never imports OCP or build123d**: everything OCCT runs in the worker. The DLL-coexistence risk
  becomes moot (milestone 0 showed it was fine anyway), and a crash in OCCT can't take Blender down.
- The worker is started in the background when the add-on is enabled, with the `.pyc` cache in the user extension
  directory; a cold start costs ~1.5 s on Windows.
- **Text must use a bundled font.** With the OS default font, the same script gives a different solid on Windows
  and Linux (39 vs 34 faces, volume 5951.023 vs 5951.003); with the same TTF file the results are identical.
  Bundle a freely licensed font (e.g. DejaVu Sans) and always pass `font_path`.
- Pin `build123d==0.13.*`, `cadquery-ocp-novtk==8.0.*`; CI job "build123d test suite in lite mode vs full".
- For milestone 2 (selectors), build on build123d's `ShapeHistory` and follow upstream issue
  [#1454 "Persistent tags on sub-shapes"](https://github.com/gumyr/build123d/issues/1454) (opened 2026-09-13 by
  build123d's author), which proposes exactly the persistent naming our selectors need.
- The MVP I/O row (STEP, IGES, BREP) is covered by OCP and build123d without the stubbed packages; DXF/SVG/3MF/glTF
  would need their dependencies (ezdxf 3–6 MB, lib3mf ~1 MB) if we want them later.
