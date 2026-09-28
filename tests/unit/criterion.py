"""Milestone 2's success criterion (docs/superpowers/specs/2026-09-27-milestone-2-selectors-design.md, section F):
references written by clicks on every face and CAD edge of 20 parts built as the tools build them, checked after
3 upstream changes against an oracle that doesn't use the labels.

- A part is a canonical script made of the operators' own feature specs (primitives.feature_spec, blend_spec,
  push_spec); a Fillet or Push/Pull step "clicks" an entity picked by geometry and writes that entity's reference
  text, exactly what the worker sends to Blender for the click.
- Uniqueness: every entity's reference resolves to exactly that entity.
- Oracle: continuation tracking. Each change goes from the original value to the new one in STEPS small steps and
  every entity is followed from one step to the next by nearest geometry (same kind and type, closest centre,
  direction and size). An entity whose match is not clearly better than the runner-up, or jumps, is "lost" and left
  out of the share (reported). For an inserted unrelated feature: entities with identical geometry before and after.
- Scoring after the changes, per entity: "ok" (the reference resolves to the oracle's entity, without warning),
  "flagged" (error or warning: reported, not silent), "wrong" (resolves to other entities without a warning:
  a silent wrong binding).
"""
import math
import re
from dataclasses import dataclass, field

import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopoDS import TopoDS

import provenance
import tessellate
from blendsolid import params
from blendsolid import script_model as sm

SCRIPT = "<history>"
STEPS = 20


class Build:
    """A part script run as the worker runs it, with its references and a namespace to resolve more."""

    def __init__(self, source):
        self.source = source
        self.tracker = provenance.Tracker()
        self.tracker.filename = SCRIPT
        code = provenance.instrument(source, SCRIPT) or compile(source, SCRIPT, "exec")
        self.ns = provenance.namespace(self.tracker)
        exec(code, self.ns)
        self.shape = self.ns["result"]
        self.faces = tessellate.face_map(self.shape.wrapped)
        self.edges = tessellate.edge_map(self.shape.wrapped)
        refs = provenance.reference_texts(self.tracker, self.faces, self.edges) or ([None] * len(self.faces),
                                                                                    [None] * len(self.edges))
        self.refs = {"face": list(refs[0]), "edge": list(refs[1])}
        self.desc = {"face": [describe(f, "face") for f in self.faces],
                     "edge": [describe(e, "edge") for e in self.edges]}
        # a seam (one face on both sides) is no CAD edge: the display mesh doesn't carry it, a click can't pick it
        self.clickable = {"face": set(range(len(self.faces))),
                          "edge": {i for i, e in enumerate(self.edges) if len(self.tracker.edge_faces(e)) == 2}}
        lo, hi = np.min([d.centre for d in self.desc["face"]], 0), np.max([d.centre for d in self.desc["face"]], 0)
        self.size = float(np.linalg.norm(hi - lo)) or 1.0

    def entities(self, kind):
        return self.faces if kind == "face" else self.edges

    def resolve(self, kind, ref):
        """(ids of the entities `ref` resolves to, or None on an error; warnings it raised)."""
        before = len(self.tracker.warnings)
        try:  # eval: a reference text the worker itself wrote, run in the part script's own namespace
            found = eval(ref, self.ns)
        except Exception as e:  # BrokenReference, or anything the reference text runs into
            return None, [f"{type(e).__name__}: {e}"]
        self.tracker.flush()
        warnings = [w for _, w in self.tracker.warnings[before:]]
        own = self.entities(kind)
        ids = []
        for item in found:
            match = [i for i, x in enumerate(own) if x.IsSame(item.wrapped)]
            ids.extend(match)
        return sorted(set(ids)), warnings


@dataclass
class Desc:
    kind: str
    geom: int
    centre: np.ndarray
    direction: np.ndarray   # plane normal, cylinder/cone axis, line direction, circle normal; zeros otherwise
    size: float             # area or length


def describe(shape, kind):
    props = GProp_GProps()
    direction = np.zeros(3)
    if kind == "face":
        face = TopoDS.Face(shape)
        BRepGProp.SurfaceProperties_s(face, props)
        s = BRepAdaptor_Surface(face)
        geom = int(s.GetType())
        if geom == 0:
            d = s.Plane().Axis().Direction()
            direction = np.array([d.X(), d.Y(), d.Z()])
        elif geom in (1, 2):
            d = (s.Cylinder() if geom == 1 else s.Cone()).Axis().Direction()
            direction = np.array([d.X(), d.Y(), d.Z()])
    else:
        edge = TopoDS.Edge(shape)
        BRepGProp.LinearProperties_s(edge, props)
        c = BRepAdaptor_Curve(edge)
        geom = int(c.GetType())
        if geom == 0:
            d = c.Line().Direction()
            direction = np.array([d.X(), d.Y(), d.Z()])
        elif geom == 1:
            d = c.Circle().Axis().Direction()
            direction = np.array([d.X(), d.Y(), d.Z()])
    p = props.CentreOfMass()
    return Desc(kind, geom, np.array([p.X(), p.Y(), p.Z()]), direction, props.Mass())


def _cost(a, b, scale):
    """How far entity b is from a: centre distance (relative to the part), direction change, size ratio."""
    if a.geom != b.geom:
        return math.inf
    dirs = 1 - abs(float(np.dot(a.direction, b.direction))) if a.direction.any() and b.direction.any() else 0.0
    size = abs(math.log(max(b.size, 1e-12) / max(a.size, 1e-12)))
    return float(np.linalg.norm(a.centre - b.centre)) / scale + dirs + size


LOST_JUMP = 0.05  # a match further than this (cost) in one small step: the entity changed too much to follow
CLEAR = 3.0       # the runner-up must cost this many times the best match (or the entity is ambiguous: lost)


def follow(prev, nxt, kind, tracked):
    """{original id: id in prev} -> {original id: id in nxt} by nearest geometry; lost entities are dropped."""
    out = {}
    cands = nxt.desc[kind]
    for orig, i in tracked.items():
        a = prev.desc[kind][i]
        costs = sorted((_cost(a, b, prev.size), j) for j, b in enumerate(cands))
        if not costs or costs[0][0] > LOST_JUMP:
            continue
        if len(costs) > 1 and costs[1][0] < CLEAR * costs[0][0] + 1e-9:
            continue
        out[orig] = costs[0][1]
    # two entities followed onto the same one: neither is known any more
    seen = {}
    for orig, j in out.items():
        seen.setdefault(j, []).append(orig)
    return {orig: j for orig, j in out.items() if len(seen[j]) == 1}


def identical(before, after, kind):
    """{id before: id after} for entities with the same geometry (an unrelated feature inserted upstream)."""
    out = {}
    for i, a in enumerate(before.desc[kind]):
        found = [j for j, b in enumerate(after.desc[kind]) if _cost(a, b, before.size) < 1e-7]
        if len(found) == 1:
            out[i] = found[0]
    return out


# -- editing a script: the upstream changes ---------------------------------------------------------------------

def set_param(source, name, value):
    return re.sub(rf"^{re.escape(name)} = .*$", f"{name} = {sm.fmt(value)}", source, count=1, flags=re.M)


def param_value(source, name):
    return next(p.value for p in params.parse_params(source) if p.name == name)


_LOC = re.compile(r"Location\(\(([^)]*)\)")


def move_feature(source, feature, delta):
    """Shift the literal placement of `feature` (its `with Locations(Location((x, y, z), ...))` line) by delta."""
    lines = source.split("\n")
    for k, line in enumerate(lines):
        if line.rstrip().endswith(f"# feature: {feature}"):
            found = _LOC.search(line)
            xyz = [float(v) for v in found.group(1).split(",")]
            moved = ", ".join(sm.fmt(a + d) for a, d in zip(xyz, delta))
            lines[k] = line[:found.start(1)] + moved + line[found.end(1):]
            return "\n".join(lines)
    raise KeyError(feature)


def insert_after_first(source, statement_lines):
    """Insert a feature right after the first feature's statement (an unrelated feature upstream)."""
    lines = source.split("\n")
    first = next(k for k, line in enumerate(lines) if "# feature:" in line)
    lines[first + 1:first + 1] = statement_lines
    return "\n".join(lines)


@dataclass
class Change:
    kind: str       # "param" or "move"
    target: str     # parameter name, or feature name
    amount: object  # factor for a parameter, (dx, dy, dz) mm for a move

    def apply(self, start, t):
        """`start` (the script before this change) with a fraction t of the change."""
        if self.kind == "param":
            v0 = param_value(start, self.target)
            return set_param(start, self.target, v0 * (1 + (self.amount - 1) * t))
        return move_feature(start, self.target, [a * t for a in self.amount])


@dataclass
class Score:
    total: int = 0
    unique: int = 0
    tracked: int = 0
    ok: int = 0
    flagged: int = 0
    wrong: list = field(default_factory=list)

    def share(self):
        return self.ok / self.tracked if self.tracked else 1.0


def run_changes(source, changes):
    """The builds along the changes, one after the other, STEPS steps each: [Build]."""
    builds = [Build(source)]
    for change in changes:
        start = builds[-1].source
        builds.extend(Build(change.apply(start, s / STEPS)) for s in range(1, STEPS + 1))
    return builds


def score(builds, mapping_of=None):
    """Score every clicked entity of builds[0] after builds[-1] (tracking through all builds, or `mapping_of`)."""
    first, last = builds[0], builds[-1]
    out = Score()
    for kind in ("face", "edge"):
        ids = range(len(first.entities(kind)))
        if mapping_of is None:
            tracked = {i: i for i in ids}
            for prev, nxt in zip(builds, builds[1:]):
                tracked = follow(prev, nxt, kind, tracked)
        else:
            tracked = mapping_of(kind)
        for i in ids:
            if i not in first.clickable[kind]:
                continue
            out.total += 1
            ref = first.refs[kind][i]
            unique = ref is not None and first.resolve(kind, ref)[0] == [i]
            out.unique += unique
            if i not in tracked:
                continue  # the oracle lost it: no verdict either way
            out.tracked += 1
            if not unique:
                continue  # a click that can't name its entity: a failure of the criterion
            got, warnings = last.resolve(kind, ref)
            if got == [tracked[i]] and not warnings:
                out.ok += 1
            elif got is None or warnings:
                out.flagged += 1
            else:
                out.wrong.append((kind, ref, got, tracked[i]))
    return out
