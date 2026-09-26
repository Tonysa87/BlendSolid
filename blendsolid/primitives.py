"""The parametric primitives: their parameters, the build123d call each one writes, and where their gizmo
arrows go. Pure Python (no bpy): the operators, the Draw Solid tool and the gizmos all read this catalog.

All numbers are millimetres (ADR 0003). A primitive "sits" on its placement plane: its base is centred on the
origin and it grows along +Z (align BASE); a cut drawn into a face hangs from it and grows along -Z (align TOP).
"""
from dataclasses import dataclass

from .script_model import FeatureSpec

BASE = ("CENTER", "CENTER", "MIN")
TOP = ("CENTER", "CENTER", "MAX")
_FLIP = {"MIN": "MAX", "CENTER": "CENTER", "MAX": "MIN"}


@dataclass(frozen=True)
class GizmoSpec:
    param: str          # parameter suffix, e.g. "height"
    axis: int           # 0, 1, 2: the feature-frame axis the arrow follows
    k: float            # extent along that axis per unit of the parameter (2 for a radius)
    level: str = ""     # "min"/"max": put the arrow on the bottom/top Z level instead of the middle
    shift: tuple[str, int] | None = None   # (param, axis): move the arrow's origin by that parameter


@dataclass(frozen=True)
class Primitive:
    kind: str                                   # "box", ... (script_model.Feature.kind)
    label: str                                  # "Box", ... (menus, object names)
    params: tuple[tuple[str, str, float], ...]  # (suffix, UI label, default in mm)
    call: str                                   # build123d call; {name} = feature name, {align}, {mode}
    gizmos: tuple[GizmoSpec, ...]

    def extents(self, v):
        """Size along the feature's X, Y, Z axes for parameter values `v` (suffix -> mm)."""
        return _EXTENTS[self.kind](v)


def _align_code(align):
    if len(set(align)) == 1:
        return f"Align.{align[0]}"
    return "(" + ", ".join(f"Align.{a}" for a in align) + ")"


PRIMITIVES = {p.kind: p for p in (
    Primitive("box", "Box", (("length", "Length", 40.0), ("width", "Width", 30.0), ("height", "Height", 20.0)),
              "Box({name}_length, {name}_width, {name}_height, align={align}{mode})",
              (GizmoSpec("length", 0, 1.0), GizmoSpec("width", 1, 1.0), GizmoSpec("height", 2, 1.0))),
    Primitive("cylinder", "Cylinder", (("radius", "Radius", 10.0), ("height", "Height", 20.0)),
              "Cylinder({name}_radius, {name}_height, align={align}{mode})",
              (GizmoSpec("radius", 0, 2.0), GizmoSpec("height", 2, 1.0))),
    Primitive("sphere", "Sphere", (("radius", "Radius", 10.0),),
              "Sphere({name}_radius, align={align}{mode})",
              (GizmoSpec("radius", 0, 2.0),)),
    Primitive("cone", "Cone", (("bottom_radius", "Bottom Radius", 10.0), ("top_radius", "Top Radius", 5.0),
                               ("height", "Height", 20.0)),
              "Cone({name}_bottom_radius, {name}_top_radius, {name}_height, align={align}{mode})",
              (GizmoSpec("bottom_radius", 0, 2.0, level="min"), GizmoSpec("top_radius", 0, 2.0, level="max"),
               GizmoSpec("height", 2, 1.0))),
    Primitive("torus", "Torus", (("major_radius", "Major Radius", 20.0), ("minor_radius", "Minor Radius", 5.0)),
              "Torus({name}_major_radius, {name}_minor_radius, align={align}{mode})",
              (GizmoSpec("major_radius", 0, 2.0), GizmoSpec("minor_radius", 2, 2.0, shift=("major_radius", 0)))),
    # build123d's Wedge rises along its Y axis: rotation=(90, 0, 0) makes it rise along Z; its align is written
    # in Wedge's own (unrotated) axes, see wedge_align().
    Primitive("wedge", "Wedge", (("length", "Length", 40.0), ("width", "Width", 30.0), ("height", "Height", 20.0),
                                 ("top_length", "Top Length", 10.0)),
              "Wedge({name}_length, {name}_height, {name}_width, 0, 0, {name}_top_length, {name}_width, "
              "rotation=(90, 0, 0), align={align}{mode})",
              (GizmoSpec("length", 0, 1.0), GizmoSpec("width", 1, 1.0), GizmoSpec("height", 2, 1.0))),
)}

_EXTENTS = {
    "box": lambda v: (v["length"], v["width"], v["height"]),
    "cylinder": lambda v: (2 * v["radius"], 2 * v["radius"], v["height"]),
    "sphere": lambda v: (2 * v["radius"],) * 3,
    "cone": lambda v: (2 * max(v["bottom_radius"], v["top_radius"]),) * 2 + (v["height"],),
    "torus": lambda v: (2 * (v["major_radius"] + v["minor_radius"]),) * 2 + (2 * v["minor_radius"],),
    "wedge": lambda v: (v["length"], v["width"], v["height"]),
}


def wedge_align(align):
    """Wedge align in its own axes for a wanted align in the part's axes: rotation (90, 0, 0) maps the
    wedge's Y to the part's Z and its Z to the part's -Y (so MIN and MAX swap on that axis)."""
    return (align[0], align[2], _FLIP[align[1]])


def wedge_align_inverse(native):
    """The part-axes align of a wedge written with Wedge-axes align `native` (inverse of wedge_align)."""
    return (native[0], _FLIP[native[2]], native[1])


def feature_spec(kind, values, mode="ADD", align=BASE, location=None, rotation=(0.0, 0.0, 0.0)):
    """The FeatureSpec a tool appends for primitive `kind` with parameter values `values` (suffix -> mm).
    mode "ADD" features are named after the kind (box_1), "SUBTRACT" ones cut_1, "INTERSECT" ones common_1."""
    prim = PRIMITIVES[kind]
    code_align = wedge_align(align) if kind == "wedge" else align
    call = prim.call.replace("{align}", _align_code(code_align)).replace(
        "{mode}", "" if mode == "ADD" else f", mode=Mode.{mode}")
    prefix = {"ADD": kind, "SUBTRACT": "cut", "INTERSECT": "common"}[mode]
    return FeatureSpec(prefix, tuple((suffix, float(values[suffix])) for suffix, _, _ in prim.params), call,
                       location, tuple(rotation))


def insert_spec(part_id, mode):
    """The feature that applies another part (a live cutter) to this one: build123d's insert() (add() is
    deprecated in 0.13) of ref(<part id>), which the worker resolves in this part's frame."""
    prefix = {"ADD": "union", "SUBTRACT": "bool", "INTERSECT": "common"}[mode]
    return FeatureSpec(prefix, (), f'insert(ref("{part_id}"), mode=Mode.{mode})')


@dataclass(frozen=True)
class Arrow:
    param: str                              # full parameter name, e.g. "box_1_height"
    origin: tuple[float, float, float]      # feature frame, mm: the point the arrow measures from
    direction: tuple[float, float, float]   # unit vector, feature frame
    scale: float                            # arrow offset (mm) = parameter value * scale


def arrows(feature, values):
    """Gizmo arrows for one script_model.Feature, given the script's parameter values (full name -> mm).
    Empty when the feature isn't a catalog primitive, its align or placement isn't literal, or one of its
    parameters is missing."""
    prim = PRIMITIVES.get(feature.kind)
    if prim is None or feature.align is None or feature.location is None:
        return []
    align = wedge_align_inverse(feature.align) if feature.kind == "wedge" else feature.align
    try:
        v = {suffix: values[f"{feature.name}_{suffix}"] for suffix, _, _ in prim.params}
    except KeyError:
        return []
    ext = prim.extents(v)
    lo = [{"MIN": 0.0, "CENTER": -e / 2, "MAX": -e}[a] for a, e in zip(align, ext)]
    mid = [low + e / 2 for low, e in zip(lo, ext)]
    out = []
    for g in prim.gizmos:
        origin, direction = list(mid), [0.0, 0.0, 0.0]
        a = align[g.axis]
        if a == "CENTER":
            scale, direction[g.axis] = g.k / 2, 1.0
        elif a == "MIN":
            origin[g.axis], scale, direction[g.axis] = lo[g.axis], g.k, 1.0
        else:
            origin[g.axis], scale, direction[g.axis] = lo[g.axis] + ext[g.axis], g.k, -1.0
        if g.level == "min":
            origin[2] = lo[2]
        elif g.level == "max":
            origin[2] = lo[2] + ext[2]
        if g.shift is not None:
            origin[g.shift[1]] += v[g.shift[0]]
        out.append(Arrow(f"{feature.name}_{g.param}", tuple(origin), tuple(direction), scale))
    return out
