import argparse
import json
import os
import sys
from importlib.metadata import version

from .api import BuildError, Layout, build, layout, render_into
from .fonts import FontInstallError, install_fonts, on_windows
from .pik import PikSyntaxError, parse
from .pik.layout import LayoutError, LayoutWarning
from .help import hint as help_hint
from .help import show as show_help
from .help import topics_text as help_topics_text
from .render import FORMATS, RENDERERS

# The library (src/pikslide/api.py, docs/spec.md SS6), and the command.
__all__ = ["parse", "layout", "render_into", "Layout", "PikSyntaxError", "LayoutError", "main"]


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        # The first thing to try, for a person or an LLM: say where to go.
        print(_parser().format_usage(), end="")
        print("Draw a .pik diagram as a PowerPoint deck: pikslide diagram.pik diagram.pptx")
        print("New to pikslide? pikslide --help intro; an LLM, pikslide --help llm. "
              "All options and help topics: pikslide --help")
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
    # --install-font SOURCE ... (issue #37) takes no INPUT either.
    if "--install-font" in argv:
        raise SystemExit(_install_fonts(argv))

    args = _parse_args(argv)
    with open(args.input, encoding="utf-8") as f:
        text = f.read()
    # An `image` object's path resolves against the source file's own
    # directory (docs/spec.md SS3.5).
    base_dir = os.path.dirname(os.path.abspath(args.input))
    _run(args, text, base_dir)


def _install_fonts(argv: list[str]) -> int:
    """`pikslide --install-font SOURCE ...`: each SOURCE's fonts in the
    user's font directory (fonts.install_fonts()), each named with its
    family names, as `typeface` takes them."""
    i = argv.index("--install-font")
    sources = argv[i + 1 :]
    if argv[:i] or not sources or any(source.startswith("-") for source in sources):
        print("usage: pikslide --install-font SOURCE [SOURCE ...]", file=sys.stderr)
        return 2
    for source in sources:
        try:
            installed = install_fonts(source)
        except FontInstallError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        for path, families, already in installed:
            print(f"{'already installed' if already else 'installed'} {path}: {' / '.join(families)}")
    if on_windows():
        sys.stdout.flush()  # after what was installed, even through a pipe
        print("note: for `fit` and --renderer direct; PowerPoint draws only with fonts installed in Windows, "
              "so for it, install them in Windows too (open each font file and choose Install)", file=sys.stderr)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pikslide",
        description="Render a .pik diagram to a new one-slide PowerPoint deck. "
        "Language reference: pikslide --help TOPIC -- start with `--help intro`, then a "
        "keyword (`--help box`) or a list (`--help keywords`); topics are listed below. "
        "An LLM reads `--help llm`, all it takes to write a diagram in one text.",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help", nargs="?", metavar="TOPIC",
        help="show this help, or help on TOPIC: a keyword (box, chop, fill, ...), "
        "a list (colors, shapes, ...) or a page (intro, template, llm)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('pikslide')}")
    parser.add_argument(
        "--install-font", metavar="SOURCE", nargs="+",
        help="install the fonts in SOURCE, a font file (.ttf .otf .ttc), a directory or zip of them, or a "
        "URL of a font or a zip, in your font directory, for `fit` and --renderer direct to use, then exit; "
        "on Windows and WSL, PowerPoint doesn't see them: install them in Windows for it",
    )
    parser.add_argument("input", help="a .pik source file")
    parser.add_argument(
        "output", nargs="?", default=None,
        help="output .pptx path, always overwritten; omit entirely (with no --template either) to "
        "dump the parsed tree instead of writing anything",
    )
    parser.add_argument(
        "--template", metavar="FILE", default=None,
        help="make the deck from this .pptx/.potx instead of the built-in Office theme: its theme, its "
        "slide size, and the diagram in the slide's content area (pikslide --help template)",
    )
    parser.add_argument(
        "--settings", metavar="FILE", default=None,
        help="a template's settings file (pikslide --help template); default: <template name>.theme.pik "
        "beside it, if any",
    )
    parser.add_argument(
        "--layout", metavar="NAME", default=None,
        help="the --template slide layout to make the new slide from, by its name or its id, overriding "
        "the settings file's `layout` (pikslide --help template)",
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
        help="what renders --png/--pdf: PowerPoint (via powershell.exe); direct, pikslide itself, close to "
        "PowerPoint but never showing text overflowing (the warnings and --strict tell that); LibreOffice "
        "(soffice); or auto, PowerPoint if reachable, else direct (default: auto)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="make a stand-in an error: no --template (the built-in theme), or a font that isn't installed",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="lay the source out without writing anything, and print the result as JSON: the errors, the "
        "warnings, and where each object went",
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
# Diagnostics (docs/spec.md SS5): plain text, or JSON with --check.
# ---------------------------------------------------------------------------














def _succeed(message: str, warnings: list[LayoutWarning] = (), notes: list[str] = ()) -> None:
    """`notes` are informational only -- unlike `warnings`, --strict never
    makes them fatal (e.g. --png drawn without PowerPoint: a fact about
    how the image was made, not a problem with the diagram)."""
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    print(message)


def _succeed_check(warnings: list[LayoutWarning], slide: dict, objects: list[dict]) -> None:
    """--check's JSON: the warnings, each with the names of the objects it
    is about, the slide (slide_frame()), and where each object went, one
    to a line so that it reads (and greps) as a list."""
    slide = {k: round(v, 2) if isinstance(v, float) else v for k, v in slide.items()}
    warnings = [{"message": w.message, "objects": list(w.objects)} for w in warnings]
    head = json.dumps({"ok": True, "errors": [], "warnings": warnings, "slide": slide}, ensure_ascii=False)
    listed = ",\n".join(f"  {json.dumps(o, ensure_ascii=False)}" for o in objects)
    print(f'{head[:-1]}, "objects": [\n{listed}\n]}}')


# ---------------------------------------------------------------------------


def _run(args: argparse.Namespace, text: str, base_dir: str) -> None:
    """The command: build(), its result or its error printed, plain or
    as --check's JSON."""
    try:
        built = build(
            text, args.input, base_dir=base_dir, output=args.output, template=args.template,
            settings=args.settings, layout_name=args.layout, include_paths=args.include_paths, png=args.png,
            pdf=args.pdf, renderer=args.renderer, strict=args.strict, check=args.check,
        )
    except BuildError as e:
        if args.check:
            print(json.dumps({"ok": False, "errors": [e.to_dict()]}))
        else:
            print(f"error: {e.shown}", file=sys.stderr)
            if e.help:
                print(help_hint(e.help), file=sys.stderr)
        raise SystemExit(1)
    if built.tree is not None:
        print(built.tree)
    elif built.check is not None:
        _succeed_check(built.warnings, built.check["slide"], built.check["objects"])
    else:
        written = [f"wrote {path}" + (f" (drawn by {drawn_by})" if drawn_by else "") for path, drawn_by in built.written]
        _succeed("\n".join(written), warnings=built.warnings, notes=built.notes)
