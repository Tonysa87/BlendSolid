"""File > Import / Export of STEP, IGES and BREP files (ADR 0016).

Import: each solid of the file becomes a part whose script inserts it, `insert(imported("<blob id>"))`, with its
shape kept in the .blend (blobs.py). Assemblies become nested collections under one named after the file; every
instance of a product is a linked duplicate of the first; colours become materials.
Export: the selected parts, or every visible part no other part uses as a cutter, built exactly by the worker from
their scripts and placed by their objects (not the display mesh: modifiers are not exported).
Both run in the worker and block Blender while it reads or writes (about a second for a large file).
"""
import os

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Matrix

from . import blobs, deps, part, runtime, script_model, trust

FILTER = "*.step;*.stp;*.iges;*.igs;*.brep;*.brp"
FORMATS = [("STEP", "STEP (.step)", "STEP AP214 with part names and colours"),
           ("IGES", "IGES (.iges)", "IGES solids (MSBO) with part names and colours"),
           ("BREP", "BREP (.brep)", "OpenCASCADE's own format: exact shapes, no names or colours")]
EXTENSIONS = {"STEP": ".step", "IGES": ".iges", "BREP": ".brep"}


def _matrix(values, factor):
    """A 3x4 row-major placement in millimetres as a Blender matrix in scene units (ADR 0003)."""
    m = Matrix([values[0:4], values[4:8], values[8:12], (0.0, 0.0, 0.0, 1.0)])
    m.translation = m.translation * factor
    return m


def _material(color, cache):
    """A material of linear RGBA `color` (Base Color and Viewport Display), one per colour."""
    key = tuple(round(c, 4) for c in color)
    mat = cache.get(key)
    if mat is None:
        r, g, b, a = key
        hexa = "".join(f"{round(max(0.0, min(1.0, c)) ** (1 / 2.2) * 255):02X}" for c in (r, g, b))
        mat = bpy.data.materials.new(f"CAD #{hexa}")
        mat.diffuse_color = (r, g, b, a)
        bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree is not None else None
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
            if a < 1.0:
                bsdf.inputs["Alpha"].default_value = a
        cache[key] = mat
    return mat


def _collection(parent, path, cache):
    """The collection for an assembly path ([[key, name], ...]) under `parent`, created on first use."""
    coll = parent
    for key, name in path:
        found = cache.get(key)
        if found is None:
            found = bpy.data.collections.new(name)
            coll.children.link(found)
            cache[key] = found
        coll = found
    return coll


def import_file(context, path):
    """Import `path`; returns (objects, report text) or raises RuntimeError with the user's message."""
    answer = runtime.exchange({"type": "import", "path": path})
    if not answer["ok"]:
        raise RuntimeError(answer["error"])
    parts = answer["parts"]
    if not parts:
        skipped = answer.get("skipped", 0)
        raise RuntimeError(f"{os.path.basename(path)} has no solids" +
                           (f" ({skipped} surface or wire bodies: only solids are imported)" if skipped else ""))
    factor = part.unit_factor(context.scene)
    root = bpy.data.collections.new(answer["name"])
    context.collection.children.link(root)
    collections, materials, texts, firsts, objects = {}, {}, {}, {}, []
    for item in parts:
        coll = _collection(root, item["path"], collections)
        first = firsts.get(item["product"])
        if first is None:
            blob = texts.get(item["blob"])
            if blob is None:
                blob = texts[item["blob"]] = blobs.store(item["blob"], answer["blobs"][item["blob"]], item["name"],
                                                         path)
            source, _ = script_model.new_script(script_model.import_spec(item["blob"]))
            obj = part.new_part(context, source, item["name"])
            blobs.attach(obj.blendsolid_script, blob)
            context.collection.objects.unlink(obj)
            coll.objects.link(obj)
            firsts[item["product"]] = obj
            if item["color"] is not None:
                obj.data.materials.append(_material(item["color"], materials))
        else:  # another instance of the same product: a linked duplicate (Alt+D)
            obj = bpy.data.objects.new(first.name, first.data)
            obj.blendsolid_script = first.blendsolid_script
            coll.objects.link(obj)
            if item["color"] is not None and first.data.materials and \
                    tuple(round(c, 4) for c in item["color"]) != tuple(round(c, 4) for c in
                                                                       first.data.materials[0].diffuse_color):
                obj.material_slots[0].link = "OBJECT"  # this instance has its own colour
                obj.material_slots[0].material = _material(item["color"], materials)
        obj.matrix_world = _matrix(item["matrix"], factor)
        objects.append(obj)
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = objects[0]
    shared = len(objects) - len(firsts)
    notes = [f"Imported {len(objects)} part{'s' if len(objects) != 1 else ''} from {os.path.basename(path)}"]
    if shared:
        notes.append(f"{shared} linked duplicate{'s' if shared != 1 else ''} of repeated parts")
    if answer.get("skipped"):
        notes.append(f"{answer['skipped']} surface or wire bodies skipped (only solids are imported)")
    if answer.get("invalid"):
        notes.append(f"{answer['invalid']} solid{'s are' if answer['invalid'] != 1 else ' is'} not valid "
                     f"(see the part's warning)")
    return objects, "; ".join(notes)


class BLENDSOLID_OT_import_cad(bpy.types.Operator, ImportHelper):
    """Import the solids of a STEP, IGES or BREP file as BlendSolid parts"""
    bl_idname = "blendsolid.import_cad"
    bl_label = "Import CAD"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: StringProperty(default=FILTER, options={"HIDDEN"})

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            _, report = import_file(context, self.filepath)
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, report)
        return {"FINISHED"}


def export_parts(context, use_selection):
    """The objects an export writes: the selected parts, or every visible part no other part uses."""
    if use_selection:
        return [o for o in context.selected_objects if part.is_local_part(o)]
    used = set()
    for obj in bpy.data.objects:
        if part.is_local_part(obj):
            used.update(deps.references(part.source_of(obj)))
    return [o for o in context.view_layer.objects if part.is_local_part(o) and o.visible_get()
            and part.part_id(o) not in used]


def _color(obj):
    """The linear RGB of obj's first material (its Principled Base Color, else its viewport colour), or None."""
    mat = obj.material_slots[0].material if obj.material_slots else None
    if mat is None:
        return None
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.use_nodes and mat.node_tree is not None else None
    if bsdf is not None and not bsdf.inputs["Base Color"].is_linked:
        return list(bsdf.inputs["Base Color"].default_value[:3])
    return list(mat.diffuse_color[:3])


def export_file(context, path, objects):
    """Write `objects` (parts) to `path`; returns the report text or raises RuntimeError with the user's message."""
    if not objects:
        raise RuntimeError("No BlendSolid parts to export")
    factor = part.unit_factor(context.scene)
    index = deps.part_index()
    items = []
    for obj in objects:
        primary = part.primary(obj)
        if not trust.is_trusted(primary):
            raise RuntimeError(f"'{obj.name}': its script is not trusted: press Trust Scripts in This File")
        source = part.source_of(primary)
        try:
            resolved = deps.resolve(primary, source, factor, index)
        except deps.DepError as e:
            raise RuntimeError(f"'{obj.name}': {e}") from None
        m = obj.matrix_world
        matrix = [m[r][c] / (factor if c == 3 else 1.0) for r in range(3) for c in range(4)]
        items.append({"name": obj.name, "source": source, "deps": resolved.deps, "blobs": resolved.blob_data(),
                      "tag": resolved.tag, "matrix": matrix, "color": _color(obj)})
    answer = runtime.exchange({"type": "export", "path": path, "items": items})
    if not answer["ok"]:
        raise RuntimeError(answer["error"])
    n = answer.get("count", len(items))
    return f"Exported {n} part{'s' if n != 1 else ''} to {os.path.basename(path)}"


class BLENDSOLID_OT_export_cad(bpy.types.Operator, ExportHelper):
    """Export BlendSolid parts as exact solids to a STEP, IGES or BREP file"""
    bl_idname = "blendsolid.export_cad"
    bl_label = "Export CAD"
    filename_ext = ".step"
    filter_glob: StringProperty(default=FILTER, options={"HIDDEN"})
    file_format: EnumProperty(name="Format", items=FORMATS, default="STEP")
    use_selection: BoolProperty(name="Selected Only", default=False,
                                description="Export the selected parts only (otherwise every visible part that "
                                            "isn't another part's cutter)")

    def check(self, context):
        self.filename_ext = EXTENSIONS[self.file_format]
        return super().check(context)

    def execute(self, context):
        self.filename_ext = EXTENSIONS[self.file_format]
        path = bpy.path.ensure_ext(self.filepath, self.filename_ext)
        if os.path.splitext(path)[1].lower() not in (".step", ".stp", ".iges", ".igs", ".brep", ".brp"):
            path += self.filename_ext
        try:
            report = export_file(context, path, export_parts(context, self.use_selection))
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, report)
        return {"FINISHED"}


def _menu_import(self, context):
    self.layout.operator(BLENDSOLID_OT_import_cad.bl_idname, text="CAD (.step, .iges, .brep) – BlendSolid")


def _menu_export(self, context):
    self.layout.operator(BLENDSOLID_OT_export_cad.bl_idname, text="CAD (.step, .iges, .brep) – BlendSolid")


_classes = (BLENDSOLID_OT_import_cad, BLENDSOLID_OT_export_cad)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)
    bpy.types.TOPBAR_MT_file_export.append(_menu_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(_menu_export)
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
