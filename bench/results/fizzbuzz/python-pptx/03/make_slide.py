"""Write fizzbuzz.pptx: a single slide holding a FizzBuzz flowchart."""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt
from lxml import etree

SLIDE_W, SLIDE_H = 13.333, 7.5

LINE = RGBColor(0x26, 0x32, 0x38)
TEXT = RGBColor(0x1A, 0x1A, 0x1A)
LABEL = RGBColor(0x37, 0x47, 0x4F)
LINE_W = Pt(1.5)

FILL = {
    "oval": RGBColor(0xC8, 0xE6, 0xC9),
    "rect": RGBColor(0xBB, 0xDE, 0xFB),
    "diamond": RGBColor(0xFF, 0xF3, 0xC4),
    "para": RGBColor(0xE1, 0xD5, 0xF0),
}
GEOM = {
    "oval": MSO_SHAPE.OVAL,
    "rect": MSO_SHAPE.RECTANGLE,
    "diamond": MSO_SHAPE.DIAMOND,
    "para": MSO_SHAPE.PARALLELOGRAM,
}

SHAPE_FONT, SHAPE_PT = "Consolas", 14
LABEL_FONT, LABEL_PT = "Calibri", 12

# Shape sizes (inches)
OVAL_W, OVAL_H = 1.4, 0.45
RECT_W, RECT_H = 1.6, 0.45
DIA_W, DIA_H = 2.8, 0.70
PARA_W, PARA_H = 2.6, 0.45
PRINT_I_W = 1.8
PARA_SLANT = 0.25 * min(PARA_W, PARA_H)  # default parallelogram adj = 25%

MARGIN_Y = 0.2
LOOP_GAP = 0.45      # loop line distance left of the widest shape
YES_ARROW = 1.1      # diamond vertex -> print bounding-box left
BUS_GAP = 0.45       # bus line distance right of the prints

prs = Presentation()
prs.slide_width = Inches(SLIDE_W)
prs.slide_height = Inches(SLIDE_H)
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
for ph in list(slide.placeholders):
    ph._element.getparent().remove(ph._element)


def E(v):
    """inches -> EMU int"""
    return int(round(Inches(v)))


def drop_style(shape):
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)


def style_line(line, arrow=False):
    line.color.rgb = LINE
    line.width = LINE_W
    ln = line._get_or_add_ln()
    etree.SubElement(ln, qn("a:round"))
    if arrow:
        tail = etree.SubElement(ln, qn("a:tailEnd"))
        tail.set("type", "triangle")
        tail.set("w", "med")
        tail.set("len", "med")


def add_node(kind, text, cx, cy, w, h):
    shp = slide.shapes.add_shape(GEOM[kind], E(cx - w / 2), E(cy - h / 2), E(w), E(h))
    drop_style(shp)
    shp.fill.solid()
    shp.fill.fore_color.rgb = FILL[kind]
    shp.line.color.rgb = LINE
    shp.line.width = LINE_W
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    r.font.name = SHAPE_FONT
    r.font.size = Pt(SHAPE_PT)
    r.font.color.rgb = TEXT
    return {"cx": cx, "cy": cy, "w": w, "h": h, "kind": kind,
            "top": cy - h / 2, "bottom": cy + h / 2,
            "left": cx - w / 2, "right": cx + w / 2}


def left_pt(n):
    """Point on the outline at the middle of the shape's left side."""
    if n["kind"] == "para":
        return n["left"] + PARA_SLANT / 2, n["cy"]
    return n["left"], n["cy"]


def right_pt(n):
    if n["kind"] == "para":
        return n["right"] - PARA_SLANT / 2, n["cy"]
    return n["right"], n["cy"]


def arrow(p1, p2, head=True):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                   E(p1[0]), E(p1[1]), E(p2[0]), E(p2[1]))
    drop_style(c)
    style_line(c.line, arrow=head)
    return c


def polyline(points, head=True):
    """Open freeform path through points (inches), arrowhead at the end."""
    pts = [(E(x), E(y)) for x, y in points]
    fb = slide.shapes.build_freeform(pts[0][0], pts[0][1], scale=1.0)
    fb.add_line_segments(pts[1:], close=False)
    shp = fb.convert_to_shape()
    drop_style(shp)
    shp.fill.background()
    shp.shadow.inherit = False
    style_line(shp.line, arrow=head)
    return shp


def label(text, left, top, w=0.45, h=0.24, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(E(left), E(top), E(w), E(h))
    tf = tb.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.name = LABEL_FONT
    r.font.size = Pt(LABEL_PT)
    r.font.color.rgb = LABEL
    return tb


# ---- vertical layout of the main column ----
column = [
    ("oval", "Start", OVAL_W, OVAL_H),
    ("rect", "i = 1", RECT_W, RECT_H),
    ("diamond", "i <= 100", DIA_W, DIA_H),
    ("diamond", "i % 15 == 0", DIA_W, DIA_H),
    ("diamond", "i % 3 == 0", DIA_W, DIA_H),
    ("diamond", "i % 5 == 0", DIA_W, DIA_H),
    ("para", "print i", PRINT_I_W, PARA_H),
    ("rect", "i = i + 1", RECT_W, RECT_H),
]
total_h = sum(h for *_, h in column)
gap = (SLIDE_H - 2 * MARGIN_Y - total_h) / (len(column) - 1)

# ---- horizontal layout: centre the whole drawing on the slide ----
loop_x_off = -(DIA_W / 2 + LOOP_GAP)
print_left_off = DIA_W / 2 + YES_ARROW
bus_x_off = print_left_off + PARA_W + BUS_GAP
CX = SLIDE_W / 2 - (loop_x_off + bus_x_off) / 2

nodes = []
y = MARGIN_Y
for kind, text, w, h in column:
    nodes.append(add_node(kind, text, CX, y + h / 2, w, h))
    y += h + gap
start, init, cond, m15, m3, m5, print_i, inc = nodes

# ---- right-hand shapes ----
print_cx = CX + print_left_off + PARA_W / 2
end = add_node("oval", "End", print_cx, cond["cy"], OVAL_W, OVAL_H)
p_fb = add_node("para", 'print "FizzBuzz"', print_cx, m15["cy"], PARA_W, PARA_H)
p_f = add_node("para", 'print "Fizz"', print_cx, m3["cy"], PARA_W, PARA_H)
p_b = add_node("para", 'print "Buzz"', print_cx, m5["cy"], PARA_W, PARA_H)

# ---- main column arrows (with labels beside them) ----
column_labels = {cond["cy"]: "yes", m15["cy"]: "no", m3["cy"]: "no", m5["cy"]: "no"}
for a, b in zip(nodes, nodes[1:]):
    arrow((CX, a["bottom"]), (CX, b["top"]))
    if a["cy"] in column_labels:
        lh = 0.24
        label(column_labels[a["cy"]], CX + 0.1, a["bottom"] + (gap - lh) / 2, h=lh)


def side_arrow(src, dst, text):
    p1, p2 = right_pt(src), left_pt(dst)
    arrow(p1, p2)
    w = 0.45
    label(text, (p1[0] + p2[0]) / 2 - w / 2, p1[1] - 0.04 - 0.24, w=w,
          align=PP_ALIGN.CENTER)


side_arrow(cond, end, "no")
side_arrow(m15, p_fb, "yes")
side_arrow(m3, p_f, "yes")
side_arrow(m5, p_b, "yes")

# ---- prints join into one line down the right side, into i = i + 1 ----
bus_x = CX + bus_x_off
polyline([right_pt(p_fb), (bus_x, p_fb["cy"]), (bus_x, inc["cy"]), right_pt(inc)])
arrow(right_pt(p_f), (bus_x, p_f["cy"]), head=False)
arrow(right_pt(p_b), (bus_x, p_b["cy"]), head=False)

# ---- loop back round the left side into i <= 100 ----
loop_x = CX + loop_x_off
polyline([left_pt(inc), (loop_x, inc["cy"]), (loop_x, cond["cy"]), left_pt(cond)])

prs.save("fizzbuzz.pptx")
print("wrote fizzbuzz.pptx")
