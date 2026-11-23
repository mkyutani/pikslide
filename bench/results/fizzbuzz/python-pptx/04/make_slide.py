"""Write fizzbuzz.pptx: a one-slide flowchart of FizzBuzz (i = 1..100)."""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

# ---------------------------------------------------------------- geometry
SLIDE_W, SLIDE_H = 13.333, 7.5          # inches, 16:9

H_BOX = 0.45                            # ovals, rectangles, parallelograms
H_DIA = 0.70                            # diamonds
MARGIN_Y = 0.15

W_OVAL = 1.5
W_RECT = 1.8
W_DIA = 2.6
W_PRINT_I = 1.8
W_PRINT = 2.5                           # the three side prints

LOOP_GAP = 0.55                         # diamond left vertex -> loop line
YES_LEN = 1.0                           # diamond right vertex -> print
BUS_GAP = 0.5                           # print right edge -> bus line

PARA_ADJ = 0.25                         # default parallelogram slant ratio

FONT = "Consolas"
FONT_SIZE = Pt(14)
LABEL_FONT = "Calibri"
LABEL_SIZE = Pt(12)
LABEL_W, LABEL_H = 0.42, 0.22

INK = RGBColor(0x26, 0x26, 0x26)
LINE_W = Pt(1.5)
OUTLINE_W = Pt(1.25)

FILL = {
    "oval": RGBColor(0xD9, 0xEA, 0xD3),
    "rect": RGBColor(0xD6, 0xE4, 0xF5),
    "diamond": RGBColor(0xFF, 0xF2, 0xCC),
    "para": RGBColor(0xEA, 0xDC, 0xF2),
}
PRESET = {
    "oval": MSO_SHAPE.OVAL,
    "rect": MSO_SHAPE.RECTANGLE,
    "diamond": MSO_SHAPE.DIAMOND,
    "para": MSO_SHAPE.PARALLELOGRAM,
}


def emu(inches):
    return Emu(int(round(inches * 914400)))


# Column, top to bottom: (key, kind, text, width)
COLUMN = [
    ("start", "oval", "Start", W_OVAL),
    ("init", "rect", "i = 1", W_RECT),
    ("cond", "diamond", "i <= 100", W_DIA),
    ("m15", "diamond", "i % 15 == 0", W_DIA),
    ("m3", "diamond", "i % 3 == 0", W_DIA),
    ("m5", "diamond", "i % 5 == 0", W_DIA),
    ("pri", "para", "print i", W_PRINT_I),
    ("inc", "rect", "i = i + 1", W_RECT),
]


def height(kind):
    return H_DIA if kind == "diamond" else H_BOX


total_h = sum(height(k) for _, k, _, _ in COLUMN)
GAP = (SLIDE_H - 2 * MARGIN_Y - total_h) / (len(COLUMN) - 1)

# Horizontal: centre the whole drawing (loop line .. bus line) on the slide.
left_extent = W_DIA / 2 + LOOP_GAP
right_extent = W_DIA / 2 + YES_LEN + W_PRINT + BUS_GAP
XC = SLIDE_W / 2 - (right_extent - left_extent) / 2
LOOP_X = XC - left_extent
PRINT_L = XC + W_DIA / 2 + YES_LEN
BUS_X = PRINT_L + W_PRINT + BUS_GAP

# box[key] = (left, top, width, height)
box = {}
y = MARGIN_Y
for key, kind, _, w in COLUMN:
    h = height(kind)
    box[key] = (XC - w / 2, y, w, h)
    y += h + GAP


def cy(key):
    l, t, w, h = box[key]
    return t + h / 2


def top(key):
    return box[key][1]


def bottom(key):
    l, t, w, h = box[key]
    return t + h


def left(key):
    return box[key][0]


def right(key):
    l, t, w, h = box[key]
    return l + w


def para_slant(key):
    l, t, w, h = box[key]
    return PARA_ADJ * min(w, h)


# Side shapes: End beside "i <= 100", prints beside their diamonds.
box["end"] = (PRINT_L + (W_PRINT - W_OVAL) / 2, cy("cond") - H_BOX / 2,
              W_OVAL, H_BOX)
SIDE = [
    ("end", "oval", "End"),
    ("p15", "para", 'print "FizzBuzz"'),
    ("p3", "para", 'print "Fizz"'),
    ("p5", "para", 'print "Buzz"'),
]
for pkey, dkey in (("p15", "m15"), ("p3", "m3"), ("p5", "m5")):
    box[pkey] = (PRINT_L, cy(dkey) - H_BOX / 2, W_PRINT, H_BOX)


# ---------------------------------------------------------------- helpers
def drop_style(shape):
    """Remove the theme style reference so nothing (e.g. shadows) leaks in."""
    el = shape._element
    style = el.find(qn("p:style"))
    if style is not None:
        el.remove(style)


def set_line(shape, width, arrow):
    shape.line.color.rgb = INK
    shape.line.width = width
    if arrow:
        ln = shape.line._get_or_add_ln()
        tail = ln.makeelement(qn("a:tailEnd"),
                              {"type": "triangle", "w": "med", "len": "med"})
        ln.append(tail)


def style_text(tf, text, font, size, align=PP_ALIGN.CENTER):
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font
    run.font.size = size
    run.font.color.rgb = INK


def add_node(slide, key, kind, text):
    l, t, w, h = box[key]
    shp = slide.shapes.add_shape(PRESET[kind], emu(l), emu(t), emu(w), emu(h))
    drop_style(shp)
    shp.fill.solid()
    shp.fill.fore_color.rgb = FILL[kind]
    set_line(shp, OUTLINE_W, arrow=False)
    style_text(shp.text_frame, text, FONT, FONT_SIZE)
    return shp


def add_segment(slide, p0, p1, arrow=True):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                   emu(p0[0]), emu(p0[1]),
                                   emu(p1[0]), emu(p1[1]))
    drop_style(c)
    set_line(c, LINE_W, arrow)
    return c


def add_path(slide, points, arrow=True):
    """Open polyline through `points` (inches), arrowhead at the last one."""
    pts = [(emu(x), emu(y)) for x, y in points]
    fb = slide.shapes.build_freeform(pts[0][0], pts[0][1], scale=1.0)
    fb.add_line_segments(pts[1:], close=False)
    shp = fb.convert_to_shape()
    drop_style(shp)
    shp.fill.background()
    set_line(shp, LINE_W, arrow)
    return shp


def add_label(slide, text, cx, cy_):
    tb = slide.shapes.add_textbox(emu(cx - LABEL_W / 2), emu(cy_ - LABEL_H / 2),
                                  emu(LABEL_W), emu(LABEL_H))
    style_text(tb.text_frame, text, LABEL_FONT, LABEL_SIZE)
    return tb


# ---------------------------------------------------------------- build
prs = Presentation()
prs.slide_width = emu(SLIDE_W)
prs.slide_height = emu(SLIDE_H)
slide = prs.slides.add_slide(prs.slide_layouts[6])        # blank layout

for key, kind, text, _ in COLUMN:
    add_node(slide, key, kind, text)
for key, kind, text in SIDE:
    add_node(slide, key, kind, text)

# Vertical arrows down the column, bottom outline -> top outline.
keys = [k for k, _, _, _ in COLUMN]
for a, b in zip(keys, keys[1:]):
    add_segment(slide, (XC, bottom(a)), (XC, top(b)))

# Labels on the downward arrows out of the diamonds: right of the line,
# centred in the gap below the diamond.
LABEL_DX = 0.08 + LABEL_W / 2
for key, text in (("cond", "yes"), ("m15", "no"), ("m3", "no"), ("m5", "no")):
    add_label(slide, text, XC + LABEL_DX, bottom(key) + GAP / 2)

# "i <= 100" --no--> End
x0 = right("cond")
x1 = left("end")
add_segment(slide, (x0, cy("cond")), (x1, cy("cond")))
LABEL_DY = 0.05 + LABEL_H / 2
add_label(slide, "no", (x0 + x1) / 2, cy("cond") - LABEL_DY)

# Diamonds --yes--> their prints (arrow ends on the slanted left side).
for dkey, pkey in (("m15", "p15"), ("m3", "p3"), ("m5", "p5")):
    x0 = right(dkey)
    x1 = left(pkey) + para_slant(pkey) / 2
    add_segment(slide, (x0, cy(dkey)), (x1, cy(dkey)))
    add_label(slide, "yes", (x0 + x1) / 2, cy(dkey) - LABEL_DY)

# Prints join one line down the right side, into "i = i + 1".
def print_out_x(pkey):
    return right(pkey) - para_slant(pkey) / 2


add_path(slide, [(print_out_x("p15"), cy("p15")),
                 (BUS_X, cy("p15")),
                 (BUS_X, cy("inc")),
                 (right("inc"), cy("inc"))])
for pkey in ("p3", "p5"):
    add_segment(slide, (print_out_x(pkey), cy(pkey)), (BUS_X, cy(pkey)),
                arrow=False)

# "i = i + 1" round the left side, back into "i <= 100".
add_path(slide, [(left("inc"), cy("inc")),
                 (LOOP_X, cy("inc")),
                 (LOOP_X, cy("cond")),
                 (left("cond"), cy("cond"))])

prs.save("fizzbuzz.pptx")
print("wrote fizzbuzz.pptx")
