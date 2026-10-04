"""File > Import / Export of STEP, IGES and BREP (ADR 0016), run headless."""
import math
import os
import tempfile

import bpy
import pytest

from blendsolid import blobs, deps, part, primitives, script_model
from conftest import mm3, select, up_to_date, wait_for

CORPUS = "/mnt/e/bs_debug/step_corpus"
BOX = 40 * 30 * 20


def primitive(kind, values, name, location=(0.0, 0.0, 0.0)):
    source, _ = script_model.new_script(primitives.feature_spec(kind, values))
    obj = part.new_part(bpy.context, source, name=name)
    obj.location = location
    return obj


def imported_parts():
    return [o for o in bpy.data.objects if "imported(" in part.source_of(o)] if bpy.data.objects else []


def export(path, *objs, selection=True):
    bpy.context.view_layer.update()  # after clean()'s batch_remove, view_layer.objects still lists None
    select(*objs)
    bpy.ops.blendsolid.export_cad(filepath=path, file_format={".step": "STEP", ".iges": "IGES",
                                                              ".brep": "BREP"}[os.path.splitext(path)[1]],
                                  use_selection=selection)


@pytest.mark.parametrize("ext", [".step", ".iges", ".brep"])
def test_a_part_round_trips_through_a_file(clean, tmp_path, ext):
    box = primitive("box", {"length": 40, "width": 30, "height": 20}, "Bracket", location=(0.1, 0.0, 0.0))
    wait_for(lambda: up_to_date(box))
    path = str(tmp_path / f"bracket{ext}")
    export(path, box)
    assert os.path.getsize(path) > 0
    bpy.ops.blendsolid.import_cad(filepath=path)
    new = imported_parts()
    assert len(new) == 1
    obj = new[0]
    wait_for(lambda: up_to_date(obj))
    assert obj.blendsolid_error == ""
    assert abs(mm3(obj) - BOX) / BOX < 1e-6
    if ext != ".brep":
        assert obj.name.startswith("Bracket")  # the object's name went into the file and came back
    centre = sum((obj.matrix_world @ v.co for v in obj.data.vertices), obj.matrix_world.translation * 0) / \
        len(obj.data.vertices)
    assert abs(centre.x - 0.1) < 1e-6  # placed where it was exported (100 mm)
    script = obj.blendsolid_script
    (blob_id,) = script_model.imports(script.as_string())
    assert blobs.find(script, blob_id) is script[blobs.BLOBS_KEY][blob_id]


def test_an_imported_part_takes_features_and_exports_them(clean, tmp_path):
    box = primitive("box", {"length": 40, "width": 30, "height": 20}, "Block")
    wait_for(lambda: up_to_date(box))
    path = str(tmp_path / "block.step")
    export(path, box)
    bpy.ops.blendsolid.import_cad(filepath=path)
    (obj,) = imported_parts()
    spec = primitives.feature_spec("box", {"length": 10, "width": 10, "height": 5}, "SUBTRACT", location=(0, 0, 15))
    source, _ = script_model.append_feature(part.source_of(obj), spec)
    obj.blendsolid_script.from_string(source)
    wait_for(lambda: up_to_date(obj))
    assert abs(mm3(obj) - (BOX - 10 * 10 * 5)) / BOX < 1e-6
    again = str(tmp_path / "again.brep")
    export(again, obj)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.blendsolid.import_cad(filepath=again)
    (back,) = imported_parts()
    wait_for(lambda: up_to_date(back))
    assert abs(mm3(back) - (BOX - 500)) / BOX < 1e-6


def test_the_blob_is_saved_with_the_file_and_the_mesh_stays_valid(clean, tmp_path):
    box = primitive("box", {"length": 40, "width": 30, "height": 20}, "Saved")
    wait_for(lambda: up_to_date(box))
    path = str(tmp_path / "saved.step")
    export(path, box)
    bpy.data.objects.remove(box)
    bpy.ops.blendsolid.import_cad(filepath=path)
    (obj,) = imported_parts()
    wait_for(lambda: up_to_date(obj))
    blend = str(tmp_path / "saved.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    bpy.ops.wm.open_mainfile(filepath=blend)
    (obj,) = imported_parts()
    assert [t for t in bpy.data.texts if t.get(blobs.BLOB_KEY)]
    assert up_to_date(obj)  # the blob resolves: same tag, no recompute needed
    assert obj.blendsolid_error == ""


def test_a_missing_blob_is_the_parts_error(clean, tmp_path):
    box = primitive("box", {"length": 40, "width": 30, "height": 20}, "Lost")
    wait_for(lambda: up_to_date(box))
    path = str(tmp_path / "lost.step")
    export(path, box)
    bpy.ops.blendsolid.import_cad(filepath=path)
    (obj,) = imported_parts()
    wait_for(lambda: up_to_date(obj))
    blob = next(t for t in bpy.data.texts if t.get(blobs.BLOB_KEY))
    del obj.blendsolid_script[blobs.BLOBS_KEY]
    bpy.data.texts.remove(blob)
    wait_for(lambda: obj.blendsolid_error != "")
    assert "imported shape's data is missing" in obj.blendsolid_error


def test_export_leaves_out_cutters_and_applies_scale(clean, tmp_path):
    plate = primitive("box", {"length": 40, "width": 30, "height": 20}, "Plate")
    pin = primitive("cylinder", {"radius": 3, "height": 40}, "Pin", location=(0.0, 0.0, -0.01))
    big = primitive("box", {"length": 40, "width": 30, "height": 20}, "Big", location=(0.2, 0.0, 0.0))
    big.scale = (2.0, 2.0, 2.0)  # (a scaled part can't use cutters, but it can be exported)
    bpy.context.view_layer.update()
    source, _ = script_model.append_feature(part.source_of(plate),
                                            primitives.insert_spec(part.part_id(pin), "SUBTRACT"))
    plate.blendsolid_script.from_string(source)
    wait_for(lambda: up_to_date(plate) and up_to_date(pin) and up_to_date(big))
    path = str(tmp_path / "all.brep")
    export(path, plate, selection=False)  # every visible part that isn't a cutter: the plate and the big box
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.blendsolid.import_cad(filepath=path)
    objs = imported_parts()
    wait_for(lambda: all(up_to_date(o) for o in objs))
    holed = BOX - math.pi * 9 * 20
    got = sorted(mm3(o) for o in objs)  # display mesh volumes: the hole's polygon is a little smaller
    assert got[0] == pytest.approx(holed, rel=1e-3) and got[1] == pytest.approx(8 * BOX, rel=1e-6)


def test_import_is_one_undo_step(clean, tmp_path):
    box = primitive("box", {"length": 40, "width": 30, "height": 20}, "Undo")
    wait_for(lambda: up_to_date(box))
    path = str(tmp_path / "undo.step")
    export(path, box)
    bpy.data.objects.remove(box)
    bpy.ops.ed.undo_push()
    bpy.ops.blendsolid.import_cad("EXEC_DEFAULT", True, filepath=path)
    assert len(imported_parts()) == 1
    bpy.ops.ed.undo()
    assert imported_parts() == []
    bpy.ops.ed.redo()
    assert len(imported_parts()) == 1


def test_errors_are_reported(clean, tmp_path):
    bad = tmp_path / "bad.step"
    bad.write_text("not a step file")
    with pytest.raises(RuntimeError, match="not a valid STEP file"):
        bpy.ops.blendsolid.import_cad(filepath=str(bad))
    with pytest.raises(RuntimeError, match="No BlendSolid parts"):
        bpy.ops.blendsolid.export_cad(filepath=str(tmp_path / "none.step"), use_selection=True)


@pytest.mark.skipif(not os.path.isdir(CORPUS), reason="the maintainer's STEP corpus is not mounted")
def test_corpus_assembly_instances_become_linked_duplicates(clean):
    bpy.ops.blendsolid.import_cad(filepath=os.path.join(CORPUS, "bearing_6200_10x30x9.step"))
    objs = imported_parts()
    assert len(objs) == 16
    assert len({o.data.session_uid for o in objs}) == 3  # 3 products: every instance shares its product's mesh
    assert len({o.blendsolid_script.session_uid for o in objs}) == 3
    wait_for(lambda: all(up_to_date(o) for o in objs), timeout=180)
    assert all(o.blendsolid_error == "" and mm3(o) > 0 for o in objs)
    assert all(o.material_slots and o.material_slots[0].material for o in objs)
    assert {c.name for c in objs[0].users_collection}  # inside the file's collection tree


@pytest.mark.parametrize("name, fmt, written", [("a.stp", "STEP", "a.stp"), ("b.igs", "STEP", "b.igs"),
                                                ("c.brp", "STEP", "c.brp"), ("d", "IGES", "d.iges")])
def test_the_typed_extension_decides_the_format(clean, tmp_path, name, fmt, written):
    box = primitive("box", {"length": 40, "width": 30, "height": 20}, "Ext")
    wait_for(lambda: up_to_date(box))
    bpy.context.view_layer.update()
    select(box)
    bpy.ops.blendsolid.export_cad(filepath=str(tmp_path / name), file_format=fmt, use_selection=True)
    assert sorted(os.listdir(tmp_path)) == [written]
    head = open(tmp_path / written, "rb").read(80)
    kind = {"a.stp": b"ISO-10303", "b.igs": b"S0000001", "c.brp": b"CASCADE", "d.iges": b"S0000001"}[written]
    assert kind in head or kind in open(tmp_path / written, "rb").read(400)


def test_an_instance_coloured_when_the_first_is_not(clean, tmp_path):
    from blendsolid import ops_exchange, runtime
    box = primitive("box", {"length": 40, "width": 30, "height": 20}, "Src")
    wait_for(lambda: up_to_date(box))
    path = str(tmp_path / "one.step")
    export(path, box)
    answer = runtime.exchange({"type": "import", "path": path})
    item = answer["parts"][0]
    answer["parts"] = [{**item, "color": None}, {**item, "color": [1.0, 0.0, 0.0, 1.0]}]
    real = runtime.exchange
    runtime.exchange = lambda request: answer
    try:
        objs, _ = ops_exchange.import_file(bpy.context, path)
    finally:
        runtime.exchange = real
    assert objs[1].data == objs[0].data  # one product: linked duplicates
    assert objs[0].material_slots[0].material is None
    assert objs[1].material_slots[0].material.diffuse_color[:3] == pytest.approx((1, 0, 0))
