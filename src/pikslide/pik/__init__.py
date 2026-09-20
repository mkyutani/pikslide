"""Parser for the pikchr (.pik) diagram language.

``parse(text)`` turns pikchr source into a :class:`pikslide.pik.ast.Document`
tree -- the intermediate representation that later pikslide stages convert
into PowerPoint objects, SVG, and other output formats.
"""

from . import ast
from .dump import dump
from .parser import parse
from .tokens import PikSyntaxError

__all__ = ["ast", "parse", "dump", "PikSyntaxError"]
