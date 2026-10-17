"""Tests for attached lines (issue #18): `attach` and `path`, from parsing
to the connector's attached ends in the deck and --check's object list,
and the elbow connector's route, against PowerPoint's own."""

from __future__ import annotations

import json
import math
import pathlib

import pytest
from pptx import Presentation
from pptx.oxml.ns import qn

from pikslide import main
from pikslide.pik import ast, parse
from pikslide.pik.elbow import route
from pikslide.pik.layout import LayoutError, connection_sites, flatten_shapes, resolve_layout
from pikslide.pik.tokens import PikSyntaxError
from pikslide.pptx_writer import resolve_for_pptx, write_pptx


def layout(src: str):
    return resolve_layout(parse(src))


def attached(src: str, name: str | None = None) -> list[tuple[str, int] | None]:
    """The objects and sites the last line `src` draws (or `name`) attached its ends to."""
    lines = [s for s in flatten_shapes(layout(src).shapes) if s.attach]
    line = next(s for s in lines if s.name == name) if name else lines[-1]
    return [None if end is None else (end[0].name, end[1]) for end in line.attached]


def warnings(src: str) -> list[str]:
    return [w.message for w in layout(src).warnings]


def test_attach_and_path_parse():
    [stmt] = parse("arrow from A.e to B.w attach path straight\n").statements
    assert stmt.attributes[2:] == [ast.Attach(), ast.ConnectorPath("straight")]
    with pytest.raises(PikSyntaxError, match="after 'path'"):
        parse("arrow attach path\n")


def test_connection_sites_are_the_presets_in_a_connectors_order():
    # A rectangle's: top, left, bottom, right. An ellipse's eight go round
    # counterclockwise from the top, on its compass points.
    box = layout("box\n").shapes[0]
    assert connection_sites(box) == [pytest.approx(p) for p in [(0, 0.25), (-0.375, 0), (0, -0.25), (0.375, 0)]]
    circle = layout("circle\n").shapes[0]
    compass = ["n", "nw", "w", "sw", "s", "se", "e", "ne"]
    assert connection_sites(circle) == [pytest.approx(circle.edge_point(e)) for e in compass]
    assert connection_sites(layout("Q: (0, 0)\n").shapes[0]) == []


def test_ends_attach_to_the_objects_from_and_to_name():
    src = "A: box\nB: circle at (2, 1)\n"
    assert attached(src + "arrow from A.e to B.w attach\n") == [("A", 3), ("B", 2)]
    assert attached(src + "arrow from A.n to B.nw attach\n") == [("A", 0), ("B", 1)]
    assert warnings(src + "arrow from A.e to B.w attach\n") == []


def test_an_unnamed_end_attaches_to_the_object_whose_site_it_is_on_placed_before_or_after():
    assert attached("A: box\narrow attach\nB: box\n") == [("A", 3), ("B", 1)]


def test_an_end_off_a_site_warns_with_the_nearest_and_stays_unattached():
    src = "A: box\nB: box at (2, 0)\n"
    assert attached(src + "arrow from A.ne to B.w attach\n") == [None, ("B", 1)]
    assert warnings(src + "arrow from A.ne to B.w attach\n") == [
        "arrow 1's start isn't on a connection site of A, so it isn't attached: end it at A.e, the nearest"]
    assert attached(src + "arrow from A.e + (0, 0.1) to B.w attach\n") == [None, ("B", 1)]
    # A default name can't be written in the source as it is.
    assert "end it at the .w of box 2" in warnings("box\nbox at (2, 0)\narrow from 1st box.e to 2nd box.nw attach\n")[0]


@pytest.mark.parametrize("src, what", [
    ("Q: (0, 0)\nA: box at (2, 0)\narrow from Q to A.w attach\n", "Q, a point"),
    ("M: move\nA: box at (2, 0)\narrow from M.end to A.w attach\n", "M, a move"),
    ("L: line from (0, 0) right 1\nA: box at (2, 0)\narrow from L.end to A.w attach\n", "L, a line"),
])
def test_an_end_on_an_object_with_no_sites_warns(src: str, what: str):
    [message] = warnings(src)
    assert message == f"arrow 1's start is on {what}, which nothing attaches to: it isn't attached"
    assert attached(src) == [None, ("A", 1)]


def test_an_unnamed_end_on_two_objects_sites_warns():
    src = "A: box\nB: box with .w at A.e\nC: box at (3, 0)\narrow from (0.375, 0) to C.w attach\n"
    assert attached(src) == [None, ("C", 1)]
    [message] = warnings(src)
    assert message.startswith("arrow 1's start is on a connection site of both A and B")
    assert [w.objects for w in layout(src).warnings] == [("arrow 1", "A", "B")]


def test_an_unnamed_end_inside_an_object_isnt_on_it():
    # Only its outline counts: an arrow ending inside a frame is fine.
    src = "F: box wid 3 ht 2\nA: box at F\narrow from A.e right 0.5 attach\n"
    assert attached(src) == [("A", 3), None]
    assert warnings(src) == []


def test_a_path_a_straight_connector_cant_take_warns_and_stays_unattached():
    src = "A: box\nB: box at (2, -1)\narrow from A.e right 1 then down until even with B.n attach\n"
    assert attached(src) == [None, None]
    assert warnings(src) == ["arrow 1 has 2 segments, and a straight connector has one: it is written as drawn, "
                             "not attached; with `path elbow`, a path that turns at right angles attaches"]


@pytest.mark.parametrize("src, message", [
    ("box attach", "'attach' is only valid on a line or an arrow, not a box"),
    ("arc attach", "'attach' is only valid on a line or an arrow, not an arc"),
    ("arrow from (0, 0) to (1, 0) attach", "'attach' on arrow 1: neither of its ends is on an object"),
    ("A: box\narrow from A.e path straight", "'path straight' is the form of an attached line's connector: "
                                             "it needs 'attach'"),
    ("A: box\narrow from A.e attach path wavy", "unknown connector form 'path wavy': use straight, elbow or curved"),
])
def test_attach_errors(src: str, message: str):
    with pytest.raises(LayoutError, match="^" + message.replace("(", r"\(").replace(")", r"\)") + "$"):
        layout(src + "\n")


def render(src: str, tmp_path: pathlib.Path) -> dict[str, object]:
    out = tmp_path / "out.pptx"
    write_pptx(resolve_for_pptx(parse(src), base_dir=str(tmp_path)), str(out))
    return {s.name: s for s in Presentation(str(out)).slides[0].shapes}


def ends(connector, shapes) -> list[tuple[str, int] | None]:
    names = {s.shape_id: name for name, s in shapes.items()}
    nv = connector._element.nvCxnSpPr.cNvCxnSpPr
    return [None if (el := nv.find(qn(tag))) is None else (names[int(el.get("id"))], int(el.get("idx")))
            for tag in ("a:stCxn", "a:endCxn")]


def test_an_attached_line_is_a_connector_attached_where_it_was_drawn(tmp_path: pathlib.Path):
    # B is drawn after the arrow, and the circle's site 1 is its .nw.
    shapes = render("A: box\narrow attach\nB: box\nC: circle at (2, 1)\narrow from A.n to C.nw attach\n", tmp_path)
    assert ends(shapes["arrow 1"], shapes) == [("A", 3), ("B", 1)]
    assert ends(shapes["arrow 2"], shapes) == [("A", 0), ("C", 1)]
    # Not moved: still where pikslide drew it.
    plain = render("A: box\narrow\nB: box\nC: circle at (2, 1)\narrow from A.n to C.nw\n", tmp_path)
    for name in ("arrow 1", "arrow 2"):
        a, b = shapes[name], plain[name]
        assert (a.begin_x, a.begin_y, a.end_x, a.end_y) == (b.begin_x, b.begin_y, b.end_x, b.end_y)
        assert ends(b, plain) == [None, None]


def test_a_picture_and_a_text_take_an_attached_end(tmp_path: pathlib.Path):
    from PIL import Image

    Image.new("RGB", (40, 20), "white").save(tmp_path / "x.png")
    shapes = render('I: image "x.png" wid 0.8\nT: text "note" at (0, -1)\narrow from T.n to I.s attach\n', tmp_path)
    assert ends(shapes["arrow 1"], shapes) == [("T", 0), ("I", 2)]


def test_check_says_which_ends_are_attached(monkeypatch, capsys, tmp_path: pathlib.Path):
    src = tmp_path / "d.pik"
    src.write_text("A: box\nB: box at (2, 0)\narrow from A.e to B.w attach\narrow from A.ne to B.w attach\n",
                   encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["pikslide", str(src), "--check"])
    main()
    objects = {o["name"]: o for o in json.loads(capsys.readouterr().out)["objects"]}
    assert objects["arrow 1"]["attached"] == {"start": "A", "end": "B"}
    assert objects["arrow 2"]["attached"] == {"end": "B"}
    assert "attached" not in objects["A"]


# ---------------------------------------------------------------------------
# path elbow
# ---------------------------------------------------------------------------


def elbow(src: str, name: str | None = None) -> list[tuple[float, float]]:
    lines = [s for s in flatten_shapes(layout(src).shapes) if s.attach]
    line = next(s for s in lines if s.name == name) if name else lines[-1]
    assert line.routed
    return [(round(x, 3), round(y, 3)) for x, y in line.path]


def test_an_elbow_is_routed_between_the_sites_as_powerpoint_routes_it():
    src = "A: box\nB: box at (2, -1)\n"
    # An L, down the middle of the gap, and round below both.
    assert elbow(src + "arrow from A.e to B.n attach path elbow\n") == [(0.375, 0), (2, 0), (2, -0.75)]
    assert elbow(src + "arrow from A.e to B.w attach path elbow\n") == [(0.375, 0), (1, 0), (1, -1), (1.625, -1)]
    assert elbow(src + "arrow from A.s to B.s attach path elbow\n") == [(0, -0.25), (0, -1.5), (2, -1.5), (2, -1.25)]
    assert attached(src + "arrow from A.s to B.s attach path elbow\n") == [("A", 2), ("B", 2)]


def test_an_elbow_to_an_object_placed_after_it_meets_it_head_on():
    assert elbow("A: box\narrow attach path elbow\nB: box\n") == [(0.375, 0), (0.875, 0)]
    assert attached("A: box\narrow attach path elbow\nB: box\n") == [("A", 3), ("B", 1)]


def test_a_path_that_turns_at_right_angles_is_an_elbow_as_it_stands():
    src = "A: box\nB: box at (2, -1)\narrow from A.e right 0.5 then right 0.5 then down until even with B.w " \
          "then right until even with B.w attach path elbow\n"
    assert elbow(src) == [(0.375, 0), (1.375, 0), (1.375, -1), (1.625, -1)]
    assert attached(src) == [("A", 3), ("B", 1)]


@pytest.mark.parametrize("path", ["to B.w", "to B.w then right 1 then up 1 then right 1 then down 1 then left 1"])
def test_a_path_an_elbow_cant_take_warns_and_stays_unattached(path: str):
    src = f"A: box\nB: box at (2, -1)\narrow from A.e right 0.5 then {path} attach path elbow\n"
    assert attached(src) == [None, None]
    assert warnings(src) == ["arrow 1 isn't a route an elbow connector can take, with a slanted segment or more "
                             "than four bends: it is written as drawn, not attached"]


def _powerpoint_elbows():
    path = pathlib.Path(__file__).parent / "fixtures" / "powerpoint_elbows.txt"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        head, points = line.split(" : ")
        s, e, *box = head.split()
        yield s, e, [float(v) for v in box[:4]], [float(v) for v in box[4:]], \
            [tuple(float(v) for v in p.split(",")) for p in points.split()]


_SIDES = {"t": ((0.5, 1), (0, 1)), "l": ((0, 0.5), (-1, 0)), "b": ((0.5, 0), (0, -1)), "r": ((1, 0.5), (1, 0))}


def test_elbow_routes_match_powerpoints_own():
    """PowerPoint's routes between rectangles of two sizes, at 46 places,
    every pair of sides (tests/fixtures/powerpoint_elbows.txt), in points
    with y down; route() takes inches with y up."""
    misses = []
    for s, e, a, b, want in _powerpoint_elbows():
        boxes = [(x / 72, -(y + h) / 72, (x + w) / 72, -y / 72) for x, y, w, h in (a, b)]
        ends = []
        for side, (x0, y0, x1, y1) in zip((s, e), boxes):
            (fx, fy), direction = _SIDES[side]
            ends.append(((x0 + fx * (x1 - x0), y0 + fy * (y1 - y0)), direction))
        (start, ds), (end, de) = ends
        got = [(x * 72, -y * 72) for x, y in route(start, ds, end, de, *boxes)]
        if len(got) != len(want) or any(math.dist(p, q) > 1.6 for p, q in zip(got, want)):
            misses.append((s, e, a, b, want, got))
    assert misses == []


def _rotated_local(connector) -> tuple[str, int, bool, bool, list[int]]:
    xfrm = connector._element.spPr.find(qn("a:xfrm"))
    geometry = connector._element.spPr.find(qn("a:prstGeom"))
    av = geometry.find(qn("a:avLst"))
    return (geometry.get("prst"), int(xfrm.get("rot", 0)), xfrm.get("flipH") == "1", xfrm.get("flipV") == "1",
            [] if av is None else [int(gd.get("fmla").split()[1]) for gd in av])


def test_an_elbow_is_written_as_powerpoint_writes_one(tmp_path: pathlib.Path):
    src = "A: box\nB: box at (2, -1)\nC: box at (2, 1)\n" \
          "arrow from A.e to B.n attach path elbow\narrow from A.e to B.w attach path elbow\n" \
          "arrow from A.n to C.w attach path elbow\narrow from A.s to B.s attach path elbow\n" \
          "arrow from B.n to C.s attach path elbow\n"
    shapes = render(src, tmp_path)
    # Down the slide: an L; a Z, its bend in the middle (50000). Leaving
    # upward, turned a quarter and flipped; round below both, its bend 1.25in
    # down a 1in drop (125000); straight up, a bentConnector3 of no height.
    # As PowerPoint wrote them (tests/fixtures: r t, r l, t l, b b, and t b).
    assert _rotated_local(shapes["arrow 1"]) == ("bentConnector2", 0, False, False, [])
    assert _rotated_local(shapes["arrow 2"]) == ("bentConnector3", 0, False, False, [50000])
    assert _rotated_local(shapes["arrow 3"]) == ("bentConnector2", 5400000, True, True, [])
    assert _rotated_local(shapes["arrow 4"]) == ("bentConnector3", 5400000, False, True, [125000])
    assert _rotated_local(shapes["arrow 5"]) == ("bentConnector3", 5400000, True, False, [])
    assert ends(shapes["arrow 4"], shapes) == [("A", 2), ("B", 2)]


# ---------------------------------------------------------------------------
# path curved
# ---------------------------------------------------------------------------


def test_a_curved_connector_curves_through_its_elbow_route():
    # curvedConnector3's geometry: through the middle segment's middle, its
    # controls half the first segment and a quarter of the middle one along.
    from pikslide.pik.layout import curved_connector

    assert curved_connector([(0, 0), (1, 0), (1, 2), (3, 2)]) == [
        ((0, 0), (0.5, 0), (1, 0.5), (1, 1)), ((1, 1), (1, 1.5), (2, 2), (3, 2))]
    # curvedConnector2: one curve, its controls the middles of both segments.
    assert curved_connector([(0, 0), (2, 0), (2, 1)]) == [((0, 0), (1, 0), (2, 0.5), (2, 1))]


def test_a_curved_connector_takes_the_elbows_route_and_is_judged_by_its_curve():
    src = "A: box\nB: box at (2, -1)\narrow from A.e to B.n attach path {}\n"
    curved = [s for s in flatten_shapes(layout(src.format("curved")).shapes) if s.attach][0]
    assert curved.routed and curved.path == [s for s in flatten_shapes(layout(src.format("elbow")).shapes)
                                             if s.attach][0].path
    assert attached(src.format("curved")) == [("A", 3), ("B", 0)]
    # A box at the L's corner is on the elbow, but off the curve, which
    # cuts the corner.
    corner = "C: box wid 0.3 ht 0.3 at (2, 0)\n"

    def overlaps(src: str) -> list[tuple[str, ...]]:
        return [w.objects for w in resolve_for_pptx(parse(src)).warnings if "passes through" in w.message]

    assert overlaps(src.format("elbow") + corner) == [("arrow 1", "C")]
    assert overlaps(src.format("curved") + corner) == []


def test_a_curved_connector_is_written_as_powerpoint_writes_one(tmp_path: pathlib.Path):
    src = "A: box\nB: box at (2, -1)\narrow from A.e to B.n attach path curved\n" \
          "arrow from A.s to B.s attach path curved\n"
    shapes = render(src, tmp_path)
    assert _rotated_local(shapes["arrow 1"]) == ("curvedConnector2", 0, False, False, [])
    assert _rotated_local(shapes["arrow 2"]) == ("curvedConnector3", 5400000, False, True, [125000])
    assert ends(shapes["arrow 2"], shapes) == [("A", 2), ("B", 2)]
