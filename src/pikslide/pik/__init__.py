"""The diagram language, independent of any output format.

``parse(text)`` turns diagram source into a :class:`pikslide.pik.ast.Document`
tree (lexing in :mod:`~pikslide.pik.tokens`, ``#define`` expansion in
:mod:`~pikslide.pik.macros`, parsing in :mod:`~pikslide.pik.parser`), and
:func:`pikslide.pik.layout.resolve_layout` resolves that tree into concrete
2-D geometry. Output backends such as :mod:`pikslide.pptx_writer` consume
the resolved layout; nothing in this package depends on them.
"""

from . import ast
from .dump import dump
from .parser import parse
from .tokens import PikSyntaxError, format_syntax_error

__all__ = ["ast", "parse", "dump", "PikSyntaxError", "format_syntax_error"]
