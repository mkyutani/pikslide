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

The specification is ahead of the implementation.

**Implemented today** is the pikchr-derived core: a parser, a layout stage (a
pragmatic subset of pikchr's own), and PowerPoint (`.pptx`) output of a single
slide sized to the diagram.

**Specified, not implemented yet**: theme colours and fonts, preset shapes
(`shape`), images and icons (`image`), `include`, a prelude of built-in names,
three fixed text sizes, per-template settings files, and insertion into an
existing deck. The rules marked `(ext)` in [docs/grammar.md](docs/grammar.md)
are the ones not implemented yet; [docs/implementation-plan.md](docs/implementation-plan.md)
lists everything that has to change.

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
  approximation rather than each shape's true outline,
- `behind` is parsed but doesn't yet affect rendering order.

See the module docstrings in `src/pikslide/pik/layout.py` for details.

## Development

```sh
uv run pytest
```

Test fixtures under `tests/fixtures/examples/` are pikchr's own official
example scripts, kept as a corpus for behaviour that has not deliberately
changed.

## Acknowledgments

The tokenizer, grammar, macro expansion, and layout engine in this project are
substantially ported from [pikchr](https://pikchr.org/) by D. Richard Hipp,
whose [source](https://pikchr.org/home/doc/tip/pikchr.y) states it is released
under the Zero-Clause BSD license. See [NOTICE](NOTICE) for details.

## License

[0BSD](LICENSE)
