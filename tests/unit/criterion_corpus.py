"""The 20 parts of milestone 2's success criterion, built step by step with the tools' own feature specs: primitives
(Shift+A), Draw Solid union/cut (a primitive placed on a face, a fixed Location), Fillet/Chamfer on clicked edges
or faces, Push/Pull on a clicked face. A click is simulated by picking the entity closest to a point and writing
the reference text the worker gives that entity (what the Blender tools write).

Each part comes with its 3 upstream changes (parameters of early features scaled by ±20%, a feature moved) and an
unrelated feature to insert after its first feature (a small hole away from everything else).
"""
from dataclasses import dataclass
from pathlib import Path

from blendsolid import primitives as pr
from blendsolid import script_model as sm
from criterion import Build, Change

TEMPLATE = Path(__file__).resolve().parents[2] / "blendsolid" / "templates" / "default_part.py"


def box(l, w, h, **kw):
    return pr.feature_spec("box", {"length": l, "width": w, "height": h}, **kw)


def cyl(r, h, **kw):
    return pr.feature_spec("cylinder", {"radius": r, "height": h}, **kw)


def cut(kind, values, at, rotation=(0.0, 0.0, 0.0)):
    """Draw Solid's cut into a face at `at` (the solid hangs from the face)."""
    return pr.feature_spec(kind, values, mode="SUBTRACT", align=pr.TOP, location=at, rotation=rotation)


def on(kind, values, at, rotation=(0.0, 0.0, 0.0)):
    """Draw Solid's union on a face at `at`."""
    return pr.feature_spec(kind, values, location=at, rotation=rotation)


def click(source, kind, point):
    """The reference a click on the entity (face or edge) closest to `point` writes."""
    import build123d as bd
    b = Build(source)
    wrap = bd.Face if kind == "face" else bd.Edge
    where = bd.Vertex(*point)
    ids = sorted(b.clickable[kind])
    i = min(ids, key=lambda k: wrap(b.entities(kind)[k]).distance_to(where))
    ref = b.refs[kind][i]
    assert ref, (kind, point)
    return ref


class Part:
    def __init__(self, first):
        self.source, _ = sm.new_script(first)

    def add(self, spec):
        self.source, name = sm.append_feature(self.source, spec)
        return name

    def fillet(self, points, size, chamfer=False, face=False):
        refs = [f"edges_of({click(self.source, 'face', p)})" if face else click(self.source, "edge", p)
                for p in points]
        return self.add(pr.blend_spec(refs, size, chamfer))

    def push(self, point, amount):
        return self.add(pr.push_spec(click(self.source, "face", point), amount))


@dataclass
class Case:
    name: str
    source: str
    changes: list
    insert: list    # statement lines of the unrelated feature inserted after the first one


def hole_at(x, y, z_top, r=0.5, depth=2):
    return [f"    with Locations(Location(({x}, {y}, {z_top}), (0.0, 0.0, 0.0))):  # feature: extra_1",
            f"        Cylinder({r}, {depth}, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)"]


def corpus():
    out = []

    # 1. milestone 1's default part (box, boss, fillet): the template
    src = TEMPLATE.read_text()
    out.append(Case("default_part", src, [Change("param", "box_1_length", 1.2), Change("param", "box_1_width", 0.8),
                                          Change("param", "boss_1_radius", 1.2)], hole_at(36, 26, 20)))

    # 2. milestone 1.5's bracket: plate, wall, 3 holes, a fillet in the corner
    p = Part(box(60, 40, 5))
    p.add(on("box", {"length": 5, "width": 40, "height": 30}, (-27.5, 0.0, 5.0)))
    for x, y in ((0, 10), (15, -10), (15, 10)):
        p.add(cut("cylinder", {"radius": 3, "height": 5}, (float(x), float(y), 5.0)))
    p.fillet([(-25, 0, 5)], 2)
    out.append(Case("bracket", p.source, [Change("param", "box_1_length", 1.2), Change("param", "box_2_height", 0.8),
                                          Change("move", "cut_1", (-4.0, 3.0, 0.0))], hole_at(28, 18, 5)))

    # 3-6. boxes with fillets and chamfers on edges, faces and tangent chains
    p = Part(box(40, 30, 20))
    p.fillet([(20, 0, 20)], 4)
    out.append(Case("box_fillet_edge", p.source, [Change("param", "box_1_length", 1.2),
                                                   Change("param", "box_1_width", 0.8),
                                                   Change("param", "box_1_height", 1.2)], hole_at(-18, -13, 20)))
    p = Part(box(40, 30, 20))
    p.fillet([(0, 0, 20)], 3, face=True)
    out.append(Case("box_fillet_face", p.source, [Change("param", "box_1_length", 1.2),
                                                   Change("param", "box_1_width", 0.8),
                                                   Change("param", "fillet_1_radius", 1.2)], hole_at(0, 0, 2)))
    p = Part(box(40, 30, 20))
    p.fillet([(0, 0, 20)], 2, chamfer=True, face=True)
    out.append(Case("box_chamfer_face", p.source, [Change("param", "box_1_length", 1.2),
                                                    Change("param", "box_1_height", 0.8),
                                                    Change("param", "chamfer_1_length", 1.2)], hole_at(0, 0, 2)))
    p = Part(box(40, 30, 20))
    p.fillet([(20, 15, 10), (20, -15, 10), (-20, 15, 10), (-20, -15, 10)], 5)
    p.fillet([(0, 15, 20)], 2)  # one top edge: the whole tangent loop
    out.append(Case("tangent_chain", p.source, [Change("param", "box_1_length", 1.2),
                                                 Change("param", "box_1_width", 0.8),
                                                 Change("param", "fillet_1_radius", 1.2)], hole_at(0, 0, 2)))

    # 7. bosses in a symmetric pattern, filleted where they meet the top
    p = Part(box(60, 60, 10))
    for x, y in ((-15, -15), (15, -15), (-15, 15), (15, 15)):
        p.add(on("cylinder", {"radius": 5, "height": 10}, (float(x), float(y), 10.0)))
    p.fillet([(20, -15, 10)], 1)
    out.append(Case("boss_pattern", p.source, [Change("param", "box_1_length", 1.2),
                                                Change("param", "cylinder_1_radius", 0.8),
                                                Change("move", "cylinder_2", (3.0, -2.0, 0.0))], hole_at(0, 0, 10)))

    # 8. a slot splitting the top face, a fillet on one half's outer edge
    p = Part(box(40, 30, 20))
    p.add(cut("box", {"length": 8, "width": 30, "height": 5}, (0.0, 0.0, 20.0)))
    p.fillet([(-20, 0, 20)], 2)
    out.append(Case("slot", p.source, [Change("param", "box_1_length", 1.2), Change("param", "box_1_width", 0.8),
                                       Change("move", "cut_1", (4.0, 0.0, 0.0))], hole_at(-14, -10, 2)))

    # 9. a wedge with a chamfer
    p = Part(pr.feature_spec("wedge", {"length": 40, "width": 30, "height": 20, "top_length": 10}))
    p.fillet([(-20, 0, 0)], 2, chamfer=True)
    out.append(Case("wedge_chamfer", p.source, [Change("param", "wedge_1_length", 1.2),
                                                 Change("param", "wedge_1_width", 0.8),
                                                 Change("param", "wedge_1_top_length", 1.2)], hole_at(0, 0, 2)))

    # 10-11. push/pull on a cylinder's top and on a box's side, then a fillet
    p = Part(cyl(10, 20))
    p.push((0, 0, 20), 5)
    out.append(Case("cylinder_push", p.source, [Change("param", "cylinder_1_radius", 1.2),
                                                 Change("param", "cylinder_1_height", 0.8),
                                                 Change("param", "push_1_amount", 1.2)], hole_at(0, 0, 2)))
    p = Part(box(40, 30, 20))
    p.push((20, 0, 10), 8)
    p.fillet([(28, 15, 10)], 2)
    out.append(Case("box_push_fillet", p.source, [Change("param", "box_1_width", 0.8),
                                                   Change("param", "box_1_height", 1.2),
                                                   Change("param", "push_1_amount", 1.2)], hole_at(-10, 0, 20)))

    # 12. a rotated box cut into a box, chamfered
    p = Part(box(40, 30, 20))
    p.add(cut("box", {"length": 12, "width": 8, "height": 6}, (0.0, 0.0, 20.0), (0.0, 0.0, 30.0)))
    p.fillet([(-20, 0, 20)], 1, chamfer=True)
    out.append(Case("rotated_cut", p.source, [Change("param", "box_1_length", 1.2), Change("param", "cut_1_length", 0.8),
                                              Change("move", "cut_1", (3.0, 2.0, 0.0))], hole_at(15, -11, 20)))

    # 13. a cone with a filleted base
    p = Part(pr.feature_spec("cone", {"bottom_radius": 15, "top_radius": 5, "height": 20}))
    p.fillet([(15, 0, 0)], 2)
    out.append(Case("cone_fillet", p.source, [Change("param", "cone_1_bottom_radius", 1.2),
                                              Change("param", "cone_1_top_radius", 0.8),
                                              Change("param", "cone_1_height", 1.2)], hole_at(0, 0, 20, r=0.5)))

    # 14. a torus on a plate
    p = Part(box(60, 60, 5))
    p.add(on("torus", {"major_radius": 15, "minor_radius": 4}, (0.0, 0.0, 5.0)))
    out.append(Case("torus_on_plate", p.source, [Change("param", "box_1_length", 1.2),
                                                  Change("param", "torus_1_minor_radius", 0.8),
                                                  Change("move", "torus_1", (4.0, 0.0, 0.0))], hole_at(25, 25, 5)))

    # 15. a sphere cut into a box, its rim filleted
    p = Part(box(40, 30, 20))
    p.add(pr.feature_spec("sphere", {"radius": 8}, mode="SUBTRACT", location=(0.0, 0.0, 20.0), align=("CENTER",) * 3))
    p.fillet([(8, 0, 20)], 1)
    out.append(Case("sphere_cut", p.source, [Change("param", "box_1_length", 1.2), Change("param", "cut_1_radius", 0.8),
                                             Change("move", "cut_1", (3.0, 2.0, 0.0))], hole_at(-17, -12, 20)))

    # 16. a boss with its concave edge filleted
    p = Part(box(40, 30, 10))
    p.add(on("cylinder", {"radius": 6, "height": 10}, (0.0, 0.0, 10.0)))
    p.fillet([(6, 0, 10)], 2)
    out.append(Case("boss_concave", p.source, [Change("param", "box_1_length", 1.2),
                                                Change("param", "cylinder_1_radius", 0.8),
                                                Change("move", "cylinder_1", (4.0, 3.0, 0.0))], hole_at(-17, -12, 10)))

    # 17. an L (a box cut from a box) with its concave edge filleted
    p = Part(box(40, 30, 20))
    p.add(cut("box", {"length": 20, "width": 30, "height": 10}, (10.0, 0.0, 20.0)))
    p.fillet([(0, 0, 10)], 3)
    out.append(Case("l_concave", p.source, [Change("param", "box_1_length", 1.2), Change("param", "box_1_width", 0.8),
                                            Change("param", "cut_1_height", 0.8)], hole_at(-15, -10, 20)))

    # 18. a plate with a bolt pattern, its outline chamfered
    p = Part(box(60, 40, 6))
    for x, y in ((-20, -12), (20, -12), (-20, 12), (20, 12)):
        p.add(cut("cylinder", {"radius": 2.5, "height": 6}, (float(x), float(y), 6.0)))
    p.fillet([(0, -20, 6), (0, 20, 6), (-30, 0, 6), (30, 0, 6)], 1, chamfer=True)
    out.append(Case("bolt_plate", p.source, [Change("param", "box_1_length", 1.2), Change("param", "box_1_width", 0.8),
                                             Change("move", "cut_2", (-3.0, 2.0, 0.0))], hole_at(0, 0, 6)))

    # 19. a step (a box on a box) with fillets on the step's edges
    p = Part(box(40, 30, 10))
    p.add(on("box", {"length": 20, "width": 30, "height": 10}, (-10.0, 0.0, 10.0)))
    p.fillet([(0, 0, 20)], 2)
    p.fillet([(0, 0, 10)], 2)
    out.append(Case("step", p.source, [Change("param", "box_1_length", 1.2), Change("param", "box_2_length", 0.8),
                                       Change("param", "box_2_height", 1.2)], hole_at(15, -10, 10)))

    # 20. a cross hole: a cylinder cut along X through a box, its openings chamfered
    p = Part(box(40, 30, 20))
    p.add(pr.feature_spec("cylinder", {"radius": 4, "height": 60}, mode="SUBTRACT", location=(0.0, 0.0, 10.0),
                          rotation=(0.0, 90.0, 0.0), align=("CENTER",) * 3))
    p.fillet([(20, 4, 10)], 1, chamfer=True)
    out.append(Case("cross_hole", p.source, [Change("param", "box_1_length", 1.2), Change("param", "box_1_width", 0.8),
                                             Change("param", "cut_1_radius", 1.2)], hole_at(-15, -10, 20)))
    return out
