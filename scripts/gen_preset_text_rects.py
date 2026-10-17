"""Write src/pikslide/pik/preset_text_rects.py: the text rectangle, the
adjust values and the connection sites of every preset shape, from
OOXML's preset shape definitions.

    uv run python scripts/gen_preset_text_rects.py presetShapeDefinitions.xml

presetShapeDefinitions.xml is part of ECMA-376 (Part 1, the "Office Open
XML File Formats" zip); a copy is in LibreOffice's sources, at
oox/source/drawingml/customshapes/presetShapeDefinitions.xml.

A preset's text rectangle, `<rect l t r b>`, names shape guides: formulas
in the shape's width and height and its adjust values. For each preset
pikslide knows (PRESET_NAMES), this keeps the rectangle and only the
guides it needs, in order; pikslide.pik.text_area evaluates them.

A preset's adjust values, `<avLst>`, are the guides its handles set
(`adjust NAME VALUE`); this keeps their names and defaults, in order.

A preset's connection sites, `<cxnLst>`, are where a connector's end
attaches to it (`attach`, issue #18), each a `<pos x y>` and the angle a
connector leaves it at (`ang`), naming guides, in the order a connector
numbers them (`idx`); this keeps them and the guides they need, as for
the text rectangle.
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


def needed_guides(preset: ET.Element, names) -> list[tuple[str, str]]:
    """The guides `names` need, in order."""
    guides = [
        (gd.get("name"), gd.get("fmla"))
        for lst in ("avLst", "gdLst")
        if (el := preset.find(NS + lst)) is not None
        for gd in el.findall(NS + "gd")
    ]
    # Walk back from the names, keeping each guide a later one reads.
    # A name can be defined twice (gear6's a1), so a guide is needed only
    # if it's the last definition before a read.
    needed, kept = set(names), []
    for name, fmla in reversed(guides):
        if name in needed:
            needed.discard(name)
            needed.update(fmla.split()[1:])
            kept.append((name, fmla))
    return kept[::-1]


def text_rect(preset: ET.Element) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    """The guides a preset's text rectangle needs, in order, and the
    rectangle's l, t, r, b."""
    rect = preset.find(NS + "rect")
    sides = WHOLE_SHAPE if rect is None else tuple(rect.get(k) for k in "ltrb")
    sides = ERRATA.get(preset.tag, sides)
    return needed_guides(preset, sides), sides


def connection_sites(preset: ET.Element) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """The guides a preset's connection sites need, in order, and each
    site's x, y and angle, in the order a connector numbers them."""
    cxn_lst = preset.find(NS + "cxnLst")
    sites = [] if cxn_lst is None else [
        (pos.get("x"), pos.get("y"), cxn.get("ang")) for cxn in cxn_lst.findall(NS + "cxn") for pos in cxn.findall(NS + "pos")
    ]
    return needed_guides(preset, {name for site in sites for name in site}), sites


def adjust_values(preset: ET.Element) -> list[tuple[str, int]]:
    """A preset's adjust values and their defaults, in order."""
    av = preset.find(NS + "avLst")
    return [] if av is None else [(gd.get("name"), int(gd.get("fmla").split()[1])) for gd in av.findall(NS + "gd")]


def module_source(xml_path: pathlib.Path) -> str:
    root = ET.parse(xml_path).getroot()
    out = [
        '"""The text rectangle of each preset shape: the guides it needs, and its',
        "l, t, r, b (see pikslide.pik.text_area); its adjust values, which its",
        "handles set, with their defaults (100000 for 1); and its connection",
        "sites, where a connector's end attaches and the angle it leaves at,",
        "and the guides they need.",
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
    out += ["}", "", "ADJUST_VALUES: dict[str, tuple[tuple[str, int], ...]] = {"]
    for name in sorted(PRESET_NAMES.values(), key=str.lower):
        values = [f"({_str(g)}, {v})" for g, v in adjust_values(root.find(name))]
        line = f"    {_str(name)}: {_tuple(values) if values else '()'},"
        if len(line) <= 100:
            out.append(line)
        else:
            out += [f"    {_str(name)}: (", *(f"        {value}," for value in values), "    ),"]
    out += ["}", "", "CONNECTION_SITES: dict[str, tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str, str], ...]]] = {"]
    for name in sorted(PRESET_NAMES.values(), key=str.lower):
        guides, sites = connection_sites(root.find(name))
        pairs = [f"({_str(g)}, {_str(f)})" for g, f in guides]
        points = [f"({_str(x)}, {_str(y)}, {_str(a)})" for x, y, a in sites]
        line = f"    {_str(name)}: ({_tuple(pairs) if pairs else '()'}, {_tuple(points) if points else '()'}),"
        if len(line) <= 100:
            out.append(line)
        else:
            out += [f"    {_str(name)}: (", "        (" if pairs else "        (),"]
            if pairs:
                out += [f"            {pair}," for pair in pairs]
                out.append("        ),")
            out += ["        (", *(f"            {point}," for point in points), "        ),", "    ),"]
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
