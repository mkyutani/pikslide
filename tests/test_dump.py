"""Tests for pikslide.pik.dump: the indented text dump of a parsed AST."""

from __future__ import annotations

from pikslide.pik import dump, parse


def test_dump_shows_nesting_for_blocks():
    doc = parse('Outer: [\n  box "one"\n  [ box "two" ]\n]\n')
    text = dump(doc)
    assert text.count("BlockBase") == 2
    # the inner block's box is indented further than the outer block's own box
    outer_box_indent = text.index("text: 'one'")
    inner_box_indent = text.index("text: 'two'")
    assert text[:outer_box_indent].count("  ") < text[:inner_box_indent].count("  ")


def test_dump_is_deterministic_text():
    doc = parse("A: box\n")
    assert dump(doc) == dump(parse("A: box\n"))


def test_dump_empty_list_field():
    doc = parse("box\n")
    text = dump(doc)
    assert "attributes: []" in text
    assert "macros: []" in text
