"""The macros pikslide ships in includes/figures.pik, for diagrams whose
shape is the point (issue #38): what scripts/gen_figures.py writes, each
drawn without a warning, its parts named in its block, and its help."""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

from pikslide import parse
from pikslide.help import figure_entries, llm_text, render, _Style
from pikslide.pik.layout import flatten_shapes, resolve_layout
from pikslide.pptx_writer import resolve_for_pptx

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIGURES = ROOT / "src" / "pikslide" / "includes" / "figures.pik"
WORDS = ["Plan", "Do", "Check", "Act", "Learn", "Share", "Grow", "Rest"]


def macros() -> dict[str, int]:
    """Each macro in figures.pik, and how many arguments it takes."""
    text = FIGURES.read_text(encoding="utf-8")
    bodies = re.findall(r"(?m)^define (\w+) \{\n(.*?)\n\}$", text, re.S)
    return {name: max(int(n) for n in re.findall(r"\$(\d)", body)) for name, body in bodies}


def call(name: str, n: int) -> str:
    return f'include "figures.pik"\nP: {name}({", ".join(chr(34) + w + chr(34) for w in WORDS[:n])})\n'


def test_it_is_what_the_script_writes():
    spec = importlib.util.spec_from_file_location("gen_figures", ROOT / "scripts" / "gen_figures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert FIGURES.read_text(encoding="utf-8") == module.figures_source(), "run scripts/gen_figures.py"


def test_there_are_the_families_and_counts_promised():
    assert sorted(macros()) == sorted(
        [f"cycle{n}" for n in range(3, 7)] + [f"chevron{n}" for n in range(3, 7)]
        + [f"pyramid{n}" for n in range(3, 6)] + [f"funnel{n}" for n in range(3, 6)]
        + ["venn2", "venn3", "matrix2"] + [f"hub{n}" for n in range(3, 9)])


@pytest.mark.parametrize("name, n", sorted(macros().items()))
def test_each_draws_without_a_warning(name, n):
    # The warnings about the diagram, not about fonts this machine lacks.
    warnings = [w.message for w in resolve_for_pptx(parse(call(name, n))).warnings if w.objects]
    assert warnings == []


@pytest.mark.parametrize("name, n", sorted(macros().items()))
def test_its_parts_are_named_in_its_block(name, n):
    shapes = {s.name for s in flatten_shapes(resolve_layout(parse(call(name, n))).shapes)}
    assert "S1" in shapes
    # And a later object can refer to them through the block's label.
    resolve_layout(parse(call(name, n) + "arrow from P.S1.n up 0.3\n"))


def test_an_argument_says_what_its_part_is_last():
    shapes = flatten_shapes(resolve_layout(parse(
        'include "figures.pik"\nP: cycle3("a", "b" fill red, "c")\n')).shapes)
    fills = {s.name: s.fill for s in shapes if s.name in ("S1", "S2")}
    assert fills["S1"] != fills["S2"]


def test_figwid_and_fight_size_it():
    def width(src):
        return resolve_layout(parse(src)).bbox[2] - resolve_layout(parse(src)).bbox[0]
    assert width('include "figures.pik"\nfigwid = 3\nP: funnel3("a", "b", "c")\n') == pytest.approx(3)
    assert width('include "figures.pik"\nP: funnel3("a", "b", "c")\n') == pytest.approx(6)


def test_a_file_of_ones_own_by_that_name_comes_first(tmp_path):
    (tmp_path / "figures.pik").write_text("define cycle3 { box $1 }\n", encoding="utf-8")
    doc = parse('include "figures.pik"\ncycle3("a")\n', base_dir=str(tmp_path))
    assert [s.kind for s in flatten_shapes(resolve_layout(doc).shapes)] == ["box"]


def test_each_has_help():
    entries = figure_entries()
    assert sorted(name for e in entries for name in e.names) == sorted(macros())
    style = _Style(tty=False)
    listing = render("figures", style)
    for entry in entries:
        assert entry.summary in listing
        for name in entry.names:
            page = render(name, style)
            assert page.startswith(entry.names[0].upper() + " — ") and "EXAMPLE" in page
    assert "--help figures" in render("include", style)
    assert 'include "figures.pik"' in llm_text()


@pytest.mark.parametrize("entry", figure_entries(), ids=lambda e: e.names[0])
def test_each_example_draws_without_a_warning(entry):
    warnings = [w.message for w in resolve_for_pptx(parse(entry.example + "\n")).warnings if w.objects]
    assert warnings == []
