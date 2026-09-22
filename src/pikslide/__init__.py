import os
import sys

from .markdown import MarkdownDiagramError, extract_pik_blocks
from .pik import PikSyntaxError, dump, parse
from .pik.layout import LayoutError
from .pptx_writer import resolve_for_pptx, write_pptx


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Hello from pikslide!")
        return

    path = args[0]
    out_path = args[1] if len(args) > 1 else None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # An `image` object's path resolves against the source file's own
    # directory (docs/spec.md SS3.5) -- for Markdown, that's the .md file
    # itself, not some notional location of the extracted block.
    base_dir = os.path.dirname(os.path.abspath(path))

    if path.endswith((".md", ".markdown")):
        try:
            blocks = extract_pik_blocks(text)
        except MarkdownDiagramError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(1)
        if not blocks:
            print("no ```pik```/```pikchr```/```pikslide``` code blocks found", file=sys.stderr)
            raise SystemExit(1)
        for i, block in enumerate(blocks, start=1):
            block_out = _numbered(out_path, i, len(blocks)) if out_path else None
            if len(blocks) > 1 and block_out is None:
                label = f'"{block.name}"' if block.name else f"{i} of {len(blocks)}"
                print(f"--- block {label} ---")
            _process(block.text, block_out, base_dir)
        return

    _process(text, out_path, base_dir)


def _numbered(path: str, i: int, total: int) -> str:
    if total == 1:
        return path
    stem, dot, ext = path.rpartition(".")
    return f"{stem}-{i}.{ext}" if dot else f"{path}-{i}"


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
