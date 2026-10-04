import sys; sys.path.insert(0, "/home/tony/Projects/BlendSolid/spike/m3_bug_sweep/sweep_blender")
from h import *
from blendsolid import ops_add, primitives
from mathutils import Vector

headers = []
area = SimpleNamespace(header_text_set=lambda t: headers.append(t), tag_redraw=lambda: None)

def make(kind="box", size=10.0):
    clean()
    obj = ops_add.add_primitive_part(bpy.context, kind, primitives.sized_values(kind, size))
    p = ops_add._Placement()
    p.prim, p.obj, p.handle, p.typed = primitives.PRIMITIVES[kind], obj, None, ""
    p.matrix = obj.matrix_world.copy(); p.anchor = p.matrix.translation.copy(); p.factor = part.unit_factor()
    p.written = p.size = size
    p.anchor_px, p.start_px = Vector((0.0, 0.0)), 100.0
    op = SimpleNamespace()
    ctx = SimpleNamespace(area=area, scene=bpy.context.scene, preferences=bpy.context.preferences)
    return p, op, ctx, obj

def ev(t, value="PRESS", x=100, y=0, ctrl=False):
    return SimpleNamespace(type=t, value=value, mouse_region_x=x, mouse_region_y=y, ctrl=ctrl, shift=False)

def feed(p, op, ctx, keys):
    r = None
    for k in keys:
        r = p.modal(op, ctx, ev(k) if isinstance(k, str) else k)
    return r

def main():
    cases = [
        ("0", ["ZERO", "RET"]),
        (".", ["PERIOD", "RET"]),
        ("..", ["PERIOD", "PERIOD", "RET"]),
        ("1.2.3", ["ONE", "PERIOD", "TWO", "PERIOD", "THREE", "RET"]),
        ("5 bksp bksp", ["FIVE", "BACK_SPACE", "BACK_SPACE", "RET"]),
        ("0.0000001", ["ZERO", "PERIOD"] + ["ZERO"] * 6 + ["ONE", "RET"]),
        ("0.0004", ["ZERO", "PERIOD", "ZERO", "ZERO", "ZERO", "FOUR", "RET"]),
        ("7 then bksp then mouse", ["SEVEN", "BACK_SPACE", ev("MOUSEMOVE", "NOTHING", x=250), "RET"]),
        ("same size confirm", ["RET"]),
        ("1e5 via digits", ["ONE"] + ["ZERO"] * 9 + ["RET"]),
    ]
    for label, keys in cases:
        p, op, ctx, obj = make()
        name = obj.name
        r = feed(p, op, ctx, keys)
        vals = {k: getattr(op, k, None) for k in ("length", "width", "height")}
        src = part.source_of(obj)
        lines = [l for l in src.splitlines() if l.startswith("box_1_")]
        print(f"[{label}] result={r} size={p.size} typed={p.typed!r} label={p.label()!r} op={vals} script={lines} scale={tuple(obj.scale)}")
        try:
            settle(name, 30)
        except AssertionError:
            pass
        print("   ->", state(name))
        if obj.blendsolid_error:
            FINDINGS.append(f"typed {label}: part fails: {obj.blendsolid_error}")
        if vals["length"] is not None and lines and abs(vals["length"] - float(lines[0].split("=")[1])) > 1e-9:
            FINDINGS.append(f"typed {label}: operator props {vals['length']} != script {lines[0]}")
    # cancel after typing: part removed
    p, op, ctx, obj = make()
    name = obj.name
    r = feed(p, op, ctx, ["THREE", "ESC"])
    print("cancel:", r, name in bpy.data.objects, len([t for t in bpy.data.texts]), len(bpy.data.meshes), headers[-1])
    check(name not in bpy.data.objects and len(bpy.data.texts) == 0 and len(bpy.data.meshes) == 0, "cancel removes object, text and mesh")
    # Ctrl toggling with mouse
    p, op, ctx, obj = make()
    p.modal(op, ctx, ev("MOUSEMOVE", "NOTHING", x=137))
    s1 = p.size
    p.modal(op, ctx, ev("LEFT_CTRL", "PRESS", x=137, ctrl=True))
    s2 = p.size
    p.modal(op, ctx, ev("LEFT_CTRL", "RELEASE", x=137, ctrl=False))
    s3 = p.size
    print("ctrl toggling sizes", s1, s2, s3, "scale", tuple(obj.scale))
    # typed then Ctrl: typed should win
    p.modal(op, ctx, ev("FOUR"))
    p.modal(op, ctx, ev("LEFT_CTRL", "PRESS", x=500, ctrl=True))
    print("typed 4 then ctrl:", p.size)

run(main)
