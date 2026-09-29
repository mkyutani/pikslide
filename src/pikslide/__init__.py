import argparse
import json
import os
import sys

from .pik import PikSyntaxError, dump, format_syntax_error, parse
from .pik.layout import LayoutError
from .pik.tokens import column_at
from .pptx_writer import find_settings_file, resolve_for_pptx, write_pptx, write_pptx_from_template
from .help import hint as help_hint
from .help import layout_error_topics, syntax_error_topics
from .help import show as show_help
from .help import topics_text as help_topics_text
from .render import FORMATS, RENDERERS, RenderError, render_deck


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        # The first thing to try, for a person or an LLM: say where to go.
        print(_parser().format_usage(), end="")
        print("Draw a .pik diagram as a PowerPoint deck: pikslide diagram.pik diagram.pptx")
        print("New to pikslide? pikslide --help intro. All options and help topics: pikslide --help")
        raise SystemExit(2)

    # --help [TOPIC] (src/pikslide/help.py) is handled before the rest, since
    # INPUT is otherwise required.
    for i, arg in enumerate(argv):
        if arg in ("-h", "--help"):
            topic = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("-") else None
            if topic is None:
                _parser().print_help()
                print()
                print(help_topics_text(), end="")
                return
            raise SystemExit(show_help(topic))

    args = _parse_args(argv)
    with open(args.input, encoding="utf-8") as f:
        text = f.read()
    # An `image` object's path resolves against the source file's own
    # directory (docs/spec.md SS3.5).
    base_dir = os.path.dirname(os.path.abspath(args.input))
    _run(args, text, base_dir)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pikslide",
        description="Render a .pik diagram to a new one-slide PowerPoint deck. "
        "Language reference: pikslide --help TOPIC -- start with `--help intro`, then a "
        "keyword (`--help box`) or a list (`--help keywords`); topics are listed below.",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help", nargs="?", metavar="TOPIC",
        help="show this help, or help on TOPIC: a keyword (box, chop, fill, ...), "
        "a list (colors, shapes, ...) or a manual (grammar, spec)",
    )
    parser.add_argument("input", help="a .pik source file")
    parser.add_argument(
        "output", nargs="?", default=None,
        help="output .pptx path, always overwritten; omit entirely (with no --template either) to "
        "dump the parsed tree instead of writing anything",
    )
    parser.add_argument(
        "--template", metavar="FILE", default=None,
        help="start a new standalone deck from this .pptx/.potx's theme instead of the built-in Office one",
    )
    parser.add_argument(
        "--settings", metavar="FILE", default=None,
        help="a template's settings file (docs/spec.md SS3.8); default: <template name>.theme.pik beside it, if any",
    )
    parser.add_argument(
        "--layout", metavar="NAME", default=None,
        help="the --template slide layout to make the new slide from, overriding the settings file's "
        "`layout` (docs/spec.md SS3.8)",
    )
    parser.add_argument(
        "--include-path", metavar="DIR", action="append", default=None,
        help="an extra directory to search for `include \"path\"` (may be given more than once)",
    )
    for fmt in FORMATS:
        parser.add_argument(
            f"--{fmt}", metavar="PATH", nargs="?", const="", default=None,
            help=f"also render the written deck to a {fmt.upper()} at PATH (default: OUTPUT with its "
            f"extension changed to .{fmt})",
        )
    parser.add_argument(
        "--renderer", choices=RENDERERS, default="auto",
        help="what renders --png/--pdf: PowerPoint (via powershell.exe), LibreOffice (soffice), or "
        "auto, PowerPoint if reachable, else LibreOffice (default: auto)",
    )
    parser.add_argument("--strict", action="store_true", help="turn warnings into errors")
    parser.add_argument("--check", action="store_true", help="parse and lay out the source without writing any output")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="diagnostics format (default: text)"
    )
    return parser


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = _parser()
    args = parser.parse_args(argv)

    args.include_paths = args.include_path or []

    # OUTPUT's own default (docs/spec.md SS4), when omitted but --template
    # is given: INPUT's own path with its extension changed to .pptx.
    if args.output is None and args.template is not None:
        args.output = _with_extension(args.input, "pptx")
    if args.layout is not None and args.template is None:
        parser.error("--layout names a slide layout of --template, so it needs --template")

    # --png/--pdf (docs/spec.md SS4): rendered from the deck just written,
    # so they need one to be written at all.
    for fmt in FORMATS:
        path = getattr(args, fmt)
        if path is None:
            continue
        if path and not path.lower().endswith(f".{fmt}"):
            # Also catches `pikslide d.pik --png d.pptx`, where the
            # optional PATH swallowed what was meant as OUTPUT.
            parser.error(f"--{fmt} PATH must end in .{fmt} (got {path!r}); give OUTPUT before --{fmt}")
        if args.output is None or args.check:
            parser.error(f"--{fmt} renders the written OUTPUT deck, so it needs an OUTPUT and no --check")
        if path == "":
            path = _with_extension(args.output, fmt)
        setattr(args, fmt, path)

    return args


def _with_extension(path: str, ext: str) -> str:
    """`diagram.pik` -> `diagram.pptx` (docs/spec.md SS4, ext): OUTPUT's
    own default when it's omitted but --template is given, and --png/--pdf's
    from OUTPUT the same way."""
    stem, dot, _ext = path.rpartition(".")
    return f"{stem}.{ext}" if dot and "/" not in _ext and os.sep not in _ext else f"{path}.{ext}"


# ---------------------------------------------------------------------------
# Diagnostics (docs/spec.md SS5): plain text (default) or --format json.
# ---------------------------------------------------------------------------


def _syntax_error_detail(err: PikSyntaxError, main_path: str, main_text: str) -> dict:
    file = err.file or main_path
    text = main_text if err.file is None else _try_read(err.file)
    column = column_at(text, err.pos) if text else None
    return {"file": file, "line": err.line, "column": column, "message": err.message}


def _try_read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _fail(args: argparse.Namespace, message: str) -> None:
    """A plain diagnostic with no file position (an unsupported output
    format, an unreadable settings file, and the like)."""
    if args.format == "json":
        print(json.dumps({"ok": False, "errors": [{"file": None, "line": None, "column": None, "message": message}]}))
    else:
        print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _fail_syntax(args: argparse.Namespace, err: PikSyntaxError, main_path: str, main_text: str) -> None:
    """With the help topics for the statement it's in (help.py), so a
    person or an LLM stuck on the syntax knows where to look it up."""
    text = main_text if err.file is None else (_try_read(err.file) or "")
    lines = text.splitlines()
    source_line = lines[err.line - 1] if 0 < err.line <= len(lines) else ""
    topics = syntax_error_topics(source_line, err.text)
    if args.format == "json":
        detail = _syntax_error_detail(err, main_path, main_text)
        print(json.dumps({"ok": False, "errors": [{**detail, "help": _help_commands(topics)}]}))
    else:
        print(f"error: {format_syntax_error(err, main_path, main_text)}", file=sys.stderr)
        print(help_hint(topics), file=sys.stderr)
    raise SystemExit(1)


def _help_commands(topics: list[str]) -> list[str]:
    return [f"pikslide --help {t}" for t in topics]


def _fail_layout(args: argparse.Namespace, err: LayoutError) -> None:
    """A LayoutError (docs/spec.md SS5: undefined names and the like)
    carries no file position -- unlike a
    PikSyntaxError, it isn't tied to one token."""
    topics = layout_error_topics(str(err))
    if args.format == "json":
        error = {"file": None, "line": None, "column": None, "message": str(err), "help": _help_commands(topics)}
        print(json.dumps({"ok": False, "errors": [error]}))
    else:
        print(f"error: {err}", file=sys.stderr)
        if topics:
            print(help_hint(topics), file=sys.stderr)
    raise SystemExit(1)


def _succeed(args: argparse.Namespace, message: str, warnings: list[str] = (), notes: list[str] = (), **extra) -> None:
    """`notes` are informational only -- unlike `warnings`, --strict never
    makes them fatal (e.g. --png falling back to LibreOffice: a fact about
    how the image was made, not a problem with the diagram)."""
    if args.format == "json":
        print(json.dumps({"ok": True, "errors": [], "warnings": list(warnings), "notes": list(notes), **extra}))
    else:
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        for n in notes:
            print(f"note: {n}", file=sys.stderr)
        print(message)


# ---------------------------------------------------------------------------


def _run(args: argparse.Namespace, text: str, base_dir: str) -> None:
    out_path = args.output
    try:
        doc = parse(text, base_dir=base_dir, include_paths=args.include_paths)
    except PikSyntaxError as e:
        _fail_syntax(args, e, args.input, text)
        return

    if out_path is None and not args.check:
        print(dump(doc))
        return

    settings_text = None
    settings_base_dir = "."
    try:
        if args.template is not None or args.settings is not None:
            settings_path = find_settings_file(args.template or args.input, explicit=args.settings)
            if settings_path is not None:
                settings_text = _try_read(settings_path)
                if settings_text is None:
                    _fail(args, f"could not read settings file: {settings_path}")
                settings_base_dir = os.path.dirname(os.path.abspath(settings_path))
        result = resolve_for_pptx(
            doc,
            base_dir=base_dir,
            settings_text=settings_text,
            settings_base_dir=settings_base_dir,
            template_path=args.template,
            layout_name=args.layout,
        )
    except LayoutError as e:
        _fail_layout(args, e)
        return

    if args.check:
        _succeed(args, f"ok: {args.input} parses and lays out cleanly (--check, nothing written)")
        return

    if not out_path.endswith(".pptx"):
        _fail(args, f"unsupported output format: {out_path}")
        return

    warnings = list(result.warnings)
    if args.template is not None:
        try:
            layout_name = args.layout if args.layout is not None else result.layout_name
            write_pptx_from_template(result, args.template, out_path, layout_name=layout_name)
        except LayoutError as e:
            _fail_layout(args, e)
            return
    else:
        # No --template (docs/spec.md SS3.3 rule 2): the built-in Office
        # theme stands in for a real one, which --strict makes fatal
        # rather than just noted.
        warning = "no --template given: colors and fonts are stand-ins from the built-in Office theme (docs/spec.md SS3.3)"
        if args.strict:
            _fail(args, warning)
            return
        warnings.append(warning)
        write_pptx(result, out_path)

    written = {"output": out_path}
    notes = []
    for fmt in FORMATS:
        path = getattr(args, fmt)
        if path is None:
            continue
        try:
            notes += render_deck(out_path, path, fmt, renderer=args.renderer)
        except RenderError as e:
            _fail(args, f"could not render {path}: {e}")
            return
        written[fmt] = path
    _succeed(args, "\n".join(f"wrote {p}" for p in written.values()), warnings=warnings, notes=notes, **written)
