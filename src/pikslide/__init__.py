import sys

from .markdown import extract_pik_blocks
from .pik import PikSyntaxError, dump, parse
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

    if path.endswith((".md", ".markdown")):
        blocks = extract_pik_blocks(text)
        if not blocks:
            print("no ```pik``` or ```pikchr``` code blocks found", file=sys.stderr)
            raise SystemExit(1)
        for i, block in enumerate(blocks, start=1):
            block_out = _numbered(out_path, i, len(blocks)) if out_path else None
            if len(blocks) > 1 and block_out is None:
                print(f"--- block {i} of {len(blocks)} ---")
            _process(block, block_out)
        return

    _process(text, out_path)


def _numbered(path: str, i: int, total: int) -> str:
    if total == 1:
        return path
    stem, dot, ext = path.rpartition(".")
    return f"{stem}-{i}.{ext}" if dot else f"{path}-{i}"


def _process(text: str, out_path: str | None) -> None:
    try:
        doc = parse(text)
    except PikSyntaxError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    if out_path is None:
        print(dump(doc))
        return

    if out_path.endswith(".pptx"):
        write_pptx(resolve_for_pptx(doc), out_path)
        print(f"wrote {out_path}")
        return

    print(f"error: unsupported output format: {out_path}", file=sys.stderr)
    raise SystemExit(1)
