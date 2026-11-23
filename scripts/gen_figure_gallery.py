"""Write the figures gallery in docs/: docs/figures/NAME.pik, each family's
example from its `--help` entry (figures.pik's `#:` comment), and
docs/figures.md, which shows each with its PNG.

    uv run python scripts/gen_figure_gallery.py        # the .pik files and figures.md
    uv run python scripts/gen_figure_gallery.py --png  # and render each PNG

The PNGs are rendered with PowerPoint, the renderer pikslide's output is
meant for, and so stand for it in tests/test_draw.py. tests/test_docs.py
checks that docs/ holds what this writes.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import tempfile

from pikslide.help import figure_entries

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"


def family(names: tuple[str, ...]) -> str:
    """A family's name, its macros' less the count: cycle, venn, matrix."""
    return re.sub(r"\d+$", "", names[0])


def _names(names: tuple[str, ...]) -> str:
    return f"`{names[0]}`" if len(names) == 1 else f"`{names[0]}` … `{names[-1]}`"


def expected_files() -> dict[pathlib.Path, str]:
    files: dict[pathlib.Path, str] = {}
    sections = []
    for entry in figure_entries():
        name = family(entry.names)
        files[DOCS / "figures" / f"{name}.pik"] = entry.example + "\n"
        sections.append("\n".join([
            f"## {_names(entry.names)}", "",
            f"{entry.summary[0].upper()}{entry.summary[1:]}. {entry.body}", "",
            "```pikslide", entry.example, "```", "",
            f"![{name}](figures/{name}.png)", "",
        ]))
    files[DOCS / "figures.md"] = "\n".join([
        "# Figures",
        "",
        "Macros for diagrams whose shape is the point, in a file pikslide ships:",
        '`include "figures.pik"`, then one call draws the figure. Each draws a',
        "block whose parts are named in it (`P.S1`, `P.C`); each argument is a",
        "part's strings and attributes, written last, so that they win. `figwid`",
        "and `fight` are the size a figure fits in. `pikslide --help figures`",
        "lists them, and `pikslide --help NAME` describes one.",
        "",
        "Written by `scripts/gen_figure_gallery.py` from each family's",
        "`--help` entry (`--png` to render the pictures, with PowerPoint).",
        "",
        *sections,
    ]).rstrip("\n") + "\n"
    return files


def png_paths() -> list[pathlib.Path]:
    return [DOCS / "figures" / f"{family(e.names)}.png" for e in figure_entries()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--png", action="store_true", help="also render each figure's PNG, with PowerPoint")
    args = parser.parse_args()
    (DOCS / "figures").mkdir(exist_ok=True)
    for path, text in expected_files().items():
        path.write_text(text, encoding="utf-8")
        print(path.relative_to(DOCS.parent))
    if args.png:
        with tempfile.TemporaryDirectory() as tmp:
            for png in png_paths():
                deck = pathlib.Path(tmp) / f"{png.stem}.pptx"
                subprocess.run(["pikslide", str(png.with_suffix(".pik")), str(deck), "--png", str(png),
                                "--renderer", "powerpoint"], check=True)


if __name__ == "__main__":
    main()
