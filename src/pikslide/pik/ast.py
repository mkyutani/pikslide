"""Abstract syntax tree produced by :func:`pikslide.pik.parser.parse`.

The tree mirrors the shape of pikchr's own internal ``PObj``/``PList``
structure: a :class:`Document` holds a list of :class:`Statement` nodes,
and an :class:`ObjectStatement` whose base is a :class:`BlockBase`
(``[ ... ]``) recursively holds another such list -- so a ``[...]``
grouping is the point where the tree actually branches.

Numeric expressions, positions and attributes are kept as small,
un-evaluated node trees (e.g. ``BinOp``, ``DirectionOffset``) rather than
being resolved to final coordinates: resolving them requires pikchr's
layout engine (default sizes, "current position/direction" state,
variable scope, etc.), which is a later stage in the pik -> PPTX/SVG
pipeline, not part of the tree-building stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


class Expr:
    """Base class for arithmetic expression nodes."""


@dataclass
class Num(Expr):
    value: float


@dataclass
class Var(Expr):
    name: str


@dataclass
class BinOp(Expr):
    op: str  # '+', '-', '*', '/'
    left: Expr
    right: Expr


@dataclass
class UnaryOp(Expr):
    op: str  # '+' or '-'
    operand: Expr


@dataclass
class FuncCall(Expr):
    name: str  # 'abs', 'cos', 'int', 'sin', 'sqrt', 'max', 'min'
    args: list[Expr]


@dataclass
class Dist(Expr):
    p1: "Position"
    p2: "Position"


@dataclass
class PlaceCoord(Expr):
    """``place.x`` or ``place.y``."""

    place: "Place"
    axis: str  # 'x' or 'y'


@dataclass
class ObjectProp(Expr):
    """``object.width``, ``object.dashed``, ``object.color`` etc."""

    obj: "ObjectRef"
    prop: str


@dataclass
class ColorName(Expr):
    """A bare capitalized name used where a color is expected (rvalue)."""

    name: str


# ---------------------------------------------------------------------------
# Object references / places / positions
# ---------------------------------------------------------------------------


class ObjectRef:
    """Base class for ways of referring to a previously-defined object."""


@dataclass
class ThisRef(ObjectRef):
    """``this`` -- the object currently being defined."""


@dataclass
class NameRef(ObjectRef):
    path: list[str]  # PLACENAME(.PLACENAME)*


@dataclass
class NthRef(ObjectRef):
    ordinal: int  # positive = Nth, negative = Nth-to-last ("last" == -1)
    classname: str | None  # None means an unnamed "[...]" block object
    container: ObjectRef | None = None  # set for "nth OF|IN object"


class Place:
    """Base class for a 2-D place reference used inside a Position."""


@dataclass
class ObjectEdge(Place):
    obj: ObjectRef
    edge: str | None = None  # e.g. 'n', 'ne', 'center', 'start', 'end'


@dataclass
class NthVertex(Place):
    ordinal: int
    obj: ObjectRef


class Position:
    """Base class for a symbolic 2-D position expression."""


@dataclass
class Coord(Position):
    x: Expr
    y: Expr


@dataclass
class PlacePosition(Position):
    place: Place


@dataclass
class OffsetPosition(Position):
    """``place + (dx, dy)`` or ``place - (dx, dy)``."""

    base: Place
    op: str  # '+' or '-'
    dx: Expr
    dy: Expr


@dataclass
class XYFromPositions(Position):
    """``(xpos, ypos)`` -- x is taken from the first, y from the second."""

    x_from: Position
    y_from: Position


@dataclass
class Between(Position):
    fraction: Expr
    p1: Position
    p2: Position


@dataclass
class DirectionOffset(Position):
    """``expr ABOVE|BELOW|LEFT OF|RIGHT OF position``."""

    direction: str  # 'above', 'below', 'left of', 'right of'
    distance: Expr
    base: Position


@dataclass
class HeadingOffset(Position):
    """``expr HEADING EDGEPT OF position`` or ``expr HEADING expr FROM position``."""

    distance: Expr
    edge: str | None  # compass edge point name, or None if angle is given
    angle: Expr | None  # explicit heading angle in degrees, or None if edge is given
    base: Position


# ---------------------------------------------------------------------------
# Attributes
# ---------------------------------------------------------------------------


class Attribute:
    """Base class for one item in an object's attribute list."""


@dataclass
class RelExpr:
    """An absolute value, or a percentage of the current value."""

    abs: Expr | None = None
    percent: Expr | None = None


@dataclass
class LeadingDirection(Attribute):
    """The distance leading an attribute list with no direction keyword,
    e.g. the ``150%`` in ``arrow 150%`` (moves in the current direction)."""

    amount: RelExpr


@dataclass
class NumProperty(Attribute):
    name: str  # 'width', 'height', 'radius', 'diameter', 'thickness'
    value: RelExpr


@dataclass
class DashProperty(Attribute):
    name: str  # 'dashed' or 'dotted'
    value: Expr | None


@dataclass
class ColorProperty(Attribute):
    name: str  # 'fill' or 'color'
    value: Expr


@dataclass
class GoDirection(Attribute):
    direction: str  # 'up', 'down', 'left', 'right'
    amount: RelExpr | None = None
    even_with: Position | None = None


@dataclass
class MoveHeading(Attribute):
    keyword: str  # 'then' or 'go'
    amount: RelExpr
    edge: str | None = None
    angle: Expr | None = None


@dataclass
class Close(Attribute):
    pass


@dataclass
class Chop(Attribute):
    pass


@dataclass
class From_(Attribute):
    position: Position


@dataclass
class To(Attribute):
    position: Position


@dataclass
class Then(Attribute):
    pass


@dataclass
class BoolProperty(Attribute):
    name: str  # 'cw', 'ccw', 'thick', 'thin', 'solid', 'invis'


@dataclass
class ArrowDirection(Attribute):
    kind: str  # 'left', 'right', 'both'


@dataclass
class TextAttribute(Attribute):
    text: str
    flags: list[str]  # 'center', 'ljust', 'rjust', 'above', 'below', 'bold', ...


@dataclass
class Fit(Attribute):
    pass


@dataclass
class Behind(Attribute):
    obj: ObjectRef


@dataclass
class At(Attribute):
    position: Position


@dataclass
class With(Attribute):
    edge: str | None
    position: Position


@dataclass
class Same(Attribute):
    obj: ObjectRef | None = None


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


class Statement:
    """Base class for a single top-level or block-level statement."""


class Basetype:
    """Base class for the un-labeled, un-attributed core of a statement."""


@dataclass
class ClassBase(Basetype):
    classname: str  # 'box', 'circle', 'arrow', ...


@dataclass
class TextBase(Basetype):
    text: str
    flags: list[str]


@dataclass
class BlockBase(Basetype):
    """A ``[ ... ]`` grouping -- this is where the tree branches."""

    statements: list[Statement] = field(default_factory=list)


@dataclass
class ObjectStatement(Statement):
    label: str | None
    base: Basetype
    attributes: list[Attribute] = field(default_factory=list)


@dataclass
class LabelPosition(Statement):
    """``PLACENAME: position`` -- names a bare point in space."""

    label: str
    position: Position


@dataclass
class DirectionStatement(Statement):
    direction: str  # 'up', 'down', 'left', 'right'


@dataclass
class AssignStatement(Statement):
    name: str
    op: str  # '=', '+=', '-=', '*=', '/='
    value: Expr


@dataclass
class PrintStatement(Statement):
    items: list[Expr | str]


@dataclass
class AssertExprStatement(Statement):
    left: Expr
    right: Expr


@dataclass
class AssertPositionStatement(Statement):
    left: Position
    right: Position


@dataclass
class MacroDefinition:
    name: str
    body: str


@dataclass
class Document:
    """The root of the tree: a statement list plus any macros seen."""

    statements: list[Statement] = field(default_factory=list)
    macros: list[MacroDefinition] = field(default_factory=list)
