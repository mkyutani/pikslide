"""render-png PPTX [PNG]: the deck's first slide as a PNG, drawn by
PowerPoint, as `pikslide --png` draws one; an error when PowerPoint can't
be reached (where `pikslide --png` draws it itself, which this can't).
setup.sh installs it with the venv's Python as its interpreter."""

import sys
from pathlib import Path

from pikslide.render import RenderError, render_deck

if len(sys.argv) not in (2, 3):
    sys.exit("usage: render-png PPTX [PNG]")
pptx = sys.argv[1]
png = sys.argv[2] if len(sys.argv) == 3 else str(Path(pptx).with_suffix(".png"))
try:
    render_deck(pptx, png, "png", renderer="powerpoint")
except RenderError as e:
    sys.exit(f"render-png: {e}")
print(f"wrote {png}")
