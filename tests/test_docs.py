"""The diagrams in the docs: every `.pik` under docs/, and every
```pikslide block in docs/'s Markdown and the top-level README, must parse
and lay out (docs/README.md).

The packaged manuals (src/pikslide/docs/) are left out: spec.md's blocks
are fragments of a design -- an image or include file that isn't there, a
template's settings file -- not diagrams to run."""

from __future__ import annotations

import pathlib
import re

import pytest

from pikslide.pik import parse
from pikslide.pik.layout import resolve_layout

ROOT = pathlib.Path(__file__).parent.parent
DOCS = ROOT / "docs"
PIK_FILES = sorted(DOCS.rglob("*.pik"))
MARKDOWN_FILES = [ROOT / "README.md", *sorted(DOCS.rglob("*.md"))]
_BLOCK = re.compile(r"^```pikslide\n(.*?)^```", re.M | re.S)


def _blocks() -> list[tuple[str, str, pathlib.Path]]:
    """(id, source, the Markdown file's directory) for each block."""
    found = []
    for md in MARKDOWN_FILES:
        text = md.read_text(encoding="utf-8")
        for m in _BLOCK.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            found.append((f"{md.relative_to(ROOT)}:{line}", m.group(1), md.parent))
    return found


def _lays_out(source: str, base_dir: pathlib.Path) -> None:
    result = resolve_layout(parse(source, base_dir=str(base_dir)), base_dir=str(base_dir))
    assert result.shapes


def test_docs_have_diagrams():
    assert PIK_FILES and _blocks()


@pytest.mark.parametrize("path", PIK_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_pik_file_lays_out(path: pathlib.Path):
    _lays_out(path.read_text(encoding="utf-8"), path.parent)


@pytest.mark.parametrize("block", _blocks(), ids=lambda b: b[0])
def test_markdown_block_lays_out(block):
    _, source, base_dir = block
    _lays_out(source, base_dir)
