"""Write the data flow diagrams gallery in docs/: docs/dfd/NAME.pik, the
diagram of each DFD recipe in pikslide (`--help dfd`) and each dfd.pik
macro's example from its `--help` entry, and docs/dfd.md, which shows
each with its PNG.

    uv run python scripts/gen_dfd_gallery.py        # the .pik files and dfd.md
    uv run python scripts/gen_dfd_gallery.py --png  # and render each PNG

The PNGs are rendered with PowerPoint, as scripts/gen_figure_gallery.py's
are, and stand for it in tests/test_draw.py. tests/test_docs.py checks
that docs/ holds what this writes. No file in docs/dfd/ is named dfd.pik:
the others include that, and would read it.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile

from pikslide.help import RECIPE_FILES, dfd_entries, recipe_text

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"

# Each notation: its name in the gallery, its recipe and what it draws.
NOTATIONS = [
    ("demarco-yourdon", "DeMarco/Yourdon", RECIPE_FILES["dfd"][0],
     "A process is a numbered circle, `dfdprocess`, and a data store two parallel lines with its id and "
     "name between them, `dfdstore`."),
    ("gane-sarson", "Gane-Sarson", RECIPE_FILES["dfd"][1],
     "A process is a rounded rectangle with its number in a band at the top, `dfdgsprocess`, and a data "
     "store a rectangle open on its right with its id in a compartment of its own, `dfdgsstore`."),
]


def diagram(recipe: str) -> str:
    """A recipe's diagram: the recipe less the notes it starts with."""
    lines = recipe_text(recipe).splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip() and not line.startswith("#"))
    return "\n".join(lines[first:]) + "\n"


def expected_files() -> dict[pathlib.Path, str]:
    files: dict[pathlib.Path, str] = {}
    notations = []
    for name, title, recipe, says in NOTATIONS:
        source = diagram(recipe)
        files[DOCS / "dfd" / f"{name}.pik"] = source
        notations.append("\n".join([
            f"## {title}", "",
            f"{says} An external entity is a box, `dfdentity`, and a flow an arrow labeled with the data it "
            "carries. Order handling, as the recipe in `pikslide --help dfd` draws it, less its notes:", "",
            "```pikslide", source.rstrip("\n"), "```", "",
            f"![Order handling in {title} notation](dfd/{name}.png)", "",
        ]))
    macros = []
    for entry in dfd_entries():
        name = entry.names[0]
        files[DOCS / "dfd" / f"{name}.pik"] = entry.example + "\n"
        macros.append("\n".join([
            f"### `{name}`", "",
            f"{entry.summary[0].upper()}{entry.summary[1:]}. {entry.body}", "",
            "```pikslide", entry.example, "```", "",
            f"![{name}](dfd/{name}.png)", "",
        ]))
    files[DOCS / "dfd.md"] = "\n".join([
        "# Data flow diagrams",
        "",
        "Macros for a data flow diagram's parts, in a file pikslide ships:",
        '`include "dfd.pik"`, then a call draws each process, data store and',
        "external entity, in DeMarco/Yourdon or Gane-Sarson notation; the flows",
        "are arrows. `pikslide --help dfd` lists the macros, then gives a recipe",
        "in each notation, and `pikslide --help NAME` describes one.",
        "",
        "Written by `scripts/gen_dfd_gallery.py` from the recipes and each",
        "macro's `--help` entry (`--png` to render the pictures, with",
        "PowerPoint).",
        "",
        *notations,
        "## The macros",
        "",
        *macros,
    ]).rstrip("\n") + "\n"
    return files


def png_paths() -> list[pathlib.Path]:
    return [p.with_suffix(".png") for p in expected_files() if p.suffix == ".pik"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--png", action="store_true", help="also render each diagram's PNG, with PowerPoint")
    args = parser.parse_args()
    (DOCS / "dfd").mkdir(exist_ok=True)
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
