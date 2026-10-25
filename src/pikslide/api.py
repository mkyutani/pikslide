"""pikslide as a library (docs/spec.md SS6, issue #21): a diagram drawn
onto a slide another tool has, instead of a one-slide deck of its own.

    doc = pikslide.parse(source, base_dir=".")
    result = pikslide.layout(doc, template="corporate.potx")
    names = pikslide.render_into(slide, result, origin=(Inches(1), Inches(1.5)))

What is public is parse(), layout(), render_into(), Layout and the errors
they raise, PikSyntaxError and LayoutError. The rest of the package is
not, and can change between versions."""

from __future__ import annotations

import os

from pptx.util import Emu

from .pik import ast
from .pik.layout import LayoutResult, LayoutWarning, flatten_shapes
from .pptx_writer import draw_at, find_settings_file, object_list, resolve_for_pptx


class Layout:
    """A diagram layout() laid out, for render_into() to draw. What it
    tells of the layout is what --check prints (docs/spec.md SS5)."""

    def __init__(self, result: LayoutResult, warnings: list[LayoutWarning]):
        self._result = result
        self._warnings = warnings

    def objects(self) -> list[dict]:
        """--check's `objects`: each drawn object's name, kind, text and
        place, in inches with y up. The box round them is all that
        render_into() draws, and its top left is what `origin` places."""
        return object_list(flatten_shapes(self._result.shapes))

    def warnings(self) -> list[dict]:
        """--check's `warnings`: each a `message`, and the `objects` it
        names, by their names in objects()."""
        return [{"message": w.message, "objects": list(w.objects)} for w in self._warnings]


def layout(
    doc: ast.Document, template: str | None = None, settings: str | None = None, slide_layout: str | None = None
) -> Layout:
    """Lay out `doc`, from parse(), for a deck made from `template`, a
    .pptx or .potx, as `--template` does (docs/spec.md SS3.8): `fit`
    measures text in its theme's fonts, and its settings file, `settings`
    or else `<template name>.theme.pik` beside it, sets the text sizes and
    colors. With no template, the built-in Office theme stands in, which
    is a warning. Raises LayoutError.

    The theme is that of the master the slide's layout belongs to:
    `slide_layout`, by its name or id, as `--layout` names it, or else the
    settings file's `layout`. A template whose masters differ in their
    fonts needs it, for the slide render_into() draws on.

    Where the diagram goes is the caller's, so unlike `--template`, a
    diagram bigger than the template slide's content area, or on a
    placeholder it keeps, isn't a warning."""
    if slide_layout is not None and template is None:
        raise ValueError("slide_layout names a slide layout of template, so it needs template")
    settings_text = None
    settings_base_dir = "."
    if template is not None or settings is not None:
        settings_path = find_settings_file(template or settings, explicit=settings)
        if settings_path is not None:
            with open(settings_path, encoding="utf-8") as f:
                settings_text = f.read()
            settings_base_dir = os.path.dirname(os.path.abspath(settings_path))
    result = resolve_for_pptx(
        doc, base_dir=doc.base_dir, settings_text=settings_text, settings_base_dir=settings_base_dir,
        template_path=template, layout_name=slide_layout, own_slide=False,
    )
    warnings = [LayoutWarning(s) for s in result.stand_ins] + result.warnings
    if template is None:
        warnings.append(LayoutWarning(
            "no template given: `fit` measured text in the built-in Office theme's fonts, not the deck's"
        ))
    return Layout(result, warnings)


def render_into(slide, result: Layout, origin: tuple[int, int], name_suffix: str = "") -> dict[str, str]:
    """Draw `result` onto `slide`, a python-pptx slide, on top of what it
    has: the top left of all that is drawn at `origin`, (left, top) in
    EMU as python-pptx measures a slide (`Inches(1)`). A diagram is never
    scaled (docs/spec.md SS4).

    Each shape is named after its object, as objects() names it, with
    `-<name_suffix>` after it if one is given; a name that a shape on
    the slide already has moves on to `-2`, `-3`, ... (docs/spec.md
    SS3.1). Returns each object's name in objects(), mapped to the name
    its shape got."""
    left, top = origin
    if not (isinstance(left, int) and isinstance(top, int)):
        raise TypeError(f"origin is in EMU, as python-pptx's Inches() gives it, not {origin!r}")
    return draw_at(slide, result._result, (Emu(left).inches, Emu(top).inches), name_suffix)
