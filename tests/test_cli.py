"""`pikslide.main()` -- the `argparse` CLI (docs/spec.md SS4), covering
both standalone rendering (unchanged from before this file existed) and
`--into` (docs/spec.md SS4.2), backed by the already-tested
`pptx_writer.insert_into_pptx`."""

from __future__ import annotations

import pathlib

import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches

from pikslide import main

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _existing_deck(tmp_path: pathlib.Path, name: str = "deck.pptx") -> pathlib.Path:
    """A deck with one slide: an ordinary named shape "Figure" big enough
    to hold a small diagram, as a --region/--rect target."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(10), Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fig = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(4), Inches(3))
    fig.name = "Figure"
    path = tmp_path / name
    prs.save(str(path))
    return path


def _write(tmp_path: pathlib.Path, name: str, text: str) -> pathlib.Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _run(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr("sys.argv", ["pikslide", *argv])
    main()


# ---------------------------------------------------------------------------
# Standalone mode (pre-existing behaviour, now via argparse)
# ---------------------------------------------------------------------------


def test_no_args_prints_hello(monkeypatch, capsys):
    _run(monkeypatch, [])
    assert "Hello from pikslide" in capsys.readouterr().out


def test_dump_mode_prints_parsed_tree(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src)])
    out = capsys.readouterr().out
    assert "Document" in out and "box" in out.lower()


def test_standalone_render_to_pptx(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out_path = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out_path)])
    assert out_path.exists()
    assert f"wrote {out_path}" in capsys.readouterr().out


def test_standalone_render_with_o_flag(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out_path = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), "-o", str(out_path)])
    assert out_path.exists()


def test_unsupported_output_format_errors(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(tmp_path / "d.svg")])
    assert exc.value.code == 1
    assert "unsupported output format" in capsys.readouterr().err


def test_syntax_error_prints_message_and_exits(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", '"unterminated\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src)])
    assert exc.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_positional_and_o_together_is_an_error(monkeypatch, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(tmp_path / "a.pptx"), "-o", str(tmp_path / "b.pptx")])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# --into (docs/spec.md SS4.2)
# ---------------------------------------------------------------------------


def test_into_with_rect_and_default_output_filename(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), "--into", str(deck), "--slide", "1", "--rect", "1,1,2,1"])

    default_out = tmp_path / "deck.pikslide.pptx"
    assert default_out.exists()
    assert f"wrote {default_out}" in capsys.readouterr().out
    assert not deck.with_suffix(".pptx.bak").exists()  # the original deck is untouched
    prs = Presentation(str(deck))
    assert [s.name for s in prs.slides[0].shapes] == ["Figure"]  # unmodified

    inserted = Presentation(str(default_out))
    names = [s.name for s in inserted.slides[0].shapes]
    assert names == ["Figure", "pikslide:d"]  # --id defaulted to the source file's stem


def test_into_with_region_and_explicit_output(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "out.pptx"
    _run(
        monkeypatch,
        [str(src), "--into", str(deck), "--slide", "1", "--region", "Figure", "--id", "arch", "-o", str(out)],
    )
    assert out.exists()
    names = [s.name for s in Presentation(str(out)).slides[0].shapes]
    assert names == ["Figure", "pikslide:arch"]  # region is an ordinary shape, so it's left in place


def test_into_in_place_overwrites_deck(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), "--into", str(deck), "--slide", "1", "--region", "Figure", "--in-place"])
    assert not (tmp_path / "deck.pikslide.pptx").exists()
    names = [s.name for s in Presentation(str(deck)).slides[0].shapes]
    assert "pikslide:d" in names


def test_into_requires_slide(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), "--into", str(deck), "--region", "Figure"])
    assert exc.value.code == 2


def test_slide_without_into_is_an_error(monkeypatch, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), "--slide", "1"])
    assert exc.value.code == 2


def test_in_place_and_output_together_is_an_error(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(
            monkeypatch,
            [str(src), "--into", str(deck), "--slide", "1", "--region", "Figure", "--in-place", "-o", str(tmp_path / "x.pptx")],
        )
    assert exc.value.code == 2


def test_rect_must_have_four_numbers(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), "--into", str(deck), "--slide", "1", "--rect", "1,1,2"])
    assert exc.value.code == 2


def test_into_diagram_larger_than_region_is_a_clean_error(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", "box wid 2000% ht 2000%\n")
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), "--into", str(deck), "--slide", "1", "--region", "Figure"])
    assert exc.value.code == 1
    assert "larger than its region" in capsys.readouterr().err


def test_into_markdown_single_unnamed_block_defaults_id_to_file_stem(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "arch.md", '# doc\n\n```pikslide\nbox "Web"\n```\n')
    _run(monkeypatch, [str(src), "--into", str(deck), "--slide", "1", "--region", "Figure"])
    out = tmp_path / "deck.pikslide.pptx"
    names = [s.name for s in Presentation(str(out)).slides[0].shapes]
    assert "pikslide:arch" in names


def test_into_markdown_named_block_defaults_id_to_block_name(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "doc.md", '# doc\n\n```pikslide architecture\nbox "Web"\n```\n')
    _run(monkeypatch, [str(src), "--into", str(deck), "--slide", "1", "--region", "Figure"])
    out = tmp_path / "deck.pikslide.pptx"
    names = [s.name for s in Presentation(str(out)).slides[0].shapes]
    assert "pikslide:architecture" in names


def test_into_markdown_multiple_blocks_without_block_flag_is_an_error(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(
        tmp_path,
        "doc.md",
        '# doc\n\n```pikslide one\nbox "A"\n```\n\n```pikslide two\nbox "B"\n```\n',
    )
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), "--into", str(deck), "--slide", "1", "--region", "Figure"])
    assert exc.value.code == 1
    assert "--block" in capsys.readouterr().err
