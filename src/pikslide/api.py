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
from dataclasses import dataclass, field

from pptx.util import Emu

from .help import layout_error_topics, syntax_error_topics
from .pik import PikSyntaxError, ast, dump, format_syntax_error, parse
from .pik.layout import LayoutError, LayoutResult, LayoutWarning, flatten_shapes
from .pik.tokens import column_at
from .pptx_writer import (
    draw_at, find_settings_file, object_list, resolve_for_pptx, slide_frame, write_pptx, write_pptx_from_template,
)
from .render import DRAWN_BY, FORMATS, RenderError, render_deck


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


# ---------------------------------------------------------------------------
# build(): the command's run, without printing (issue #33). Not public: the
# command prints what it returns, and pikslide-mcp returns it.
# ---------------------------------------------------------------------------


class BuildError(Exception):
    """An error build() stops at, as the command reports it: its message,
    where in which file for a syntax error, and the help topics to read
    (None for an error that names none, such as an unreadable file)."""

    def __init__(self, message: str, help: list[str] | None = None, file: str | None = None,
                 line: int | None = None, column: int | None = None, shown: str | None = None):
        super().__init__(message)
        self.message, self.help = message, help
        self.file, self.line, self.column = file, line, column
        self.shown = shown or message
        """The message as the command prints it: a syntax error with its
        line and a caret under where it is."""

    def to_dict(self) -> dict:
        """The error as --check gives it, in `errors`."""
        error: dict = {"file": self.file, "line": self.line, "column": self.column, "message": self.message}
        if self.help is not None:
            error["help"] = [f"pikslide --help {t}" for t in self.help]
        return error


@dataclass
class Built:
    """What build() did."""

    written: list[tuple[str, str | None]] = field(default_factory=list)
    """Each file written, and for a picture what drew it ("PowerPoint",
    "pikslide" or "LibreOffice"), for the deck None."""
    warnings: list[LayoutWarning] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Facts about how a picture was made, not problems with the diagram:
    --strict leaves them alone."""
    check: dict | None = None
    """With `check`, --check's `slide` and `objects`."""
    tree: str | None = None
    """With no `output`, no `template` and no `check`, the parsed tree."""


def build(
    text: str, input_path: str, base_dir: str = ".", output: str | None = None, template: str | None = None,
    settings: str | None = None, layout_name: str | None = None, include_paths: list[str] | tuple = (),
    png: str | None = None, pdf: str | None = None, renderer: str = "auto", strict: bool = False,
    check: bool = False,
) -> Built:
    """What the command does with `text`, the source read from
    `input_path`, its images and includes found from `base_dir`: lay it
    out, then write the deck to `output` (a .pptx), from `template` if
    given, and render it to `png` and `pdf` with `renderer`; or with
    `check`, lay it out only. As the command's options say, each given in
    full: `output`, `png` and `pdf` are paths, not defaults to work out.
    Raises BuildError, as the command reports it."""
    try:
        doc = parse(text, base_dir=base_dir, include_paths=list(include_paths))
    except PikSyntaxError as e:
        raise _syntax_error(e, input_path, text) from None
    if output is None and not check:
        return Built(tree=dump(doc))

    settings_text = None
    settings_base_dir = "."
    try:
        if template is not None or settings is not None:
            settings_path = find_settings_file(template or input_path, explicit=settings)
            if settings_path is not None:
                settings_text = _try_read(settings_path)
                if settings_text is None:
                    raise BuildError(f"could not read settings file: {settings_path}")
                settings_base_dir = os.path.dirname(os.path.abspath(settings_path))
        result = resolve_for_pptx(
            doc, base_dir=base_dir, settings_text=settings_text, settings_base_dir=settings_base_dir,
            template_path=template, layout_name=layout_name,
        )
    except LayoutError as e:
        raise _layout_error(e) from None

    # --strict (docs/spec.md SS5): a stand-in for what the deck will really
    # have is an error; a problem with the diagram itself stays a warning.
    if strict and result.stand_ins:
        raise BuildError("; ".join(result.stand_ins))
    built = Built(warnings=[LayoutWarning(s) for s in result.stand_ins] + result.warnings)
    slide_layout = "" if template is None else layout_name if layout_name is not None else result.layout_name

    if check:
        try:
            slide = slide_frame(result, template, slide_layout)
        except LayoutError as e:
            raise _layout_error(e) from None
        built.check = {"slide": slide, "objects": object_list(flatten_shapes(result.shapes))}
        return built

    assert output is not None
    if not output.endswith(".pptx"):
        raise BuildError(f"unsupported output format: {output}")
    if template is not None:
        try:
            write_pptx_from_template(result, template, output, layout_name=slide_layout)
        except LayoutError as e:
            raise _layout_error(e) from None
    else:
        # No --template (docs/spec.md SS3.3 rule 2): the built-in Office
        # theme stands in for a real one, which --strict makes fatal
        # rather than just noted.
        warning = ("no --template given: colors and fonts are stand-ins from the built-in Office theme "
                   "(pikslide --help template)")
        if strict:
            raise BuildError(warning)
        built.warnings.append(LayoutWarning(warning))
        write_pptx(result, output)
    built.written.append((output, None))

    def draw_direct(path: str, fmt: str) -> None:
        from . import draw

        draw.save(draw.draw(result, template, slide_layout), path, fmt)

    for fmt, path in zip(FORMATS, (png, pdf)):
        if path is None:
            continue
        try:
            drawn_by, notes = render_deck(output, path, fmt, renderer=renderer, draw=draw_direct)
        except RenderError as e:
            raise BuildError(f"could not render {path}: {e}") from None
        built.notes += notes
        built.written.append((path, DRAWN_BY[drawn_by]))
    return built


def _try_read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _syntax_error(err: PikSyntaxError, main_path: str, main_text: str) -> BuildError:
    """With the help topics for the statement it's in (help.py), so a
    person or an LLM stuck on the syntax knows where to look it up."""
    text = main_text if err.file is None else (_try_read(err.file) or "")
    lines = text.splitlines()
    source_line = lines[err.line - 1] if 0 < err.line <= len(lines) else ""
    column = column_at(text, err.pos) if text else None
    return BuildError(err.message, syntax_error_topics(source_line, err.text), file=err.file or main_path,
                      line=err.line, column=column, shown=format_syntax_error(err, main_path, main_text))


def _layout_error(err: LayoutError) -> BuildError:
    """A LayoutError (docs/spec.md SS5: undefined names and the like)
    carries no file position: unlike a PikSyntaxError, it isn't tied to
    one token."""
    return BuildError(str(err), layout_error_topics(str(err)))
