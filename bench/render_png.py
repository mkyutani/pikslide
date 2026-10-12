"""render-png PPTX [PNG]: the deck's first slide as a PNG, drawn by
PowerPoint (LibreOffice when PowerPoint can't be reached), the same way
`pikslide --png` draws one. setup.sh installs it with the venv's Python
as its interpreter."""

import sys
from pathlib import Path

from pikslide.render import RenderError, render_deck

if len(sys.argv) not in (2, 3):
    sys.exit("usage: render-png PPTX [PNG]")
pptx = sys.argv[1]
png = sys.argv[2] if len(sys.argv) == 3 else str(Path(pptx).with_suffix(".png"))
try:
    notes = render_deck(pptx, png, "png")
except RenderError as e:
    sys.exit(f"render-png: {e}")
for note in notes:
    print(f"render-png: {note}", file=sys.stderr)
print(f"wrote {png}")
