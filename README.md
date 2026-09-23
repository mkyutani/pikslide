# pikslide

A text language for drawing **diagrams that live inside Office slides**.

You don't write coordinates: you place objects one after another in a
direction, and refer to earlier objects by name. A diagram becomes
**native, editable PowerPoint objects** — shapes a person can select,
restyle and move afterwards.

The language is specified in [docs/spec.md](docs/spec.md) and defined, in
BNF, in [docs/grammar.md](docs/grammar.md). (pikslide's own design traces
back through two earlier languages; see Acknowledgments, below.)

## Status

v1 (docs/spec.md §1) is implemented: a parser, a layout stage, and
PowerPoint output; colors as a type of their own, with theme colors
(`theme "accent1"`, `lighter`/`darker`) rendered as real `schemeClr`,
never resolved to RGB; fonts the same way — text set in the theme's own
font by default, not a hard-coded family, with `major` selecting the
heading font and `typeface` overriding both with one literal family;
three fixed text sizes (`small`/`medium`/`large`); a prelude of built-in
names (CSS color names, built-in defaults, the theme-color names); preset
shapes (`shape roundRect`, any of the ~180 OOXML presets, matched
case-insensitively); images (PNG/JPEG/GIF, and SVG — embedded together
with a PNG fallback for older viewers, sized explicitly or by aspect
ratio, path resolved and contained under the source file's own
directory); `include "house.pik"` for shared definitions (contained the
same way, with cycle detection); object identity — a label becomes the
shape's real PowerPoint name (an unlabeled object gets a default `box
1`-style name), and `behind X` places an object immediately below `X`
in z-order — so the Selection Pane reads like the source (`[ ... ]`
blocks are a source-level grouping construct only, flattened rather than
turned into a PowerPoint group when written out); Markdown
diagram names (the `pikslide` fence tag, naming a diagram when a file has
more than one, and selecting one with `--block`); inserting a diagram
into an existing slide as a name-prefixed, idempotently-replaceable set
of shapes (when OUTPUT already exists, with `--region`/`--rect`/`--align`
placing it); starting a new
standalone deck from another file's theme instead of the built-in Office
one (`--template`); a template's settings file (`<name>.theme.pik`, or
`--settings FILE`), for its slide layout, font, accent colors, text sizes
and content area (the default target region when inserting and neither
`--region` nor `--rect` is given); and diagnostics — `file:line:column`,
the source line and a caret for a syntax error (naming the right file
even inside a nested `include`), "did you mean" suggestions for an
unknown color/preset/image/region name, `--strict`, `--check`, and
`--format json`.

Deliberately out of v1 (docs/spec.md §7): connectors, SVG *output*,
auto-layout, tables/charts/SmartArt, animation, multi-slide authoring,
true Bézier curves, shape adjustment handles, arithmetic on colors.

## How it works

1. **Parse** — source is tokenized and parsed into an AST
   (`pikslide.pik.ast.Document`).
2. **Layout** — the AST is resolved into concrete 2-D geometry (box positions,
   arrow paths, text placement).
3. **Render** — the resolved geometry is written out as PowerPoint objects.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)

## Usage

Dump the parsed tree for a `.pik` file (useful for inspecting how a script was
understood, or for debugging):

```sh
uv run pikslide diagram.pik
```

Render a `.pik` file straight to PowerPoint:

```sh
uv run pikslide diagram.pik diagram.pptx
```

` ```pikslide ` fenced code blocks inside a Markdown file are also accepted
directly — every block in the file is processed in order:

```sh
uv run pikslide doc.md doc.pptx
```

If OUTPUT already exists, the diagram is inserted into it instead of a new
deck being created (docs/spec.md §4.2) — into a named shape or placeholder's
rectangle (`--region`), or an explicit one (`--rect x,y,w,h`, inches):

```sh
uv run pikslide diagram.pik deck.pptx --slide 5 --region "Figure"
```

OUTPUT is always overwritten in place — there's no separate output flag.
Running the same command again replaces the diagram in place rather than
adding a second copy, and leaves anything else on that slide (including an
edit made by hand since the last run) untouched. With no `--region`/`--rect`,
a `<deck>.theme.pik` settings file's content area (docs/spec.md §3.8) is the
default target.

For a standalone preview that uses a real template's theme and fonts
instead of the built-in Office ones:

```sh
uv run pikslide diagram.pik diagram.pptx --template corporate.potx
```

(OUTPUT may be omitted when `--template` is given: it then defaults to
INPUT's own path with its extension changed to `.pptx`.)

`--check` parses and lays out a source without writing anything, and
`--format json` emits diagnostics as one JSON object instead of plain
text — see `pikslide --help` for every flag.

With no arguments, `pikslide` just prints a hello-world message.

Render a `.pptx` to a PNG or a PDF with `scripts/pptx_to_png.sh` /
`scripts/pptx_to_pdf.sh`:

```sh
scripts/pptx_to_png.sh diagram.pptx diagram.png
scripts/pptx_to_pdf.sh diagram.pptx diagram.pdf
```

Each uses PowerPoint COM automation (`scripts/pptx_to_png.ps1` /
`pptx_to_pdf.ps1`, via `powershell.exe`) when one is reachable — Windows, or
WSL with a Windows PowerPoint install — since that's the actual renderer
pikslide's output is meant for, not just a stand-in for it; otherwise it
falls back to LibreOffice (`soffice`), a different rendering engine, good
for a quick look but not for verifying exact layout or text fit against
real PowerPoint. Since pikslide sizes its slide exactly to the diagram, the
PNG is an image of just the diagram, no separate cropping needed. (The
`.ps1` scripts also run on their own directly from Windows PowerShell, with
no wrapper needed.)

### Example

`examples/pipeline.pik`:

```pikslide
arrow right 200% "Markdown" "Source"
box rad 10px "Markdown" "Formatter" "(markdown.c)" fit
arrow right 200% "HTML+SVG" "Output"
arrow <-> down 70% from last box.s
box same "Pikchr" "Formatter" "(pikchr.c)" fit
```

```sh
uv run pikslide examples/pipeline.pik examples/pipeline.pptx
```

## Limits of the current layout stage

The layout stage is a deliberately pragmatic subset of a full CAD-style
layout engine, covering common diagrams well rather than every case:
default object sizes, sequential chaining,
`at`/`with`/`from`/`to`/`then`/`go`/`same`/`chop`, and box/ellipse/diamond
edge geometry are all there, but a few things are simplified:

- spline/arc curves are drawn as straight polylines,
- `fit` text sizing uses real font metrics when rendering to PowerPoint, but
  falls back to a flat per-character estimate otherwise,
- chopping against diamond/cylinder/file shapes uses a rectangle-like
  approximation rather than each shape's true outline.

See the module docstrings in `src/pikslide/pik/layout.py` for details.

## Development

```sh
uv run pytest
```

Test fixtures under `tests/fixtures/examples/` are a corpus of official
example diagrams inherited via the port described in Acknowledgments,
kept as a regression net for behavior that hasn't deliberately changed.

## Acknowledgments

pikslide traces its lineage through two earlier languages. Brian
Kernighan's `pic` (1984) introduced sequential, relative placement of
named objects — draw one thing, then the next one relative to it — rather
than absolute coordinates. D. Richard Hipp's [pikchr](https://pikchr.org/)
carried that idea into a full, modern language, emitting SVG. pikslide's
tokenizer, grammar, macro expansion, and layout engine began as a direct
port of pikchr's own, and the port goes well beyond syntax — default
object sizes, placement and chaining math, and edge geometry are all
inherited from it, not rebuilt from scratch. pikslide's own design departs
from there where a diagram that lives inside a PowerPoint slide, rather
than becoming an SVG picture, calls for a different answer.

pikchr's [source](https://pikchr.org/home/doc/tip/pikchr.y) states it is
released under the Zero-Clause BSD license. See [NOTICE](NOTICE) for
details.

## License

[0BSD](LICENSE)
