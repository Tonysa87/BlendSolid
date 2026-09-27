"""Canonical part scripts: the one structure BlendSolid's interactive tools read and extend (pure Python, ast).

    # BlendSolid part. The numbers below are its parameters (millimetres).
    box_1_length = 40.0
    box_1_width = 30.0
    box_1_height = 20.0

    with BuildPart() as part:
        Box(box_1_length, box_1_width, box_1_height, align=(Align.CENTER, Align.CENTER, Align.MIN))  # feature: box_1
        with Locations(Location((12.0, 8.0, 20.0), (0.0, 0.0, 0.0))):  # feature: cut_1
            Box(cut_1_length, cut_1_width, cut_1_height, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)

    result = part.part

- The parameter block is params.py's (leading `name = <number>` lines); a feature's parameters are named
  `<feature>_<param>` and are appended at the end of the block.
- The body of `with BuildPart() as part:` is a list of features. Each top-level statement of that body is one
  feature and carries a `# feature: <name>` marker on its first line; names are unique in the script.
- The script ends with `result = part.part`.

Scripts that don't follow this (hand edits by advanced users, milestone 1 scripts) still run; the tools refuse to
edit them with NotCanonical, whose message is meant for the user.
"""
import ast
import re
from dataclasses import dataclass

from . import params

HEADER = "# BlendSolid part. The numbers below are its parameters (millimetres)."
PRIMITIVE_CALLS = {"Box": "box", "Cylinder": "cylinder", "Sphere": "sphere", "Cone": "cone", "Torus": "torus",
                   "Wedge": "wedge", "insert": "insert"}
_MARKER = re.compile(r"#\s*feature:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$")
_ALIGNS = ("MIN", "CENTER", "MAX")
_MODES = ("ADD", "SUBTRACT", "INTERSECT")


class NotCanonical(ValueError):
    """The script isn't in the structure the tools can edit; str(e) explains why, for the user."""


@dataclass(frozen=True)
class Feature:
    name: str
    kind: str                                       # a PRIMITIVE_CALLS value, or "other"
    mode: str                                       # "ADD", "SUBTRACT" or "INTERSECT"
    align: tuple[str, str, str] | None              # e.g. ("CENTER", "CENTER", "MIN"); None if not literal
    location: tuple[float, float, float] | None     # millimetres, part frame; (0, 0, 0) when not placed
    rotation: tuple[float, float, float] | None     # degrees (build123d Location, intrinsic XYZ)
    refs: tuple[str, ...]                           # ref("<part id>") arguments used by the feature
    lineno: int
    end_lineno: int


@dataclass(frozen=True)
class FeatureSpec:
    """A feature to add. `call` is the build123d statement with `{name}` where the feature's name goes
    (e.g. "Box({name}_length, {name}_width, {name}_height, align=Align.MIN)"); `params` are (suffix, value)
    pairs that become `<name>_<suffix> = value`. With `location`, the call is wrapped in
    `with Locations(Location(location, rotation)):`. An `exact` placement (taken from a face's exact plane)
    is written with PLACEMENT_DECIMALS: a face can sit off the 6-decimal grid (y = -93.652651 + 53.694279 / 2)
    and rounding the placement would start the feature past OCCT's 1e-07 mm tolerance (skins, gaps)."""
    prefix: str
    params: tuple[tuple[str, float], ...]
    call: str
    location: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    exact: bool = False


PLACEMENT_DECIMALS = 10  # an error of at most 5e-11 mm


def fmt(value, decimals=6):
    """A number as the scripts write it: rounded to 6 decimals (float32 noise), never "-0.0"."""
    value = round(float(value), decimals) + 0.0
    text = params.format_value(value, False)  # refuses nan/inf
    return text if decimals <= 6 else repr(value)


def _structure(source):
    """(tree, the `with BuildPart() as part:` node, source lines) or NotCanonical."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise NotCanonical(f"the script has a syntax error (line {e.lineno})") from None
    try:
        n_params = len(params.parse_params(source))
    except params.ParamError as e:
        raise NotCanonical(str(e)) from None
    body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]  # module docstring
    rest = body[n_params:]
    if len(rest) != 2 or not _is_build_part(rest[0]) or not _is_result(rest[1]):
        raise NotCanonical("the script is not in BlendSolid's feature layout (parameters, then "
                           "`with BuildPart() as part:`, then `result = part.part`)")
    return tree, rest[0], source.splitlines()


def _is_build_part(node):
    if not (isinstance(node, ast.With) and len(node.items) == 1):
        return False
    item = node.items[0]
    call = item.context_expr
    return (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "BuildPart"
            and not call.args and not call.keywords
            and isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == "part")


def _is_result(node):
    return (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "result" and isinstance(node.value, ast.Attribute)
            and node.value.attr == "part" and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "part")


def _number(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _number(node.operand)
        return None if value is None else -value
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    return None


def _triple(node):
    if not (isinstance(node, ast.Tuple) and len(node.elts) == 3):
        return None
    values = tuple(_number(e) for e in node.elts)
    return None if None in values else values


def _enum(node, enum_name, allowed):
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == enum_name \
            and node.attr in allowed:
        return node.attr
    return None


def _align(node):
    single = _enum(node, "Align", _ALIGNS)
    if single is not None:
        return (single, single, single)
    if isinstance(node, ast.Tuple) and len(node.elts) == 3:
        values = tuple(_enum(e, "Align", _ALIGNS) for e in node.elts)
        return None if None in values else values
    return None


def _placement(stmt):
    """(call node or None, location, rotation) of one feature statement."""
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return stmt.value, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    if isinstance(stmt, ast.With) and len(stmt.items) == 1:
        ctx = stmt.items[0].context_expr
        location = rotation = None
        if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Name) and ctx.func.id == "Locations" \
                and len(ctx.args) == 1:
            loc = ctx.args[0]
            if isinstance(loc, ast.Call) and isinstance(loc.func, ast.Name) and loc.func.id == "Location" \
                    and len(loc.args) == 2 and not loc.keywords:
                location, rotation = _triple(loc.args[0]), _triple(loc.args[1])
                if location is None or rotation is None:
                    location = rotation = None
        call = None
        if len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Expr) and isinstance(stmt.body[0].value, ast.Call):
            call = stmt.body[0].value
        return call, location, rotation
    return None, None, None


def _refs(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "ref" and len(n.args) == 1 \
                and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            if n.args[0].value not in out:
                out.append(n.args[0].value)
    return tuple(out)


def _feature(stmt, lines):
    match = _MARKER.search(lines[stmt.lineno - 1])
    if match is None:
        raise NotCanonical(f"line {stmt.lineno} is not a feature (no `# feature: <name>` marker)")
    call, location, rotation = _placement(stmt)
    kind, mode, align = "other", "ADD", None
    if call is not None:
        if isinstance(call.func, ast.Name):
            kind = PRIMITIVE_CALLS.get(call.func.id, "other")
        for kw in call.keywords:
            if kw.arg == "mode":
                mode = _enum(kw.value, "Mode", _MODES) or "ADD"
            elif kw.arg == "align":
                align = _align(kw.value)
    return Feature(match.group(1), kind, mode, align, location, rotation, _refs(stmt), stmt.lineno,
                   stmt.end_lineno)


def features(source):
    """The features of a canonical script, in order. Raises NotCanonical."""
    _, with_node, lines = _structure(source)
    out = [_feature(stmt, lines) for stmt in with_node.body]
    seen = set()
    for f in out:
        if f.name in seen:
            raise NotCanonical(f"two features are named '{f.name}'")
        seen.add(f.name)
    return out


def is_canonical(source):
    try:
        features(source)
        return True
    except NotCanonical:
        return False


def references(source):
    """Every ref("<part id>") the script uses (static string arguments only), in order, without duplicates.
    Tolerant: a script that doesn't parse has none (the worker reports its syntax error)."""
    try:
        return list(_refs(ast.parse(source)))
    except SyntaxError:
        return []


def next_name(existing_names, prefix):
    """`<prefix>_<n>` with n one more than the highest n already used with that prefix."""
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    used = [int(m.group(1)) for m in map(pattern.match, existing_names) if m]
    return f"{prefix}_{max(used, default=0) + 1}"


def _statement_lines(spec, name, indent):
    call = spec.call.replace("{name}", name)
    if spec.location is None:
        return [f"{indent}{call}  # feature: {name}"]
    decimals = PLACEMENT_DECIMALS if spec.exact else 6
    loc = ", ".join(fmt(v, decimals) for v in spec.location)
    rot = ", ".join(fmt(v, decimals) for v in spec.rotation)
    return [f"{indent}with Locations(Location(({loc}), ({rot}))):  # feature: {name}",
            f"{indent}    {call}"]


def _param_lines(spec, name, taken):
    lines = []
    for suffix, value in spec.params:
        pname = f"{name}_{suffix}"
        if pname in taken:
            raise NotCanonical(f"the parameter '{pname}' already exists")
        lines.append(f"{pname} = {fmt(value)}")
    return lines


def new_script(spec):
    """(source, feature name) of a new canonical script whose only feature is `spec`."""
    name = f"{spec.prefix}_1"
    lines = [HEADER, *_param_lines(spec, name, set()), "", "with BuildPart() as part:",
             *_statement_lines(spec, name, "    "), "", "result = part.part", ""]
    return "\n".join(lines), name


def append_feature(source, spec):
    """(source, feature name) with `spec` added as the last feature. Raises NotCanonical."""
    existing = features(source)
    tree, with_node, lines = _structure(source)
    taken = {p.name for p in params.parse_params(source)}
    name = next_name([f.name for f in existing] + list(taken), spec.prefix)
    indent = " " * with_node.body[0].col_offset
    body_end = with_node.body[-1].end_lineno  # 1-based index of the body's last line
    lines[body_end:body_end] = _statement_lines(spec, name, indent)
    new_params = _param_lines(spec, name, taken)
    if new_params:
        param_lines = {p.lineno for p in params.parse_params(source)}
        ends = [n.end_lineno for n in tree.body if n.lineno in param_lines]
        if ends:
            at = max(ends)
        else:
            at = with_node.lineno - 1
            new_params = new_params + [""]
        lines[at:at] = new_params
    return "\n".join(lines) + "\n", name


def remove_feature(source, name):
    """`source` without feature `name`: its statement and its `<name>_*` parameters. Raises NotCanonical, or
    ValueError when there is no such feature or it is the only one (a part keeps at least one)."""
    existing = features(source)
    found = [f for f in existing if f.name == name]
    if not found:
        raise ValueError(f"there is no feature named '{name}'")
    if len(existing) == 1:
        raise ValueError("a part keeps at least one feature")
    feature = found[0]
    lines = source.split("\n")
    drop = set(range(feature.lineno - 1, feature.end_lineno))
    for p in params.parse_params(source):
        if p.name.startswith(f"{name}_"):
            drop.add(p.lineno - 1)
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)
