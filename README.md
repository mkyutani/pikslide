# pikslide

A text language for drawing **diagrams that live inside Office slides**.

pikslide descends from the *pic → pik* line ([pikchr](https://pikchr.org/)):
you don't write coordinates, you place objects one after another in a
direction and refer to earlier objects by name. Where pikchr emits an SVG
picture, pikslide emits **native, editable PowerPoint objects** — shapes a
person can select, restyle and move afterwards.

pikslide is its own language. It starts from pikchr's grammar and departs from
it where its design calls for it; compatibility with pikchr is not a goal. The
language is specified in [docs/spec.md](docs/spec.md) and defined, in BNF, in
[docs/grammar.md](docs/grammar.md).

## Status

v1 (docs/spec.md §1) is implemented: the pikchr-derived core (a parser, a
layout stage — a pragmatic subset of pikchr's own — and PowerPoint output);
colors as a type of their own, with theme colors (`theme "accent1"`,
`lighter`/`darker`) rendered as real `schemeClr`, never resolved to RGB;
fonts the same way — text set in the theme's own font by default, not a
hard-coded family, with `major` selecting the heading font and `typeface`
overriding both with one literal family; three fixed text sizes
(`small`/`medium`/`large`); a prelude of built-in names (CSS color names,
pikchr's own defaults, the theme-color names); preset shapes (`shape
roundRect`, any of the ~180 OOXML presets, matched case-insensitively);
images (PNG/JPEG/GIF, and SVG — embedded together with a PNG fallback for
older viewers, sized explicitly or by aspect ratio, path resolved and
contained under the source file's own directory); `include "house.pik"`
for shared definitions (contained the same way, with cycle detection);
object identity — a pik label becomes the shape's real PowerPoint name
(an unlabeled object gets a default `box 1`-style name), `[ ... ]` blocks
become real, nameable, nestable PowerPoint groups, and `behind X` places
an object immediately below `X` in z-order — so the Selection Pane reads
like the source; Markdown diagram names (the `pikslide` fence tag, naming
a diagram when a file has more than one, and selecting one with
`--block`); inserting a diagram into an existing slide as one named,
idempotently-replaceable group (`--into`, with `--region`/`--rect`/
`--align` placing it); starting a new standalone deck from another file's
theme instead of the built-in Office one (`--template`); a template's
settings file (`<name>.theme.pik`, or `--settings FILE`), for its slide
layout, font, accent colors, text sizes and content area (`--into`'s
default target region when neither `--region` nor `--rect` is given); and
diagnostics — `file:line:column`, the source line and a caret for a syntax
error (naming the right file even inside a nested `include`), `--strict`,
`--check`, and `--format json`.

**What's left** (both independent, both minor — see
[docs/implementation-plan.md](docs/implementation-plan.md) for the full,
current list): reading a template's actual theme *content* would sharpen
`fit` sizing for a font this machine doesn't have installed, but isn't
needed for correctness, since colors and fonts both stay theme-linked
regardless; and a `LayoutError` (unlike a syntax error) carries no source
position yet. Deliberately out of v1 (docs/spec.md §7): connectors, SVG
*output*, auto-layout, tables/charts/SmartArt, animation, multi-slide
authoring, true Bézier curves, shape adjustment handles, arithmetic on
colors.

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

`.pik` or `.pikchr` fenced code blocks inside a Markdown file are also
accepted directly — every block in the file is processed in order:

```sh
uv run pikslide doc.md doc.pptx
```

Insert a diagram into an existing deck instead of creating a new one
(docs/spec.md §4.2) — into a named shape or placeholder's rectangle
(`--region`), or an explicit one (`--rect x,y,w,h`, inches):

```sh
uv run pikslide diagram.pik --into deck.pptx --slide 5 --region "Figure" -o out.pptx
```

Omit `-o` to write `deck.pikslide.pptx` alongside the input deck, or pass
`--in-place` to overwrite `deck.pptx` itself. Running the same command again
replaces the diagram in place rather than adding a second copy. With no
`--region`/`--rect`, a `<deck>.theme.pik` settings file's content area
(docs/spec.md §3.8) is the default target.

For a standalone preview that uses a real template's theme and fonts
instead of the built-in Office ones:

```sh
uv run pikslide diagram.pik diagram.pptx --template corporate.potx
```

`--check` parses and lays out a source without writing anything, and
`--format json` emits diagnostics as one JSON object instead of plain
text — see `pikslide --help` for every flag.

With no arguments, `pikslide` just prints a hello-world message.

On Windows (or WSL with a Windows PowerPoint install), render a `.pptx` to a
PNG via `scripts/pptx_to_png.ps1` (PowerPoint COM automation; see that
script's header for usage from WSL vs. Windows PowerShell directly). Since
pikslide sizes its slide exactly to the diagram, this gives an image of just
the diagram, no separate cropping needed.

### Example

`examples/pipeline.pik`:

```pik
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

Today's parser and tokenizer still accept pikchr's language. The layout stage
is a deliberately pragmatic *subset* of pikchr's own: default object sizes,
sequential chaining, `at`/`with`/`from`/`to`/`then`/`go`/`same`/`chop`, and
box/ellipse/diamond edge geometry are ported faithfully, but a few things are
simplified:

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

Test fixtures under `tests/fixtures/examples/` are pikchr's own official
example scripts, kept as a corpus for behavior that has not deliberately
changed.

## Acknowledgments

The tokenizer, grammar, macro expansion, and layout engine in this project are
substantially ported from [pikchr](https://pikchr.org/) by D. Richard Hipp,
whose [source](https://pikchr.org/home/doc/tip/pikchr.y) states it is released
under the Zero-Clause BSD license. See [NOTICE](NOTICE) for details.

## License

[0BSD](LICENSE)
