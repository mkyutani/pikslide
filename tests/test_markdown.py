"""Tests for pikslide.markdown: extracting pik/pikchr fenced code blocks."""

from __future__ import annotations

from pikslide.markdown import extract_pik_blocks
from pikslide.pik import parse


def test_extracts_pik_and_pikchr_fences():
    text = (
        "# Title\n\n"
        "```pik\n"
        "box\n"
        "```\n\n"
        "some text\n\n"
        "```pikchr\n"
        "circle\n"
        "```\n"
    )
    blocks = extract_pik_blocks(text)
    assert blocks == ["box\n", "circle\n"]


def test_ignores_other_language_fences():
    text = "```python\nprint('hi')\n```\n\n```pik\nbox\n```\n"
    assert extract_pik_blocks(text) == ["box\n"]


def test_ignores_unlabeled_fences():
    text = "```\nbox\n```\n"
    assert extract_pik_blocks(text) == []


def test_tilde_fences_are_recognized():
    text = "~~~pik\nbox\n~~~\n"
    assert extract_pik_blocks(text) == ["box\n"]


def test_lang_tag_is_case_insensitive():
    text = "```PIK\nbox\n```\n"
    assert extract_pik_blocks(text) == ["box\n"]


def test_extracted_block_parses_as_pik():
    text = "```pik\nA: box \"hi\"\narrow right\nB: box \"there\"\n```\n"
    (block,) = extract_pik_blocks(text)
    doc = parse(block)
    assert len(doc.statements) == 3
