"""Human-readable text dump of a pik AST -- for debugging and inspection.

Every node in :mod:`pikslide.pik.ast` is a dataclass, so this walks fields
generically rather than special-casing each node type. Nesting in the
output directly reflects nesting in the tree, so a ``[...]`` block's
``BlockBase.statements`` shows up as a further-indented sub-list.
"""

from __future__ import annotations

import dataclasses

_INDENT = "  "


def dump(node: object) -> str:
    """Render ``node`` (typically a :class:`pikslide.pik.ast.Document`) as an
    indented text tree."""
    lines: list[str] = []
    _dump_node(node, 0, lines)
    return "\n".join(lines)


def _dump_node(node: object, depth: int, lines: list[str]) -> None:
    pad = _INDENT * depth
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        fields = dataclasses.fields(node)
        if not fields:
            lines.append(f"{pad}{type(node).__name__}()")
            return
        lines.append(f"{pad}{type(node).__name__}")
        for f in fields:
            _dump_field(f.name, getattr(node, f.name), depth + 1, lines)
    elif isinstance(node, list):
        if not node:
            lines.append(f"{pad}[]")
            return
        for item in node:
            _dump_node(item, depth, lines)
    else:
        lines.append(f"{pad}{node!r}")


def _dump_field(name: str, value: object, depth: int, lines: list[str]) -> None:
    pad = _INDENT * depth
    is_node = dataclasses.is_dataclass(value) and not isinstance(value, type)
    if is_node or (isinstance(value, list) and value):
        lines.append(f"{pad}{name}:")
        _dump_node(value, depth + 1, lines)
    elif isinstance(value, list):
        lines.append(f"{pad}{name}: []")
    else:
        lines.append(f"{pad}{name}: {value!r}")
