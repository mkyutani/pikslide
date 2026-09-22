import argparse
import os
import sys

from .markdown import MarkdownDiagramError, extract_pik_blocks
from .pik import PikSyntaxError, dump, parse
from .pik.layout import LayoutError
from .pptx_writer import insert_into_pptx, resolve_for_pptx, write_pptx


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
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(1)
        if not blocks:
            print("no ```pik```/```pikchr```/```pikslide``` code blocks found", file=sys.stderr)
            raise SystemExit(1)
        if args.into is not None:
            if len(blocks) > 1:
                # docs/spec.md SS6: `--block NAME` is how a multi-diagram
                # file picks one for `--into`, but it isn't implemented
                # yet (docs/implementation-plan.md) -- so, for now, only a
                # single-diagram file can be used this way.
                print(
                    "error: this file has more than one diagram; --into places one "
                    "at a time and --block (to choose which) isn't implemented yet",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            block = blocks[0]
            default_id = block.name or os.path.splitext(os.path.basename(args.input))[0]
            _process_into(block.text, args, base_dir, default_id)
            return
        for i, block in enumerate(blocks, start=1):
            block_out = _numbered(args.output, i, len(blocks)) if args.output else None
            if len(blocks) > 1 and block_out is None:
                label = f'"{block.name}"' if block.name else f"{i} of {len(blocks)}"
                print(f"--- block {label} ---")
            _process(block.text, block_out, base_dir)
        return

    if args.into is not None:
        default_id = os.path.splitext(os.path.basename(args.input))[0]
        _process_into(text, args, base_dir, default_id)
        return

    _process(text, args.output, base_dir)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pikslide",
        description="Render a .pik/.pikchr/.pikslide diagram (or a Markdown file "
        "containing one) to PowerPoint, either as a new deck or inserted into an "
        "existing one (docs/spec.md SS4).",
    )
    parser.add_argument(
        "input", help="a .pik/.pikchr/.pikslide source file, or a Markdown file containing fenced blocks"
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
    args = parser.parse_args(argv)

    if args.output is not None and args.output_opt is not None:
        parser.error("output given twice: as a positional argument and with -o")
    if args.output_opt is not None:
        args.output = args.output_opt

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
    else:
        if args.slide is None:
            parser.error("--into requires --slide")
        if args.in_place and args.output is not None:
            parser.error("--in-place and -o/OUTPUT are mutually exclusive")
        if args.rect is not None:
            args.rect = _parse_rect(args.rect, parser)

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


def _process(text: str, out_path: str | None, base_dir: str = ".") -> None:
    try:
        doc = parse(text, base_dir=base_dir)
    except PikSyntaxError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    if out_path is None:
        print(dump(doc))
        return

    if out_path.endswith(".pptx"):
        try:
            write_pptx(resolve_for_pptx(doc, base_dir=base_dir), out_path)
        except LayoutError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(1)
        print(f"wrote {out_path}")
        return

    print(f"error: unsupported output format: {out_path}", file=sys.stderr)
    raise SystemExit(1)


def _process_into(text: str, args: argparse.Namespace, base_dir: str, default_id: str) -> None:
    try:
        doc = parse(text, base_dir=base_dir)
    except PikSyntaxError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    try:
        result = resolve_for_pptx(doc, base_dir=base_dir)
        prs = insert_into_pptx(
            result,
            args.into,
            args.slide,
            region=args.region,
            rect=args.rect,
            group_id=args.id or default_id,
        )
    except LayoutError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    out_path = args.into if args.in_place else (args.output or _default_into_output(args.into))
    prs.save(out_path)
    print(f"wrote {out_path}")
