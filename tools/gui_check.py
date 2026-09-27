"""Automated GUI-session check of milestone 1.5: the 16 steps of the manual GUI test (plan
docs/superpowers/plans/2026-09-26-milestone-1.5-build-without-selectors.md, Task 14, Step 1) walked through in
a real Blender window, without a person.

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


def warm_up():
    """A throwaway click (the very first simulated press is only used to focus the window)."""
    a = px((0, 0, 0))
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
    yield from settled("Box", cutter)
    hole = math.pi * 25 * 20
    expect(close(mm3(ob("Box")), v0 - hole), f"hole: {mm3(ob('Box')):.1f} != {v0 - hole:.1f}")
    screenshot("live-cutter")
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
            f"radius 3 in the panel -> {mm3(ob('Box')):.1f} mm³; cutter wire, not rendered")


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
            expect(after_sel == before_sel, f"selection changed {before_sel} -> {after_sel}: "
                                            f"object.select_more/select_less may have run instead")
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


STEPS = [step1, step2, step3, step4, step5, step6, step7, step8, step9, step10, step11, step12, step13, step14,
         step15, step16, step17]


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
                    "script_model", "params", "trust", "ui", "deps"):
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
