"""Write src/pikslide/includes/figures.pik: the macros pikslide bundles
for diagrams whose shape is the point (issue #38).

    python scripts/gen_figures.py

A macro's arguments are pasted in as text and there are at most nine, so
each count of parts is a macro of its own (cycle3 ... cycle6), written
out here rather than by hand. Each draws a block, so that its names stay
in it: `P: cycle4(...)` is `P.S1` ... `P.S4` and `P.C`. Each part's
argument goes last among its attributes, so that what it says wins.

Each family's `#:` comment is its `--help` entry (help.py): its names and
summary, its synopsis, its description, and after EXAMPLE, its example.
tests/test_figures.py checks the file is what this writes."""

from __future__ import annotations

import math
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "src" / "pikslide" / "includes" / "figures.pik"

PART = "fill primary lighter 80% stroke primary"
LINE = "stroke primary"
GAP = 0.04


def num(x: float) -> str:
    """`x` as short as it is exact to four places: 90, -54, 38.5714."""
    text = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def angle(n: int, k: int) -> str:
    """The k-th of n places round a circle, from the top, clockwise."""
    return num(90 - 360 * k / n)


def doc(names: list[str], summary: str, synopsis: str, body: str, example: str) -> str:
    lines = [f"{' '.join(names)} | {summary}", synopsis, *body.strip().splitlines(), "EXAMPLE",
             *example.strip().splitlines()]
    return "\n".join(f"#: {line}".rstrip() for line in lines)


def define(name: str, statements: list[str]) -> str:
    return "\n".join([f"define {name} {{", "  [", *(f"    {s}" for s in statements), "  ]", "}"])


# ---------------------------------------------------------------------------
# The families
# ---------------------------------------------------------------------------


# A cycle's steps are boxes figwid*W by fight*0.17, W narrower for more of
# them, centered on an ellipse that fits them in figwid by fight, so that in
# units of figwid and fight, where a box is and where the ellipse leaves it
# are the same at any size: the arrows can be worked out here, once.
_STEP_WID = {3: 0.3, 4: 0.3, 5: 0.26, 6: 0.26}
_STEP_HT = 0.17


def _on_ring(n: int, theta: float) -> tuple[float, float]:
    rx, ry = (1 - _STEP_WID[n]) / 2, (1 - _STEP_HT) / 2
    return rx * math.cos(math.radians(theta)), ry * math.sin(math.radians(theta))


def _leaves(n: int, center: float, step: float) -> float:
    """Where the ellipse, from a step's center at `center` degrees, going
    `step` degrees at a time, leaves its box."""
    cx, cy = _on_ring(n, center)
    theta = center
    while True:
        theta += step
        x, y = _on_ring(n, theta)
        if abs(x - cx) > _STEP_WID[n] / 2 or abs(y - cy) > _STEP_HT / 2:
            return theta


def _ring_arrow(n: int, k: int) -> str:
    """The arrow from step k to the next, along the ellipse: from just
    outside the one box to just outside the other, through a point every
    10 degrees or so, as a curve."""
    here = 90 - 360 * k / n
    start = _leaves(n, here, -0.1) - 1.5
    end = _leaves(n, here - 360 / n, 0.1) + 1.5
    stops = max(2, round((start - end) / 10))
    points = [_on_ring(n, start + (end - start) * i / stops) for i in range(stops + 1)]
    path = " then to ".join(f"(figwid*{num(x)}, fight*{num(y)})" for x, y in points[1:])
    x, y = points[0]
    return f"spline -> from (figwid*{num(x)}, fight*{num(y)}) to {path} {LINE}"


def cycle(n: int) -> str:
    w = _STEP_WID[n]
    rx, ry = num((1 - w) / 2), num((1 - _STEP_HT) / 2)
    out = ["C: (0, 0)"]
    for k in range(n):
        a = angle(n, k)
        out.append(f"S{k + 1}: box wid figwid*{num(w)} ht fight*{num(_STEP_HT)} rad 0.06 {PART} ${k + 1} "
                   f"at (figwid*{rx}*cos({a}), fight*{ry}*sin({a}))")
    out += [_ring_arrow(n, k) for k in range(n)]
    return define(f"cycle{n}", out)


def chevron(n: int) -> str:
    head = "fight*0.072"
    wid = f"(figwid + {n - 1}*({head} - {GAP}))/{n}"
    size = f"wid {wid} ht fight*0.2 adjust head.length {head}"
    out = [f"S1: shape homePlate {size} {PART} $1 with .w at (-figwid/2, 0)"]
    # Each fits into the one before, so their boxes overlap: behind says it's meant.
    out += [f"S{k}: shape chevron {size} {PART} behind S{k - 1} ${k} with .w at S{k - 1}.e - ({head} - {GAP}, 0)"
            for k in range(2, n + 1)]
    return define(f"chevron{n}", out)


def pyramid(n: int) -> str:
    tier = f"(fight - {num((n - 1) * GAP)})/{n}"
    out = []
    for k in range(n):
        top = f"{k}*(fight + {GAP})/{n}"  # how far down from the apex the tier starts
        y = f"fight/2 - {top} - {tier}/2" if k else f"fight/2 - {tier}/2"
        if k == 0:
            out.append(f"S1: shape triangle wid figwid*{tier}/fight ht {tier} {PART} $1 at (0, {y})")
            continue
        bottom = f"figwid*({top} + {tier})/fight"
        inset = f"figwid*{tier}/(2*fight)"
        out.append(f"S{k + 1}: shape trapezoid wid {bottom} ht {tier} adjust adj {inset}*100000/min({bottom}, {tier}) "
                   f"{PART} ${k + 1} at (0, {y})")
    return define(f"pyramid{n}", out)


def funnel(n: int) -> str:
    tier = f"(fight - {num((n - 1) * GAP)})/{n}"
    out = []
    for k in range(n):
        width = f"figwid*{num(1 - 0.6 * k / (n - 1))}"
        y = f"fight/2 - {k}*(fight + {GAP})/{n} - {tier}/2" if k else f"fight/2 - {tier}/2"
        out.append(f"S{k + 1}: box wid {width} ht {tier} {PART} ${k + 1} at (0, {y})")
    return define(f"funnel{n}", out)


def venn(n: int) -> str:
    d = "min(fight, figwid*0.6)" if n == 2 else "min(fight*0.65, figwid*0.4)"
    if n == 2:
        centers = [("-0.3", "0"), ("0.3", "0")]
        names = [("-0.5", "0"), ("0.5", "0")]
    else:
        r = 0.29
        centers = [(num(r * math.cos(math.radians(a))), num(r * math.sin(math.radians(a)))) for a in (150, 30, 270)]
        names = [(num(0.5 * math.cos(math.radians(a))), num(0.5 * math.sin(math.radians(a)))) for a in (150, 30, 270)]
    out = []
    for k, (x, y) in enumerate(centers):
        behind = f" behind S{k}" if k else ""
        out.append(f"S{k + 1}: circle diameter {d} {LINE}{behind} at ({d}*{x}, {d}*{y})")
    out += [f"T{k + 1}: text ${k + 1} at ({d}*{x}, {d}*{y})" for k, (x, y) in enumerate(names)]
    out.append(f"C: text ${n + 1} at (0, 0)")
    return define(f"venn{n}", out)


def matrix() -> str:
    box = f"box wid (figwid - {GAP})/2 ht (fight - {GAP})/2 {PART}"
    x, y = f"(figwid + {GAP})/4", f"(fight + {GAP})/4"
    out = [f"S1: {box} $1 at (-{x}, {y})", f"S2: {box} $2 at ({x}, {y})",
           f"S3: {box} $3 at (-{x}, -{y})", f"S4: {box} $4 at ({x}, -{y})",
           "L: text $5 with .e at (-figwid/2 - 0.08, 0)", "R: text $6 with .w at (figwid/2 + 0.08, 0)",
           "B: text $7 with .n at (0, -fight/2 - 0.08)", "T: text $8 with .s at (0, fight/2 + 0.08)"]
    return define("matrix2", out)


def hub(n: int) -> str:
    out = ["C: circle diameter fight*0.36 fill primary lighter 60% stroke primary $1 at (0, 0)"]
    for k in range(n):
        a = angle(n, k)
        out.append(f"S{k + 1}: box wid figwid*0.24 ht fight*0.16 rad 0.06 {PART} ${k + 2} "
                   f"at (figwid*0.38*cos({a}), fight*0.42*sin({a}))")
    out += [f"line from C to S{k + 1} chop {LINE}" for k in range(n)]
    return define(f"hub{n}", out)


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------

HEADER = """\
# figures.pik: macros for diagrams whose shape is the point, bundled with
# pikslide (pikslide --help figures). Generated by scripts/gen_figures.py.
#
#     include "figures.pik"
#     P: cycle4("Plan", "Do", "Check", "Act")
#
# Each macro draws a block whose parts are named in it: P.S1, ... and P.C.
# Each part's argument is its strings and attributes, written last, so
# that they win: "Check" bold fill emphasis lighter 60%. figwid and fight
# are the size the figure fits; assign them after the include to change it.

figwid = 6
fight = 3.5
"""

FAMILIES = [
    (doc([f"cycle{n}" for n in range(3, 7)], "steps round a circle, each joined to the next by an arrow",
         "P: cycle4(STEP, STEP, STEP, STEP)",
         """
Three to six steps, the first at the top and the rest clockwise, each an
arrow from the one before: PDCA, a feedback loop. Each STEP is its box's
strings and attributes. The parts: S1 ... the steps, and C, the center,
for a word in the middle.""",
         """
include "figures.pik"
P: cycle4("Plan", "Do", "Check" fill emphasis lighter 60%, "Act")
text "Improve" bold at P.C"""),
     [cycle(n) for n in range(3, 7)]),
    (doc([f"chevron{n}" for n in range(3, 7)], "stages in a row of chevrons, left to right",
         "P: chevron4(STAGE, STAGE, STAGE, STAGE)",
         """
Three to six stages, the first a pentagon and the rest chevrons, each
fitting into the one before, as wide as figwid together and a fifth of
fight high. Each STAGE is its shape's strings and attributes. The parts:
S1 ... the stages.""",
         """
include "figures.pik"
P: chevron4("Plan", "Build", "Test", "Launch" fill emphasis lighter 60%)"""),
     [chevron(n) for n in range(3, 7)]),
    (doc([f"pyramid{n}" for n in range(3, 6)], "tiers of a pyramid, top to bottom",
         "P: pyramid3(TIER, TIER, TIER)",
         """
Three to five tiers of one triangle figwid wide at its base and fight
high, the top tier a triangle and the rest trapezoids: a hierarchy, a
mission, vision and values. The top tier is narrow: give it a word. Each
TIER is its shape's strings and attributes. The parts: S1 ... the tiers,
from the top.""",
         """
include "figures.pik"
P: pyramid3("Mission", "Vision", "Values")"""),
     [pyramid(n) for n in range(3, 6)]),
    (doc([f"funnel{n}" for n in range(3, 6)], "stages of a funnel, top to bottom",
         "P: funnel4(STAGE, STAGE, STAGE, STAGE)",
         """
Three to five stages, each a box narrower than the one above, centered,
from figwid wide at the top to four tenths of it at the bottom, fight
high together. Each STAGE is its box's strings and attributes. The
parts: S1 ... the stages, from the top.""",
         """
include "figures.pik"
P: funnel4("Visitors", "Leads", "Trials", "Customers" bold)"""),
     [funnel(n) for n in range(3, 6)]),
    (doc(["venn2", "venn3"], "two or three overlapping circles, with a word where they all overlap",
         "P: venn3(NAME, NAME, NAME, OVERLAP)",
         """
Two circles side by side, or three in a triangle, the first at the left
(top left), as big as figwid and fight allow. Each NAME is a text's
strings and attributes, in its circle's own part; OVERLAP is the text
where all of them overlap. The parts: S1 ... the circles, T1 ... their
names, and C, the overlap's text.""",
         """
include "figures.pik"
P: venn3("Will", "Can", "Must", "Calling" bold)"""),
     [venn(2), venn(3)]),
    (doc(["matrix2"], "a two-by-two matrix, with words at the ends of its axes",
         "P: matrix2(TOPLEFT, TOPRIGHT, BOTTOMLEFT, BOTTOMRIGHT, LEFT, RIGHT, BOTTOM, TOP)",
         """
Four boxes in two rows, figwid by fight together, and the axes' words
outside them: LEFT and RIGHT at the ends of the horizontal one, BOTTOM
and TOP of the vertical one. Leave an axis's words out (\"\") and it has
none. Each argument is its box's or text's strings and attributes. The
parts: S1 ... S4 the boxes, in reading order, and L, R, B, T the words.""",
         """
include "figures.pik"
P: matrix2("Strengths", "Weaknesses", "Opportunities", "Threats", "", "", "External", "Internal")"""),
     [matrix()]),
    (doc([f"hub{n}" for n in range(3, 9)], "a center joined to the items round it",
         "P: hub4(CENTER, ITEM, ITEM, ITEM, ITEM)",
         """
A circle in the center, and three to eight items round it, the first at
the top and the rest clockwise, each joined to it by a line. CENTER is
the circle's strings and attributes, and each ITEM its box's. The parts:
C, the center, and S1 ... the items.""",
         """
include "figures.pik"
P: hub4("Customer" bold, "Sales", "Support", "Product", "Marketing")"""),
     [hub(n) for n in range(3, 9)]),
]


def figures_source() -> str:
    parts = [HEADER]
    for docs, macros in FAMILIES:
        parts.append(docs + "\n" + "\n".join(macros) + "\n")
    return "\n".join(parts)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(figures_source(), encoding="utf-8")
    print(OUT)
