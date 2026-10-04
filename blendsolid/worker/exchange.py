"""STEP / IGES / BREP files, and the blobs imported solids are kept as (ADR 0016).

read() turns a file into parts: one per solid, each solid a blob (binary BRep, zlib, base64) whose id is the
SHA-256 of its compressed bytes, placed by its instance's location in the assembly. Instances of one product
share their blobs, so Blender makes them linked duplicates. write() writes built shapes to a file.

Lengths are millimetres throughout: OCCT converts a file's units to millimetres when reading
(xstep.cascade.unit) and the writers are told the shapes are in millimetres.
"""
import base64
import hashlib
import io
import math
import os
import zlib
from collections import OrderedDict

BLOB_LINE = 76          # base64 characters per line of a blob Text
SEW_TOLERANCE = 0.01    # mm: gaps between loose faces (IGES trimmed surfaces) closed by sewing
_DECODED_SIZE = 32


class ExchangeError(Exception):
    """A file that can't be read or written, or a damaged blob; str(e) is for the user."""


# -- blobs ---------------------------------------------------------------------------------------------------------

def encode(shape):
    """(blob id, base64 text) of a TopoDS_Shape."""
    from OCP.BinTools import BinTools
    buf = io.BytesIO()
    BinTools.Write_s(shape, buf)
    packed = zlib.compress(buf.getvalue(), 9)
    return hashlib.sha256(packed).hexdigest()[:32], base64.b64encode(packed).decode("ascii")


def _unpack(blob_id, text):
    """The binary BRep bytes of a blob; raises ExchangeError when the text doesn't match its id (damaged)."""
    try:
        packed = base64.b64decode(text)  # line breaks are skipped
    except ValueError:
        packed = b""
    if hashlib.sha256(packed).hexdigest()[:32] != blob_id:
        raise ExchangeError("its imported shape's data is damaged (it doesn't match its id)")
    return zlib.decompress(packed)


def _shape(raw):
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape
    shape = TopoDS_Shape()
    BinTools.Read_s(shape, io.BytesIO(raw))
    if shape.IsNull():
        raise ExchangeError("its imported shape's data is empty")
    return shape


def decode(blob_id, text):
    """The TopoDS_Shape of a blob; raises ExchangeError when the text doesn't match its id (damaged)."""
    return _shape(_unpack(blob_id, text))


class _Decoded:
    """Unpacked blobs by id, least recently used dropped first (ids are content hashes: never stale). Each get()
    reads a new shape (~2 ms for the largest corpus solid): OCCT and build123d change their inputs in place
    (build123d's clean() made a cached solid invalid for every later run), so a shape is never shared between
    runs."""

    def __init__(self, size=_DECODED_SIZE):
        self.size, self._items = size, OrderedDict()

    def get(self, blob_id, text):
        """(a new shape, valid) of a blob; unpacks and checks it (BRepCheck) once."""
        item = self._items.get(blob_id)
        if item is None:
            raw = _unpack(blob_id, text)
            item = (raw, _valid(_shape(raw)))
            self._items[blob_id] = item
            while len(self._items) > self.size:
                self._items.popitem(last=False)
        self._items.move_to_end(blob_id)
        return _shape(item[0]), item[1]


DECODED = _Decoded()


def _valid(shape):
    from OCP.BRepCheck import BRepCheck_Analyzer
    return BRepCheck_Analyzer(shape).IsValid()


# -- reading -------------------------------------------------------------------------------------------------------

def _quiet():
    """OCCT's translators print every step to stdout: the worker's stdout is not read, but keep it short."""
    from OCP.Message import Message, Message_Gravity
    for printer in Message.DefaultMessenger_s().Printers():
        printer.SetTraceLevel(Message_Gravity.Message_Fail)


def _name(label):
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_Name
    attr = TDataStd_Name()
    if label.IsNull() or not label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return ""
    name = TCollection_AsciiString(attr.Get()).ToCString()
    return "".join(ch for ch in name if ch.isprintable()).strip()


def _rgba(color):
    from OCP.Quantity import Quantity_TOC_RGB
    rgb = color.GetRGB()
    r, g, b = rgb.Values(Quantity_TOC_RGB)  # linear RGB, as Blender's material colours
    return [r, g, b, color.Alpha()]


def _label_color(label):
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.XCAFDoc import XCAFDoc_ColorCurv, XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_ColorTool
    col = Quantity_ColorRGBA()
    for kind in (XCAFDoc_ColorSurf, XCAFDoc_ColorGen, XCAFDoc_ColorCurv):
        if XCAFDoc_ColorTool.GetColor_s(label, kind, col):
            return _rgba(col)
    return None


def _shape_color(tool, shape):
    """The colour set on `shape`, or on its largest face (largest bounding box) when it has none."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Quantity import Quantity_ColorRGBA
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf

    def own(s):
        col = Quantity_ColorRGBA()
        if tool.GetColor(s, XCAFDoc_ColorSurf, col) or tool.GetColor(s, XCAFDoc_ColorGen, col):
            return _rgba(col)
        return None

    found = own(shape)
    if found is not None:
        return found
    best, size = None, -1.0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        col = own(exp.Current())
        if col is not None:
            box = Bnd_Box()
            BRepBndLib.Add_s(exp.Current(), box)
            if box.SquareExtent() > size:
                best, size = col, box.SquareExtent()
        exp.Next()
    return best


def _explore(shape, kind, avoid=None):
    from OCP.TopExp import TopExp_Explorer
    exp = TopExp_Explorer(shape, kind) if avoid is None else TopExp_Explorer(shape, kind, avoid)
    while exp.More():
        yield exp.Current()
        exp.Next()


def _bodies(shape):
    """(solids, skipped): the solids of `shape`, with closed shells and sewn loose faces made solids; `skipped`
    counts the bodies that can't be (open shells and faces that don't close, a group of loose wires or points)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX
    from OCP.TopoDS import TopoDS

    solids = [TopoDS.Solid(s) for s in _explore(shape, TopAbs_SOLID)]
    loose = list(_explore(shape, TopAbs_SHELL, TopAbs_SOLID)) + list(_explore(shape, TopAbs_FACE, TopAbs_SHELL))
    skipped = 0
    if loose:
        sewing = BRepBuilderAPI_Sewing(SEW_TOLERANCE)
        for s in loose:
            sewing.Add(s)
        sewing.Perform()
        sewn = sewing.SewedShape()
        for sh in _explore(sewn, TopAbs_SHELL):
            shell = TopoDS.Shell(sh)
            maker = BRepBuilderAPI_MakeSolid(shell) if BRep_Tool.IsClosed_s(shell) else None
            if maker is None or not maker.IsDone():
                skipped += 1
                continue
            fix = ShapeFix_Solid(maker.Solid())
            fix.Perform()
            solids.extend(TopoDS.Solid(s) for s in _explore(fix.Solid(), TopAbs_SOLID))
        skipped += sum(1 for _ in _explore(sewn, TopAbs_FACE, TopAbs_SHELL))
    if next(_explore(shape, TopAbs_EDGE, TopAbs_FACE), None) is not None or \
            next(_explore(shape, TopAbs_VERTEX, TopAbs_EDGE), None) is not None:
        skipped += 1
    return solids, skipped


def _matrix(trsf):
    """gp_Trsf -> 12 floats (3x4 row-major, millimetres)."""
    return [trsf.Value(r, c) for r in (1, 2, 3) for c in (1, 2, 3, 4)]


def _rigid(trsf):
    from OCP.gp import gp_TrsfForm
    return abs(trsf.ScaleFactor() - 1.0) < 1e-9 and trsf.Form() != gp_TrsfForm.gp_Other and \
        trsf.VectorialPart().Determinant() > 0


class _Reader:
    def __init__(self):
        self.parts, self.blobs = [], {}
        self.skipped = self.invalid = 0
        self._products = {}  # (product label entry, solid index) -> blob id, for instances

    def add(self, key, solid, name, color, trsf, path):
        """One part: `solid` in its product's frame, placed by `trsf` (the instance's location)."""
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        if trsf is not None and not _rigid(trsf):  # bake a scale or mirror into this instance's shape
            solid = BRepBuilderAPI_Transform(solid, trsf, True).Shape()
            trsf, key = None, None
        product = f"{key[0]}#{key[1]}" if key is not None else f"#{len(self.parts)}"
        blob_id = self._products.get(key)
        if blob_id is None:
            blob_id, text = encode(solid)
            if blob_id not in self.blobs:
                self.blobs[blob_id] = text
                self.invalid += 0 if _valid(solid) else 1
            if key is not None:
                self._products[key] = blob_id
        from OCP.gp import gp_Trsf
        self.parts.append({"name": name, "blob": blob_id, "product": product, "matrix": _matrix(trsf or gp_Trsf()),
                           "color": color, "path": path})


def _read_xde(path, kind):
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
    from OCP.collections import Sequence_TDF_Label

    doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    app = XCAFApp_Application.GetApplication_s()
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    if kind == "step":
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        reader = STEPCAFControl_Reader()
    else:
        from OCP.IGESCAFControl import IGESCAFControl_Reader
        reader = IGESCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)
    if reader.ReadFile(path) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ExchangeError(f"can't read {os.path.basename(path)}: not a valid {kind.upper()} file")
    if not reader.Transfer(doc):
        raise ExchangeError(f"can't read {os.path.basename(path)}: OCCT could not translate its contents")
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    out = _Reader()

    def visit(label, instance, trsf, path, key_path):
        """`label`: a product (referred) label; `instance`: the component label placing it, or a null label."""
        name = _name(label) or _name(instance)
        if XCAFDoc_ShapeTool.IsAssembly_s(label):
            sub = Sequence_TDF_Label()
            XCAFDoc_ShapeTool.GetComponents_s(label, sub)
            node = (key_path, name or "Assembly")
            for i in range(1, sub.Length() + 1):
                comp = sub.Value(i)
                ref = TDF_Label()
                if not XCAFDoc_ShapeTool.GetReferredShape_s(comp, ref):
                    ref = comp
                loc = XCAFDoc_ShapeTool.GetLocation_s(comp).Transformation()
                visit(ref, comp, trsf.Multiplied(loc), path + [node], f"{key_path}/{i}")
            return
        shape = XCAFDoc_ShapeTool.GetShape_s(label)
        solids, skipped = _bodies(shape)
        out.skipped += skipped
        inherited = (_label_color(instance) if not instance.IsNull() else None) or _label_color(label)
        for i, solid in enumerate(solids):
            color = inherited or _shape_color(colors, solid) or _shape_color(colors, shape)
            out.add((_entry(label), i), solid, name or "Part", color, trsf, path)

    roots = Sequence_TDF_Label()
    shapes.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        root = roots.Value(i)
        visit(root, TDF_Label(), XCAFDoc_ShapeTool.GetLocation_s(root).Transformation(), [], str(i))
    return out


def _entry(label):
    """A label's entry ("0:1:1:3"): the product's identity within the document."""
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDF import TDF_Tool
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _read_brep(path):
    from OCP.BRep import BRep_Builder
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    shape = TopoDS_Shape()
    try:
        ok = BRepTools.Read_s(shape, path, BRep_Builder())
    except Exception:
        ok = False
    if not ok or shape.IsNull():
        raise ExchangeError(f"can't read {os.path.basename(path)}: not a valid BREP file")
    out = _Reader()
    solids, out.skipped = _bodies(shape)
    name = os.path.splitext(os.path.basename(path))[0]
    for i, solid in enumerate(solids):
        out.add(None, solid, name, None, None, [])
    return out


FORMATS = {".step": "step", ".stp": "step", ".iges": "iges", ".igs": "iges", ".brep": "brep", ".brp": "brep"}


def read(path):
    """{"name", "parts": [{"name", "blob", "product", "matrix", "color", "path"}], "blobs": {id: base64},
    "skipped", "invalid"}. Parts with the same "product" are instances of one solid (linked duplicates); "matrix"
    places the blob's shape (3x4 row-major, mm); "color" is linear RGBA or None. A part's "path" lists the assemblies it sits in, outermost first, as [key, name] pairs (one key
    per assembly instance)."""
    kind = FORMATS.get(os.path.splitext(path)[1].lower())
    if kind is None:
        raise ExchangeError(f"{os.path.basename(path)}: not a STEP, IGES or BREP file")
    if not os.path.isfile(path):
        raise ExchangeError(f"{path}: no such file")
    _quiet()
    out = _read_brep(path) if kind == "brep" else _read_xde(path, kind)
    return {"name": os.path.splitext(os.path.basename(path))[0], "parts": out.parts, "blobs": out.blobs,
            "skipped": out.skipped, "invalid": out.invalid}


# -- writing -------------------------------------------------------------------------------------------------------

def placed(shape, matrix):
    """`shape` moved by a 3x4 row-major matrix (mm). A uniform scale or a mirror is applied to the geometry
    exactly; a non-uniform scale or a shear turns the faces into B-splines (BRepBuilderAPI_GTransform)."""
    import numpy as np
    from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform, BRepBuilderAPI_Transform
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_GTrsf, gp_Mat, gp_Trsf, gp_XYZ
    m = [float(v) for v in matrix]
    if len(m) != 12 or not all(math.isfinite(v) for v in m):
        raise ExchangeError("a part's placement is malformed")
    lin = np.array([m[0:3], m[4:7], m[8:11]])
    det = np.linalg.det(lin)
    if abs(det) < 1e-12:
        raise ExchangeError("a part is scaled to zero")
    scale = float(np.cbrt(det))  # negative for a mirror
    rot = lin / scale
    if np.allclose(rot @ rot.T, np.eye(3), atol=1e-5):
        u, _, vt = np.linalg.svd(rot)  # float32 matrix_world: re-orthonormalize (see runner._location)
        rot = (u @ vt) * (1.0 if abs(scale - 1.0) < 1e-5 else scale)
        trsf = gp_Trsf()
        trsf.SetValues(rot[0, 0], rot[0, 1], rot[0, 2], m[3], rot[1, 0], rot[1, 1], rot[1, 2], m[7],
                       rot[2, 0], rot[2, 1], rot[2, 2], m[11])
        if abs(scale - 1.0) < 1e-5:
            return shape.Moved(TopLoc_Location(trsf))
        return BRepBuilderAPI_Transform(shape, trsf, True).Shape()
    gtrsf = gp_GTrsf()
    gtrsf.SetVectorialPart(gp_Mat(*[float(v) for v in lin.flatten()]))
    gtrsf.SetTranslationPart(gp_XYZ(m[3], m[7], m[11]))
    return BRepBuilderAPI_GTransform(shape, gtrsf, True).Shape()


def _xde(items):
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.TDF import TDF_Label
    from OCP.XCAFDoc import XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
    doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    app = XCAFApp_Application.GetApplication_s()
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
    app.InitDocument(doc)
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 0.001)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    shapes.SetAutoNaming_s(False)
    looks = {}  # TShape -> (name, colour) of the product it became
    for item in items:
        shape, look = item["shape"], (item["name"], None if item.get("color") is None else tuple(item["color"][:3]))
        if looks.setdefault(shape.TShape(), look) != look:
            # one shape placed twice (linked duplicates) is one product; named or coloured differently, it needs a
            # product of its own, since readers take the product's name and colour
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
            from OCP.TopLoc import TopLoc_Location
            shape = BRepBuilderAPI_Copy(shape.Located(TopLoc_Location())).Shape().Moved(shape.Location())
            looks[shape.TShape()] = look
        label = shapes.AddShape(shape, False)
        product = TDF_Label()  # a placed shape is an instance (label) of a product: name and colour both
        labels = [label]
        if XCAFDoc_ShapeTool.IsReference_s(label) and XCAFDoc_ShapeTool.GetReferredShape_s(label, product):
            labels.append(product)
        for lab in labels:
            TDataStd_Name.Set_s(lab, TCollection_ExtendedString(item["name"]))
            if item.get("color") is not None:
                r, g, b = (min(1.0, max(0.0, float(v))) for v in item["color"][:3])
                col = Quantity_Color(r, g, b, Quantity_TOC_RGB)
                colors.SetColor(lab, col, XCAFDoc_ColorGen)
                colors.SetColor(lab, col, XCAFDoc_ColorSurf)
    shapes.UpdateAssemblies()
    return doc


def write(path, items):
    """Write `items` ([{"shape": TopoDS_Shape placed in mm, "name", "color": [r, g, b] linear or None}]) to a
    STEP, IGES or BREP file chosen by the path's extension."""
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    kind = FORMATS.get(os.path.splitext(path)[1].lower())
    if kind is None:
        raise ExchangeError(f"{os.path.basename(path)}: the file name must end in .step, .iges or .brep")
    if not items:
        raise ExchangeError("nothing to export")
    _quiet()
    if kind == "brep":
        from OCP.BRep import BRep_Builder
        from OCP.BRepTools import BRepTools
        from OCP.TopoDS import TopoDS_Compound
        compound, builder = TopoDS_Compound(), BRep_Builder()
        builder.MakeCompound(compound)
        for item in items:
            builder.Add(compound, item["shape"])
        ok = BRepTools.Write_s(compound, path)
    elif kind == "step":
        from OCP.STEPCAFControl import STEPCAFControl_Controller, STEPCAFControl_Writer
        from OCP.STEPControl import STEPControl_StepModelType
        from OCP.XSControl import XSControl_WorkSession
        STEPCAFControl_Controller.Init_s()
        Interface_Static.SetCVal_s("write.step.unit", "MM")
        writer = STEPCAFControl_Writer(XSControl_WorkSession(), False)
        writer.SetNameMode(True)
        writer.SetColorMode(True)
        if not writer.Transfer(_xde(items), STEPControl_StepModelType.STEPControl_AsIs):
            raise ExchangeError("OCCT could not translate the parts to STEP")
        ok = writer.Write(path) == IFSelect_ReturnStatus.IFSelect_RetDone
    else:
        from OCP.IGESCAFControl import IGESCAFControl_Writer
        from OCP.IGESControl import IGESControl_Controller
        IGESControl_Controller.Init_s()
        Interface_Static.SetIVal_s("write.iges.brep.mode", 1)  # solids as MSBO, not loose trimmed surfaces
        writer = IGESCAFControl_Writer()  # (WorkSession, "MM") wrote untrimmed infinite faces
        writer.SetNameMode(True)
        writer.SetColorMode(True)
        if not writer.Transfer(_xde(items)):
            raise ExchangeError("OCCT could not translate the parts to IGES")
        ok = writer.Write(path)
    if not ok:
        raise ExchangeError(f"can't write {path}")
