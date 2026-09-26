"""Import build123d without its heavy optional dependencies (research for the build123d decision).

Installs a meta path finder that serves *stub* modules for packages we don't bundle. A stub module
(and any of its submodules) returns placeholder objects for every attribute; a placeholder only fails,
with a clear ImportError, when it is actually used (called, instantiated, subclassed at runtime...).
build123d itself is not modified.

Stubs are served only for packages that are genuinely missing: if the real package is importable it wins.
Meant to run inside the OCCT worker process, so the stubs never leak into Blender's own interpreter.
"""
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import types

# Heavy (or only export/import/notebook related) dependencies of build123d 0.13 that we don't bundle.
STUBBED = {
    "scipy", "sklearn", "threejs_materials", "IPython", "PIL", "ezdxf", "fontTools", "lib3mf",
    "py_lib3mf", "ocpsvg", "svgpathtools", "svgelements", "svgwrite", "requests", "pygltflib",
    "dataclasses_json", "sympy",
}

# Real implementations served inside stub modules: {module: {attribute: "module:function"}}
OVERRIDES = {
    "scipy.optimize": {"minimize_scalar": "compat_scipy:minimize_scalar"},
}

used = []  # (placeholder name) → recorded when a placeholder is actually used, for reporting


class MissingDependency(ImportError):
    pass


def _fail(name):
    used.append(name)
    root = name.split(".")[0]
    raise MissingDependency(f"'{name}' needs the optional dependency '{root}', which BlendSolid doesn't bundle")


class _PlaceholderMeta(type):
    def __getattr__(cls, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        return _placeholder(f"{cls.__qualname__}.{attr}")

    def __call__(cls, *a, **k):
        _fail(cls.__qualname__)

    def __mro_entries__(cls, bases):  # subclassing a placeholder at import time is allowed
        return (object,)

    def __or__(cls, other):  # type hints like `RGB | None` evaluated at import time
        return cls

    __ror__ = __or__

    def __getitem__(cls, item):  # type hints like `Stub[int]`
        return cls

    def __iter__(cls):
        _fail(cls.__qualname__)


def _placeholder(qualname):
    # an Exception subclass, so `except StubbedError:` clauses in build123d still work
    return _PlaceholderMeta(qualname, (Exception,), {"__qualname__": qualname, "__module__": "blendsolid_stub"})


class _StubModule(types.ModuleType):
    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        target = OVERRIDES.get(self.__name__, {}).get(attr)
        if target:
            mod, fn = target.split(":")
            return getattr(importlib.import_module(mod), fn)
        return _placeholder(f"{self.__name__}.{attr}")


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        m = _StubModule(spec.name)
        m.__path__ = []  # behaves as a package: submodules resolve to stubs too
        m.__blendsolid_stub__ = True
        return m

    def exec_module(self, module):
        pass


class _StubFinder(importlib.abc.MetaPathFinder):
    def __init__(self):
        self._real = {}

    def _missing(self, root):
        if root not in self._real:
            # look for the real package with the other finders only
            self._real[root] = any(
                f.find_spec(root, None) for f in sys.meta_path if f is not self and hasattr(f, "find_spec"))
        return not self._real[root]

    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in STUBBED and self._missing(root):
            return importlib.machinery.ModuleSpec(fullname, _StubLoader(), is_package=True)
        return None


def install():
    if not any(isinstance(f, _StubFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _StubFinder())


def stubbed_modules():
    return sorted(n for n, m in sys.modules.items() if getattr(m, "__blendsolid_stub__", False))
