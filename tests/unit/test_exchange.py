"""STEP / IGES / BREP import and export in the worker, and imported() in part scripts (ADR 0016)."""
import glob
import math
import os

import pytest

import exchange
import runner

HOLED_VOLUME = 10 * 20 * 30 - math.pi * 9 * 25  # the hole runs from z = -10 past the top (15)
CORPUS = "/mnt/e/bs_debug/step_corpus"


def holed():
    from build123d import Box, Cylinder, Pos
    return (Box(10, 20, 30) - Pos(0, 0, 5) * Cylinder(3, 30)).solids()[0].wrapped


def volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def faces(shape):
    from OCP.TopAbs import TopAbs_FACE
    return sum(1 for _ in exchange._explore(shape, TopAbs_FACE))


def moved(x, y, z):
    return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z]


def script(blob_id, extra=""):
    return ("with BuildPart() as part:\n"
            f"    insert(imported(\"{blob_id}\"), clean=False)  # feature: import_1\n" + extra +
            "result = part.part\n")


def test_a_blob_round_trips_and_its_id_is_its_hash():
    blob_id, text = exchange.encode(holed())
    assert len(blob_id) == 32
    assert exchange.encode(holed())[0] == blob_id  # content-addressed: the same solid, the same id
    wrapped = "\n".join(text[i:i + exchange.BLOB_LINE] for i in range(0, len(text), exchange.BLOB_LINE))
    shape = exchange.decode(blob_id, wrapped)  # line breaks (a blob Text) are skipped
    assert abs(volume(shape) - HOLED_VOLUME) < 1e-6


def test_a_damaged_blob_is_an_error_not_a_shape():
    blob_id, text = exchange.encode(holed())
    with pytest.raises(exchange.ExchangeError, match="damaged"):
        exchange.decode(blob_id, text[:-8] + "AAAAAAAA")


@pytest.mark.parametrize("ext", [".step", ".iges", ".brep"])
def test_files_round_trip_volume_faces_names_colours(tmp_path, ext):
    path = str(tmp_path / f"parts{ext}")
    exchange.write(path, [{"shape": exchange.placed(holed(), moved(5, 0, 0)), "name": "holed", "color": [1, 0, 0]},
                          {"shape": exchange.placed(holed(), moved(50, 0, 0)), "name": "second", "color": None}])
    data = exchange.read(path)
    assert len(data["parts"]) == 2 and data["skipped"] == 0 and data["invalid"] == 0
    for part in data["parts"]:
        shape = exchange.decode(part["blob"], data["blobs"][part["blob"]])
        assert abs(volume(shape) - HOLED_VOLUME) < 1e-6 * HOLED_VOLUME
        assert faces(shape) == faces(holed())
    xs = sorted(round(p["matrix"][3] + volume_centre_x(data, p), 6) for p in data["parts"])
    assert xs == [5.0, 50.0]  # placed where they were written, whether the format keeps locations or not
    if ext == ".brep":
        assert {p["name"] for p in data["parts"]} == {"parts"}  # BREP has no names: the file's
    else:
        by_name = {p["name"]: p for p in data["parts"]}
        assert set(by_name) == {"holed", "second"}
        assert by_name["holed"]["color"][:3] == pytest.approx([1, 0, 0], abs=1e-6)
        assert by_name["second"]["color"] is None


def volume_centre_x(data, part):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(exchange.decode(part["blob"], data["blobs"][part["blob"]]), props)
    return props.CentreOfMass().X()


def test_instances_of_one_product_share_their_blob(tmp_path):
    path = str(tmp_path / "pair.step")
    shape = holed()
    exchange.write(path, [{"shape": exchange.placed(shape, moved(0, 0, 0)), "name": "pin", "color": None},
                          {"shape": exchange.placed(shape, moved(40, 0, 0)), "name": "pin", "color": None}])
    data = exchange.read(path)
    assert len(data["parts"]) == 2 and len(data["blobs"]) == 1
    assert data["parts"][0]["product"] == data["parts"][1]["product"]
    assert sorted(p["matrix"][3] for p in data["parts"]) == [0.0, 40.0]


def test_placed_applies_scale_and_mirror_exactly():
    assert abs(volume(exchange.placed(holed(), [2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0])) - 8 * HOLED_VOLUME) < 1e-6
    mirrored = exchange.placed(holed(), [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0])
    assert abs(volume(mirrored) - HOLED_VOLUME) < 1e-6  # not inside out


def test_a_closed_shell_is_imported_as_a_solid_and_loose_faces_are_counted(tmp_path):
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
    from OCP.TopoDS import TopoDS_Compound
    from build123d import Box
    box = Box(10, 10, 10).wrapped
    shell = next(exchange._explore(box, TopAbs_SHELL))
    stray = next(exchange._explore(Box(5, 5, 5).moved(__import__("build123d").Location((50, 0, 0))).wrapped,
                                   TopAbs_FACE))
    compound, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(compound)
    builder.Add(compound, shell)
    builder.Add(compound, stray)
    path = str(tmp_path / "shells.brep")
    BRepTools.Write_s(compound, path)
    data = exchange.read(path)
    assert len(data["parts"]) == 1 and data["skipped"] == 1
    part = data["parts"][0]
    assert abs(volume(exchange.decode(part["blob"], data["blobs"][part["blob"]])) - 1000) < 1e-6


def test_unknown_or_missing_files_are_errors(tmp_path):
    with pytest.raises(exchange.ExchangeError, match="not a STEP"):
        exchange.read(str(tmp_path / "a.obj"))
    with pytest.raises(exchange.ExchangeError, match="no such file"):
        exchange.read(str(tmp_path / "a.step"))
    bad = tmp_path / "bad.step"
    bad.write_text("not a step file")
    with pytest.raises(exchange.ExchangeError):
        exchange.read(str(bad))


@pytest.mark.skipif(not os.path.isdir(CORPUS), reason="the maintainer's STEP corpus is not mounted")
def test_corpus_bearing_instances():
    data = exchange.read(os.path.join(CORPUS, "bearing_6200_10x30x9.step"))
    assert len(data["parts"]) == 16 and len(data["blobs"]) == 3
    assert {p["name"] for p in data["parts"]} == {"InnerRace", "OuterRace", "Roller"}
    assert all(p["color"] is not None for p in data["parts"])


# -- imported() in part scripts --------------------------------------------------------------------------------------

def test_an_imported_solid_is_a_part_and_takes_features():
    blob_id, text = exchange.encode(holed())
    r = runner.run_script(script(blob_id), blobs={blob_id: text}, cache=runner.ShapeCache())
    assert r.ok, r.error
    assert abs(r.volume - HOLED_VOLUME) < 1e-6
    assert any(ref.startswith('face("import_1", "+Z"') for ref in r.face_refs)  # roles as on any inserted solid
    cut = script(blob_id, "    with Locations((0, 7, 15)):  # feature: cut_1\n"
                          "        Box(4, 4, 4, mode=Mode.SUBTRACT)\n")
    r = runner.run_script(cut, blobs={blob_id: text}, cache=runner.ShapeCache())
    assert r.ok, r.error
    assert abs(r.volume - (HOLED_VOLUME - 4 * 4 * 2)) < 1e-6


def test_a_missing_or_damaged_blob_fails_on_its_line(monkeypatch):
    monkeypatch.setattr(exchange, "DECODED", exchange._Decoded())  # a good copy decoded before would be used
    blob_id, text = exchange.encode(holed())
    r = runner.run_script(script(blob_id), blobs={}, cache=runner.ShapeCache())
    assert not r.ok and r.line == 2 and "not sent" in r.error
    r = runner.run_script(script(blob_id), blobs={blob_id: text[:-8] + "AAAAAAAA"}, cache=runner.ShapeCache())
    assert not r.ok and r.line == 2 and "damaged" in r.error


def test_an_invalid_imported_solid_is_shown_with_a_warning():
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
    from OCP.TopoDS import TopoDS
    from build123d import Box
    sewing = BRepBuilderAPI_Sewing()
    for i, face in enumerate(exchange._explore(Box(10, 10, 10).wrapped, TopAbs_FACE)):
        if i:  # one face missing: a solid bounded by an open shell
            sewing.Add(face)
    sewing.Perform()
    shell = TopoDS.Shell(next(exchange._explore(sewing.SewedShape(), TopAbs_SHELL)))
    blob_id, text = exchange.encode(BRepBuilderAPI_MakeSolid(shell).Solid())
    r = runner.run_script(script(blob_id), blobs={blob_id: text}, cache=runner.ShapeCache())
    assert r.ok, r.error
    assert any(runner.INVALID_IMPORT in w for _, w in r.warnings)


def test_build_for_export_uses_the_cache_and_names_failures():
    blob_id, text = exchange.encode(holed())
    cache = runner.ShapeCache()
    shape = runner.build(script(blob_id), blobs={blob_id: text}, tag="t1", cache=cache)
    assert cache.get("t1") is shape
    with pytest.raises(exchange.ExchangeError, match="'Bad' can't be built"):
        runner.build("result = 1 / 0\n", cache=cache, label="'Bad'")
