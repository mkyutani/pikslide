"""scripts/release_notes.py: a GitHub release's notes, from the message
of the commit its tag points at."""

from __future__ import annotations

import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).parent.parent / "scripts" / "release_notes.py"
_spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)


def test_a_paragraph_wrapped_in_the_commit_is_one_line():
    body = "PyPI shows the README a release\ncame with.\n\nA patch: nothing\nhas changed.\n"
    assert release_notes.unwrap(body) == "PyPI shows the README a release came with.\n\nA patch: nothing has changed."


def test_each_list_item_is_one_line():
    body = "Changes:\n\n- one, wrapped\n  onto two lines\n- two\n1. three\n"
    assert release_notes.unwrap(body) == "Changes:\n\n- one, wrapped onto two lines\n- two\n1. three"


def test_a_code_block_is_left_as_it_is():
    body = "Write\nthis:\n\n    arrow from A.e to B.n attach\n    box \"B\"\n"
    assert release_notes.unwrap(body) == "Write this:\n\n    arrow from A.e to B.n attach\n    box \"B\""


def test_the_notes_end_with_the_release_on_pypi():
    assert release_notes.notes("v0.2.1", "A patch.\n") == (
        "A patch.\n\nOn PyPI: https://pypi.org/project/pikslide/0.2.1/\n")
