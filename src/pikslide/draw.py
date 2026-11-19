"""--renderer direct (issue #34): a diagram's PNG, or PDF, drawn by
pikslide itself with Pillow -- where PowerPoint can't be had: a Mac or a
Linux machine, an LLM host's sandbox, a server.

It draws from the layout, not from the deck, what pptx_writer writes, as
PowerPoint draws it: each preset's own outline (pik.outline), filled and
outlined as the deck has it, its shaded faces shaded, turned and
flipped; lines with their arrowheads, sized as PowerPoint sizes them;
text in the fonts `fit` measured with, at the same sizes, where
PowerPoint sets it; images. It draws on the slide the deck has, so a
--template's slide is its size, with the diagram in its content area;
but not the template's background, its master's graphics or its
placeholders.

It can differ from PowerPoint a little: where a line of text breaks, a
baseline by a pixel or so, an arrowhead's or a curve's shape. And it
never shows text overflowing its shape, being drawn in the fonts `fit`
made room for: --check's warnings and --strict tell that.
"""

from __future__ import annotations

import colorsys
import io
import math
import subprocess

from PIL import Image, ImageChops, ImageDraw

from .fonts import baseline_ratio
from .pik.layout import (
    LINE_LIKE,
    Color,
    LayoutResult,
    Shape,
    _rsvg_convert_path,
    arrowheads,
    assign_text_slots,
    drawn_size,
    flatten_shapes,
    line_points,
    preset_of,
    string_color,
)
from .pik.outline import outline
from .pik.text_area import text_rect
from .pptx_writer import _LINE_PITCH, FontRun, PilFontMetrics, _is_east_asian, _line_label_rects, slide_setup

DPI = 200
"""Pixels to the inch, as pptx_to_png.ps1 exports PowerPoint's."""

# Drawn this many times bigger, then scaled down, for smooth edges; less
# on a slide so big that it would take too much memory.
_SUPERSAMPLE = 3
_MAX_PIXELS = 60_000_000

# A preset's shaded faces (ECMA-376 Part 1, 20.1.10.37): a lighter one is
# the fill blended with that much white, a darker one that much nearer
# black, as PowerPoint draws them (checked: a 0x808080 fill's faces are
# 179, 153, 77 and 103, the last 205/255 of it rather than 0.8).
_SHADES = {"lighten": 0.4, "lightenLess": 0.2, "darken": -0.4, "darkenLess": -50 / 255}

# An arrowhead's width and length, each a multiple of the line's width
# but no less than 0.7mm's, by its size (checked against PowerPoint at
# two widths and the three sizes).
_ARROW_SCALE = {"small": 2.0, None: 3.0, "large": 5.0}
_ARROW_LEAST_BASE = 0.7 / 25.4
# How far back from its tip a stealth arrowhead's notch is, of its length.
_STEALTH_NOTCH = 2 / 3

# How much thicker PowerPoint draws a bold it has no bold face for, of
# the size, its strokes grown rightward, its widths kept (checked: BIZ
# UD明朝 Medium at 40pt).
_EMBOLDEN = 1 / 55

# Dashes and gaps, as multiples of the line's width: PowerPoint's `dash`
# and `sysDot`, which pptx_writer writes for `dashed` and `dotted`.
_DASH = (4.0, 3.0)
_DOT = (1.0, 1.0)


def draw(result: LayoutResult, template_path: str | None = None, layout_name: str = "", dpi: int = DPI) -> Image.Image:
    """`result` drawn on its slide (pptx_writer.slide_setup()), `dpi`
    pixels to the inch."""
    setup = slide_setup(result, template_path, layout_name)
    painter = _Painter(setup, dpi)
    for shape in flatten_shapes(result.shapes):
        if shape.kind in LINE_LIKE:
            painter.line(shape)
        elif shape.kind == "image":
            painter.image(shape)
        else:
            painter.block(shape)
    return painter.finish()


def save(image: Image.Image, path: str, fmt: str, dpi: int = DPI) -> None:
    """Write `image` to `path` as a PNG, or as a PDF of the same picture
    (`fmt`, "png" or "pdf")."""
    if fmt == "pdf":
        image.save(path, "PDF", resolution=float(dpi))
    else:
        image.save(path, "PNG", dpi=(dpi, dpi))


Point = tuple[float, float]


class _Painter:
    def __init__(self, setup, dpi: int):
        self.tf = setup.tf
        self.colors = setup.theme_colors
        self.metrics = PilFontMetrics(theme_fonts=setup.theme_fonts)
        self.size = (_pixels(self.tf.slide_width, dpi), _pixels(self.tf.slide_height, dpi))
        self.ss = _SUPERSAMPLE
        while self.ss > 1 and self.size[0] * self.size[1] * self.ss**2 > _MAX_PIXELS:
            self.ss -= 1
        self.scale = dpi * self.ss  # canvas pixels to the inch
        self.canvas = Image.new("RGB", (self.size[0] * self.ss, self.size[1] * self.ss), "white")
        self._ratios: dict[tuple[str, int], float] = {}

    def finish(self) -> Image.Image:
        return self.canvas.reduce(self.ss) if self.ss > 1 else self.canvas

    # -- colors --------------------------------------------------------

    def rgb(self, color: Color | None) -> tuple[int, int, int]:
        """`color` as RGB: a theme color in this slide's theme, `lighter`
        and `darker` applied to its luminance, as PowerPoint applies
        lumMod and lumOff. None is black, as the writer has it."""
        if color is None:
            return (0, 0, 0)
        value = self.colors.get(color.theme_slot, 0) if color.theme_slot else (color.rgb or 0)
        r, g, b = (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF
        if color.lum_mod != 1.0 or color.lum_off != 0.0:
            h, light, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            light = min(1.0, max(0.0, light * color.lum_mod + color.lum_off))
            r, g, b = (round(c * 255) for c in colorsys.hls_to_rgb(h, light, s))
        return (r, g, b)

    # -- block shapes: a preset, its text ------------------------------

    def block(self, shape: Shape) -> None:
        """A preset shape, a box, a circle, ... or a text object: drawn on
        a tile of its own about its center, unturned, then turned."""
        left, top, w, h = self.tf.rect(shape)
        preset = preset_of(shape) or "rect"
        adjust = {}
        if preset == "roundRect" and shape.rad > 0 and min(w, h) > 0:
            adjust["adj"] = min(0.5, shape.rad / min(w, h)) * 100000  # as pptx_writer sets it
        adjust.update(shape.adjust)
        paths = outline(preset, w, h, adjust)

        def flip(p: Point) -> Point:
            return (w - p[0] if shape.flip_h else p[0], h - p[1] if shape.flip_v else p[1])

        paths = [(path, [([flip(p) for p in points], closed) for points, closed in path.subpaths]) for path in paths]
        lines = self._frame_text(shape, preset, w, h, adjust) if shape.texts else []
        lw = 0.0 if shape.kind == "text" or shape.sw < 0 else max(shape.sw, 0.001)

        # The tile: centered on the shape's center, holding all it draws
        # (a callout's tip is outside its box), turned.
        extent = [p for _path, subpaths in paths for points, _ in subpaths for p in points]
        extent += [corner for line in lines for corner in line.corners()]
        pad = lw + 2 * self.ss / self.scale  # and two pixels
        cx, cy = w / 2, h / 2
        if shape.rotate:
            r = max(math.dist((cx, cy), p) for p in extent) + pad
            hx = hy = r
        else:
            hx = max(abs(x - cx) for x, _ in extent) + pad
            hy = max(abs(y - cy) for _, y in extent) + pad
        size = (max(1, math.ceil(2 * hx * self.scale)), max(1, math.ceil(2 * hy * self.scale)))
        tile = Image.new("RGBA", size, (0, 0, 0, 0))
        origin = (size[0] / 2 - cx * self.scale, size[1] / 2 - cy * self.scale)

        def px(p: Point) -> Point:
            return (origin[0] + p[0] * self.scale, origin[1] + p[1] * self.scale)

        fill = None if shape.kind == "text" or shape.fill is None else self.rgb(shape.fill)
        stroke = self.rgb(shape.color)
        for path, subpaths in paths:
            subpaths_px = [([px(p) for p in points], closed) for points, closed in subpaths]
            if fill is not None and path.fill != "none":
                _fill(tile, [points for points, _ in subpaths_px], _shade(fill, path.fill))
        for path, subpaths in paths:
            if lw and path.stroke:
                for points, closed in subpaths:
                    self._stroke(ImageDraw.Draw(tile), [px(p) for p in points], closed, lw, stroke, shape)

        if lines:
            text = Image.new("RGBA", size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(text)
            for line in lines:
                line.draw(draw, px)
            if shape.flip_v:
                # PowerPoint turns a flipped shape's text upside down, in place.
                text = text.rotate(180, center=px(lines[0].frame_center))
            tile.alpha_composite(text)
        if shape.rotate:
            tile = tile.rotate(-shape.rotate, resample=Image.Resampling.BICUBIC, center=(size[0] / 2, size[1] / 2))
        at = ((left + cx) * self.scale - size[0] / 2, (top + cy) * self.scale - size[1] / 2)
        self.canvas.paste(tile, (round(at[0]), round(at[1])), tile)

    def _frame_text(self, shape: Shape, preset: str, w: float, h: float, adjust: dict) -> list[_TextLine]:
        """Where `shape`'s strings go, as pptx_writer._apply_text() sets
        them: in its preset's text rectangle, less `margin` and `vmargin`
        (above/below moving them), middle-anchored, wrapped unless `fit`
        sized the shape to them."""
        l, t, r, b = text_rect(preset, w, h, adjust)
        if shape.flip_h:
            l, r = w - r, w - l
        if shape.flip_v:
            t, b = h - b, h - t
        top = bottom = shape.text_vmargin
        if shape.text_dy > 0:
            bottom += 2 * shape.text_dy
        elif shape.text_dy < 0:
            top += -2 * shape.text_dy
        frame = (l + shape.text_margin, t + top, r - shape.text_margin, b - bottom)
        return self._layout_text(shape, frame, wrap=not shape.fit, split=shape.text_split)

    def _layout_text(self, shape: Shape, frame: tuple[float, float, float, float], wrap: bool,
                     split: float = 0.0, anchor_top: bool = False) -> list[_TextLine]:
        """`shape`'s strings set in `frame` (l, t, r, b inches), a paragraph
        each, at single spacing (_LINE_PITCH), aligned as their flags say."""
        fl, ft, fr, fb = frame
        first_below = None
        if split > 0:
            slots = assign_text_slots(shape.texts)
            first_below = next(i for i, slot in enumerate(slots) if slot.startswith("below"))
        center = ((fl + fr) / 2, (ft + fb) / 2)
        lines: list[_TextLine] = []
        for i, (text, flags) in enumerate(shape.texts):
            size_in = self.metrics.size_pt(flags, shape.text_sizes) / 72
            size_px = max(1, round(size_in * self.scale))
            color = self.rgb(string_color(shape, i) or Color(rgb=0))
            runs = self.metrics.run_fonts(text, flags, shape.text_sizes, shape.typeface, size_px)
            for k, line_runs in enumerate(_wrap(runs, (fr - fl) * self.scale) if wrap and fr > fl else [runs]):
                width = sum(run.font.getlength(run.text) for run in line_runs) / self.scale
                if "ljust" in flags:
                    x = fl
                elif "rjust" in flags:
                    x = fr - width
                else:
                    x = (fl + fr - width) / 2
                # A line mixing scripts sits between its fonts' baselines
                # (checked: Calibri's and MS PGothic's).
                faces = {run.face for run in line_runs if run.face is not None}
                ratio = sum(self._ratio(face) for face in faces) / len(faces) if faces else 0.96
                before = split if i == first_below and k == 0 else 0.0
                lines.append(_TextLine(x, width, before, _LINE_PITCH * size_in, ratio * size_in, line_runs, color,
                                       center))
        total = sum(line.before + line.pitch for line in lines)
        y = ft if anchor_top else ft + ((fb - ft) - total) / 2
        for line in lines:
            y += line.before
            line.top = y
            y += line.pitch
        return lines

    def _ratio(self, face: tuple[str, int]) -> float:
        if face not in self._ratios:
            self._ratios[face] = baseline_ratio(*face)
        return self._ratios[face]

    # -- lines ---------------------------------------------------------

    def line(self, shape: Shape) -> None:
        """A line, an arrow, a spline or an arc, with its arrowheads, and
        its labels."""
        if shape.sw >= 0 and shape.path is not None:
            points = [self._px(self.tf.point(p)) for p in line_points(shape)]
            points = [p for i, p in enumerate(points) if i == 0 or p != points[i - 1]]
            if len(points) > 1:
                self._line_with_heads(shape, points)
        # Each label in a text box of its own, as pptx_writer._add_line_text()
        # draws it: one line, top-anchored, no insets, aligned in the box.
        draw = ImageDraw.Draw(self.canvas)
        for i, ((x0, y0, x1, y1), text, flags) in enumerate(_line_label_rects(shape)):
            left, top = self.tf.point((x0, y1))
            label = Shape(kind="text", name=None, cx=0.0, cy=0.0, w=0.0, h=0.0, texts=[(text, flags)],
                          text_colors=[string_color(shape, i)], text_sizes=shape.text_sizes, typeface=shape.typeface)
            for line in self._layout_text(label, (left, top, left + (x1 - x0), top + (y1 - y0)), wrap=False,
                                          anchor_top=True):
                line.draw(draw, self._px)

    def _px(self, p: Point) -> Point:
        return (p[0] * self.scale, p[1] * self.scale)

    def _line_with_heads(self, shape: Shape, points: list[Point]) -> None:
        lw_in = max(shape.sw, 0.001)
        lw = lw_in * self.scale
        color = self.rgb(shape.color)
        draw = ImageDraw.Draw(self.canvas)
        base = max(lw_in, _ARROW_LEAST_BASE) * self.scale
        heads = []
        for (kind, size), end, before in zip(arrowheads(shape), (points[0], points[-1]), (points[1], points[-2])):
            if kind == "none":
                heads.append(None)
                continue
            dx, dy = end[0] - before[0], end[1] - before[1]
            norm = math.hypot(dx, dy) or 1.0
            u = (dx / norm, dy / norm)
            heads.append((kind, end, u, _ARROW_SCALE[size] * base, _ARROW_SCALE[size] * base))
        # The line stops inside its arrowheads, so that its square end
        # doesn't show past a tip.
        trimmed = list(points)
        for i, head in ((0, heads[0]), (-1, heads[1])):
            if head is None:
                continue
            kind, end, u, width, length = head
            back = {"triangle": length / 2, "stealth": length / 2, "open": _open_inset(width, length, lw)}.get(kind, 0.0)
            trimmed[i] = (end[0] - u[0] * back, end[1] - u[1] * back)
        if shape.closed:
            trimmed = trimmed + [trimmed[0]]
        self._stroke(draw, trimmed, False, lw_in, color, shape)
        for head in heads:
            if head is not None:
                _arrowhead(draw, *head, lw, color)

    def _stroke(self, draw: ImageDraw.ImageDraw, points: list[Point], closed: bool, lw_in: float,
                color: tuple[int, int, int], shape: Shape) -> None:
        """`points` stroked `lw_in` inches wide, dashed or dotted as
        `shape` is. The dashes start at the start, and along a closed
        outline run the other way round from it: PowerPoint's on two dashed
        rectangles fit that best (a line's run along it, checked)."""
        lw = max(1.0, lw_in * self.scale)
        pattern = _DASH if shape.dashed > 0 else _DOT if shape.dotted > 0 else None
        if closed and len(points) > 2:
            ring = [points[0], *points[:0:-1], points[0]]
            points = ring if pattern is not None else ring + [ring[1]]  # the last corner joined too
        pieces = [points] if pattern is None else _dashes(points, pattern[0] * lw, pattern[1] * lw)
        for piece in pieces:
            if len(piece) > 1:
                draw.line(piece, fill=color, width=max(1, round(lw)), joint="curve")

    # -- images --------------------------------------------------------

    def image(self, shape: Shape) -> None:
        left, top, w, h = self.tf.rect(shape)
        size = (max(1, round(w * self.scale)), max(1, round(h * self.scale)))
        assert shape.image_path is not None
        if shape.image_path.lower().endswith(".svg"):
            png = subprocess.run([_rsvg_convert_path(), "--format=png", f"--width={size[0]}", f"--height={size[1]}",
                                  shape.image_path], capture_output=True, check=True).stdout
            picture = Image.open(io.BytesIO(png))
        else:
            picture = Image.open(shape.image_path)
        picture = picture.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
        at = (round(left * self.scale), round(top * self.scale))
        self.canvas.paste(picture, at, picture)
        if shape.texts:
            # As pptx_writer._add_image_shape() sets it: a text box over the
            # picture, middle-anchored, no insets.
            lines = self._layout_text(shape, (left, top, left + w, top + h), wrap=not shape.fit)
            draw = ImageDraw.Draw(self.canvas)
            for line in lines:
                line.draw(draw, self._px)


class _TextLine:
    """A line of text, in inches: its left edge and width, the space
    before it (a paragraph's), its height (_LINE_PITCH times its size)
    and its baseline below its top (fonts.baseline_ratio()), its runs
    (FontRun) and color; and the middle of the frame it's set in. `top`
    is set once all of a frame's lines are known."""

    def __init__(self, x: float, width: float, before: float, pitch: float, baseline: float, runs,
                 color: tuple[int, int, int], frame_center: Point):
        self.x, self.width, self.before, self.pitch, self.baseline = x, width, before, pitch, baseline
        self.runs, self.color, self.frame_center = runs, color, frame_center
        self.top = 0.0

    def corners(self) -> list[Point]:
        return [(self.x, self.top), (self.x + self.width, self.top + self.pitch)]

    def draw(self, draw: ImageDraw.ImageDraw, px) -> None:
        x, y = px((self.x, self.top + self.baseline))
        for run in self.runs:
            # A bold with no bold face, emboldened as PowerPoint does it:
            # thicker to the right, as wide as it was.
            grow = round(run.font.size * _EMBOLDEN / 2) if run.embolden else 0
            draw.text((x + grow, y), run.text, font=run.font, fill=self.color, anchor="ls",
                      stroke_width=grow, stroke_fill=self.color)
            x += run.font.getlength(run.text)


def _pixels(inches: float, dpi: int) -> int:
    """A slide side in pixels as pptx_to_png.ps1 has PowerPoint export it:
    the side in whole EMU, as the deck has it, rounded to PowerPoint's own
    576ths of an inch, then to the pixel (checked: a side of 457.4998
    pixels comes out 458, one of 2294.61 2294)."""
    return max(1, round(round(int(inches * 914400) / 1587.5) * dpi / 576))


def _wrap(runs: list[FontRun], width: float) -> list[list[FontRun]]:
    """`runs` broken into lines no wider than `width` pixels where
    PowerPoint would break them: after a space, or between East Asian
    characters, or else anywhere in a word too long for a line of its
    own."""
    pieces: list[FontRun] = []
    for run in runs:
        word = ""
        for ch in run.text:
            if _is_east_asian(ch):
                if word:
                    pieces.append(run._replace(text=word))
                    word = ""
                pieces.append(run._replace(text=ch))
            else:
                word += ch
                if ch == " ":
                    pieces.append(run._replace(text=word))
                    word = ""
        if word:
            pieces.append(run._replace(text=word))

    def length(piece: FontRun, text: str | None = None) -> float:
        return piece.font.getlength(piece.text if text is None else text)

    lines: list[list[FontRun]] = [[]]
    used = 0.0
    for piece in pieces:
        w = length(piece, piece.text.rstrip(" "))
        if lines[-1] and used + w > width:
            lines.append([])
            used = 0.0
        while not lines[-1] and w > width and len(piece.text) > 1:
            # A word too long for a line of its own: as much as fits.
            text = piece.text
            n = max(1, max((k for k in range(1, len(text)) if length(piece, text[:k]) <= width), default=1))
            lines[-1].append(piece._replace(text=text[:n]))
            lines.append([])
            piece = piece._replace(text=text[n:])
            w = length(piece, piece.text.rstrip(" "))
        lines[-1].append(piece)
        used += length(piece)
    out = []
    for line in lines:
        if line:
            *head, last = line
            out.append(head + [last._replace(text=last.text.rstrip(" "))])
    return out or [[]]


def _shade(rgb: tuple[int, int, int], mode: str) -> tuple[int, int, int]:
    f = _SHADES.get(mode, 0.0)
    if f > 0:
        return tuple(round(c + f * (255 - c)) for c in rgb)
    return tuple(round(c * (1 + f)) for c in rgb)


def _fill(tile: Image.Image, subpaths: list[list[Point]], rgb: tuple[int, int, int]) -> None:
    """Fill `subpaths` on `tile`, even-odd: a donut's hole stays empty."""
    subpaths = [points for points in subpaths if len(points) > 2]
    if not subpaths:
        return
    if len(subpaths) == 1:
        ImageDraw.Draw(tile).polygon(subpaths[0], fill=rgb + (255,))
        return
    mask = Image.new("L", tile.size, 0)
    for points in subpaths:
        one = Image.new("L", tile.size, 0)
        ImageDraw.Draw(one).polygon(points, fill=255)
        mask = ImageChops.difference(mask, one)
    tile.paste(rgb + (255,), mask=mask)


def _dashes(points: list[Point], on: float, off: float) -> list[list[Point]]:
    """The dashes along `points`, `on` long with `off` between them."""
    pieces: list[list[Point]] = []
    current: list[Point] = [points[0]]
    drawing, left = True, on
    for a, b in zip(points, points[1:]):
        seg = math.dist(a, b)
        pos = 0.0
        while seg - pos > left:
            pos += left
            t = pos / seg
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if drawing:
                current.append(p)
                pieces.append(current)
            else:
                current = [p]
            drawing = not drawing
            left = on if drawing else off
        left -= seg - pos
        if drawing:
            current.append(b)
    if drawing and len(current) > 1:
        pieces.append(current)
    return pieces


def _open_inset(width: float, length: float, lw: float) -> float:
    """How far back from its tip an open arrowhead's arms meet, so that
    their outer edges meet at the tip."""
    half_angle = math.atan2(width / 2, length)
    return lw / 2 / max(math.sin(half_angle), 1e-6)


def _arrowhead(draw: ImageDraw.ImageDraw, kind: str, end: Point, u: Point, width: float, length: float,
               lw: float, color: tuple[int, int, int]) -> None:
    """An arrowhead at `end`, pointing along `u`, as PowerPoint draws its
    line ends: a triangle's, a stealth's and an open one's tip at the end,
    a diamond and an oval centered on it."""
    n = (-u[1], u[0])

    def at(along: float, across: float) -> Point:
        return (end[0] + u[0] * along + n[0] * across, end[1] + u[1] * along + n[1] * across)

    if kind == "triangle":
        draw.polygon([at(0, 0), at(-length, width / 2), at(-length, -width / 2)], fill=color)
    elif kind == "stealth":
        draw.polygon([at(0, 0), at(-length, width / 2), at(-length * _STEALTH_NOTCH, 0), at(-length, -width / 2)],
                     fill=color)
    elif kind == "diamond":
        draw.polygon([at(length / 2, 0), at(0, width / 2), at(-length / 2, 0), at(0, -width / 2)], fill=color)
    elif kind == "oval":
        points = [at(length / 2 * math.cos(a), width / 2 * math.sin(a)) for a in
                  (2 * math.pi * k / 48 for k in range(48))]
        draw.polygon(points, fill=color)
    elif kind == "open":
        # A V of two arms the line's width, their outer edges meeting at
        # the tip, rounded at their ends.
        half = math.atan2(width / 2, length)
        inner = _open_inset(width, length, lw) * 2
        outer = [at(-length, width / 2), at(0, 0), at(-length, -width / 2)]
        across = lw / math.cos(half)
        inner_pts = [at(-length, width / 2 - across), at(-inner, 0), at(-length, -width / 2 + across)]
        draw.polygon(outer + inner_pts[::-1], fill=color)
        for o, i in zip((outer[0], outer[2]), (inner_pts[0], inner_pts[2])):
            x, y = (o[0] + i[0]) / 2, (o[1] + i[1]) / 2
            r = math.dist(o, i) / 2
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
