"""Write the preset shape gallery in docs/: docs/shapes/shapes-N.pik, a
page of preset shapes each, and docs/shapes.md, which shows their PNGs.

    uv run python scripts/gen_shape_gallery.py        # the .pik pages and shapes.md
    uv run python scripts/gen_shape_gallery.py --png  # and render each page's PNG

The PNGs are rendered with PowerPoint, the renderer pikslide's output is
meant for: LibreOffice draws some presets differently. tests/test_docs.py
checks that docs/ holds what this writes.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile

from pikslide.pik.layout import PRESET_NAMES

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
COLS, ROWS = 6, 6
# Inches. The wide gaps leave room for what reaches outside a shape's box:
# a line callout's leader line runs off to its lower left.
PITCH_X, PITCH_Y, LABEL_Y = 2.0, 1.6, 0.6
# Filled, so that a shape with no outline (callout1) still shows its box.
FILL = "accent1 lighter 80%"


def pages() -> list[list[str]]:
    names = sorted(PRESET_NAMES.values(), key=str.lower)
    n = COLS * ROWS
    return [names[i:i + n] for i in range(0, len(names), n)]


def page_source(names: list[str]) -> str:
    lines = ["# Written by scripts/gen_shape_gallery.py: don't edit.", ""]
    for i, name in enumerate(names):
        x, y = i % COLS * PITCH_X, -(i // COLS) * PITCH_Y
        lines.append(f"shape {name} wid 1in ht 0.7in fill {FILL} at ({x:g}in, {y:g}in)")
        lines.append(f'text "{name}" small at ({x:g}in, {y - LABEL_Y:g}in)')
    return "\n".join(lines) + "\n"


def markdown(all_pages: list[list[str]]) -> str:
    out = [
        "# Preset shapes",
        "",
        "<!-- Written by scripts/gen_shape_gallery.py: don't edit. -->",
        "",
        f"All {sum(map(len, all_pages))} preset shapes that `shape NAME` draws, each as PowerPoint",
        "renders it at its default geometry in a 1 in × 0.7 in box.",
        "`pikslide --help shapes` says in words what each one looks like.",
        "",
        f"They're filled here (`fill {FILL}`) to show their area. With",
        "pikslide's default, no fill, a shape with no outline, such as",
        "`callout1`, shows only its leader line.",
    ]
    for i, names in enumerate(all_pages, 1):
        out += ["", f"## {names[0]} … {names[-1]}", "",
                f"![Preset shapes {names[0]} to {names[-1]}](shapes/shapes-{i}.png)", "",
                ", ".join(f"`{n}`" for n in names)]
    return "\n".join(out) + "\n"


def expected_files() -> dict[pathlib.Path, str]:
    """What this writes: each path under docs/, with its text."""
    all_pages = pages()
    files = {DOCS / "shapes.md": markdown(all_pages)}
    for i, names in enumerate(all_pages, 1):
        files[DOCS / "shapes" / f"shapes-{i}.pik"] = page_source(names)
    return files


def png_paths() -> list[pathlib.Path]:
    """Each page's PNG, in page order."""
    return [DOCS / "shapes" / f"shapes-{i}.png" for i in range(1, len(pages()) + 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--png", action="store_true", help="also render each page's PNG, with PowerPoint")
    args = parser.parse_args()

    files = expected_files()
    (DOCS / "shapes").mkdir(exist_ok=True)
    keep = set(files) | set(png_paths())
    for old in (DOCS / "shapes").glob("shapes-*.*"):
        if old not in keep:
            old.unlink()
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(DOCS.parent)}")
    if args.png:
        with tempfile.TemporaryDirectory() as tmp:
            for png in png_paths():
                pptx = pathlib.Path(tmp) / png.with_suffix(".pptx").name
                subprocess.run(["pikslide", str(png.with_suffix(".pik")), str(pptx), "--png", str(png),
                                "--renderer", "powerpoint"], check=True)


if __name__ == "__main__":
    main()
