"""Parameters of a history script: its leading top-level `name = <number>` assignments.

The docstring and imports may come first; the parameter block ends at the first other statement.
Editing a parameter rewrites only the number literal, keeping comments and formatting.
"""
import ast
from dataclasses import dataclass


class ParamError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    name: str
    value: float
    is_int: bool
    lineno: int


def _numeric_assignment(node):
    """(name, value, is_int, value_node) for `name = <number>` or `name = -<number>`, else None."""
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
        return None
    value, sign = node.value, 1
    if isinstance(value, ast.UnaryOp) and isinstance(value.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(value.op, ast.USub) else 1
        value = value.operand
    if isinstance(value, ast.Constant) and type(value.value) in (int, float):
        return node.targets[0].id, sign * value.value, type(value.value) is int, node.value
    return None


def _parameter_nodes(tree):
    for i, node in enumerate(tree.body):
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue  # module docstring
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        found = _numeric_assignment(node)
        if found is None:
            return
        yield node, found


def parse_params(source):
    out, seen = [], set()
    for node, (name, value, is_int, _) in _parameter_nodes(ast.parse(source)):
        if name in seen:
            raise ParamError(f"parameter '{name}' is assigned twice (line {node.lineno})")
        seen.add(name)
        out.append(Param(name, float(value), is_int, node.lineno))
    return out


def format_value(value, is_int):
    if is_int:
        return str(int(round(value)))
    return repr(round(float(value), 6))  # drops float32 noise from Blender properties


def set_param(source, name, value):
    parse_params(source)  # validates duplicates
    for node, (pname, _, is_int, value_node) in _parameter_nodes(ast.parse(source)):
        if pname != name:
            continue
        if value_node.lineno != value_node.end_lineno:
            raise ParamError(f"parameter '{name}' must be written on one line")
        lines = source.splitlines(keepends=True)
        line = lines[value_node.lineno - 1].encode("utf-8")  # AST column offsets are UTF-8 byte offsets
        new = format_value(value, is_int).encode("utf-8")
        lines[value_node.lineno - 1] = (line[:value_node.col_offset] + new
                                        + line[value_node.end_col_offset:]).decode("utf-8")
        return "".join(lines)
    raise ParamError(f"unknown parameter '{name}'")
