"""Tests for pikslide.markdown: extracting ```pikslide``` fenced code blocks."""

from __future__ import annotations

import pytest

from pikslide.markdown import MarkdownDiagramError, PikBlock, extract_pikslide_blocks
from pikslide.pik import parse


def test_extracts_pikslide_fences():
    # More than one diagram, so each fence must be named (docs/spec.md SS6).
    text = (
        "# Title\n\n"
        "```pikslide one\n"
        "box\n"
        "```\n\n"
        "some text\n\n"
        "```pikslide two\n"
        "circle\n"
        "```\n"
    )
    blocks = extract_pikslide_blocks(text)
    assert [b.text for b in blocks] == ["box\n", "circle\n"]
    assert [b.name for b in blocks] == ["one", "two"]


def test_ignores_other_language_fences():
    text = "```python\nprint('hi')\n```\n\n```pikslide\nbox\n```\n"
    assert [b.text for b in extract_pikslide_blocks(text)] == ["box\n"]


def test_ignores_unlabeled_fences():
    text = "```\nbox\n```\n"
    assert extract_pikslide_blocks(text) == []


def test_tilde_fences_are_recognized():
    text = "~~~pikslide\nbox\n~~~\n"
    assert [b.text for b in extract_pikslide_blocks(text)] == ["box\n"]


def test_lang_tag_is_case_insensitive():
    text = "```PIKSLIDE\nbox\n```\n"
    assert [b.text for b in extract_pikslide_blocks(text)] == ["box\n"]


def test_extracted_block_parses_as_pik():
    text = "```pikslide\nA: box \"hi\"\narrow right\nB: box \"there\"\n```\n"
    (block,) = extract_pikslide_blocks(text)
    doc = parse(block.text)
    assert len(doc.statements) == 3


# ---------------------------------------------------------------------------
# Diagram names (docs/spec.md SS6)
# ---------------------------------------------------------------------------


def test_single_unnamed_block_needs_no_name():
    text = "```pikslide\nbox\n```\n"
    (block,) = extract_pikslide_blocks(text)
    assert block == PikBlock(None, "box\n")


def test_named_block_is_captured():
    text = "```pikslide architecture\nbox\n```\n"
    (block,) = extract_pikslide_blocks(text)
    assert block.name == "architecture"
    assert block.text == "box\n"


def test_multiple_named_blocks_are_fine():
    text = "```pikslide one\nbox\n```\n\n```pikslide two\ncircle\n```\n"
    blocks = extract_pikslide_blocks(text)
    assert [b.name for b in blocks] == ["one", "two"]


def test_multiple_blocks_without_a_name_is_an_error():
    text = "```pikslide\nbox\n```\n\n```pikslide\ncircle\n```\n"
    with pytest.raises(MarkdownDiagramError):
        extract_pikslide_blocks(text)


def test_multiple_blocks_one_unnamed_is_an_error():
    text = "```pikslide one\nbox\n```\n\n```pikslide\ncircle\n```\n"
    with pytest.raises(MarkdownDiagramError):
        extract_pikslide_blocks(text)


def test_duplicate_names_is_an_error():
    text = "```pikslide dup\nbox\n```\n\n```pikslide dup\ncircle\n```\n"
    with pytest.raises(MarkdownDiagramError):
        extract_pikslide_blocks(text)
