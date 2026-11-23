"""Write fizzbuzz.pptx: a single slide holding a FizzBuzz flowchart."""

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

SLIDE_W, SLIDE_H = 13.333, 7.5

INK = RGBColor(0x20, 0x20, 0x20)
FILL = {
    "oval": RGBColor(0xD9, 0xEA, 0xD3),
    "rect": RGBColor(0xCF, 0xE2, 0xF3),
    "diamond": RGBColor(0xFF, 0xF2, 0xCC),
    "para": RGBColor(0xFC, 0xE5, 0xCD),
}
KIND = {
    "oval": MSO_SHAPE.OVAL,
    "rect": MSO_SHAPE.RECTANGLE,
    "diamond": MSO_SHAPE.DIAMOND,
    "para": MSO_SHAPE.PARALLELOGRAM,
}

FONT = "Consolas"
SHAPE_PT = 14
LABEL_PT = 12
LINE_PT = 1.25

# Sizes (inches)
H_BOX = 0.44     # ovals, rectangles, parallelograms
H_DIA = 0.72     # diamonds
W_DIA = 2.8
W_RECT = 1.8
W_OVAL = 1.6
W_PRINT_I = 1.8
W_PRINT = 2.6    # the three prints on the right
GAP_PLAIN = 0.28     # vertical gap for unlabeled arrows
GAP_LABEL = 0.36     # vertical gap for labeled arrows
TOP = 0.25
DIA_TO_PRINT = 0.8   # horizontal gap: diamond's right vertex to print's left
PRINT_TO_BUS = 0.4   # horizontal gap: print's right to the joining line
LOOP_MARGIN = 0.45   # horizontal gap: diamond's left vertex to loop line

prs = Presentation()
prs.slide_width = Inches(SLIDE_W)
prs.slide_height = Inches(SLIDE_H)
slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank: no placeholders
shapes = slide.shapes


def para_offset(w, h):
    """Horizontal slant of the preset parallelogram (default adj 25000)."""
    return 0.25 * min(w, h)


def style_text(tf, text, size, align=PP_ALIGN.CENTER):
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = INK


def node(kind, text, cx, cy, w, h):
    shp = shapes.add_shape(
        KIND[kind], Inches(cx - w / 2), Inches(cy - h / 2), Inches(w), Inches(h)
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = FILL[kind]
    shp.line.color.rgb = INK
    shp.line.width = Pt(LINE_PT)
    shp.shadow.inherit = False
    style_text(shp.text_frame, text, SHAPE_PT)
    return dict(cx=cx, cy=cy, w=w, h=h, kind=kind,
                top=cy - h / 2, bottom=cy + h / 2,
                left=cx - w / 2, right=cx + w / 2)


def edge_left(n):
    """x where a horizontal line at the shape's mid-height meets its left outline."""
    if n["kind"] == "para":
        return n["left"] + para_offset(n["w"], n["h"]) / 2
    return n["left"]


def edge_right(n):
    if n["kind"] == "para":
        return n["right"] - para_offset(n["w"], n["h"]) / 2
    return n["right"]


def finish_line(line, arrow):
    line.color.rgb = INK
    line.width = Pt(LINE_PT)
    ln = line._get_or_add_ln()
    etree.SubElement(ln, qn("a:round"))
    if arrow:
        etree.SubElement(ln, qn("a:tailEnd"), type="triangle", w="med", len="med")


def path(points, arrow=True):
    """A line through `points` (inches); arrowhead at the last point."""
    if len(points) == 2:
        (x1, y1), (x2, y2) = points
        shp = shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)
        )
    else:
        emu = [(Inches(x), Inches(y)) for x, y in points]
        fb = shapes.build_freeform(emu[0][0], emu[0][1], scale=1.0)
        fb.add_line_segments(emu[1:], close=False)
        shp = fb.convert_to_shape()
        shp.fill.background()
        shp.shadow.inherit = False
    finish_line(shp.line, arrow)
    return shp


def label(text, x, y, w, h, align=PP_ALIGN.CENTER):
    tb = shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    style_text(tb.text_frame, text, LABEL_PT, align)


# ---- horizontal placement: center the whole drawing on the slide ----------
# Offsets from the column's center line cx:
loop_dx = -(W_DIA / 2 + LOOP_MARGIN)
print_left_dx = W_DIA / 2 + DIA_TO_PRINT
bus_dx = print_left_dx + W_PRINT + PRINT_TO_BUS
cx = SLIDE_W / 2 - (loop_dx + bus_dx) / 2
x_loop = cx + loop_dx
x_bus = cx + bus_dx
px = cx + print_left_dx + W_PRINT / 2  # center of the right-hand prints

# ---- vertical placement of the main column --------------------------------
column = [
    ("oval", "Start", W_OVAL, H_BOX),
    ("rect", "i = 1", W_RECT, H_BOX),
    ("diamond", "i <= 100", W_DIA, H_DIA),
    ("diamond", "i % 15 == 0", W_DIA, H_DIA),
    ("diamond", "i % 3 == 0", W_DIA, H_DIA),
    ("diamond", "i % 5 == 0", W_DIA, H_DIA),
    ("para", "print i", W_PRINT_I, H_BOX),
    ("rect", "i = i + 1", W_RECT, H_BOX),
]
gaps = [GAP_PLAIN, GAP_PLAIN, GAP_LABEL, GAP_LABEL, GAP_LABEL, GAP_LABEL,
        GAP_PLAIN]
total = sum(h for *_, h in column) + sum(gaps)
y = (SLIDE_H - total) / 2
nodes = []
for i, (kind, text, w, h) in enumerate(column):
    nodes.append(node(kind, text, cx, y + h / 2, w, h))
    y += h + (gaps[i] if i < len(gaps) else 0)

start, init, cond, d15, d3, d5, print_i, incr = nodes

# ---- column arrows ----------------------------------------------------------
LABEL_W, LABEL_H = 0.42, 0.24
for a, b, text in [
    (start, init, None),
    (init, cond, None),
    (cond, d15, "yes"),
    (d15, d3, "no"),
    (d3, d5, "no"),
    (d5, print_i, "no"),
    (print_i, incr, None),
]:
    path([(cx, a["bottom"]), (cx, b["top"])])
    if text:
        mid = (a["bottom"] + b["top"]) / 2
        label(text, cx + 0.09, mid - LABEL_H / 2, LABEL_W, LABEL_H,
              align=PP_ALIGN.LEFT)


def right_arrow(src, dst, text):
    """Labeled horizontal arrow from a diamond's right vertex to `dst`."""
    x1, x2 = src["right"], edge_left(dst)
    path([(x1, src["cy"]), (x2, src["cy"])])
    label(text, (x1 + x2) / 2 - LABEL_W / 2, src["cy"] - LABEL_H - 0.03,
          LABEL_W, LABEL_H)


# ---- End, to the right of the loop test -------------------------------------
end = node("oval", "End", px, cond["cy"], W_OVAL, H_BOX)
right_arrow(cond, end, "no")

# ---- the three prints on the right -----------------------------------------
prints = []
for d, text in [(d15, 'print "FizzBuzz"'), (d3, 'print "Fizz"'),
                (d5, 'print "Buzz"')]:
    p = node("para", text, px, d["cy"], W_PRINT, H_BOX)
    right_arrow(d, p, "yes")
    prints.append(p)

# The prints join one line down the right side, into i = i + 1.
fizzbuzz, fizz, buzz = prints
path([(edge_right(fizzbuzz), fizzbuzz["cy"]),
      (x_bus, fizzbuzz["cy"]),
      (x_bus, incr["cy"]),
      (incr["right"], incr["cy"])])
for p in (fizz, buzz):
    path([(edge_right(p), p["cy"]), (x_bus, p["cy"])], arrow=False)

# ---- loop back round the left side into the loop test -----------------------
path([(incr["left"], incr["cy"]),
      (x_loop, incr["cy"]),
      (x_loop, cond["cy"]),
      (cond["left"], cond["cy"])])

prs.save("fizzbuzz.pptx")
print("wrote fizzbuzz.pptx")
