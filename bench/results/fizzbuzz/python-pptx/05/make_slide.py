"""Write fizzbuzz.pptx: a single slide holding a FizzBuzz flowchart."""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

EMU_PER_INCH = 914400


def E(inches):
    return Emu(int(round(inches * EMU_PER_INCH)))


# ---------------------------------------------------------------- style
INK = RGBColor(0x26, 0x32, 0x38)        # outlines, arrows, text
LABEL = RGBColor(0x45, 0x5A, 0x64)      # yes / no labels
FILL = {
    "oval": RGBColor(0xC8, 0xE6, 0xC9),
    "rect": RGBColor(0xBB, 0xDE, 0xFB),
    "diamond": RGBColor(0xFF, 0xEC, 0xB3),
    "para": RGBColor(0xF8, 0xD7, 0xE6),
}
PRESET = {
    "oval": MSO_SHAPE.OVAL,
    "rect": MSO_SHAPE.RECTANGLE,
    "diamond": MSO_SHAPE.DIAMOND,
    "para": MSO_SHAPE.PARALLELOGRAM,
}
CODE_FONT = "Consolas"
TEXT_FONT = "Calibri"
LINE_W = Pt(1.5)

# ---------------------------------------------------------------- geometry (inches)
SLIDE_W, SLIDE_H = 13.333, 7.5
H = {"oval": 0.48, "rect": 0.48, "diamond": 0.70, "para": 0.48}
W_OVAL, W_RECT, W_DIA, W_PRINT_I, W_PRINT = 1.4, 1.6, 2.6, 1.8, 2.5
GAP = 0.30                 # vertical gap between column shapes
YES_RUN = 1.0              # horizontal run from a diamond to its print
MERGE_RUN = 0.45           # print right side -> merge line
LOOP_RUN = 0.5             # diamond left vertex -> loop line

column = [
    ("start", "oval", "Start", W_OVAL),
    ("init", "rect", "i = 1", W_RECT),
    ("test", "diamond", "i <= 100", W_DIA),
    ("m15", "diamond", "i % 15 == 0", W_DIA),
    ("m3", "diamond", "i % 3 == 0", W_DIA),
    ("m5", "diamond", "i % 5 == 0", W_DIA),
    ("pi", "para", "print i", W_PRINT_I),
    ("inc", "rect", "i = i + 1", W_RECT),
]

total_h = sum(H[k] for _, k, _, _ in column) + GAP * (len(column) - 1)
top = (SLIDE_H - total_h) / 2

# Horizontal extent: loop line on the left, merge line on the right.
left_extent = W_DIA / 2 + LOOP_RUN
right_extent = W_DIA / 2 + YES_RUN + W_PRINT + MERGE_RUN
cx = (SLIDE_W - (left_extent + right_extent)) / 2 + left_extent

box = {}  # name -> (left, top, width, height, kind)
y = top
for name, kind, _, w in column:
    box[name] = (cx - w / 2, y, w, H[kind], kind)
    y += H[kind] + GAP


def mid_y(name):
    _, t, _, h, _ = box[name]
    return t + h / 2


def bottom(name):
    _, t, _, h, _ = box[name]
    return t + h


print_left = cx + W_DIA / 2 + YES_RUN
for name, diamond in (("pfb", "m15"), ("pf", "m3"), ("pb", "m5")):
    box[name] = (print_left, mid_y(diamond) - H["para"] / 2, W_PRINT,
                 H["para"], "para")
end_left = print_left + (W_PRINT - W_OVAL) / 2
box["end"] = (end_left, mid_y("test") - H["oval"] / 2, W_OVAL, H["oval"], "oval")


def para_slant(name):
    """Horizontal offset of a parallelogram's slanted side (preset adj 25000)."""
    _, _, w, h, _ = box[name]
    return 0.25 * min(w, h)


def para_left_mid(name):
    l, t, w, h, _ = box[name]
    return l + para_slant(name) / 2, t + h / 2


def para_right_mid(name):
    l, t, w, h, _ = box[name]
    return l + w - para_slant(name) / 2, t + h / 2


# ---------------------------------------------------------------- drawing helpers
prs = Presentation()
prs.slide_width = Emu(12192000)
prs.slide_height = Emu(6858000)
slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
for ph in list(slide.placeholders):
    ph._element.getparent().remove(ph._element)
shapes = slide.shapes


def no_effects(shape):
    spPr = shape._element.spPr
    if spPr.find(qn("a:effectLst")) is None:
        ln = spPr.find(qn("a:ln"))
        eff = spPr.makeelement(qn("a:effectLst"), {})
        if ln is not None:
            ln.addnext(eff)
        else:
            spPr.append(eff)


def style_line(shape, arrow):
    line = shape.line
    line.color.rgb = INK
    line.width = LINE_W
    ln = shape._element.spPr.find(qn("a:ln"))
    ln.append(ln.makeelement(qn("a:round"), {}))
    if arrow:
        ln.append(ln.makeelement(qn("a:tailEnd"),
                                 {"type": "triangle", "w": "med", "len": "med"}))
    no_effects(shape)


def segment(p, q, arrow=False):
    c = shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(p[0]), E(p[1]),
                             E(q[0]), E(q[1]))
    style_line(c, arrow)
    return c


def polyline(points, arrow=True):
    pts = [(E(x), E(y)) for x, y in points]
    fb = shapes.build_freeform(pts[0][0], pts[0][1], scale=1.0)
    fb.add_line_segments(pts[1:], close=False)
    s = fb.convert_to_shape()
    s.fill.background()
    style_line(s, arrow)
    return s


def node(name, text):
    l, t, w, h, kind = box[name]
    s = shapes.add_shape(PRESET[kind], E(l), E(t), E(w), E(h))
    s.fill.solid()
    s.fill.fore_color.rgb = FILL[kind]
    s.line.color.rgb = INK
    s.line.width = LINE_W
    no_effects(s)
    tf = s.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    f = r.font
    if kind == "oval":
        f.name, f.size, f.bold = TEXT_FONT, Pt(16), True
    else:
        f.name, f.size = CODE_FONT, Pt(14)
    f.color.rgb = INK
    return s


def label(text, l, t, w, h, align):
    tb = shapes.add_textbox(E(l), E(t), E(w), E(h))
    tf = tb.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.name, r.font.size, r.font.italic = TEXT_FONT, Pt(13), True
    r.font.color.rgb = LABEL
    return tb


def label_below(name, text):
    """Label beside a downward arrow leaving the bottom of `name`."""
    label(text, cx + 0.08, bottom(name), 0.6, GAP, PP_ALIGN.LEFT)


def label_above(x0, x1, yline, text):
    """Label centred above a horizontal arrow from x0 to x1 at yline."""
    label(text, x0, yline - 0.30, x1 - x0, 0.26, PP_ALIGN.CENTER)


# ---------------------------------------------------------------- shapes
texts = {name: text for name, _, text, _ in column}
texts.update({"pfb": 'print "FizzBuzz"', "pf": 'print "Fizz"',
              "pb": 'print "Buzz"', "end": "End"})
for name in [n for n, _, _, _ in column] + ["end", "pfb", "pf", "pb"]:
    node(name, texts[name])

# ---------------------------------------------------------------- column arrows
names = [n for n, _, _, _ in column]
for a, b in zip(names, names[1:]):
    segment((cx, bottom(a)), (cx, box[b][1]), arrow=True)
label_below("test", "yes")
for d in ("m15", "m3", "m5"):
    label_below(d, "no")

# i <= 100 --no--> End
x0 = cx + W_DIA / 2
segment((x0, mid_y("test")), (end_left, mid_y("test")), arrow=True)
label_above(x0, end_left, mid_y("test"), "no")

# diamonds --yes--> prints
for d, p in (("m15", "pfb"), ("m3", "pf"), ("m5", "pb")):
    px, py = para_left_mid(p)
    segment((x0, py), (px, py), arrow=True)
    label_above(x0, box[p][0], py, "yes")

# prints join into one line down the right side, into i = i + 1
xm = print_left + W_PRINT + MERGE_RUN
y_inc = mid_y("inc")
rx, ry = para_right_mid("pfb")
polyline([(rx, ry), (xm, ry), (xm, y_inc), (cx + W_RECT / 2, y_inc)])
for p in ("pf", "pb"):
    rx, ry = para_right_mid(p)
    segment((rx, ry), (xm, ry))

# i = i + 1 round the left side, back into i <= 100
xl = cx - W_DIA / 2 - LOOP_RUN
polyline([(cx - W_RECT / 2, y_inc), (xl, y_inc), (xl, mid_y("test")),
          (cx - W_DIA / 2, mid_y("test"))])

prs.save("fizzbuzz.pptx")
print("wrote fizzbuzz.pptx")
