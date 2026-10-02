"""Automated GUI-session check: the 16 steps of milestone 1.5's manual GUI test (plan
docs/superpowers/plans/2026-09-26-milestone-1.5-build-without-selectors.md, Task 14, Step 1) and milestone 2's
steps 17-21 (Draw Solid on a bevelled part, Fillet, Push/Pull, fillet preview latency, focus click) and milestone
3a's step 22 (Sketch path with an arc, Groove, face split + Extrude Sketch, Revolve Sketch), walked through
in a real Blender window, without a person.

Usage (a real window, not -b):
    blender [--factory-startup --addons blendsolid] --enable-event-simulate --python tools/gui_check.py [-- --out DIR]

- Linux/WSLg, repository add-on: WAYLAND_DISPLAY= LIBGL_ALWAYS_SOFTWARE=1 PYTHONPATH=<repo> blender
  --factory-startup --gpu-backend opengl --python-use-system-env --addons blendsolid --enable-event-simulate
  --python tools/gui_check.py
- Windows portable Blender with the installed extension: no --factory-startup (the extension is enabled in the
  portable preferences). Preferences the check changes (undo steps, Auto Run) are restored and never saved.

A timer walks a scripted scenario once the window is up. Operators run with a window/area/region override;
undo and redo are Blender's own (ed.undo / ed.redo / ed.undo_redo, the last one being what the Adjust Last
Operation panel does when a value changes). With --enable-event-simulate, the interactive parts get real,
simulated mouse and keyboard events (Window.event_simulate): the Draw Solid tool's modal (drag, height, Ctrl
snapping, Esc/right-click, drawing through a cutter), dragging a gizmo arrow, and the Ctrl+Numpad boolean keys.
Without the flag those parts fall back to the operators' execute path. Every step is verified with numbers
(volumes in mm³, up-to-date mesh tags, feature counts) and prints `STEP <n> OK|FAIL <detail>`; the run ends
with `GUI CHECK PASS` or `GUI CHECK FAIL` and quits Blender (also on an unexpected exception). A viewport
screenshot is saved per block (screen.screenshot, or an offscreen render of the viewport when the screen can't
be read back, e.g. software OpenGL under WSLg). The worker's process id is printed (`WORKER PID <n>`) so the
caller can check that no worker is left once Blender has quit.

What this cannot check (still for a person): how dragging a gizmo or drawing feels (latency, the preview
following the mouse), colours and the visual look of arrows, outlines and wireframes, the Adjust Last
Operation panel as a widget (its values are changed through the same redo call), menus opened by hand
(Shift+A, the Object menu: their content is checked), the header text on screen (the text set is checked),
tooltips, whether another installed add-on uses the same keys, and quitting Blender by hand.
"""
import importlib
import math
import os
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace

import bpy
import numpy as np
from bpy_extras import view3d_utils
from mathutils import Euler, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[ARGS.index("--out") + 1] if "--out" in ARGS else os.path.join(tempfile.gettempdir(),
                                                                         "blendsolid-gui-check")
os.makedirs(OUT, exist_ok=True)
SIM = bpy.app.use_event_simulate
# `-- --only 17,18`: run only those steps (the ones that build their own parts)
ONLY = {int(n) for n in ARGS[ARGS.index("--only") + 1].split(",")} if "--only" in ARGS else None
T0 = time.monotonic()

bs = SimpleNamespace()  # the add-on's modules, found in the first tick (repository add-on or bl_ext.*)
results = []            # (step, ok, detail)
shots = []
rec = SimpleNamespace(prepare=[], panel=[], preview=[], headers=[], finish=0, invoke=[], errors=[])


class Fail(Exception):
    pass


def log(*a):
    print(f"[gui-check {time.monotonic() - T0:7.1f}]", *a, flush=True)


# -- context, objects, numbers --------------------------------------------------------------------------------

def ctx():
    win = bpy.context.window_manager.windows[0]
    area = max((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == "WINDOW")
    return win, area, region


def override():
    win, area, region = ctx()
    return bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region)


def op(fn, **props):
    """Run an operator as a user action (undo push), in the 3D viewport."""
    with override():
        result = fn("EXEC_DEFAULT", True, **props)
    if result != {"FINISHED"}:
        raise Fail(f"{fn.idname_py()} returned {result}")
    return result


def ob(name):
    return bpy.data.objects.get((name, None))


def f():
    return bs.part.unit_factor()


def mm3(obj):
    return bs.part.mesh_volume(obj.data) / f() ** 3


def up_to_date(obj):
    return bs.part.applied_hash(obj) == bs.part.current_tag(obj)


def parts():
    return [o for o in bpy.data.objects if o.type == "MESH" and o.blendsolid_script is not None]


def features(obj):
    return [(x.name, x.mode) for x in bs.script_model.features(bs.part.source_of(obj))]


def active():
    return bpy.context.view_layer.objects.active


def select(act, *others):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in (act, *others):
        if o is not None:
            o.select_set(True)
    bpy.context.view_layer.objects.active = act


def click(act, *others):
    """Select as a click in the viewport does: the selection is its own undo step."""
    select(act, *others)
    op(bpy.ops.ed.undo_push, message="Select")


def deselect():
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = None


def cursor(mm=(0, 0, 0), rot_deg=(0, 0, 0)):
    c = bpy.context.scene.cursor
    c.location = Vector(mm) * f()
    c.rotation_euler = Euler([math.radians(a) for a in rot_deg])


def close(a, b, rel=0.005):
    return abs(a - b) <= rel * max(abs(b), 1.0)


def expect(cond, what):
    if not cond:
        raise Fail(what)


def until(pred, timeout=120.0, what="condition"):
    t = time.monotonic()
    while True:
        try:
            if pred():
                return
        except (ReferenceError, KeyError, AttributeError):
            pass
        if time.monotonic() - t > timeout:
            raise Fail(f"timed out after {timeout:.0f} s waiting for {what}")
        redraw()  # a viewport only redraws when something tags it (draw callbacks, gizmos, panels)
        yield 0.05


def settled(*names, timeout=120.0):
    """Wait until the named parts (all parts if none) are up to date or show an error."""
    def ok():
        objs = [ob(n) for n in names] if names else parts()
        return all(o is not None and (up_to_date(o) or o.blendsolid_error) for o in objs)
    yield from until(ok, timeout, f"parts up to date: {', '.join(names) or 'all'}")


def redraw():
    for area in ctx()[0].screen.areas:
        area.tag_redraw()


def frames(n=3):
    for _ in range(n):
        redraw()
        yield 0.1


def params_match(obj):
    found = {p.name: p.value for p in bs.params.parse_params(bs.part.source_of(obj))}
    have = {p.name: p.value for p in obj.blendsolid_params}
    return found.keys() == have.keys() and all(abs(found[k] - have[k]) < 1e-3 for k in found)


# -- viewport, screenshots, simulated events ------------------------------------------------------------------

def set_view(center_mm, rot_deg=(60, 0, 30), dist=0.25):
    _, area, region = ctx()
    rv3d = region.data
    rv3d.view_perspective = "PERSP"
    rv3d.view_rotation = Euler([math.radians(a) for a in rot_deg]).to_quaternion()
    rv3d.view_location = Vector(center_mm) * f()
    rv3d.view_distance = dist
    yield from frames(3)


def px(world_mm):
    _, _, region = ctx()
    c = view3d_utils.location_3d_to_region_2d(region, region.data, Vector(world_mm) * f())
    if c is None:
        raise Fail(f"{world_mm} is behind the view")
    return int(round(c.x)) + region.x, int(round(c.y)) + region.y


def ev(kind, value, xy, **mods):
    ctx()[0].event_simulate(kind, value, x=xy[0], y=xy[1], **mods)


def move(a, b, steps=6, **mods):
    for i in range(1, steps + 1):
        t = i / steps
        ev("MOUSEMOVE", "NOTHING", (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t)), **mods)
        yield 0.04


def key(kind, xy, **mods):
    ev(kind, "PRESS", xy, **mods)
    yield 0.05
    ev(kind, "RELEASE", xy, **mods)
    yield 0.2


def screenshot(label):
    path = os.path.join(OUT, f"{len(shots) + 1:02d}-{label}.png")
    try:
        with override():
            bpy.ops.screen.screenshot(filepath=path)
        if _max_pixel(path) < 0.02:  # the screen can't be read back (software OpenGL): render the viewport
            _offscreen_shot(path)
            path += " (offscreen viewport render)"
        shots.append(path)
    except Exception as e:
        shots.append(f"{path}: failed ({type(e).__name__}: {e})")


def _max_pixel(path):
    img = bpy.data.images.load(path)
    try:
        a = np.empty(len(img.pixels), np.float32)
        img.pixels.foreach_get(a)
        return float(a.reshape(-1, 4)[:, :3].max()) if a.size else 0.0
    finally:
        bpy.data.images.remove(img)


def _offscreen_shot(path):
    import gpu
    _, area, region = ctx()
    w, h = region.width, region.height
    off = gpu.types.GPUOffScreen(w, h)
    try:
        off.draw_view3d(bpy.context.scene, bpy.context.view_layer, area.spaces.active, region,
                        region.data.view_matrix, region.data.window_matrix, do_color_management=True)
        buf = off.texture_color.read()
        buf.dimensions = w * h * 4
        pixels = np.array(buf, dtype=np.float32) / 255.0
    finally:
        off.free()
    img = bpy.data.images.new("gui-check-shot", w, h, alpha=True)
    try:
        img.pixels.foreach_set(pixels)
        img.filepath_raw, img.file_format = path, "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


# -- instrumentation (wrappers call the originals: nothing the add-on does is replaced) ----------------------

def instrument():
    gg = bs.gizmos.BLENDSOLID_GGT_parameters
    orig_prepare = gg.draw_prepare

    def draw_prepare(self, context):
        orig_prepare(self, context)
        rec.prepare.append((context.object.name, list(self.gizmos)))
        del rec.prepare[:-5]
    gg.draw_prepare = draw_prepare

    panel = bs.ui.BLENDSOLID_PT_part
    orig_panel = panel.draw

    def panel_draw(self, context):
        try:
            orig_panel(self, context)
            rec.panel.append(context.object.name if context.object else None)
        except Exception as e:
            rec.errors.append(f"panel: {type(e).__name__}: {e}")
            raise
    panel.draw = panel_draw

    orig_preview = bs.ops_draw._draw_preview

    def draw_preview(op_):
        try:
            mode = op_._mode() if op_._drawn is not None else None
            orig_preview(op_)
            rec.preview.append(mode)
        except Exception as e:
            rec.errors.append(f"preview: {type(e).__name__}: {e}")
    bs.ops_draw._draw_preview = draw_preview

    OP = bs.ops_draw.BLENDSOLID_OT_draw_solid
    orig_header, orig_finish, orig_invoke = OP._header, OP._finish, OP.invoke

    class AreaRecorder:
        def __init__(self, area):
            self.area = area

        def header_text_set(self, text):
            rec.headers.append(text)
            self.area.header_text_set(text)

    def header(self, context):
        orig_header(self, SimpleNamespace(area=AreaRecorder(context.area), scene=context.scene))

    def finish(self, context):
        orig_finish(self, context)
        rec.finish += 1
        rec.headers.append(None)

    def invoke(self, context, event):
        result = orig_invoke(self, context, event)
        rec.invoke.append((result, getattr(self, "_target", None) and self._target.name,
                           getattr(self, "_plane", None)))
        return result
    OP._header, OP._finish, OP.invoke = header, finish, invoke


def register_sidebar_copy():
    """The sidebar opens on its Item tab and a script can't switch tabs: show the BlendSolid panel's own draw()
    in the Item tab too (a check-only panel class), so it is drawn by a real UI region."""
    cls = type("GUICHECK_PT_part", (bs.ui.BLENDSOLID_PT_part,), {"bl_idname": "GUICHECK_PT_part",
                                                                  "bl_category": "Item",
                                                                  "bl_label": "BlendSolid (gui check)"})
    bpy.utils.register_class(cls)


class FakeLayout:
    """Records what a panel/menu draw() puts in its layout (labels, operators, properties)."""

    def __init__(self, items=None):
        self.items = [] if items is None else items
        self.enabled = True
        self.use_property_split = False

    def label(self, text="", icon="NONE"):
        self.items.append(("label", text))

    def operator(self, idname, text="", icon="NONE", **_):
        self.items.append(("op", idname, text))
        return SimpleNamespace()

    def prop(self, data, name, text=None, **_):
        self.items.append(("prop", name if text is None else text))

    def menu(self, *a, **k):
        self.items.append(("menu",) + a)

    def separator(self, *a, **k):
        pass

    def _sub(self, *a, **k):
        return FakeLayout(self.items)
    box = row = column = grid_flow = split = _sub


def panel_items(obj):
    layout = FakeLayout()
    with override():
        bpy.context.view_layer.objects.active = obj
        bs.ui.BLENDSOLID_PT_part.draw(SimpleNamespace(layout=layout), bpy.context)
    return layout.items


def labels(items):
    return [i[1] for i in items if i[0] == "label"]


# -- the steps -------------------------------------------------------------------------------------------------

S = {}  # names and numbers carried between steps


def step1():
    op(bpy.ops.object.select_all, action="SELECT")
    op(bpy.ops.object.delete)  # the default cube, light and camera
    expect(not bpy.data.objects[:], "the startup objects are still there")
    cursor()
    op(bpy.ops.blendsolid.add_box, length=40, width=30, height=20)
    box = active()
    expect(box.name == "Box" and box.select_get(), f"new part named {box.name}, selected {box.select_get()}")
    last = bpy.context.window_manager.operators[-1]
    expect(last.bl_idname == "BLENDSOLID_OT_add_box", f"last operator {last.bl_idname} (Adjust Last Operation)")
    layout = FakeLayout()
    bs.ops_add._draw_millimetres(SimpleNamespace(layout=layout), bs.primitives.PRIMITIVES["box"])
    expect(labels(layout.items) == ["Dimensions (millimetres)"] and
           [i[1] for i in layout.items if i[0] == "prop"] == ["length", "width", "height"],
           f"redo panel {layout.items}")
    t = time.monotonic()
    yield from settled("Box")
    first = time.monotonic() - t
    expect(close(mm3(ob("Box")), 24000), f"volume {mm3(ob('Box')):.1f} != 24000")
    expect((ob("Box").matrix_world.translation).length < 1e-9, "not at the cursor")
    # the Adjust Last Operation panel: change a value -> Blender undoes and re-runs the operator (ed.undo_redo)
    bpy.context.window_manager.operators[-1].length = 60
    op(bpy.ops.ed.undo_redo)
    yield from settled("Box")
    box = ob("Box")
    expect(len(parts()) == 1 and box is not None, f"redo made {[o.name for o in parts()]}")
    expect(close(mm3(box), 36000), f"after redo Length 60: volume {mm3(box):.1f} != 36000")
    yield from set_view((0, 0, 10))
    screenshot("box")
    return f"Box 40x30x20 -> 24000 mm³ (first result {first:.1f} s), redo Length 60 -> {mm3(box):.1f} mm³"


def step2():
    cursor((-100, 0, 0), (30, 0, 0))
    op(bpy.ops.blendsolid.add_cylinder, radius=10, height=20)
    cyl = active()
    S["cyl_tilted"] = cyl.name
    diff = max(abs(a - b) for ra, rb in zip(cyl.matrix_world, bpy.context.scene.cursor.matrix)
               for a, b in zip(ra, rb))
    expect(diff < 1e-6, f"cylinder matrix differs from the cursor's by {diff}")
    yield from settled(cyl.name)
    cyl = ob(S["cyl_tilted"])
    cur = bpy.context.scene.cursor.matrix.inverted()
    z = [(cur @ (cyl.matrix_world @ v.co)).z / f() for v in cyl.data.vertices]
    expect(abs(min(z)) < 1e-3 and abs(max(z) - 20) < 1e-3, f"cursor-frame z range {min(z):.3f}..{max(z):.3f}")
    expected = math.pi * 100 * 20
    expect(close(mm3(cyl), expected, 0.01), f"volume {mm3(cyl):.1f} != {expected:.1f}")
    cursor()
    expect(tuple(bpy.context.scene.cursor.rotation_euler) == (0, 0, 0), "cursor rotation not reset")
    return f"cylinder on the 30° cursor plane: z {min(z):.3f}..{max(z):.3f} mm, {mm3(cyl):.1f} mm³"


PRIMS = {  # kind: (values, place mm, expected volume)
    "sphere": ({}, (0, 100, 0), 4 / 3 * math.pi * 1000),  # tessellated: curved volumes within 2 %
    "cone": ({}, (50, 100, 0), math.pi * 20 / 3 * (100 + 50 + 25)),
    "torus": ({}, (120, 100, 0), 2 * math.pi ** 2 * 20 * 25),
    "wedge": ({}, (-80, 100, 0), 20 * 30 * (40 + 10) / 2),
}


def step3():
    names, details = {}, []
    for kind, (values, place, _) in PRIMS.items():
        cursor()
        op(getattr(bpy.ops.blendsolid, f"add_{kind}"), **values)
        obj = active()
        names[kind] = obj.name
        op(bpy.ops.transform.translate, value=Vector(place) * f())  # G: moved aside
        expect((ob(names[kind]).location - Vector(place) * f()).length < 1e-9, f"{kind} not moved")
    S["prims"] = names
    yield from settled(*names.values())
    for kind, (_, _, expected) in PRIMS.items():
        obj = ob(names[kind])
        expect(not obj.blendsolid_error, f"{kind}: {obj.blendsolid_error}")
        expect(close(mm3(obj), expected, 0.02), f"{kind} volume {mm3(obj):.1f} != {expected:.1f}")
        details.append(f"{kind} {mm3(obj):.0f}")
    items = panel_items(ob(names["cone"]))
    buttons = [i[1] for i in items if i[0] == "op" and i[1].startswith("blendsolid.add_")]
    props = [i[1] for i in items if i[0] == "prop"]
    expect(len(buttons) == 6, f"sidebar buttons {buttons}")
    expect("Cone 1 top radius" in props, f"sidebar parameters {props}")
    menu = FakeLayout()
    bs.ops_add.VIEW3D_MT_blendsolid_add.draw(SimpleNamespace(layout=menu), bpy.context)
    expect(len([i for i in menu.items if i[0] == "op"]) == 6, f"Shift+A menu {menu.items}")
    add_draws = bpy.types.VIEW3D_MT_add._dyn_ui_initialize()
    expect(bs.ops_add._add_menu_entry in add_draws, "BlendSolid is not in the Shift+A menu")
    # the real sidebar: open it (it starts on the Item tab; a script can't switch tabs, so the check-only panel
    # registered by register_sidebar_copy() lives there too) and let it draw
    win, area, _ = ctx()
    area.spaces.active.show_region_ui = True
    select(ob(names["cone"]))
    rec.panel.clear()
    yield from frames(4)
    drew = bool(rec.panel) and not rec.errors
    expect(drew, f"the real sidebar panel was not drawn (recorded {rec.panel}, errors {rec.errors})")
    yield from set_view((20, 60, 10), dist=0.45)
    screenshot("primitives")
    return f"{', '.join(details)} mm³; sidebar: 6 buttons, 'Cone 1 top radius'; real panel drawn: {drew}"


def gizmo_state(name):
    for obj_name, gzs in reversed(rec.prepare):
        if obj_name == name:
            return gzs
    return None


def step4():
    click(ob("Box"))
    rec.prepare.clear()
    yield from set_view((0, 0, 10))
    yield from until(lambda: gizmo_state("Box") is not None, 10, "the gizmo group's draw_prepare on Box")
    gzs = gizmo_state("Box")
    box = ob("Box")
    layout = bs.gizmos.arrow_matrices(box)
    expect(len(gzs) == 3 and [p for p, _, _ in layout] == ["box_1_length", "box_1_width", "box_1_height"],
           f"{len(gzs)} gizmos, layout {[p for p, _, _ in layout]}")
    starts = {}
    for gz, (param, basis, scale) in zip(gzs, layout):
        d = max(abs(a - b) for ra, rb in zip(gz.matrix_basis, basis) for a, b in zip(ra, rb))
        expect(d < 1e-6, f"{param}: gizmo matrix differs by {d}")
        offset = gz.target_get_value("offset")
        offset = offset[0] if hasattr(offset, "__len__") else offset
        starts[param] = (gz.matrix_basis @ Vector((0, 0, offset))) / f()
    want = {"box_1_length": (30, 0, 10), "box_1_width": (0, 15, 10), "box_1_height": (0, 0, 20)}
    for param, p in want.items():
        expect((starts[param] - Vector(p)).length < 1e-3, f"{param} arrow at {tuple(starts[param])}, not {p}")
    expect(all(v.length > 5 for v in starts.values()), "an arrow starts at the object origin (move gizmo)")
    detail = "3 arrows on the +X, +Y, top faces"
    if not SIM:
        return "PARTIAL: " + detail + "; drag: needs --enable-event-simulate (manual test)"
    before = bs.part.source_of(box)
    height_gz = gzs[2]
    base = px((0, 0, 20))
    up = px((0, 0, 40))
    direction = Vector((up[0] - base[0], up[1] - base[1])).normalized()
    found = None
    for d in range(2, 200, 3):
        at = (round(base[0] + direction.x * d), round(base[1] + direction.y * d))
        ev("MOUSEMOVE", "NOTHING", at)
        yield 0.03
        redraw()
        yield 0.03
        if height_gz.is_highlight:
            found = at
            break
    expect(found is not None, "no pixel highlights the height arrow")
    ev("LEFTMOUSE", "PRESS", found)
    yield 0.1
    target = (round(found[0] + direction.x * 120), round(found[1] + direction.y * 120))
    heights = []
    for i in range(1, 9):
        ev("MOUSEMOVE", "NOTHING", (round(found[0] + direction.x * 15 * i), round(found[1] + direction.y * 15 * i)))
        yield 0.15
        heights.append(ob("Box").blendsolid_params["box_1_height"].value)
    ev("LEFTMOUSE", "RELEASE", target)
    yield 0.3
    yield from settled("Box")
    box = ob("Box")
    h = box.blendsolid_params["box_1_height"].value
    expect(h > 21 and heights == sorted(heights) and len(set(heights)) > 1,
           f"height after the drag {h:.3f}, during {heights}")
    expect(f"box_1_height = {bs.script_model.fmt(h)}\n" in bs.part.source_of(box) or
           abs(bs.params.parse_params(bs.part.source_of(box))[2].value - h) < 1e-6, "script != panel value")
    expect(close(mm3(box), 60 * 30 * h), f"volume {mm3(box):.1f} != {60 * 30 * h:.1f}")
    yield from frames(2)
    screenshot("gizmo-drag")
    op(bpy.ops.ed.undo)
    yield from settled("Box")
    box = ob("Box")
    expect(bs.part.source_of(box) == before, "one Ctrl+Z did not restore the height before the drag")
    expect(close(mm3(box), 36000), f"after undo volume {mm3(box):.1f}")
    return detail + f"; drag -> height {h:.3f} mm ({60 * 30 * h:.0f} mm³, heights while dragging " \
                    f"{[round(x, 2) for x in heights]}); one undo -> 20 mm"


def step5():
    click(ob("Box"))
    op(bpy.ops.transform.resize, value=(2, 2, 2))
    box = ob("Box")
    expect(bs.part.is_scaled(box), "not scaled")
    expect("This part is scaled" in labels(panel_items(box)), "the panel has no scale warning")
    with override():
        poll = bs.gizmos.BLENDSOLID_GGT_parameters.poll(bpy.context)
    expect(not poll, "the gizmo group still polls True on a scaled part")
    rec.prepare.clear()
    yield from frames(4)
    expect(gizmo_state("Box") is None, "arrows were drawn on the scaled part")
    screenshot("scaled")
    op(bpy.ops.ed.undo)
    box = ob("Box")
    expect(not bs.part.is_scaled(box), "undo did not restore scale 1")
    yield from frames(3)
    expect(gizmo_state("Box") is not None, "arrows did not come back after the undo")
    return "panel 'This part is scaled', gizmo poll False, no arrows drawn; undo -> scale 1, arrows back"


def last_op(idname="BLENDSOLID_OT_draw_solid"):
    ops = bpy.context.window_manager.operators
    expect(len(ops) and ops[-1].bl_idname == idname, f"last operator is not {idname}")
    return ops[-1]


def draw_events(base_a, base_b, height_at, ctrl=False, shift=False, warm=True):
    """Drag the base from world point base_a to base_b (mm), release, move to height_at, click."""
    mods = {"ctrl": ctrl, "shift": shift}
    a, b, c = px(base_a), px(base_b), px(height_at)
    if warm:  # the first simulated press after a pause may only focus the window: a throwaway press first
        yield from move(a, a, 1)
        ev("ESC", "PRESS", a)
        yield 0.1
        ev("ESC", "RELEASE", a)
        yield 0.1
    yield from move(a, a, 1, **mods)
    ev("LEFTMOUSE", "PRESS", a, **mods)
    yield 0.1
    yield from move(a, b, **mods)
    ev("LEFTMOUSE", "RELEASE", b, **mods)
    yield 0.1
    yield from move(b, c, **mods)
    yield 0.2
    ev("LEFTMOUSE", "PRESS", c, **mods)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", c, **mods)
    yield 0.3


def warm_up(at=(0, 0, 0)):
    """A throwaway click (the very first simulated press is only used to focus the window)."""
    a = px(at)
    ev("MOUSEMOVE", "NOTHING", a)
    yield 0.2
    ev("LEFTMOUSE", "PRESS", a)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", a)
    yield 0.1
    yield from key("ESC", a)


def box_volume(o):
    return o.length * o.width * o.height


def step6():
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.draw_solid_tool")
    tool = bpy.context.workspace.tools.from_space_view3d_mode("OBJECT")
    expect(tool.idname == "blendsolid.draw_solid_tool", f"active tool {tool.idname}")
    bpy.context.scene.blendsolid_draw_shape = "BOX"  # the tool's shape is a scene setting
    # the preview callback in the real viewport, with a synthetic drawn state
    drawn = bs.drawing.Drawn("CYLINDER", bs.drawing.plane_at_cursor(bpy.context.scene.cursor.matrix), radius=8,
                             height=12)
    # Ctrl held (_snap > 0): the grid around the dragged corner, then the height ticks; labels in pixel space
    plane = bs.drawing.plane_at_cursor(bpy.context.scene.cursor.matrix)
    labelled = []

    def labels(op_):
        try:
            bs.ops_draw._draw_labels(op_)
            labelled.append(op_._stage)
        except Exception as e:
            rec.errors.append(f"labels: {type(e).__name__}: {e}")
    for stage in ("BASE", "HEIGHT"):
        fake = SimpleNamespace(_drawn=drawn, _factor=f(), _mode=lambda: "UNION", _snap=5.0, _stage=stage,
                               _plane=plane, _p1=(8 * f(), 0.0), _base=drawn, _target=None)
        rec.preview.clear()
        handle = bpy.types.SpaceView3D.draw_handler_add(bs.ops_draw._draw_preview, (fake,), "WINDOW", "POST_VIEW")
        label_handle = bpy.types.SpaceView3D.draw_handler_add(labels, (fake,), "WINDOW", "POST_PIXEL")
        try:
            yield from set_view((0, 0, 10))
            yield from until(lambda: rec.preview and stage in labelled, 10, "the preview callback to draw")
            screenshot(f"preview-synthetic-{stage.lower()}")
        finally:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
            bpy.types.SpaceView3D.draw_handler_remove(label_handle, "WINDOW")
    expect(not [e for e in rec.errors if e.startswith(("preview", "labels"))], f"preview errors {rec.errors}")
    n_parts = len(parts())
    deselect()
    if SIM:
        yield from set_view((80, -60, 0))
        yield from warm_up()
        rec.headers.clear()
        rec.preview.clear()
        yield from draw_events((70, -65, 0), (90, -55, 0), (80, -60, 8))
        o = last_op()
        expect(o.mode == "NEW" and o.shape == "BOX", f"mode {o.mode}, shape {o.shape}")
        expect(abs(o.length - 20) < 1 and abs(o.width - 10) < 1 and abs(o.height - 8) < 1,
               f"drawn {o.length:.2f} x {o.width:.2f} x {o.height:.2f}, wanted about 20 x 10 x 8")
        expect("NEW" in rec.preview, f"preview modes {set(rec.preview)}")
        expect(any(h and h.startswith("Draw Solid: drag the base") for h in rec.headers) and
               any(h and "new part" in h for h in rec.headers), f"headers {rec.headers[:3]}")
        how = "drawn with simulated mouse events"
    else:
        op(bpy.ops.blendsolid.draw_solid, shape="BOX", mode="NEW", location=(80, -60, 0), rotation=(0, 0, 0),
           length=20, width=10, height=8)
        how = "execute path (no event simulation)"
    new = active()
    expect(len(parts()) == n_parts + 1 and new.name.startswith("Box"), f"new part {new.name if new else None}")
    S["grid_box"] = new.name
    o = last_op()
    vol = box_volume(o)
    yield from settled(new.name)
    expect(close(mm3(ob(new.name)), vol), f"volume {mm3(ob(new.name)):.1f} != {vol:.1f}")
    screenshot("draw-grid")
    o.height = 15  # Adjust Last Operation: Height
    op(bpy.ops.ed.undo_redo)
    yield from settled(S["grid_box"])
    g = ob(S["grid_box"])
    o = last_op()
    expect(len(parts()) == n_parts + 1 and abs(o.height - 15) < 1e-9, "redo made another part")
    expect(close(mm3(g), box_volume(o)), f"after redo Height 15: {mm3(g):.1f} != {box_volume(o):.1f}")
    return (f"{how}; New Part {S['grid_box']} {o.length:.2f} x {o.width:.2f} mm, redo Height 15 -> "
            f"{mm3(g):.1f} mm³; synthetic preview drew {len(rec.preview) or 'n'} frame(s)")


def step7():
    deselect()
    box = ob("Box")
    v0, n_parts, n_feat = mm3(box), len(parts()), len(features(box))
    if SIM:
        yield from set_view((0, 0, 20))
        rec.headers.clear()
        rec.preview.clear()
        yield from draw_events((-10, -5, 20), (10, 5, 20), (0, 0, 25))
        expect(any(h and "union with Box" in h for h in rec.headers), f"headers {set(rec.headers)}")
        expect("UNION" in rec.preview, f"preview modes {set(rec.preview)}")
        how = "simulated mouse; header 'union with Box', UNION preview mode"
    else:
        op(bpy.ops.blendsolid.draw_solid, shape="BOX", mode="UNION", target="Box", location=(0, 0, 20),
           rotation=(0, 0, 0), length=20, width=10, height=5)
        how = "execute path"
    o = last_op()
    expect(o.mode == "UNION" and o.target == "Box", f"mode {o.mode}, target {o.target!r}")
    expect(len(parts()) == n_parts and len(features(ob("Box"))) == n_feat + 1, "not one more feature on Box")
    yield from settled("Box")
    added = box_volume(o)
    expect(close(mm3(ob("Box")), v0 + added), f"volume {mm3(ob('Box')):.1f} != {v0 + added:.1f}")
    screenshot("draw-union")
    return f"{how}; Box +{added:.1f} mm³ -> {mm3(ob('Box')):.1f}"


def step8():
    deselect()
    bpy.context.scene.blendsolid_draw_shape = "CYLINDER"
    v0 = mm3(ob("Box"))
    if SIM:
        yield from set_view((20, 0, 20))
        rec.headers.clear()
        rec.preview.clear()
        yield from draw_events((20, 0, 20), (24, 0, 20), (20, 0, 14))
        expect(any(h and "cut from Box" in h for h in rec.headers), f"headers {set(rec.headers)}")
        expect("CUT" in rec.preview, f"preview modes {set(rec.preview)}")
        how = "simulated mouse; header 'cut from Box', CUT preview mode"
    else:
        op(bpy.ops.blendsolid.draw_solid, shape="CYLINDER", mode="CUT", target="Box", location=(20, 0, 20),
           rotation=(0, 0, 0), radius=4, height=6)
        how = "execute path"
    o = last_op()
    expect(o.shape == "CYLINDER" and o.mode == "CUT", f"shape {o.shape}, mode {o.mode}")
    r, h = o.radius, o.height
    expect(features(ob("Box"))[-1][1] == "SUBTRACT", f"last feature {features(ob('Box'))[-1]}")
    yield from settled("Box")
    expect(close(mm3(ob("Box")), v0 - math.pi * r * r * h), f"cut volume {mm3(ob('Box')):.1f}")
    screenshot("draw-cut")
    o.mode = "UNION"  # Adjust Last Operation: Mode -> Union
    op(bpy.ops.ed.undo_redo)
    yield from settled("Box")
    expect(features(ob("Box"))[-1][1] == "ADD", f"after redo Union: {features(ob('Box'))[-1]}")
    expect(close(mm3(ob("Box")), v0 + math.pi * r * r * h), f"boss volume {mm3(ob('Box')):.1f}")
    o = last_op()
    o.radius = 3
    op(bpy.ops.ed.undo_redo)
    yield from settled("Box")
    expect(close(mm3(ob("Box")), v0 + math.pi * 9 * h), f"radius 3 volume {mm3(ob('Box')):.1f}")

    return (f"{how}; hole r {r:.2f} h {h:.2f}; redo Union -> boss; "
            f"redo Radius 3 -> {mm3(ob('Box')):.1f} mm³")


def step9():
    if not SIM:
        return "SKIP: needs --enable-event-simulate (manual test)"
    deselect()
    bpy.context.scene.blendsolid_draw_shape = "BOX"  # the tool's shape is a scene setting
    out = []
    for place, shift, step_mm in (((80, -100, 0), False, 1.0), ((80, -140, 0), True, 0.1)):
        yield from set_view(place)
        rec.headers.clear()
        x, y, _ = place
        yield from draw_events((x - 9.37, y - 4.61, 0), (x + 9.71, y + 4.83, 0), (x, y, 7.44), ctrl=True, shift=shift)
        o = last_op()
        vals = (o.length, o.width, o.height)
        expect(o.mode == "NEW", f"mode {o.mode}")
        expect(all(abs(v / step_mm - round(v / step_mm)) < 1e-4 for v in vals),
               f"{'Shift+' if shift else ''}Ctrl: {vals} not multiples of {step_mm} mm")
        expect(any(h and f"{o.length:.3f} x {o.width:.3f} mm" in h for h in rec.headers), "header not snapped")
        out.append(f"{'Shift+Ctrl' if shift else 'Ctrl'} {vals[0]:g} x {vals[1]:g} x {vals[2]:g}")
        yield from settled(active().name)
        expect(close(mm3(active()), box_volume(o)), "volume")
        deselect()
    return "; ".join(out) + " mm"


def step10():
    if not SIM:
        return "SKIP: needs --enable-event-simulate (manual test)"
    deselect()
    yield from set_view((80, -60, 0))
    before = {o.name: bs.part.source_of(o) for o in parts()}
    a, b = px((60, -80, 0)), px((70, -85, 0))
    yield from warm_up()
    finish0 = rec.finish
    ev("LEFTMOUSE", "PRESS", a)
    yield 0.1
    yield from move(a, b)
    yield from key("ESC", b)
    ev("LEFTMOUSE", "RELEASE", b)
    yield 0.2
    expect(rec.finish == finish0 + 1 and rec.headers[-1] is None, "Esc did not end the drawing")
    ev("LEFTMOUSE", "PRESS", a)
    yield 0.1
    yield from move(a, b)
    ev("LEFTMOUSE", "RELEASE", b)
    yield 0.1
    yield from move(b, px((70, -85, 6)))
    yield from key("RIGHTMOUSE", b)
    expect(rec.finish == finish0 + 2 and rec.headers[-1] is None, "right-click did not end the drawing")
    after = {o.name: bs.part.source_of(o) for o in parts()}
    expect(after == before, "cancelling changed the parts")
    return "Esc during the base and right-click during the height: nothing added, header cleared"


def step11():
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    cursor((-20, 0, -10))
    op(bpy.ops.blendsolid.add_cylinder, radius=5, height=40)
    S["cutter"] = cutter = active().name
    cursor()
    yield from settled("Box", cutter)
    v0 = mm3(ob("Box"))
    click(ob("Box"), ob(cutter))
    if SIM:
        yield from set_view((0, 0, 10))
        yield from key("NUMPAD_MINUS", px((0, -40, 0)), ctrl=True)
        how = "Ctrl+Numpad - (simulated key)"
    else:
        op(bpy.ops.blendsolid.boolean, operation="DIFFERENCE")
        how = "operator"
    expect(features(ob("Box"))[-1] == ("bool_1", "SUBTRACT"),
           f"{how}: last feature {features(ob('Box'))[-1]}, selection {[o.name for o in bpy.context.selected_objects]}")
    c = ob(cutter)
    expect(c.display_type == "WIRE" and c.hide_render, "the cutter is not wire / not render-hidden")
    expect(not c.visible_get() and c.parent == ob("Box") and
           [x.name for x in c.users_collection] == [bs.ops_boolean.CUTTERS],
           "the cutter is not put away (hidden, parented to Box, in the cutters collection; ADR 0011)")
    yield from settled("Box", cutter)
    hole = math.pi * 25 * 20
    expect(close(mm3(ob("Box")), v0 - hole), f"hole: {mm3(ob('Box')):.1f} != {v0 - hole:.1f}")
    screenshot("live-cutter")
    # the sidebar's Select Cutter brings it back, selected and active
    op(bpy.ops.blendsolid.select_cutter, part_id=bs.part.part_id(ob(cutter)))
    expect(ob(cutter).visible_get() and active() == ob(cutter), "Select Cutter did not show and select it")
    # G: move half out of the box's -X side (the box spans x -30..30): half the hole goes
    click(ob(cutter))
    op(bpy.ops.transform.translate, value=Vector((-10, 0, 0)) * f())
    yield from settled("Box")
    expect(close(mm3(ob("Box")), v0 - hole / 2, 0.01), f"moved half out: {mm3(ob('Box')):.1f} != {v0 - hole / 2:.1f}")
    # R: 90° about X, then G so the cylinder lies across the box along Y through (-20, 0, 10)
    op(bpy.ops.transform.rotate, value=math.radians(90), orient_axis="X")
    c = ob(cutter)
    axis = c.matrix_world.to_3x3().col[2].normalized()
    expect(abs(abs(axis.y) - 1) < 1e-6, f"rotated axis {tuple(axis)}")
    centre = c.matrix_world.translation / f() + axis * 20
    op(bpy.ops.transform.translate, value=(Vector((-20, 0, 10)) - centre) * f())
    yield from settled("Box")
    across = math.pi * 25 * 30
    expect(close(mm3(ob("Box")), v0 - across, 0.01), f"across: {mm3(ob('Box')):.1f} != {v0 - across:.1f}")
    # the cutter's radius in the panel (the parameter's mirror property, as the sidebar field writes it)
    ob(cutter).blendsolid_params["cylinder_1_radius"].value = 3
    bpy.ops.ed.undo_push(message="radius")
    yield from settled("Box", cutter)
    across = math.pi * 9 * 30
    expect(close(mm3(ob("Box")), v0 - across, 0.01), f"radius 3: {mm3(ob('Box')):.1f} != {v0 - across:.1f}")
    S["box_with_cutter"] = mm3(ob("Box"))
    S["v_no_hole"] = v0
    screenshot("cutter-moved")
    return (f"{how}: hole {v0 - mm3(ob('Box')):.1f} mm³ ({hole:.1f} through, then half out, across after R/G), "
            f"radius 3 in the panel -> {mm3(ob('Box')):.1f} mm³; cutter put away (wire, hidden, parented, "
            f"collection), back with Select Cutter")


def step12():
    out = []
    for operation, keyname, expected in (("UNION", "NUMPAD_PLUS", 40 * 30 * 10 + math.pi * 9 * 10),
                                         ("INTERSECT", "NUMPAD_ASTERIX", math.pi * 9 * 10)):
        y = -110 if operation == "UNION" else -170
        cursor((0, y, 0))
        op(bpy.ops.blendsolid.add_box, length=40, width=30, height=10)
        target = active().name
        cursor((5, y, -5))
        op(bpy.ops.blendsolid.add_cylinder, radius=3, height=20)
        cutter = active().name
        cursor()
        click(ob(target), ob(cutter))
        if SIM:
            before_sel = {o.name for o in bpy.context.selected_objects}
            yield from set_view((0, y, 0))
            yield from key(keyname, px((0, y, 0)), ctrl=True)
            after_sel = {o.name for o in bpy.context.selected_objects}
            expect(after_sel == before_sel - {cutter}, f"selection changed {before_sel} -> {after_sel}: "
                                                       f"object.select_more/select_less may have run instead "
                                                       f"(the cutter alone leaves it: hidden, ADR 0011)")
        else:
            op(bpy.ops.blendsolid.boolean, operation=operation)
        mode = {"UNION": "ADD", "INTERSECT": "INTERSECT"}[operation]
        expect(features(ob(target))[-1][1] == mode, f"{operation}: {features(ob(target))}")
        yield from settled(target, cutter)
        expect(close(mm3(ob(target)), expected, 0.01), f"{operation}: {mm3(ob(target)):.1f} != {expected:.1f}")
        out.append(f"{operation.lower()} {mm3(ob(target)):.1f}")
    menu = FakeLayout()
    bs.ops_boolean.VIEW3D_MT_blendsolid_boolean.draw(SimpleNamespace(layout=menu), bpy.context)
    expect([i[2] for i in menu.items if i[0] == "op"] == ["Difference", "Union", "Intersect"], f"menu {menu.items}")
    expect(bs.ops_boolean._object_menu_entry in bpy.types.VIEW3D_MT_object._dyn_ui_initialize(),
           "BlendSolid Boolean is not in the Object menu")
    others = []
    kc = bpy.context.window_manager.keyconfigs.user
    for km in kc.keymaps:
        for kmi in km.keymap_items:
            if kmi.active and kmi.ctrl and kmi.type in bs.ops_boolean.KEYS.values() and \
                    kmi.idname != "blendsolid.boolean" and km.name in ("Object Mode", "Object Non-modal", "Window",
                                                                      "Screen", "3D View"):
                others.append(f"{km.name}: {kmi.idname}")
    screenshot("booleans")
    return (f"{', '.join(out)} mm³ ({'Ctrl+Numpad keys, boolean ran, selection unchanged' if SIM else 'operator'}); "
            f"Object menu entry present; other Ctrl+Numpad bindings: {others or 'none'}")


def step13():
    cutter = ob(S["cutter"])
    expect(cutter.display_type == "WIRE", "no wire cutter")
    # the cutter runs along Y through (-20, *, 10), radius 3, sticking 5 mm out of the box's -Y face (y = -15),
    # where it cut a hole. Look at a point P of that face beside the hole, along a line that first crosses the
    # part of the cutter sticking out (Q): the tool must look through the cutter and draw on the face.
    p_mm, q_mm = Vector((-16, -15, 10)), Vector((-20, -18, 10))
    d = (p_mm - q_mm).normalized()
    _, _, region = ctx()
    region.data.view_perspective = "PERSP"
    region.data.view_rotation = d.to_track_quat("-Z", "Z")
    region.data.view_location = p_mm * f()
    region.data.view_distance = 0.1
    yield from frames(3)
    at = px(p_mm)
    coord = (at[0] - region.x, at[1] - region.y)
    origin = view3d_utils.region_2d_to_origin_3d(region, region.data, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, region.data, coord)
    hit = bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(), origin, direction)
    expect(hit[0] and hit[4].original.name == S["cutter"], f"first hit {hit[4].name if hit[0] else None}, "
                                                           f"not the cutter")
    if SIM:
        deselect()
        with override():
            bpy.ops.wm.tool_set_by_id(name="blendsolid.draw_solid_tool")
        yield from warm_up()
        rec.invoke.clear()
        ev("MOUSEMOVE", "NOTHING", at)
        yield 0.1
        ev("LEFTMOUSE", "PRESS", at)
        yield 0.2
        yield from key("ESC", at)
        ev("LEFTMOUSE", "RELEASE", at)
        yield 0.1
        expect(rec.invoke, "the tool did not start")
        _, target, plane = rec.invoke[-1]
        how = "simulated press"
    else:
        with override():
            plane, target_obj = bs.ops_draw.pick_plane(bpy.context, origin, direction)
        target = target_obj.name if target_obj else None
        how = "pick_plane on the viewport ray"
    normal, point = plane.col[2].xyz, plane.translation / f()
    expect(target == "Box", f"drawn on {target}")
    # the plane's origin is the part's origin projected on the face (the snap grid's), so check it lies on
    # the -Y face's plane rather than at the clicked point
    expect((normal - Vector((0, -1, 0))).length < 1e-6 and abs(point.y - p_mm.y) < 0.2,
           f"plane normal {tuple(normal)}, at {tuple(point)}")
    screenshot("through-cutter")
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    return f"{how}: first ray hit is the wire cutter, the tool picked Box's -Y face (y = {point.y:.3f} mm)"


def step14():
    # A deleted cutter keeps cutting (its script is kept, the target remembers where it was) and can be
    # restored from the panel; undo brings the object itself back too.
    cutter = S["cutter"]
    yield from settled("Box", cutter)
    v = mm3(ob("Box"))
    click(ob(cutter))
    op(bpy.ops.object.delete)
    expect(ob(cutter) is None, "the cutter was not deleted")
    for _ in range(10):
        yield 0.1
    expect(not ob("Box").blendsolid_error, f"error on Box: {ob('Box').blendsolid_error}")
    expect(close(mm3(ob("Box")), v), f"the cut changed: {mm3(ob('Box')):.1f} != {v:.1f}")
    booleans = bs.deps.booleans(ob("Box"))
    expect(any(b.deleted and b.name == cutter for b in booleans), f"the panel doesn't list {cutter} as deleted")
    screenshot("deleted-cutter")
    op(bpy.ops.ed.undo)
    yield from settled("Box", cutter)
    expect(ob(cutter) is not None, "undo did not bring the cutter back")
    expect(close(mm3(ob("Box")), v), f"hole changed: {mm3(ob('Box')):.1f} != {v:.1f}")
    return f"deleted: Box keeps its cut, no error, listed as deleted; undo -> cutter back, {mm3(ob('Box')):.1f} mm³"


def snapshot():
    return {o.name: (bs.part.source_of(o), round(mm3(o), 1)) for o in parts()}


def consistent(label, bad, timeout=60.0):
    """Wait until every part's mesh is up to date (or shows its error) and its panel mirrors its script."""
    def ok():
        return all((up_to_date(o) or o.blendsolid_error) and params_match(o) for o in parts())
    try:
        yield from until(ok, timeout, label)
    except Fail:
        for o in parts():
            if not ((up_to_date(o) or o.blendsolid_error) and params_match(o)):
                found = {p.name: p.value for p in bs.params.parse_params(bs.part.source_of(o))}
                have = {p.name: round(p.value, 4) for p in o.blendsolid_params}
                log(f"{label}: {o.name} up to date {up_to_date(o)}, error {o.blendsolid_error!r}, "
                    f"inflight {bs.runtime._inflight.get(o.name)}, failed {bs.runtime._failed.get(o.name)}, "
                    f"synced {bs.runtime._synced.get(o.name)} tag {bs.part.current_tag(o)}, "
                    f"script {found}, panel {have}")
                bad.append(f"{label}: {o.name}")


def step15():
    yield from settled()
    end = snapshot()
    undos = 0
    bad = []
    while undos < 400:
        with override():
            if not bpy.ops.ed.undo.poll():
                break
            bpy.ops.ed.undo()
        undos += 1
        yield from consistent(f"undo {undos}", bad)
    expect(not parts(), f"after {undos} undos the scene still has {[o.name for o in parts()]}")
    redos = 0
    while redos < undos:  # the step undone in step 14 (deleting the cutter) stays redoable after these
        with override():
            if not bpy.ops.ed.redo.poll():
                break
            bpy.ops.ed.redo()
        redos += 1
        yield from consistent(f"redo {redos}", bad)
    expect(undos == redos, f"{undos} undos but {redos} redos")
    with override():
        expect(bpy.ops.ed.redo.poll(), "step 14's undone deletion is not redoable any more")
    expect(not bad, f"solids not matching the panel: {bad[:5]}")
    now = snapshot()
    diff = [n for n in end if now.get(n) != end[n]] + [n for n in now if n not in end]
    expect(not diff, f"after redoing everything these differ: {diff}")
    return f"{undos} undos to the empty scene and {redos} redos back; every step matched its scripts"


def step16():
    prefs = bpy.context.preferences
    yield from settled()
    path = os.path.join(OUT, "gui-check.blend")
    with override():
        bpy.ops.wm.save_as_mainfile(filepath=path)
    saved = {o.name: (bs.part.applied_hash(o), round(mm3(o), 1)) for o in parts()}
    prefs.filepaths.use_scripts_auto_execute = False
    with override():
        bpy.ops.wm.open_mainfile(filepath=path)
    yield 0.5
    yield from frames(2)
    expect(bpy.data.filepath == path, f"open file {bpy.data.filepath}")
    expect(not bs.trust.file_trusted(), "the reopened file is trusted with Auto Run off")
    now = {o.name: (bs.part.applied_hash(o), round(mm3(o), 1)) for o in parts()}
    expect(now == saved, "the cached meshes differ from the saved ones")
    box, cutter = ob("Box"), ob(S["cutter"])
    items = panel_items(box)
    expect("Scripts in this file are not trusted" in labels(items) and
           any(i[0] == "op" and i[1] == "blendsolid.trust_scripts" for i in items), "no untrusted note in the panel")
    select(box)
    with override():
        poll = bpy.ops.blendsolid.recompute.poll()
    expect(not poll, "Recompute is enabled on an untrusted file")
    screenshot("reopened-untrusted")
    select(cutter)
    op(bpy.ops.transform.translate, value=Vector((0, 0, 20)) * f())  # the cutter leaves the box: no hole
    yield 2.0
    box = ob("Box")
    expect(bs.part.applied_hash(box) == saved["Box"][0] and bs.part.current_tag(box) != saved["Box"][0] and
           "Box" not in bs.runtime._inflight, "an untrusted part was recomputed after moving the cutter")
    with override():
        bpy.ops.blendsolid.trust_scripts()
    yield from settled("Box", S["cutter"])
    v = mm3(ob("Box"))
    want = saved["Box"][1] + math.pi * 9 * 30
    expect(close(v, want, 0.01), f"after trusting: {v:.1f} != {want:.1f} (hole gone)")
    select(ob("Box"))
    with override():
        expect(bpy.ops.blendsolid.recompute.poll(), "Recompute still disabled after trusting")
    screenshot("trusted")
    return f"reopened untrusted: cached meshes, Recompute off, no recompute on move; trusted -> {v:.1f} mm³"


def step17():
    """Milestone 2 (ADR 0008): Draw Solid on a part with a Bevel modifier (Limit Method Weight) starts on the
    face's exact plane and unites with the part; the modifier then bevels the new edges too."""
    deselect()
    cursor((0, 150, 0))
    op(bpy.ops.blendsolid.add_box, length=40, width=30, height=20)
    beveled = active()
    cursor()
    mod = beveled.modifiers.new("Bevel", "BEVEL")
    mod.limit_method, mod.width, mod.segments = "WEIGHT", 1 * f(), 3
    yield from settled(beveled.name)
    v0, n_feat = mm3(beveled), len(features(beveled))
    deselect()
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.draw_solid_tool")
    bpy.context.scene.blendsolid_draw_shape = "BOX"
    if SIM:
        yield from set_view((0, 150, 20))
        yield from warm_up()
        rec.headers.clear()
        yield from draw_events((-10, 145, 20), (10, 155, 20), (0, 150, 26), ctrl=True)
        expect(any(h and f"union with {beveled.name}" in h for h in rec.headers), f"headers {set(rec.headers)}")
        how = "simulated Ctrl drag"
    else:
        op(bpy.ops.blendsolid.draw_solid, shape="BOX", mode="UNION", target=beveled.name, location=(0, 0, 20),
           rotation=(0, 0, 0), length=20, width=10, height=5)
        how = "execute path"
    o = last_op()
    expect(o.mode == "UNION" and o.target == beveled.name, f"mode {o.mode}, target {o.target!r}")
    expect(len(features(ob(beveled.name))) == n_feat + 1, "not one more feature")
    expect(abs(o.location[2] - 20.0) < 1e-9, f"placed at z = {o.location[2]!r} mm, not on the face (20)")
    yield from settled(beveled.name)
    added = box_volume(o)
    expect(close(mm3(ob(beveled.name)), v0 + added), f"volume {mm3(ob(beveled.name)):.1f} != {v0 + added:.1f}")
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob(beveled.name).evaluated_get(bpy.context.evaluated_depsgraph_get()).data)
    holes = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    expect(holes == 0, f"{holes} open edges after the Bevel")
    screenshot("draw-on-beveled")
    return f"{how}; +{added:.1f} mm³ on {beveled.name} (z = {o.location[2]} mm), Bevel result closed"


def step18():
    """Milestone 2 phase C: the Fillet tool. Click an edge, Shift+click another (the selection holds both), then
    drag: one fillet feature naming both edges by reference, the part recomputed without error."""
    CLICK = bs.ops_fillet.BLENDSOLID_OT_fillet_click
    orig_header = CLICK._header

    class AreaRecorder:
        def __init__(self, area):
            self.area = area

        def header_text_set(self, text):
            rec.headers.append(text)
            self.area.header_text_set(text)
    CLICK._header = lambda self, context: orig_header(self, SimpleNamespace(area=AreaRecorder(context.area),
                                                                           scene=context.scene))
    deselect()
    obj = bs.part.new_part(bpy.context)  # the default part: box 40 x 30 x 20 from the origin, boss, fillet
    obj.location = (0.0, -0.2, 0.0)
    name = obj.name
    yield from settled(name)
    op(bpy.ops.ed.undo_push, message="Part for step 18")  # made from Python: not an undo step by itself
    v0, n_feat = mm3(ob(name)), len(features(ob(name)))
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.fillet_tool")
    bs.ops_fillet.select(None)
    if not SIM:
        return "SKIP: needs --enable-event-simulate"
    yield from set_view((20, -200, 20), rot_deg=(60, 0, 20), dist=0.15)
    yield from warm_up()
    front, right = px((30, -199.7, 20)), px((39.7, -185, 20))  # near the top front edge; near the top right edge
    for xy, shift in ((front, False), (right, True)):
        yield from move(xy, xy, 1, shift=shift)
        ev("LEFTMOUSE", "PRESS", xy, shift=shift)
        yield 0.1
        ev("LEFTMOUSE", "RELEASE", xy, shift=shift)
        yield 0.3
    sel_obj, refs = bs.ops_fillet.selection()
    expect(sel_obj is not None and sel_obj.name == name and len(refs) == 2, f"selection {refs}")
    expect(refs[0] == 'edge_between(face("box_1", "+Z"), face("box_1", "-Y"))', f"first pick {refs[0]}")
    expect(refs[1] == 'edge_between(face("box_1", "+X"), face("box_1", "+Z"))', f"second pick {refs[1]}")
    screenshot("fillet-selected")
    rec.headers.clear()
    start = px((20, -200, 20))
    yield from move(start, start, 1)
    ev("LEFTMOUSE", "PRESS", start)
    yield 0.1
    yield from move(start, (start[0], start[1] + 40), ctrl=True)
    yield 0.3
    screenshot("fillet-dragging")  # the immediate preview, the handle and the snap ticks (Windows: real window)
    expect(any(h and h.startswith("Fillet: radius") for h in rec.headers), f"headers {set(rec.headers)}")
    ev("LEFTMOUSE", "RELEASE", (start[0], start[1] + 40), ctrl=True)
    yield 0.3
    feats = features(ob(name))
    expect(len(feats) == n_feat + 1 and feats[-1][0] == "fillet_2", f"features {feats}")
    source = bs.part.source_of(ob(name))
    expect(f"fillet({refs[0]} + {refs[1]}, radius=fillet_2_radius)" in source, "the feature doesn't name both edges")
    for _ in range(40):
        yield 0.5
        if ob(name).blendsolid_error or up_to_date(ob(name)):
            break
    expect(ob(name).blendsolid_error == "", f"error {ob(name).blendsolid_error!r} (line {ob(name).blendsolid_error_line})")
    yield from settled(name)
    radius = next(p.value for p in ob(name).blendsolid_params if p.name == "fillet_2_radius")
    expect(ob(name).blendsolid_error == "" and mm3(ob(name)) < v0, f"error {ob(name).blendsolid_error!r}")
    screenshot("fillet-done")
    removed = v0 - mm3(ob(name))
    op(bpy.ops.ed.undo)
    yield from settled(name)
    expect(len(features(ob(name))) == n_feat and close(mm3(ob(name)), v0), "one undo doesn't remove the fillet")
    return f"2 edges picked by reference, dragged radius {radius:.2f} mm -> {removed:.1f} mm³ less; one undo removes it"


def step19():
    """Milestone 2 phase D: the Push/Pull tool. Press on the default part's +X face and drag outwards along its
    normal (a block is added), then on the top face and drag inwards (a pocket is cut); one feature and one undo
    step each."""
    deselect()
    obj = bs.part.new_part(bpy.context)  # box 40 x 30 x 20 from the origin, boss, fillet
    obj.location = (0.0, -0.4, 0.0)
    name = obj.name
    yield from settled(name)
    op(bpy.ops.ed.undo_push, message="Part for step 19")  # made from Python: not an undo step by itself
    v0, n_feat = mm3(ob(name)), len(features(ob(name)))
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.push_pull_tool")
    if not SIM:
        return "SKIP: needs --enable-event-simulate"
    yield from set_view((45, -385, 10), rot_deg=(70, 0, 50), dist=0.18)
    yield from warm_up()
    for start_mm, end_mm, sign in (((40, -392, 10), (52, -392, 10), 1), ((30, -396, 20), (30, -396, 14), -1)):
        yield from settled(name)
        a, b = px(start_mm), px(end_mm)
        yield from move(a, a, 1)
        ev("LEFTMOUSE", "PRESS", a, ctrl=True)
        yield 0.1
        yield from move(a, b, ctrl=True)
        yield 0.3
        screenshot(f"push-pull-dragging-{'out' if sign > 0 else 'in'}")
        ev("LEFTMOUSE", "RELEASE", b, ctrl=True)
        yield 0.3
    feats = [n for n, _ in features(ob(name))]
    expect(feats[n_feat:] == ["push_1", "push_2"], f"features {feats}")
    source = bs.part.source_of(ob(name))
    expect('extrude(face("box_1", "+X"), amount=push_1_amount, mode=Mode.ADD)' in source, "no pull on box_1 +X")
    expect('extrude(face("box_1", "+Z"), amount=-push_2_amount, mode=Mode.SUBTRACT)' in source, "no push on box_1 +Z")
    yield from settled(name)
    values = {p.name: p.value for p in ob(name).blendsolid_params}
    expect(ob(name).blendsolid_error == "", f"error {ob(name).blendsolid_error!r}")
    expect(abs(values["push_1_amount"] - 12) < 1.01 and abs(values["push_2_amount"] - 6) < 1.01,
           f"amounts {values['push_1_amount']}, {values['push_2_amount']} (Ctrl snapped, about 12 and 6)")
    screenshot("push-pull")
    op(bpy.ops.ed.undo)
    yield from settled(name)
    expect([n for n, _ in features(ob(name))][n_feat:] == ["push_1"], "one undo doesn't remove only the push")
    return (f"pull +X {values['push_1_amount']:g} mm, push top {values['push_2_amount']:g} mm "
            f"({mm3(ob(name)) - v0:+.1f} mm³ after undoing the push)")


def step20():
    """Latency of the live fillet preview: time from a script edit (as the Fillet drag makes one per mouse move)
    to the part's mesh showing it, and how many edits per second the tick keeps up with."""
    deselect()
    obj = bs.part.new_part(bpy.context)
    obj.location = (0.0, -0.6, 0.0)
    name = obj.name
    yield from settled(name)
    ref = 'edge_between(face("box_1", "+Z"), face("box_1", "-Y"))'
    base = bs.part.source_of(ob(name))
    lat = []
    for k in range(8):
        src, _ = bs.script_model.append_feature(base, bs.ops_fillet.feature_spec([ref], 1.0 + 0.25 * k))
        t = time.monotonic()
        ob(name).blendsolid_script.from_string(src)
        bs.runtime.kick()  # as the Fillet drag does
        while not up_to_date(ob(name)) and time.monotonic() - t < 10:
            yield 0.005
        lat.append(time.monotonic() - t)
    ob(name).blendsolid_script.from_string(base)
    yield from settled(name)
    ms = [round(x * 1000) for x in lat]
    return f"script edit -> mesh: {ms} ms (median {sorted(ms)[len(ms) // 2]} ms)"


def step21():
    """ADR 0011: a click on a face of the selected part (Blender's own select click, then BlendSolid's focus click)
    shows the arrows of the feature that made the face; a click in empty space deselects and hides them."""
    if not SIM:
        return "SKIP: needs --enable-event-simulate"
    # the click tools (Tweak, the default, and Select Box); Circle and Lasso take the press for their own modal
    tools = ["builtin.select", "builtin.select_box"]
    report = []
    for tool in tools:
        report.append(tool + ": " + (yield from _focus_clicks(tool)))
    return "; ".join(report)


def _focus_clicks(tool):
    with override():
        bpy.ops.wm.tool_set_by_id(name=tool)
    for o in list(bpy.data.objects):
        if o.name.startswith("Focus") or o.name == "Cube":  # the factory cube would swallow the part (--only 21)
            bpy.data.objects.remove(o)
    cursor((0, 300, 0))
    op(bpy.ops.blendsolid.add_box, length=40, width=30, height=20)
    active().name = "Focus"
    name = active().name
    cursor()
    op(bpy.ops.blendsolid.draw_solid, shape="CYLINDER", mode="CUT", target=name, location=(5, 5, 20),
       rotation=(0, 0, 0), radius=4, height=6)
    yield from settled(name)
    expect(ob(name).blendsolid_focus == "cut_1", f"Draw Solid left the focus on {ob(name).blendsolid_focus!r}")
    click(ob(name))
    yield from set_view((0, 300, 10), rot_deg=(15, 0, 10), dist=0.2)  # the hole's bottom in sight
    shown = []
    yield from key("ESC", px((80, 300, 20)))  # the first simulated event after a pause only focuses the window
    for where, want in (((-12, 290, 20), "box_1"), ((5, 305, 14), "cut_1")):
        at = px(where)
        ev("MOUSEMOVE", "NOTHING", at)
        yield 0.1
        ev("LEFTMOUSE", "PRESS", at)
        yield 0.05
        ev("LEFTMOUSE", "RELEASE", at)
        yield 0.3
        redraw()
        yield from frames(2)
        o = ob(name)
        expect(o.blendsolid_focus == want and o.select_get() and active() == o,
               f"click at {where}: focus {o.blendsolid_focus!r}, selected {o.select_get()}, active {active()}")
        gzs = gizmo_state(name)
        params = [p for p, _, _ in bs.gizmos.arrow_matrices(o)]
        expect(gzs is not None and len(gzs) == len(params) and all(p.startswith(want) for p in params),
               f"arrows after the click on {want}: {params}")
        shown.append(f"{want}: {params}")
    screenshot("focus-cut")
    ev("MOUSEMOVE", "NOTHING", px((80, 300, 20)))
    yield 0.1
    at = px((80, 300, 20))  # empty space beside the part
    ev("LEFTMOUSE", "PRESS", at)
    yield 0.05
    ev("LEFTMOUSE", "RELEASE", at)
    yield 0.3
    with override():
        polled = bs.gizmos.BLENDSOLID_GGT_parameters.poll(bpy.context)
    expect(not ob(name).select_get() and not polled, "a click in empty space left the part selected or its arrows on")
    return f"clicks focus {'; '.join(shown)}; empty-space click deselects, no arrows"


def _drag(start_mm, end_mm, press_mods=None, **mods):
    a, b = px(start_mm), px(end_mm)
    yield from move(a, a, 1, **mods)
    ev("LEFTMOUSE", "PRESS", a, **mods)
    yield 0.1
    yield from move(a, b, **mods)
    yield 0.3
    ev("LEFTMOUSE", "RELEASE", b, **mods)
    yield 0.3


def _path(points_mm, arcs=(), close=False, mistakes=None):
    """Click the points of a path (a drag into the points whose index is in `arcs`), then Enter (or click the
    first point again with `close`). `mistakes` {i: [(point mm, key, mods)]}: before point i, click each point and
    take it back with its key (Backspace, Ctrl+Z)."""
    xy = [px(p) for p in points_mm]
    for i, b in enumerate(xy):
        a = xy[i - 1] if i else b
        for wrong_mm, kind, mods in (mistakes or {}).get(i, []):
            wrong = px(wrong_mm)
            yield from move(a, wrong, ctrl=True)
            ev("LEFTMOUSE", "PRESS", wrong, ctrl=True)
            yield 0.1
            ev("LEFTMOUSE", "RELEASE", wrong, ctrl=True)
            yield 0.3
            yield from key(kind, wrong, **mods)
            a = wrong
        if i in arcs:  # press on the last point, drag to this one: a tangent arc
            yield from move(a, a, 1, ctrl=True)
            ev("LEFTMOUSE", "PRESS", a, ctrl=True)
            yield 0.1
            yield from move(a, b, ctrl=True)
            ev("LEFTMOUSE", "RELEASE", b, ctrl=True)
        else:
            yield from move(a, b, ctrl=True)
            ev("LEFTMOUSE", "PRESS", b, ctrl=True)
            yield 0.1
            ev("LEFTMOUSE", "RELEASE", b, ctrl=True)
        yield 0.3
    if close:
        yield from move(xy[-1], xy[0], ctrl=True)
        ev("LEFTMOUSE", "PRESS", xy[0], ctrl=True)
        yield 0.1
        ev("LEFTMOUSE", "RELEASE", xy[0], ctrl=True)
    else:
        yield from key("RET", xy[-1])
    yield 0.3


def step22():
    """Milestone 3a: the Sketch tool draws a path (line, tangent arc by a drag, line) and a line across a box's top
    face; the Groove tool cuts a groove along the path; Extrude Sketch pushes the face piece past the line down (a
    step); the Revolve Sketch tool turns a sketch drawn on the 3D cursor's plane about one of its lines; one undo
    step each."""
    if not SIM:
        return "SKIP: needs --enable-event-simulate"
    deselect()
    cursor((0, 800, 0))
    with override():
        bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True)
    name = active().name
    yield from settled(name)
    yield from set_view((0, 800, 10), rot_deg=(50, 0, 20), dist=0.16)
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.sketch_tool")
    yield from warm_up((30, 830, 0))
    bpy.context.scene.blendsolid_sketch_shape = "PATH"
    # before the first click the hover marker snaps to a top corner and names it (the maintainer's 2026-10-02
    # test: the label only showed after the first click)
    corner = px((20, 815, 20))
    yield from move(px((15, 810, 20)), corner, 4)
    yield from frames(3)
    with override():
        _, _, region = ctx()
        at = (corner[0] - region.x, corner[1] - region.y)
        o, d = bs.ops_draw.mouse_ray(bpy.context, at)
        target = bs.ops_sketch.hover_target(bpy.context, o, d, bs.ops_draw._near_rays(bpy.context, at))
        factor = bs.part.unit_factor(bpy.context.scene)
        uv = bs.ops_sketch.ray_uv(target.plane, o, d, factor)[0]
        snapped = bs.ops_sketch.snap_to_points(bpy.context, target, uv, factor, bs.ops_sketch.part_points(target))
    expect(snapped is not None and snapped[1] == "vertex" and tuple(snapped[0]) == (20.0, 15.0),
           f"hover snap {snapped}")
    screenshot("hover-vertex")
    # a line across the top face (z 20) at x = 12, started off the face on the far side, where the ray misses the
    # box (the maintainer's 2026-09-29 test): hovering the face first keeps its plane; then on the face a path of a
    # line, a tangent arc (a drag) and a line
    start = px((12, 825, 20))
    with override():
        _, _, region = ctx()
        at = (start[0] - region.x, start[1] - region.y)
        bare = bs.ops_sketch.pick_target(bpy.context, *bs.ops_draw.mouse_ray(bpy.context, at),
                                         bs.ops_draw._near_rays(bpy.context, at))
    expect(bare is not None and bare.obj is None, "the line's start is not off the part (the case to check)")
    yield from move(px((12, 810, 20)), start, 8)
    yield from _path([(12, 825, 20), (12, 775, 20)])
    # with two wrong clicks taken back (Backspace, Ctrl+Z: the maintainer's 2026-10-02 request)
    yield from _path([(-15, 795, 20), (5, 795, 20), (5, 805, 20), (-15, 805, 20)], arcs=(2,),
                     mistakes={2: [((0, 790, 20), "BACK_SPACE", {})], 3: [((-5, 812, 20), "Z", {"ctrl": True})]})
    source = bs.part.source_of(ob(name))
    entities = [e.name for e in bs.script_model.sketch_entities(source, "sketch_1")]
    expect(entities == ["path_1", "path_2"], f"sketch entities {entities}")
    expect("sketch_1.path_2 = path((-15.0, -5.0), (5.0, -5.0), arc_to((5.0, 5.0)), (-15.0, 5.0))" in source,
           "the second path isn't line, arc, line on the top face")
    expect('with sketch(on_face(face("box_1", "+Z"))) as sketch_1:' in source, "the sketch is not on the top face")
    yield from settled(name)
    screenshot("paths-on-face")
    import json
    drawn = json.loads(ob(name).data["bs_sketches"])[0]
    expect(len(drawn["regions"]) == 2, f"{len(drawn['regions'])} regions (the line should split the face in two)")
    v0 = mm3(ob(name))
    bpy.context.scene.blendsolid_groove_profile = "rect"
    bpy.context.scene.blendsolid_groove_width = 2.0
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.groove_tool")
    yield from frames(3)
    yield from _drag((-5, 795, 20), (-5, 795, 18), ctrl=True, shift=True)   # press on the path, drag in: groove
    yield from settled(name)
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.extrude_tool")
    yield from frames(3)
    yield from _drag((16, 800, 20), (16, 800, 15), ctrl=True)               # the face piece past the line: step
    yield from settled(name)
    feats = [n for n, _ in features(ob(name))]
    expect(feats == ["box_1", "sketch_1", "groove_1", "cut_1"], f"features {feats}")
    expect(ob(name).blendsolid_error == "", f"error {ob(name).blendsolid_error!r}")
    values = {p.name: p.value for p in ob(name).blendsolid_params}
    expect(abs(values["groove_1_depth"] - 2) < 0.11 and abs(values["cut_1_amount"] - 5) < 1.01,
           f"depth {values.get('groove_1_depth')}, step {values.get('cut_1_amount')}")
    length = 40 + 5 * math.pi
    want = v0 - 2 * values["groove_1_depth"] * length - 8 * 30 * values["cut_1_amount"]
    expect(close(mm3(ob(name)), want, 0.01), f"volume {mm3(ob(name)):.1f}, expected {want:.1f}")
    screenshot("groove-and-step")
    op(bpy.ops.ed.undo)
    yield from settled(name)
    expect([n for n, _ in features(ob(name))] == ["box_1", "sketch_1", "groove_1"], "one undo doesn't undo the step")
    # revolve: a sketch on the cursor plane (a new part), a rectangle and an axis line, then Revolve Sketch
    deselect()
    cursor((200, 900, 0), (90, 0, 0))
    yield from set_view((200, 900, 0), rot_deg=(90, 0, 0), dist=0.2)
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    yield from warm_up((240, 900, 30))
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.sketch_tool")
    bpy.context.scene.blendsolid_sketch_shape = "RECTANGLE"
    yield from _drag((215, 900, 0), (219, 900, 10), ctrl=True)
    sketch_part = active().name
    bpy.context.scene.blendsolid_sketch_shape = "PATH"
    yield from _path([(200, 900, -20), (200, 900, 20)])
    yield from settled(sketch_part)
    entities = [e.name for e in bs.script_model.sketch_entities(bs.part.source_of(ob(sketch_part)), "sketch_1")]
    expect(entities == ["rect_1", "path_1"], f"cursor sketch entities {entities}")
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.revolve_tool")
    yield from frames(3)
    yield from key("ESC", px((240, 900, 30)))
    a = px((217, 900, 5))
    yield from move(a, a, 1)
    ev("LEFTMOUSE", "PRESS", a)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", a)
    yield 0.3
    b = px((200, 900, 10))
    yield from move(a, b)
    ev("LEFTMOUSE", "PRESS", b)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", b)
    yield 0.3
    yield from settled(sketch_part)
    expect(ob(sketch_part).blendsolid_error == "", f"error {ob(sketch_part).blendsolid_error!r}")
    ring = 2 * math.pi * 17 * 40
    expect(close(mm3(ob(sketch_part)), ring, 0.02), f"revolved {mm3(ob(sketch_part)):.1f}, expected {ring:.1f}")
    screenshot("revolved")
    cursor()
    return (f"path with an arc + a line across the top face, groove {values['groove_1_depth']:g} mm, step "
            f"{values['cut_1_amount']:g} mm, undo; revolve {mm3(ob(sketch_part)):.0f} mm³")



def _active_tool():
    with override():
        return bpy.context.workspace.tools.from_space_view3d_mode("OBJECT").idname


def step23():
    """ADR 0013: the command pie. A right-button drag opens it (level 0); releasing over Edit (south) opens the
    Edit pie; a click on Fillet / Chamfer (west) activates the Fillet tool. E then opens the pie as a tap: a click
    on Sketch (east), then on Circle (south), activates the Sketch tool with the Circle shape. A right-click without a drag
    doesn't open the pie (it opens Blender's context menu, closed with Esc)."""
    if not SIM:
        return "SKIP: needs --enable-event-simulate"
    deselect()
    yield from set_view((0, 0, 0), rot_deg=(60, 0, 30), dist=0.3)
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    yield from warm_up((0, 0, 0))
    radius = bpy.context.preferences.view.pie_menu_radius * (bpy.context.preferences.system.ui_scale or 1.0)
    c = px((0, 0, 0))
    # a right-click, no drag: no pie, the tool doesn't change
    ev("MOUSEMOVE", "NOTHING", c)
    yield 0.2
    ev("RIGHTMOUSE", "PRESS", c)
    yield 0.1
    ev("RIGHTMOUSE", "RELEASE", c)
    yield 0.5
    screenshot("right-click-menu")  # on Windows (a real window): Blender's Object context menu
    yield from key("ESC", c)
    expect(_active_tool() == "builtin.select_box", f"a right-click changed the tool to {_active_tool()}")
    # right-drag down: level 0 opens, release over Edit (south) -> the Edit pie at the mouse
    ev("RIGHTMOUSE", "PRESS", c)
    yield 0.1
    s = (c[0], c[1] - int(radius))
    yield from move(c, s, 10)
    yield 0.3
    ev("RIGHTMOUSE", "RELEASE", s)
    yield 0.6
    w = (s[0] - int(radius), s[1])
    yield from move(s, w, 10)
    yield 0.3
    ev("LEFTMOUSE", "PRESS", w)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", w)
    yield 0.5
    expect(_active_tool() == "blendsolid.fillet_tool", f"right-drag > Edit > Fillet gave {_active_tool()}")
    # E tapped: the pie stays open; click Sketch (east), then Circle (south in the Sketch pie)
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    bpy.context.scene.blendsolid_sketch_shape = "PATH"
    ev("MOUSEMOVE", "NOTHING", c)
    yield 0.2
    yield from key("E", c)
    yield 0.4
    e = (c[0] + int(radius), c[1])
    yield from move(c, e, 10)
    yield 0.3
    ev("LEFTMOUSE", "PRESS", e)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", e)
    yield 0.6
    e2 = (e[0], e[1] - int(radius))  # the Sketch pie: Path W, Rectangle E, Circle S
    yield from move(e, e2, 10)
    yield 0.3
    ev("LEFTMOUSE", "PRESS", e2)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", e2)
    yield 0.5
    shape = bpy.context.scene.blendsolid_sketch_shape
    expect(_active_tool() == "blendsolid.sketch_tool" and shape == "CIRCLE",
           f"E > Sketch > Circle gave {_active_tool()} / {shape}")
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    return "right-drag > Edit > Fillet; E > Sketch > Circle; right-click leaves the tool alone"


def step24():
    """ADR 0015: E > Add > Box places a cube where the pie was opened (the 3D cursor's plane under the mouse), at
    a round size; moving the mouse away scales it; a click confirms: a cube with equal round sides, scale 1, at
    the point the pie was opened on. Esc on a second one leaves nothing behind."""
    if not SIM:
        return "SKIP: needs --enable-event-simulate"
    deselect()
    cursor((0, 0, 0))
    yield from set_view((5000, 5000, 0), rot_deg=(60, 0, 30), dist=2.0)  # away from the startup cube
    with override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    yield from warm_up((5000, 5000, 0))
    radius = bpy.context.preferences.view.pie_menu_radius * (bpy.context.preferences.system.ui_scale or 1.0)
    at = (5300, 5200, 0)
    c = px(at)
    before = set(bpy.data.objects.keys())
    ev("MOUSEMOVE", "NOTHING", c)
    yield 0.2
    yield from key("E", c)
    yield 0.4
    w = (c[0] - int(radius), c[1])
    yield from move(c, w, 8)
    ev("LEFTMOUSE", "PRESS", w)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", w)
    yield 0.6
    w2 = (w[0] - int(radius), w[1])
    yield from move(w, w2, 8)
    ev("LEFTMOUSE", "PRESS", w2)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", w2)
    yield 0.6
    new = [n for n in bpy.data.objects.keys() if n not in before]
    expect(len(new) == 1, f"new objects while placing: {new}")
    name = new[0]
    far = (w2[0] - int(radius), w2[1] - int(radius // 2))
    yield from move(w2, far, 10)
    yield 0.3
    scaled = ob(name).scale[0]
    ev("LEFTMOUSE", "PRESS", far)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", far)
    yield 0.3
    yield from settled(name)
    values = {p.name: p.value for p in ob(name).blendsolid_params}
    sides = [values.get("box_1_length"), values.get("box_1_width"), values.get("box_1_height")]
    expect(len(set(sides)) == 1 and sides[0] is not None, f"not a cube: {sides}")
    size = sides[0]
    mantissa = size / 10 ** math.floor(math.log10(size))
    expect(any(abs(mantissa - s) < 1e-9 for s in bs.primitives.DRAG_STEPS), f"size {size} is not a round step")
    expect(scaled > 1.01, f"moving the mouse away didn't grow it (scale {scaled})")
    expect(tuple(ob(name).scale) == (1.0, 1.0, 1.0), f"scale left at {tuple(ob(name).scale)}")
    loc = ob(name).matrix_world.translation / f()
    expect((loc - Vector(at)).length < 0.02 * 300, f"placed at {tuple(loc)}, pie opened at {at}")
    expect(close(mm3(ob(name)), size ** 3, 1e-3), f"volume {mm3(ob(name)):.0f}, expected {size ** 3:.0f}")
    screenshot("added-box")
    # a second one, cancelled with Esc: nothing left
    before = set(bpy.data.objects.keys())
    texts = len(bpy.data.texts)
    ev("MOUSEMOVE", "NOTHING", c)
    yield 0.2
    yield from key("E", c)
    yield 0.4
    yield from move(c, w, 8)
    ev("LEFTMOUSE", "PRESS", w)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", w)
    yield 0.6
    yield from move(w, w2, 8)
    ev("LEFTMOUSE", "PRESS", w2)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", w2)
    yield 0.6
    yield from key("ESC", w2)
    yield 0.3
    expect(set(bpy.data.objects.keys()) == before and len(bpy.data.texts) == texts,
           "Esc left a part or script behind")
    return f"E > Add > Box: a {size:g} mm cube at the pie's point; Esc leaves nothing"


def step25():
    """ADR 0014 (test6.blend): a Fillet drag far past what the edges allow stops at the largest radius that works,
    so the release leaves a part that builds; the fillet's radius is that limit."""
    if not SIM:
        return "SKIP: needs --enable-event-simulate"
    deselect()
    cursor((0, -3000, 0))
    with override():
        bpy.ops.blendsolid.add_box("EXEC_DEFAULT", True, length=40.0, width=30.0, height=20.0)
    name = active().name
    yield from settled(name)
    op(bpy.ops.ed.undo_push, message="Part for step 25")
    yield from set_view((0, -3000, 10), rot_deg=(60, 0, 20), dist=0.2)
    with override():
        bpy.ops.wm.tool_set_by_id(name="blendsolid.fillet_tool")
    bs.ops_fillet.select(None)
    yield from warm_up((70, -3000, 0))  # away from the face: a second press there would be a double click
    yield 0.5
    top = px((0, -3000, 20))  # the face's centre: the selected box's height arrow is hidden while the tool is active
    yield from move(top, top, 1)
    ev("LEFTMOUSE", "PRESS", top)
    yield 0.1
    ev("LEFTMOUSE", "RELEASE", top)
    yield 0.4
    _, refs = bs.ops_fillet.selection()
    expect(len(refs) == 1 and refs[0].startswith("edges_of("), f"selection {refs}")
    ev("LEFTMOUSE", "PRESS", top)
    yield 0.1
    here = top
    for k in range(1, 13):  # drag up in steps, letting the worker answer each one
        nxt = (top[0], top[1] + 25 * k)
        yield from move(here, nxt, 3)
        here = nxt
        yield 0.5
    ev("LEFTMOUSE", "RELEASE", here)
    yield 0.3
    for _ in range(40):
        yield 0.5
        if ob(name).blendsolid_error or up_to_date(ob(name)):
            break
    yield from settled(name)
    values = {p.name: p.value for p in ob(name).blendsolid_params}
    radius = values.get("fillet_1_radius")
    expect(ob(name).blendsolid_error == "", f"error {ob(name).blendsolid_error!r}")
    expect(radius is not None and 5 < radius < 15, f"radius {radius}")
    return f"a long drag stopped at the largest radius that works: {radius:g} mm, the part builds"

STEPS = [step1, step2, step3, step4, step5, step6, step7, step8, step9, step10, step11, step12, step13, step14,
         step15, step16, step17, step18, step19, step20, step21, step22, step23, step24, step25]


def scenario():
    prefs = bpy.context.preferences
    saved_prefs = (prefs.edit.undo_steps, prefs.filepaths.use_scripts_auto_execute)
    try:
        prefs.edit.undo_steps = 256  # step 15 undoes back to the empty scene
        prefs.filepaths.use_scripts_auto_execute = True
        yield 1.0
        name = next((m for m in sys.modules if m == "blendsolid" or
                     (m.startswith("bl_ext.") and m.endswith(".blendsolid"))), None)
        if name is None:
            raise Fail("the blendsolid add-on is not enabled")
        for sub in ("part", "runtime", "gizmos", "ops_add", "ops_boolean", "ops_draw", "drawing", "primitives",
                    "script_model", "params", "trust", "ui", "deps", "ops_fillet", "ops_pushpull", "picking", "focus",
                    "ops_sketch", "ops_extrude", "sketching"):
            setattr(bs, sub, importlib.import_module(f"{name}.{sub}"))
        log(f"add-on {name} from {os.path.dirname(sys.modules[name].__file__)}; event simulation: {SIM}; out {OUT}")
        instrument()
        register_sidebar_copy()
        if SIM:
            yield from set_view((0, 0, 0))
            yield from warm_up()
        for n, fn in enumerate(STEPS, 1):
            if ONLY is not None and n not in ONLY:
                continue
            try:
                detail = yield from fn()
                for prefix, status in (("SKIP: ", "SKIP"), ("PARTIAL: ", "PARTIAL")):
                    if str(detail).startswith(prefix):
                        results.append((n, status, detail[len(prefix):]))
                        break
                else:
                    results.append((n, "OK", detail))
            except Fail as e:
                results.append((n, "FAIL", str(e)))
            except Exception as e:
                results.append((n, "FAIL", f"{type(e).__name__}: {e}"))
                traceback.print_exc()
            n_, status, detail = results[-1]
            print(f"STEP {n_} {status} {detail}", flush=True)
            if rec.errors:
                print(f"STEP {n_} FAIL errors while drawing: {rec.errors}", flush=True)
                results.append((n_, "FAIL", f"draw errors {rec.errors}"))
                rec.errors.clear()
        if bs.runtime._client is not None and bs.runtime._client._proc is not None:
            print(f"WORKER PID {bs.runtime._client._proc.pid}", flush=True)
    finally:
        prefs.edit.undo_steps, prefs.filepaths.use_scripts_auto_execute = saved_prefs
        prefs.is_dirty = False  # never auto-save the preferences over this run
    for s in shots:
        print(f"SCREENSHOT {s}")
    failed = [r for r in results if r[1] == "FAIL"]
    skipped = [r for r in results if r[1] == "SKIP"]
    partial = [r for r in results if r[1] == "PARTIAL"]
    if skipped or partial:
        print(f"{len(skipped)} step(s) SKIP, {len(partial)} step(s) PARTIAL "
              f"(no --enable-event-simulate)", flush=True)
    wanted = len(STEPS) if ONLY is None else len(ONLY)
    print("GUI CHECK PASS" if len(results) >= wanted and not failed else "GUI CHECK FAIL", flush=True)


_gen = scenario()


def _tick():
    try:
        return next(_gen)
    except StopIteration:
        pass
    except Exception:
        traceback.print_exc()
        print("GUI CHECK FAIL", flush=True)
    try:
        bpy.context.preferences.is_dirty = False
    except Exception:
        pass
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(_tick, first_interval=1.0, persistent=True)
