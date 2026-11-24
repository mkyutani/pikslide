"""The macros pikslide ships in includes/dfd.pik, for a data flow
diagram's parts (issue #74): each drawn without a warning, its pieces
named in its block, its edges where a flow meets it, and its help."""

from __future__ import annotations

import pathlib
import re

import pytest

from pikslide import parse
from pikslide.help import dfd_entries, llm_text, render, _Style
from pikslide.pik.layout import flatten_shapes, resolve_layout
from pikslide.pptx_writer import resolve_for_pptx

ROOT = pathlib.Path(__file__).resolve().parents[1]
DFD = ROOT / "src" / "pikslide" / "includes" / "dfd.pik"

# Each macro, a call of it, and the pieces of its block (none: not a block).
CALLS = {
    "dfdprocess": ('dfdprocess("1", "Take" "order")', ()),
    "dfdstore": ('dfdstore("D1", "Orders")', ("Upper", "Lower", "Id", "Name")),
    "dfdgsprocess": ('dfdgsprocess("1", "Take" "order")', ("Number", "Name")),
    "dfdgsstore": ('dfdgsstore("D1", "Orders")', ("Id", "Upper", "Lower", "Name")),
    "dfdentity": ('dfdentity("Customer")', ()),
}


def lay_out(source: str):
    return resolve_layout(parse('include "dfd.pik"\n' + source + "\n"))


def warnings(source: str) -> list[str]:
    # The warnings about the diagram, not about fonts this machine lacks.
    return [w.message for w in resolve_for_pptx(parse('include "dfd.pik"\n' + source + "\n")).warnings if w.objects]


def objects(source: str) -> dict:
    return {s.name: s for s in flatten_shapes(lay_out(source).shapes)}


def test_there_are_the_parts_promised():
    text = DFD.read_text(encoding="utf-8")
    assert sorted(re.findall(r"(?m)^define (\w+) \{$", text)) == sorted(CALLS)


@pytest.mark.parametrize("name", sorted(CALLS))
def test_each_draws_without_a_warning(name):
    assert warnings("P: " + CALLS[name][0]) == []


@pytest.mark.parametrize("name", sorted(CALLS))
def test_a_blocks_pieces_are_named_in_it(name):
    call, pieces = CALLS[name]
    found = objects("P: " + call)
    assert set(pieces) <= set(found)
    for piece in pieces:
        # A later object refers to it through the part's label.
        lay_out(f"P: {call}\narrow from P.{piece}.c down 0.3")


def test_a_store_is_a_group():
    layout = lay_out("P: " + CALLS["dfdstore"][0])
    assert [s.kind for s in layout.shapes] == ["block"] and layout.shapes[0].group


@pytest.mark.parametrize("name", ["dfdstore", "dfdgsstore"])
def test_a_stores_edges_are_its_ends_and_the_middle_of_its_lines(name):
    width, height = 1.5, 0.4
    found = objects(f"P: {CALLS[name][0]} with .w at (0, 0)\n"
                    "W: dot at P.w\nE: dot at P.e\nN: dot at P.n\nS: dot at P.s")
    assert (found["W"].cx, found["W"].cy) == pytest.approx((0, 0))
    assert (found["E"].cx, found["E"].cy) == pytest.approx((width, 0))
    assert (found["N"].cx, found["N"].cy) == pytest.approx((width / 2, height / 2))
    assert (found["S"].cx, found["S"].cy) == pytest.approx((width / 2, -height / 2))


def test_every_process_is_one_size():
    found = objects('A: dfdprocess("1", "Take" "order")\nB: dfdprocess("2", "Ship")')
    assert found["A"].w == found["B"].w == pytest.approx(1)


def test_a_name_too_long_for_its_part_warns():
    assert any("overflows" in w for w in warnings('P: dfdstore("D1", "Customer accounts receivable")'))
    assert any("overflows" in w for w in warnings('P: dfdprocess("1", "Reconcile customer accounts")'))


def test_the_sizes_are_variables():
    def width(source):
        x0, _, x1, _ = lay_out(source).bbox
        return x1 - x0
    assert width('P: dfdstore("D1", "Orders")') == pytest.approx(1.5)
    assert width('dfdstorewid = 2\nP: dfdstore("D1", "Orders")') == pytest.approx(2)
    assert width('dfdprocwid = 1.4\nP: dfdgsprocess("1", "Take")') == pytest.approx(1.4)


def test_an_argument_says_what_its_piece_is_last():
    found = objects('P: dfdgsprocess("1", "Take" fill red)')
    assert found["Name"].fill != found["Number"].fill


def test_each_has_help():
    entries = dfd_entries()
    assert sorted(name for e in entries for name in e.names) == sorted(CALLS)
    style = _Style(tty=False)
    listing = render("dfd", style)
    for entry in entries:
        assert entry.summary in listing
        page = render(entry.names[0], style)
        assert page.startswith(entry.names[0].upper() + " — ") and "EXAMPLE" in page
    assert "dfdstorewid 1.5" in listing
    assert "dfd" in render("help", style) and "dfd.pik" in render("include", style)
    llm = llm_text()
    assert 'include "dfd.pik"' in llm and "--help dfd" in llm
    assert all(name in llm for name in CALLS)


@pytest.mark.parametrize("entry", dfd_entries(), ids=lambda e: e.names[0])
def test_each_example_draws_without_a_warning(entry):
    assert entry.example.startswith('include "dfd.pik"\n')
    warned = [w.message for w in resolve_for_pptx(parse(entry.example + "\n")).warnings if w.objects]
    assert warned == []
