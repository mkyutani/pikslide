import argparse
import json
import os
import sys

from .markdown import MarkdownDiagramError, PikBlock, extract_pik_blocks
from .pik import PikSyntaxError, dump, format_syntax_error, parse
from .pik.layout import LayoutError
from .pik.tokens import column_at
from .pptx_writer import (
    ALIGN_CHOICES,
    find_settings_file,
    insert_into_pptx,
    resolve_for_pptx,
    write_pptx,
    write_pptx_from_template,
)


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        print("Hello from pikslide!")
        return

    args = _parse_args(argv)
    with open(args.input, encoding="utf-8") as f:
        text = f.read()
    # An `image` object's path resolves against the source file's own
    # directory (docs/spec.md SS3.5) -- for Markdown, that's the .md file
    # itself, not some notional location of the extracted block.
    base_dir = os.path.dirname(os.path.abspath(args.input))

    if args.input.endswith((".md", ".markdown")):
        try:
            blocks = extract_pik_blocks(text)
        except MarkdownDiagramError as e:
            _fail(args, str(e))
        if not blocks:
            _fail(args, "no ```pikslide``` code blocks found")
        if args.block is not None or args.into is not None or args.template is not None:
            block = _select_block(args, blocks)
            default_id = block.name or os.path.splitext(os.path.basename(args.input))[0]
            _run(args, block.text, base_dir, args.output, default_id)
            return
        for i, block in enumerate(blocks, start=1):
            block_out = _numbered(args.output, i, len(blocks)) if args.output else None
            if len(blocks) > 1 and block_out is None:
                label = f'"{block.name}"' if block.name else f"{i} of {len(blocks)}"
                print(f"--- block {label} ---")
            default_id = block.name or os.path.splitext(os.path.basename(args.input))[0]
            _run(args, block.text, base_dir, block_out, default_id)
        return

    if args.block is not None:
        _fail(args, "--block only applies to a Markdown input file")
    default_id = os.path.splitext(os.path.basename(args.input))[0]
    _run(args, text, base_dir, args.output, default_id)


def _select_block(args: argparse.Namespace, blocks: list[PikBlock]) -> PikBlock:
    """`--block NAME` (docs/spec.md SS6): required to pick one diagram out
    of a multi-diagram Markdown file for `--into`/`--template`, which each
    place exactly one. A single-diagram file needs no `--block` at all."""
    if args.block is None:
        if len(blocks) > 1:
            names = ", ".join(repr(b.name) for b in blocks)
            _fail(args, f"this file has more than one diagram; --block NAME selects one ({names})")
        return blocks[0]
    for block in blocks:
        if block.name == args.block:
            return block
    names = ", ".join(repr(b.name) for b in blocks if b.name)
    _fail(args, f"no diagram named {args.block!r} in this file" + (f"; it has: {names}" if names else ""))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pikslide",
        description="Render a .pik diagram (or a Markdown file containing one) to "
        "PowerPoint, either as a new deck or inserted into an existing one "
        "(docs/spec.md SS4).",
    )
    parser.add_argument(
        "input", help="a .pik source file, or a Markdown file containing ```pikslide``` fenced blocks"
    )
    parser.add_argument(
        "output", nargs="?", default=None, help="output .pptx path; omit to dump the parsed tree (standalone mode only)"
    )
    parser.add_argument(
        "-o", dest="output_opt", metavar="OUT", default=None, help="output path (same as the positional OUTPUT; use with --into)"
    )
    parser.add_argument(
        "--into", metavar="DECK", default=None, help="insert into this existing .pptx/.potx instead of writing a new deck"
    )
    parser.add_argument("--slide", type=int, metavar="N", default=None, help="1-based slide number (required with --into)")
    parser.add_argument(
        "--region", metavar="NAME", default=None, help="name of a shape/placeholder on that slide to use as the target rectangle"
    )
    parser.add_argument("--rect", metavar="X,Y,W,H", default=None, help="explicit target rectangle in inches")
    parser.add_argument(
        "--id", metavar="ID", default=None, help="group id (default: the Markdown fence name, else the source file's stem)"
    )
    parser.add_argument(
        "--in-place", action="store_true", help="overwrite the --into deck itself instead of writing a separate file"
    )
    parser.add_argument(
        "--align", metavar="ALIGN", default="top-left",
        help=f"where a smaller-than-its-region diagram sits (--into only); one of {', '.join(sorted(ALIGN_CHOICES))} (default: top-left)",
    )
    parser.add_argument(
        "--template", metavar="FILE", default=None,
        help="start a new standalone deck from this .pptx/.potx's theme instead of the built-in Office one",
    )
    parser.add_argument(
        "--settings", metavar="FILE", default=None,
        help="a template's settings file (docs/spec.md SS3.8); default: <template/deck name>.theme.pik beside it, if any",
    )
    parser.add_argument(
        "--include-path", metavar="DIR", action="append", default=None,
        help="an extra directory to search for `include \"path\"` (may be given more than once)",
    )
    parser.add_argument(
        "--block", metavar="NAME", default=None, help="select one diagram from a Markdown file with more than one (docs/spec.md SS6)"
    )
    parser.add_argument("--strict", action="store_true", help="turn warnings into errors")
    parser.add_argument("--check", action="store_true", help="parse and lay out the source without writing any output")
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="diagnostics format (default: text)"
    )
    args = parser.parse_args(argv)

    if args.output is not None and args.output_opt is not None:
        parser.error("output given twice: as a positional argument and with -o")
    if args.output_opt is not None:
        args.output = args.output_opt
    args.include_paths = args.include_path or []

    if args.into is not None and args.template is not None:
        # docs/spec.md SS3.3 rule 2: "the deck is already the template".
        parser.error("--into and --template are mutually exclusive")

    if args.into is None:
        for flag, value in (
            ("--slide", args.slide),
            ("--region", args.region),
            ("--rect", args.rect),
            ("--id", args.id),
        ):
            if value is not None:
                parser.error(f"{flag} requires --into")
        if args.in_place:
            parser.error("--in-place requires --into")
        if args.align != "top-left":
            parser.error("--align requires --into")
    else:
        if args.slide is None:
            parser.error("--into requires --slide")
        if args.in_place and args.output is not None:
            parser.error("--in-place and -o/OUTPUT are mutually exclusive")
        if args.rect is not None:
            args.rect = _parse_rect(args.rect, parser)
        if args.align not in ALIGN_CHOICES:
            parser.error(f"--align must be one of {', '.join(sorted(ALIGN_CHOICES))} (got {args.align!r})")

    return args


def _parse_rect(value: str, parser: argparse.ArgumentParser) -> tuple[float, float, float, float]:
    parts = value.split(",")
    if len(parts) != 4:
        parser.error(f"--rect must be X,Y,W,H (got {value!r})")
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError:
        parser.error(f"--rect values must be numbers (got {value!r})")
    return x, y, w, h


def _numbered(path: str, i: int, total: int) -> str:
    if total == 1:
        return path
    stem, dot, ext = path.rpartition(".")
    return f"{stem}-{i}.{ext}" if dot else f"{path}-{i}"


def _default_into_output(deck_path: str) -> str:
    """`deck.pptx` -> `deck.pikslide.pptx` (docs/spec.md SS4.2): the
    default output name when `--into` is used with neither `--in-place`
    nor `-o`."""
    stem, dot, ext = deck_path.rpartition(".")
    return f"{stem}.pikslide.{ext}" if dot else f"{deck_path}.pikslide"


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
    """A plain diagnostic with no file position (a Markdown-block-naming
    problem, an unsupported combination, and the like)."""
    if args.format == "json":
        print(json.dumps({"ok": False, "errors": [{"file": None, "line": None, "column": None, "message": message}]}))
    else:
        print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _fail_syntax(args: argparse.Namespace, err: PikSyntaxError, main_path: str, main_text: str) -> None:
    if args.format == "json":
        print(json.dumps({"ok": False, "errors": [_syntax_error_detail(err, main_path, main_text)]}))
    else:
        print(f"error: {format_syntax_error(err, main_path, main_text)}", file=sys.stderr)
    raise SystemExit(1)


def _fail_layout(args: argparse.Namespace, err: LayoutError) -> None:
    """A LayoutError (docs/spec.md SS5: undefined names, a diagram larger
    than its region, and so on) carries no file position -- unlike a
    PikSyntaxError, it isn't tied to one token."""
    if args.format == "json":
        print(json.dumps({"ok": False, "errors": [{"file": None, "line": None, "column": None, "message": str(err)}]}))
    else:
        print(f"error: {err}", file=sys.stderr)
    raise SystemExit(1)


def _succeed(args: argparse.Namespace, message: str, warnings: list[str] = (), **extra) -> None:
    if args.format == "json":
        print(json.dumps({"ok": True, "errors": [], "warnings": list(warnings), **extra}))
    else:
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        print(message)


# ---------------------------------------------------------------------------


def _run(args: argparse.Namespace, text: str, base_dir: str, out_path: str | None, default_id: str) -> None:
    try:
        doc = parse(text, base_dir=base_dir, include_paths=args.include_paths)
    except PikSyntaxError as e:
        _fail_syntax(args, e, args.input, text)
        return

    if args.into is None and args.template is None and out_path is None and not args.check:
        print(dump(doc))
        return

    settings_target = args.into or args.template
    settings_text = None
    settings_base_dir = "."
    try:
        if settings_target is not None or args.settings is not None:
            settings_path = find_settings_file(settings_target or args.input, explicit=args.settings)
            if settings_path is not None:
                settings_text = _try_read(settings_path)
                if settings_text is None:
                    _fail(args, f"could not read settings file: {settings_path}")
                settings_base_dir = os.path.dirname(os.path.abspath(settings_path))
        result = resolve_for_pptx(doc, base_dir=base_dir, settings_text=settings_text, settings_base_dir=settings_base_dir)
    except LayoutError as e:
        _fail_layout(args, e)
        return

    if args.check:
        _succeed(args, f"ok: {args.input} parses and lays out cleanly (--check, nothing written)")
        return

    if args.into is not None:
        try:
            prs = insert_into_pptx(
                result, args.into, args.slide, region=args.region, rect=args.rect,
                group_id=args.id or default_id, align=args.align,
            )
        except LayoutError as e:
            _fail_layout(args, e)
            return
        final_out = args.into if args.in_place else (out_path or _default_into_output(args.into))
        prs.save(final_out)
        _succeed(args, f"wrote {final_out}", output=final_out)
        return

    if args.template is not None:
        if out_path is None:
            _fail(args, "an output path is required with --template")
        try:
            write_pptx_from_template(result, args.template, out_path, layout_name=result.layout_name)
        except LayoutError as e:
            _fail_layout(args, e)
            return
        _succeed(args, f"wrote {out_path}", output=out_path)
        return

    # Standalone, no --template (docs/spec.md SS3.3 rule 3): the built-in
    # Office theme stands in for a real one, which --strict makes fatal
    # rather than just noted.
    warning = "no --template given: colors and fonts are stand-ins from the built-in Office theme (docs/spec.md SS3.3)"
    if args.strict:
        _fail(args, warning)
        return
    if out_path.endswith(".pptx"):
        write_pptx(result, out_path)
        _succeed(args, f"wrote {out_path}", warnings=[warning], output=out_path)
        return

    _fail(args, f"unsupported output format: {out_path}")
