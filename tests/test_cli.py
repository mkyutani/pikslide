"""`pikslide.main()` -- the `argparse` CLI (docs/spec.md SS4), covering
both standalone rendering (unchanged from before this file existed) and
inserting into an existing OUTPUT deck (docs/spec.md SS4.2), backed by
the already-tested `pptx_writer.insert_into_pptx`."""

from __future__ import annotations

import json
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
# Standalone mode (pre-existing behavior, now via argparse)
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


# ---------------------------------------------------------------------------
# Inserting into an existing deck: OUTPUT already exists (docs/spec.md SS4.2)
# ---------------------------------------------------------------------------


def test_existing_output_is_inserted_into_and_overwritten_in_place(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--rect", "1,1,2,1"])

    assert f"wrote {deck}" in capsys.readouterr().out
    names = [s.name for s in Presentation(str(deck)).slides[0].shapes]
    assert names == ["Figure", "pik:dbox 1"]  # --id defaulted to the source file's stem


def test_region_is_an_ordinary_shape_left_in_place(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--region", "Figure", "--id", "arch"])
    names = [s.name for s in Presentation(str(deck)).slides[0].shapes]
    assert names == ["Figure", "pik:archbox 1"]


def test_prefix_flag_overrides_the_id_derived_default(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--region", "Figure", "--prefix", "diagram-42:"])
    names = [s.name for s in Presentation(str(deck)).slides[0].shapes]
    assert names == ["Figure", "diagram-42:box 1"]


def test_rerun_replaces_only_what_pikslide_previously_placed(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--region", "Figure", "--id", "arch"])
    # A person edits the slide by hand in between runs.
    prs = Presentation(str(deck))
    note = prs.slides[0].shapes.add_textbox(Inches(0), Inches(5), Inches(2), Inches(1))
    note.name = "MyNote"
    prs.save(str(deck))

    src2 = _write(tmp_path, "d2.pik", 'box "Web2"\n')
    _run(monkeypatch, [str(src2), str(deck), "--slide", "1", "--region", "Figure", "--id", "arch"])
    names = [s.name for s in Presentation(str(deck)).slides[0].shapes]
    # hand-added note untouched, no duplicate; the replacement keeps the
    # z-order position the old diagram shape had (before MyNote).
    assert names == ["Figure", "pik:archbox 1", "MyNote"]


def test_slide_requires_an_existing_output_deck(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(deck), "--region", "Figure"])
    assert exc.value.code == 2


def test_slide_without_an_existing_output_is_an_error(monkeypatch, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(tmp_path / "nope.pptx"), "--slide", "1"])
    assert exc.value.code == 2


def test_rect_must_have_four_numbers(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--rect", "1,1,2"])
    assert exc.value.code == 2


def test_insert_diagram_larger_than_region_is_a_clean_error(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", "box wid 2000% ht 2000%\n")
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--region", "Figure"])
    assert exc.value.code == 1
    assert "larger than its region" in capsys.readouterr().err


def test_insert_markdown_single_unnamed_block_defaults_id_to_file_stem(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "arch.md", '# doc\n\n```pikslide\nbox "Web"\n```\n')
    _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--region", "Figure"])
    names = [s.name for s in Presentation(str(deck)).slides[0].shapes]
    assert "pik:archbox 1" in names


def test_insert_markdown_named_block_defaults_id_to_block_name(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "doc.md", '# doc\n\n```pikslide architecture\nbox "Web"\n```\n')
    _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--region", "Figure"])
    names = [s.name for s in Presentation(str(deck)).slides[0].shapes]
    assert "pik:architecturebox 1" in names


def test_insert_markdown_multiple_blocks_without_block_flag_is_an_error(monkeypatch, capsys, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(
        tmp_path,
        "doc.md",
        '# doc\n\n```pikslide one\nbox "A"\n```\n\n```pikslide two\nbox "B"\n```\n',
    )
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--region", "Figure"])
    assert exc.value.code == 1
    assert "--block" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# --template / --settings (docs/spec.md SS3.3 rule 2/3, SS3.8, SS4.1)
# ---------------------------------------------------------------------------


def _template_deck(tmp_path: pathlib.Path, name: str = "tmpl.pptx") -> pathlib.Path:
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[1]).shapes.title.text = "Sample"
    path = tmp_path / name
    prs.save(str(path))
    return path


def test_standalone_without_template_warns_and_still_writes(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out)])
    captured = capsys.readouterr()
    assert out.exists()
    assert "warning:" in captured.err and "stand-ins" in captured.err
    assert "wrote" in captured.out


def test_strict_turns_the_no_template_warning_into_an_error(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "d.pptx"
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(out), "--strict"])
    assert exc.value.code == 1
    assert not out.exists()
    assert "stand-ins" in capsys.readouterr().err


def test_template_flag_starts_a_new_deck_from_that_theme(monkeypatch, capsys, tmp_path):
    tmpl = _template_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out), "--template", str(tmpl)])
    captured = capsys.readouterr()
    assert out.exists()
    assert "warning:" not in captured.err  # a real template given -- no stand-in warning
    prs = Presentation(str(out))
    assert len(prs.slides) == 1
    assert [s.name for s in prs.slides[0].shapes] == ["box 1"]  # sample slide stripped


def test_template_with_an_existing_output_still_recreates_it_fresh(monkeypatch, capsys, tmp_path):
    # --template always starts a brand-new deck (docs/spec.md SS3.3 rule
    # 2), even if OUTPUT already exists from an earlier run -- otherwise
    # re-running the exact same --template command a second time would
    # unexpectedly switch into inserting instead of just overwriting.
    tmpl = _template_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out), "--template", str(tmpl)])
    _run(monkeypatch, [str(src), str(out), "--template", str(tmpl)])
    prs = Presentation(str(out))
    assert len(prs.slides) == 1
    assert [s.name for s in prs.slides[0].shapes] == ["box 1"]  # fresh deck, not an insert


def test_output_omitted_defaults_from_input_when_template_is_given(monkeypatch, capsys, tmp_path):
    tmpl = _template_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), "--template", str(tmpl)])
    default_out = tmp_path / "d.pptx"
    assert default_out.exists()
    assert f"wrote {default_out}" in capsys.readouterr().out


def test_settings_file_beside_template_is_found_automatically(monkeypatch, tmp_path):
    tmpl = _template_deck(tmp_path)
    _write(tmp_path, "tmpl.theme.pik", 'typeface = "Verdana"\n')
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out), "--template", str(tmpl)])
    run = Presentation(str(out)).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.name == "Verdana"


def test_explicit_settings_flag_overrides_the_beside_file(monkeypatch, tmp_path):
    tmpl = _template_deck(tmp_path)
    _write(tmp_path, "tmpl.theme.pik", 'typeface = "Verdana"\n')
    _write(tmp_path, "elsewhere.pik", 'typeface = "Georgia"\n')
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out), "--template", str(tmpl), "--settings", str(tmp_path / "elsewhere.pik")])
    run = Presentation(str(out)).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.name == "Georgia"


def test_missing_explicit_settings_file_is_an_error(monkeypatch, tmp_path):
    tmpl = _template_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(tmp_path / "out.pptx"), "--template", str(tmpl), "--settings", str(tmp_path / "nope.pik")])
    assert exc.value.code == 1


def test_settings_content_area_becomes_the_default_insert_region(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    _write(tmp_path, "deck.theme.pik", "content_left = 2in\ncontent_top = 2in\ncontent_right = 6in\ncontent_bottom = 6in\n")
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), str(deck), "--slide", "1"])  # no --region/--rect at all
    shape = Presentation(str(deck)).slides[0].shapes[-1]
    assert (shape.left.inches, shape.top.inches) == pytest.approx((2.0, 2.0))


# ---------------------------------------------------------------------------
# --include-path, --align, --check, --format json (ext)
# ---------------------------------------------------------------------------


def test_include_path_flag_is_searched_when_not_found_beside_the_source(monkeypatch, tmp_path):
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "house.pik").write_text("primary = accent3\n", encoding="utf-8")
    src = _write(tmp_path, "d.pik", 'include "house.pik"\nbox fill primary\n')
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out), "--include-path", str(lib_dir)])
    assert out.exists()


def test_align_center_when_inserting(monkeypatch, tmp_path):
    deck = _existing_deck(tmp_path)
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    _run(monkeypatch, [str(src), str(deck), "--slide", "1", "--region", "Figure", "--align", "center"])
    shape = Presentation(str(deck)).slides[0].shapes[-1]
    # Figure is (1,1,4,3); a bare box (0.75x0.5) centred within it:
    assert shape.left.inches == pytest.approx(1 + (4 - shape.width.inches) / 2, abs=0.01)
    assert shape.top.inches == pytest.approx(1 + (3 - shape.height.inches) / 2, abs=0.01)


def test_align_without_an_existing_output_is_an_error(monkeypatch, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(tmp_path / "d.pptx"), "--align", "center"])
    assert exc.value.code == 2


def test_check_parses_and_lays_out_without_writing(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out), "--check"])
    assert not out.exists()
    assert "ok" in capsys.readouterr().out


def test_check_still_catches_a_layout_error(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", "box fill nosuchcolor\n")
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [str(src), str(tmp_path / "d.pptx"), "--check"])
    assert exc.value.code == 1


def test_format_json_success(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["output"] == str(out)
    assert any("stand-ins" in w for w in payload["warnings"])


def test_format_json_syntax_error_has_file_line_column(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", '"unterminated\n')
    with pytest.raises(SystemExit):
        _run(monkeypatch, [str(src), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    err = payload["errors"][0]
    assert err["file"] == str(src)
    assert err["line"] == 1
    assert isinstance(err["column"], int)


def test_format_json_layout_error_has_no_position(monkeypatch, capsys, tmp_path):
    src = _write(tmp_path, "d.pik", "box fill nosuchcolor\n")
    out = tmp_path / "d.pptx"
    with pytest.raises(SystemExit):
        _run(monkeypatch, [str(src), str(out), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    err = payload["errors"][0]
    assert err["line"] is None
    assert "nosuchcolor" in err["message"]


def test_block_selects_the_named_diagram(monkeypatch, tmp_path):
    src = _write(
        tmp_path, "doc.md", '# doc\n\n```pikslide one\nbox "A"\n```\n\n```pikslide two\nbox "B"\n```\n'
    )
    out = tmp_path / "d.pptx"
    _run(monkeypatch, [str(src), str(out), "--block", "two"])
    text = Presentation(str(out)).slides[0].shapes[0].text_frame.text
    assert text == "B"


def test_block_unknown_name_lists_the_known_ones(monkeypatch, capsys, tmp_path):
    src = _write(
        tmp_path, "doc.md", '# doc\n\n```pikslide one\nbox "A"\n```\n\n```pikslide two\nbox "B"\n```\n'
    )
    with pytest.raises(SystemExit):
        _run(monkeypatch, [str(src), str(tmp_path / "d.pptx"), "--block", "nope"])
    assert "'one'" in capsys.readouterr().err


def test_block_on_a_non_markdown_file_is_an_error(monkeypatch, tmp_path):
    src = _write(tmp_path, "d.pik", 'box "Web"\n')
    with pytest.raises(SystemExit):
        _run(monkeypatch, [str(src), str(tmp_path / "d.pptx"), "--block", "x"])
