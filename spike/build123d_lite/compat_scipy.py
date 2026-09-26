"""Tiny pure-Python replacements for the few scipy functions build123d's core uses.

Served by lite_shim in place of the real scipy (which doesn't fit the 100 MB package budget).
Only the call patterns build123d 0.13 actually uses are supported.
"""
import math
from types import SimpleNamespace


def minimize_scalar(fun, bounds=None, method="bounded", options=None):
    """Bounded scalar minimization (golden-section search), scipy-compatible result object.

    build123d uses it as `minimize_scalar(f, bounds=(lo, hi), method="bounded", options={"xatol": tol})`.
    Like scipy's bounded method, it finds *a* local minimum inside the interval.
    """
    if method != "bounded" or bounds is None:
        raise NotImplementedError("compat minimize_scalar only supports method='bounded' with bounds")
    xatol = (options or {}).get("xatol", 1e-5)
    maxiter = (options or {}).get("maxiter", 500)
    a, b = bounds
    inv_phi = (math.sqrt(5) - 1) / 2
    c, d = b - inv_phi * (b - a), a + inv_phi * (b - a)
    fc, fd = fun(c), fun(d)
    nit = 0
    while abs(b - a) > xatol and nit < maxiter:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - inv_phi * (b - a)
            fc = fun(c)
        else:
            a, c, fc = c, d, fd
            d = a + inv_phi * (b - a)
            fd = fun(d)
        nit += 1
    x = (a + b) / 2
    return SimpleNamespace(x=x, fun=fun(x), success=nit < maxiter, nit=nit)
