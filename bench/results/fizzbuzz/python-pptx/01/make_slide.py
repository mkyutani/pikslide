"""Draw a FizzBuzz flowchart on a single blank 16:9 slide -> fizzbuzz.pptx."""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

SLIDE_W, SLIDE_H = 13.333, 7.5

INK = RGBColor(0x26, 0x32, 0x38)
LINE_W = Pt(1.5)
FONT = "Calibri"
SHAPE_PT = 14
LABEL_PT = 12

FILLS = {
    "oval": RGBColor(0xC8, 0xE6, 0xC9),
    "rect": RGBColor(0xBB, 0xDE, 0xFB),
    "diamond": RGBColor(0xFF, 0xE0, 0xB2),
    "para": RGBColor(0xE1, 0xBE, 0xE7),
}
KINDS = {
    "oval": MSO_SHAPE.OVAL,
    "rect": MSO_SHAPE.RECTANGLE,
    "diamond": MSO_SHAPE.DIAMOND,
    "para": MSO_SHAPE.PARALLELOGRAM,
}

# Shape sizes (inches)
SIZES = {
    "oval": (1.3, 0.42),
    "rect": (1.6, 0.42),
    "diamond": (2.4, 0.75),
    "para": (2.2, 0.42),
}
GAP = 0.32  # vertical gap between column shapes


class Box:
    """Geometry of a flowchart shape, in inches, with outline anchor points."""

    def __init__(self, kind, cx, cy):
        self.kind = kind
        self.w, self.h = SIZES[kind]
        self.cx, self.cy = cx, cy
        self.left = cx - self.w / 2
        self.right = cx + self.w / 2
        self.top = cy - self.h / 2
        self.bottom = cy + self.h / 2
        # Parallelogram default adj = 25000 -> slant = 0.25 * min(w, h)
        self.slant = 0.25 * min(self.w, self.h) if kind == "para" else 0.0

    def n(self):
        return (self.cx, self.top)

    def s(self):
        return (self.cx, self.bottom)

    def w_pt(self):
        # left outline at mid-height (slanted edge for parallelograms)
        return (self.left + self.slant / 2, self.cy)

    def e_pt(self):
        return (self.right - self.slant / 2, self.cy)


def strip_style(shape):
    """Remove theme style reference so nothing (shadows, colors) leaks in."""
    style = shape._element.find(qn("p:style"))
    if style is not None:
        shape._element.remove(style)


def add_arrowhead(shape):
    ln = shape.line._get_or_add_ln()
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)


def style_line(shape, arrow):
    strip_style(shape)
    shape.line.color.rgb = INK
    shape.line.width = LINE_W
    if arrow:
        add_arrowhead(shape)


def draw_shape(slide, box, text):
    shp = slide.shapes.add_shape(
        KINDS[box.kind],
        Inches(box.left), Inches(box.top), Inches(box.w), Inches(box.h),
    )
    strip_style(shp)
    shp.fill.solid()
    shp.fill.fore_color.rgb = FILLS[box.kind]
    shp.line.color.rgb = INK
    shp.line.width = LINE_W
    tf = shp.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = text
    run.font.size = Pt(SHAPE_PT)
    run.font.name = FONT
    run.font.color.rgb = INK
    return shp


def draw_segment(slide, p0, p1, arrow):
    c = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(p0[0]), Inches(p0[1]), Inches(p1[0]), Inches(p1[1]),
    )
    style_line(c, arrow)
    return c


def draw_polyline(slide, pts, arrow):
    """Open multi-segment path; the arrowhead (if any) sits at the last point."""
    emu = [(int(Inches(x)), int(Inches(y))) for x, y in pts]
    fb = slide.shapes.build_freeform(emu[0][0], emu[0][1], scale=1.0)
    fb.add_line_segments(emu[1:], close=False)
    shp = fb.convert_to_shape()
    style_line(shp, arrow)
    shp.fill.background()
    return shp


def draw_label(slide, text, x, y, w, h, align):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(LABEL_PT)
    run.font.name = FONT
    run.font.italic = True
    run.font.color.rgb = INK
    return tb


LABEL_W, LABEL_H = 0.4, 0.22


def label_below(slide, text, box):
    """Label beside a downward arrow leaving box's bottom vertex."""
    y = box.bottom + (GAP - LABEL_H) / 2
    draw_label(slide, text, box.cx + 0.08, y, LABEL_W, LABEL_H, PP_ALIGN.LEFT)


def label_above(slide, text, x0, x1, y):
    """Label centred above a horizontal arrow running from x0 to x1 at y."""
    xm = (x0 + x1) / 2
    draw_label(slide, text, xm - LABEL_W / 2, y - 0.05 - LABEL_H, LABEL_W, LABEL_H,
               PP_ALIGN.CENTER)


def main():
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank

    # ---- horizontal layout -------------------------------------------------
    dw = SIZES["diamond"][0]
    side_gap = 1.0          # diamond right vertex -> print / End
    loop_margin = 0.55      # column's widest shape -> left loop line
    bus_margin = 0.45       # print right edge -> right bus line
    pw = SIZES["para"][0]
    left_extent = dw / 2 + loop_margin
    right_extent = dw / 2 + side_gap + pw + bus_margin
    cx = SLIDE_W / 2 - (right_extent - left_extent) / 2
    side_cx = cx + dw / 2 + side_gap + pw / 2
    loop_x = cx - left_extent
    bus_x = cx + right_extent

    # ---- vertical layout ---------------------------------------------------
    column = [
        ("oval", "Start"),
        ("rect", "i = 1"),
        ("diamond", "i <= 100"),
        ("diamond", "i % 15 == 0"),
        ("diamond", "i % 3 == 0"),
        ("diamond", "i % 5 == 0"),
        ("para", "print i"),
        ("rect", "i = i + 1"),
    ]
    total_h = sum(SIZES[k][1] for k, _ in column) + GAP * (len(column) - 1)
    y = (SLIDE_H - total_h) / 2
    boxes = []
    for kind, text in column:
        h = SIZES[kind][1]
        boxes.append((Box(kind, cx, y + h / 2), text))
        y += h + GAP

    start, init, cond, m15, m3, m5, print_i, incr = [b for b, _ in boxes]

    end = Box("oval", cx + dw / 2 + side_gap + SIZES["oval"][0] / 2, cond.cy)
    p_fb = Box("para", side_cx, m15.cy)
    p_f = Box("para", side_cx, m3.cy)
    p_b = Box("para", side_cx, m5.cy)

    # ---- connectors (drawn first so shapes sit on top) ---------------------
    col = [b for b, _ in boxes]
    for a, b in zip(col, col[1:]):
        draw_segment(slide, a.s(), b.n(), arrow=True)

    label_below(slide, "yes", cond)
    for d in (m15, m3, m5):
        label_below(slide, "no", d)

    # i <= 100 --no--> End
    draw_segment(slide, cond.e_pt(), end.w_pt(), arrow=True)
    label_above(slide, "no", cond.right, end.left, cond.cy)

    # diamonds --yes--> prints
    for d, p in ((m15, p_fb), (m3, p_f), (m5, p_b)):
        draw_segment(slide, d.e_pt(), p.w_pt(), arrow=True)
        label_above(slide, "yes", d.right, p.w_pt()[0], d.cy)

    # prints join into one line down the right side, into i = i + 1
    draw_polyline(
        slide,
        [p_fb.e_pt(), (bus_x, p_fb.cy), (bus_x, incr.cy), incr.e_pt()],
        arrow=True,
    )
    for p in (p_f, p_b):
        draw_segment(slide, p.e_pt(), (bus_x, p.cy), arrow=False)

    # i = i + 1 loops round the left side back into i <= 100
    draw_polyline(
        slide,
        [incr.w_pt(), (loop_x, incr.cy), (loop_x, cond.cy), cond.w_pt()],
        arrow=True,
    )

    # ---- shapes --------------------------------------------------------------
    for box, text in boxes:
        draw_shape(slide, box, text)
    draw_shape(slide, end, "End")
    draw_shape(slide, p_fb, 'print "FizzBuzz"')
    draw_shape(slide, p_f, 'print "Fizz"')
    draw_shape(slide, p_b, 'print "Buzz"')

    prs.save("fizzbuzz.pptx")


if __name__ == "__main__":
    main()
