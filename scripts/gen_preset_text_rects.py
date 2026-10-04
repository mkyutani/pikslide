"""Write src/pikslide/pik/preset_text_rects.py: the text rectangle of
every preset shape, from OOXML's preset shape definitions.

    uv run python scripts/gen_preset_text_rects.py presetShapeDefinitions.xml

presetShapeDefinitions.xml is part of ECMA-376 (Part 1, the "Office Open
XML File Formats" zip); a copy is in LibreOffice's sources, at
oox/source/drawingml/customshapes/presetShapeDefinitions.xml.

A preset's text rectangle, `<rect l t r b>`, names shape guides: formulas
in the shape's width and height and its adjust values. For each preset
pikslide knows (PRESET_NAMES), this keeps the rectangle and only the
guides it needs, in order; pikslide.pik.text_area evaluates them.
"""

from __future__ import annotations

import argparse
import pathlib
import xml.etree.ElementTree as ET

from pikslide.pik.layout import PRESET_NAMES

OUT = pathlib.Path(__file__).resolve().parent.parent / "src" / "pikslide" / "pik" / "preset_text_rects.py"
NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
# What a preset with no <rect> gets: the whole shape (ECMA-376 Part 1, 20.1.9.22).
WHOLE_SHAPE = ("l", "t", "r", "b")
# The definitions' own mistakes: pie's <rect> swaps t and r (l="il" t="ir"
# r="it" b="ib"), which puts its top below its bottom.
ERRATA = {"pie": ("il", "it", "ir", "ib")}


def text_rect(preset: ET.Element) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    """The guides a preset's text rectangle needs, in order, and the
    rectangle's l, t, r, b."""
    guides = [
        (gd.get("name"), gd.get("fmla"))
        for lst in ("avLst", "gdLst")
        if (el := preset.find(NS + lst)) is not None
        for gd in el.findall(NS + "gd")
    ]
    rect = preset.find(NS + "rect")
    sides = WHOLE_SHAPE if rect is None else tuple(rect.get(k) for k in "ltrb")
    sides = ERRATA.get(preset.tag, sides)
    # Walk back from the rectangle, keeping each guide a later one reads.
    # A name can be defined twice (gear6's a1), so a guide is needed only
    # if it's the last definition before a read.
    needed, kept = set(sides), []
    for name, fmla in reversed(guides):
        if name in needed:
            needed.discard(name)
            needed.update(fmla.split()[1:])
            kept.append((name, fmla))
    return kept[::-1], sides


def module_source(xml_path: pathlib.Path) -> str:
    root = ET.parse(xml_path).getroot()
    out = [
        '"""The text rectangle of each preset shape: the guides it needs, and its',
        "l, t, r, b (see pikslide.pik.text_area).",
        "",
        "Written by scripts/gen_preset_text_rects.py from ECMA-376's",
        "presetShapeDefinitions.xml: don't edit.",
        '"""',
        "",
        "TEXT_RECTS: dict[str, tuple[tuple[tuple[str, str], ...], tuple[str, str, str, str]]] = {",
    ]
    for name in sorted(PRESET_NAMES.values(), key=str.lower):
        guides, sides = text_rect(root.find(name))
        pairs = [f"({_str(g)}, {_str(f)})" for g, f in guides]
        rect = _tuple(map(_str, sides))
        line = f"    {_str(name)}: ({_tuple(pairs)}, {rect}),"
        if len(line) <= 100:
            out.append(line)
        else:
            out += [f"    {_str(name)}: (", "        ("]
            out += [f"            {pair}," for pair in pairs]
            out += ["        ),", f"        {rect},", "    ),"]
    out.append("}")
    return "\n".join(out) + "\n"


def _str(s: str) -> str:
    return f'"{s}"'


def _tuple(items) -> str:
    items = list(items)
    return f"({items[0]},)" if len(items) == 1 else f"({', '.join(items)})"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("xml", type=pathlib.Path, help="presetShapeDefinitions.xml")
    args = ap.parse_args()
    OUT.write_text(module_source(args.xml), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
