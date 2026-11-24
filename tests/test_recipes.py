"""The recipes pikslide ships in recipes/, one per kind of diagram, for an
LLM to copy and adapt (issue #75): each a whole diagram, its notes in
comments, printed by `pikslide --help NAME` and named by --help llm.
That each lays out with nothing overlapping is tests/test_overlap.py's."""

from __future__ import annotations

import pathlib

import pytest

from pikslide.help import RECIPES, llm_text, recipe_text, render, _Style

ROOT = pathlib.Path(__file__).resolve().parents[1]
STYLE = _Style(tty=False)


def test_each_recipe_is_a_file_and_each_file_a_recipe():
    files = {p.stem for p in (ROOT / "src" / "pikslide" / "recipes").glob("*.pik")}
    assert files == set(RECIPES) == {"flowchart", "architecture", "dfd"}


@pytest.mark.parametrize("name", sorted(RECIPES))
def test_its_notes_come_first_the_symbols_then_the_layout(name):
    text = recipe_text(name)
    assert text.startswith("# ") and f"pikslide --help {name}" in text.replace("#\n# ", "").replace("\n# ", " ")
    assert text.index("THE SYMBOLS") < text.index("HOW IT'S LAID OUT") < text.index("\n\n", text.index("HOW"))


@pytest.mark.parametrize("name", ["flowchart", "architecture"])
def test_help_prints_it_as_it_is(name):
    assert render(name, STYLE) == recipe_text(name)


def test_help_dfd_gives_the_macros_then_the_recipe():
    text = render("dfd", STYLE)
    assert text.index("dfdgsstore") < text.index(recipe_text("dfd"))
    assert 'include "dfd.pik"' in recipe_text("dfd")


def test_they_are_listed_and_named():
    listing = render("recipes", STYLE)
    assert all(name in listing and summary in listing for name, summary in RECIPES.items())
    assert render("recipe", STYLE) == render("cookbook", STYLE) == listing
    assert "recipes" in render("help", STYLE)
    llm = llm_text()
    assert "--help recipes" in llm and all(f"--help {name}" in llm for name in RECIPES)


def test_the_flowchart_is_not_the_benchmarks_answer():
    # bench/tasks/fizzbuzz.md asks for FizzBuzz: a run reading --help
    # flowchart mustn't find it drawn there.
    assert all("Fizz" not in recipe_text(name) for name in RECIPES)
    assert "flowChartPredefinedProcess" in recipe_text("flowchart")


def test_a_bent_lines_label_is_in_lines_own_help():
    assert "on none of its segments" in " ".join(render("line", STYLE).split())
    assert "a bent line's on no segment" in llm_text()
