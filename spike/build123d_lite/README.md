# build123d "lite" research (ADR 0001)

Evidence for [docs/decisions/0001-shipping-build123d.md](../../docs/decisions/0001-shipping-build123d.md):
can unmodified build123d run with only light dependencies, inside the OCCT worker, within the 100 MB budget?

| File | Role |
| --- | --- |
| `lite_shim.py` | meta-path finder serving stub modules for the heavy dependencies we don't ship |
| `compat_scipy.py` | pure-Python replacement for `scipy.optimize.minimize_scalar` (used by `Edge.param_at_point`) |
| `b123d_worker.py` | worker process: private `sys.path`, shim, build123d; runs history scripts, returns meshes |
| `scripts.py` | MVP-style history scripts (sketch, extrude, revolve, loft, shell, sweep, mirror, text, STEP) |
| `b123d_reference.py` | runs the scripts with a full build123d install → reference volumes |
| `b123d_blender_test.py` | runs the scripts in the lite worker launched from Blender and compares |

## Reproduce (Linux, Blender's Python)

```bash
P=~/blender/blender-5.2.2-linux-x64/5.2/python/bin/python3.13
OCP=~/blender/blender-5.2.2-linux-x64/spike_site        # cadquery-ocp-novtk 8.0.1
# lite libs: build123d + light pure-Python deps (+ pure-Python fonttools for text)
$P -m pip install --no-deps --target libs build123d==0.13.0 anytree webcolors==24.8.0 \
    "typing_extensions>=4.16" bd_materials ocp_gordon trianglesolver
$P -m pip download --no-deps --only-binary=:all: --platform any --python-version 3.13 fonttools
$P -m zipfile -e fonttools-*-py3-none-any.whl libs
# full reference install
$P -m pip install --target full build123d==0.13.0
PYTHONPATH=full $P spike/build123d_lite/b123d_reference.py > reference.json
# lite worker launched from Blender
~/blender/blender-5.2.2-linux-x64/blender -b --factory-startup \
    --python spike/build123d_lite/b123d_blender_test.py -- libs $OCP reference.json
```

build123d's own test suite in lite mode: put a `sitecustomize.py` containing
`import lite_shim; lite_shim.install()` on `PYTHONPATH` together with this folder, `libs`, `$OCP` and pytest,
then run `pytest tests` in the build123d v0.13.0 source tree. Summary: `spike/logs/b123d_testsuite_summary.log`.
