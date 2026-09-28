"""Tool 3: booleans between parts with live cutters.

The selected parts (cutters) are applied to the active part (target): one `insert(ref("<cutter id>"),
mode=...)` feature per cutter in the target's script. The cutters stay parts of their own, shown as wire and
not rendered; moving, rotating or editing one recomputes the target (deps.py). After the boolean they are put
away (ADR 0011): moved into the CUTTERS collection, parented to the target (moving it carries its cuts) and
hidden with hide_set(), never hide_viewport or exclude (those freeze matrix_world: nothing in Blender's depsgraph
depends on a cutter). Select Cutter, Show Cutters and Alt+H bring them back.
Shortcuts (Object Mode, Bool Tool's convention): Ctrl+Numpad - / + / *.
"""
import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from mathutils import Matrix

from . import deps, focus, part, primitives, script_model

CUTTERS = "BlendSolid Cutters"

OPERATIONS = [
    ("DIFFERENCE", "Difference", "Cut the selected parts out of the active part", "SELECT_SUBTRACT", 0),
    ("UNION", "Union", "Add the selected parts to the active part", "SELECT_EXTEND", 1),
    ("INTERSECT", "Intersect", "Keep only what the active part shares with the selected parts",
     "SELECT_INTERSECT", 2),
]
MODES = {"DIFFERENCE": "SUBTRACT", "UNION": "ADD", "INTERSECT": "INTERSECT"}
KEYS = {"DIFFERENCE": "NUMPAD_MINUS", "UNION": "NUMPAD_PLUS", "INTERSECT": "NUMPAD_ASTERIX"}
_keymap_items = []


def cutters_of(context):
    """The selected parts other than the active one, one object per part (objects sharing a mesh are one
    part), leaving out objects of the active part itself."""
    target = context.object
    out, meshes = [], {target.data.session_uid}
    for obj in sorted(context.selected_objects, key=lambda o: o.name):
        if part.is_local_part(obj) and obj.data.session_uid not in meshes:
            meshes.add(obj.data.session_uid)
            out.append(obj)
    return out


class BLENDSOLID_OT_boolean(bpy.types.Operator):
    """Apply the selected BlendSolid parts to the active one as live cutters"""
    bl_idname = "blendsolid.boolean"
    bl_label = "Boolean"
    bl_options = {"REGISTER", "UNDO"}

    operation: EnumProperty(name="Operation", items=OPERATIONS, default="DIFFERENCE")

    @classmethod
    def poll(cls, context):
        if context.mode != "OBJECT" or not part.is_local_part(context.object):
            cls.poll_message_set("Make a BlendSolid part active (the target) and select the cutter parts")
            return False
        if not cutters_of(context):
            cls.poll_message_set("Select the cutter parts too (the active part is the target)")
            return False
        return True

    def execute(self, context):
        from . import ui  # lazy: ui.py itself imports ops_add/runtime lazily to avoid import cycles
        target = context.object
        cutters = cutters_of(context)
        if part.is_scaled(target):
            self.report({"ERROR"}, part.scaled_message(target))
            return {"CANCELLED"}
        source = part.source_of(target)
        try:
            script_model.features(source)
        except script_model.NotCanonical as e:
            self.report({"ERROR"}, part.not_canonical_message(target, e, detail=ui.scripts_visible(context)))
            return {"CANCELLED"}
        for cutter in cutters:
            if part.is_scaled(cutter):
                self.report({"ERROR"}, part.scaled_message(cutter))
                return {"CANCELLED"}
        target_id = part.part_id(target)  # None for a milestone 1 part: nothing can reference it yet
        if target_id is not None:
            for cutter in cutters:
                if part.part_id(cutter) == target_id:  # e.g. a Shift+D copy of the target, not yet made
                    # independent by the reconcile tick: its ref() would name the target itself
                    self.report({"ERROR"}, f"'{cutter.name}' is still the same part as '{target.name}': a part "
                                           f"can't cut itself (try again in a moment)")
                    return {"CANCELLED"}
            index = deps.part_index()
            for cutter in cutters:
                if deps.uses(cutter, target_id, index):
                    self.report({"ERROR"}, f"'{cutter.name}' already uses '{target.name}': they would depend "
                                           f"on each other")
                    return {"CANCELLED"}
        # everything checked: only now write anything, starting with the target's own id (ensure_part_id is
        # undoable RNA state, so it must not happen before a possible cancel above).
        part.ensure_part_id(target)
        mode = MODES[self.operation]
        for cutter in cutters:
            source, name = script_model.append_feature(source, primitives.insert_spec(part.ensure_part_id(cutter),
                                                                                       mode))
        target.blendsolid_script.from_string(source)
        focus.set_focus(target, name)
        for cutter in cutters:
            for obj in (cutter, *part.mesh_siblings(cutter)):
                put_away(context, obj, target)
        return {"FINISHED"}


def _collection_of_cutters(context):
    """The scene's CUTTERS collection (not rendered), made under the scene collection on first use."""
    scene = context.scene
    found = next((c for c in scene.collection.children_recursive if c.name == CUTTERS and c.library is None), None)
    if found is None:
        found = bpy.data.collections.new(CUTTERS)
        found.hide_render = True
        found.color_tag = "COLOR_01"
        scene.collection.children.link(found)
    return found


def _ancestors(obj):
    while obj is not None:
        yield obj
        obj = obj.parent


def put_away(context, obj, target):
    """A cutter after a boolean: wire, not rendered, in the CUTTERS collection, parented to `target` if it has
    no parent (world placement kept), hidden."""
    obj.display_type = "WIRE"
    obj.hide_render = True
    coll = _collection_of_cutters(context)
    if coll not in obj.users_collection:
        coll.objects.link(obj)
    for other in list(obj.users_collection):
        if other != coll:
            other.objects.unlink(obj)
    if obj.parent is None and obj not in _ancestors(target):
        world = obj.matrix_world.copy()
        obj.parent = target
        obj.matrix_parent_inverse = target.matrix_world.inverted_safe()
        obj.matrix_world = world
    obj.hide_set(True)


def bring_back(context, obj, target):
    """Undo put_away for a part no longer used as a cutter: solid, rendered, in `target`'s collection, unparented
    from it (world placement kept), shown."""
    obj.display_type, obj.hide_render = "TEXTURED", False
    home = target.users_collection[0] if target is not None and target.users_collection else context.scene.collection
    if home not in obj.users_collection:
        home.objects.link(obj)
    for other in list(obj.users_collection):
        if other != home and other.name == CUTTERS:
            other.objects.unlink(obj)
    if target is not None and obj.parent == target:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    obj.hide_set(False)


def show(context, obj):
    """Make a hidden cutter visible (its object and, if the user switched it off, the CUTTERS collection)."""
    obj.hide_set(False)
    if not obj.visible_get():
        for layer in _layer_collections(context.view_layer.layer_collection):
            if layer.collection in obj.users_collection:
                layer.hide_viewport = False


def _local_part(name):
    obj = bpy.data.objects.get((name, None)) if name else None
    return obj if part.is_local_part(obj) else None


class BLENDSOLID_OT_remove_boolean(bpy.types.Operator):
    """Remove this boolean from the part's history: the part is rebuilt without it. A cutter no other part uses
    is shown and rendered again"""
    bl_idname = "blendsolid.remove_boolean"
    bl_label = "Remove Boolean"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    target: StringProperty()
    feature: StringProperty()

    def execute(self, context):
        target = _local_part(self.target)
        if target is None:
            self.report({"ERROR"}, f"There is no BlendSolid part named '{self.target}'")
            return {"CANCELLED"}
        found = [b for b in deps.booleans(target) if b.feature == self.feature]
        try:
            source = script_model.remove_feature(part.source_of(target), self.feature)
        except (ValueError, script_model.NotCanonical) as e:
            self.report({"ERROR"}, f"Can't remove it: {e}")
            return {"CANCELLED"}
        target.blendsolid_script.from_string(source)
        index = deps.part_index()
        for b in found:
            if b.part_id in index and not any(b.part_id in deps.references(part.source_of(objs[0]))
                                              for objs in index.values()):
                for obj in index[b.part_id]:
                    bring_back(context, obj, target)
        return {"FINISHED"}


class BLENDSOLID_OT_restore_cutter(bpy.types.Operator):
    """Bring back a deleted cutter where it was, editable again"""
    bl_idname = "blendsolid.restore_cutter"
    bl_label = "Restore Cutter"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    target: StringProperty()
    part_id: StringProperty()

    def execute(self, context):
        target = _local_part(self.target)
        text = part.script_of_part(self.part_id)
        last = part.last_cutter(target, self.part_id) if target is not None else None
        if target is None or text is None or last is None:
            self.report({"ERROR"}, "That cutter can't be restored (its script or placement is gone)")
            return {"CANCELLED"}
        if self.part_id in deps.part_index():
            self.report({"ERROR"}, "That cutter is not deleted")
            return {"CANCELLED"}
        name, matrices = last
        factor = part.unit_factor(context.scene)
        obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        obj.blendsolid_script = text
        m = Matrix.Identity(4)
        for i in range(3):
            for j in range(4):
                m[i][j] = matrices[0][4 * i + j] * (factor if j == 3 else 1.0)
        obj.matrix_world = target.matrix_world @ m
        (target.users_collection[0] if target.users_collection else context.scene.collection).objects.link(obj)
        put_away(context, obj, target)
        obj.hide_set(False)  # brought back to be edited
        for o in context.view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        part.sync_params(obj)
        return {"FINISHED"}


class BLENDSOLID_OT_select_cutter(bpy.types.Operator):
    """Select this boolean's cutter (shown if it was hidden)"""
    bl_idname = "blendsolid.select_cutter"
    bl_label = "Select Cutter"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    part_id: StringProperty()

    def execute(self, context):
        objs = deps.part_index().get(self.part_id)
        if not objs:
            self.report({"ERROR"}, "That cutter doesn't exist")
            return {"CANCELLED"}
        for o in context.view_layer.objects:
            o.select_set(False)
        for obj in objs:
            show(context, obj)
            obj.select_set(True)
        context.view_layer.objects.active = objs[0]
        return {"FINISHED"}


def _layer_collections(layer):
    yield layer
    for child in layer.children:
        yield from _layer_collections(child)


def cutter_objects(obj):
    """The objects of obj's live cutters (deleted or lost cutters left out)."""
    index = deps.part_index()
    return [o for b in deps.booleans(obj) if not b.deleted and not b.missing for o in index.get(b.part_id, ())]


class BLENDSOLID_OT_show_cutters(bpy.types.Operator):
    """Show or hide the cutters of the active part's booleans"""
    bl_idname = "blendsolid.show_cutters"
    bl_label = "Show Cutters"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    show: BoolProperty(default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and part.is_local_part(context.object)

    def execute(self, context):
        for obj in cutter_objects(context.object):
            if self.show:
                show(context, obj)
            else:
                obj.select_set(False)
                obj.hide_set(True)
        return {"FINISHED"}


ICONS = {"SUBTRACT": "SELECT_SUBTRACT", "ADD": "SELECT_EXTEND", "INTERSECT": "SELECT_INTERSECT"}


def draw_booleans(layout, obj):
    """The part's booleans with live cutters, each with its actions (the BlendSolid sidebar panel)."""
    found = deps.booleans(obj)
    if not found:
        return
    box = layout.box()
    row = box.row()
    row.label(text="Booleans of this part:")
    cutters = cutter_objects(obj)
    if cutters:
        shown = any(o.visible_get() for o in cutters)
        row.operator(BLENDSOLID_OT_show_cutters.bl_idname, text="", icon="HIDE_OFF" if shown else "HIDE_ON",
                     depress=shown).show = not shown
    for b in found:
        row = box.row(align=True)
        if b.deleted:
            row.label(text=f"{b.name} (deleted)", icon=ICONS[b.mode])
            op = row.operator("blendsolid.restore_cutter", text="", icon="LOOP_BACK")
            op.target, op.part_id = obj.name, b.part_id
        elif b.missing:
            row.label(text="Cutter lost", icon="ERROR")
        else:
            row.label(text=b.name, icon=ICONS[b.mode])
            row.operator("blendsolid.select_cutter", text="", icon="RESTRICT_SELECT_OFF").part_id = b.part_id
        op = row.operator("blendsolid.remove_boolean", text="", icon="X")
        op.target, op.feature = obj.name, b.feature


class VIEW3D_MT_blendsolid_boolean(bpy.types.Menu):
    bl_idname = "VIEW3D_MT_blendsolid_boolean"
    bl_label = "BlendSolid Boolean"

    def draw(self, context):
        for value, label, _, icon, _ in OPERATIONS:
            self.layout.operator(BLENDSOLID_OT_boolean.bl_idname, text=label, icon=icon).operation = value


def draw_boolean_buttons(layout):
    row = layout.row(align=True)
    for value, label, _, icon, _ in OPERATIONS:
        row.operator(BLENDSOLID_OT_boolean.bl_idname, text=label, icon=icon).operation = value


def _object_menu_entry(self, context):
    self.layout.separator()
    self.layout.menu(VIEW3D_MT_blendsolid_boolean.bl_idname, icon="MOD_BOOLEAN")


CLASSES = [BLENDSOLID_OT_boolean, VIEW3D_MT_blendsolid_boolean, BLENDSOLID_OT_remove_boolean,
           BLENDSOLID_OT_restore_cutter, BLENDSOLID_OT_select_cutter, BLENDSOLID_OT_show_cutters]


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(_object_menu_entry)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is not None:  # None in some background sessions
        km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
        for operation, key in KEYS.items():
            kmi = km.keymap_items.new(BLENDSOLID_OT_boolean.bl_idname, key, "PRESS", ctrl=True)
            kmi.properties.operation = operation
            _keymap_items.append((km, kmi))


def unregister():
    for km, kmi in _keymap_items:
        km.keymap_items.remove(kmi)
    _keymap_items.clear()
    bpy.types.VIEW3D_MT_object.remove(_object_menu_entry)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
