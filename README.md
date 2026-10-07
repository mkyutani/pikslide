# pikslide

pikslide draws a diagram written as text into a PowerPoint slide.

The text, a `.pik` file, places shapes one after another and refers to
them by name, with no coordinates to work out. The slide it becomes is
made of **native, editable PowerPoint shapes**, colored by the deck's
theme: a person can select, move and restyle each one afterwards.

Text an LLM can write, and a slide a person can finish: pikslide is made
for drawing with an LLM, with you in the loop.

![pipeline.png: You prompt an LLM, which writes a .pik; pikslide renders it to a .pptx and, with --png, a .png. The LLM looks at the .png and fixes the .pik; you look at it too, and can prompt the LLM again, edit the .pik, or edit the .pptx in PowerPoint](https://raw.githubusercontent.com/mkyutani/pikslide/main/docs/examples/pipeline.png)

1. You prompt the LLM, and it writes a `.pik`.
2. pikslide renders the `.pik` to a `.pptx` and, with `--png`, to a
   `.png` as well.
3. The LLM looks at the `.png` and fixes its `.pik`: a label that
   overflows, an arrow that misses its target.
4. You look at it too, and step in where it's quickest: ask the LLM for a
   change, edit the `.pik` yourself, or edit the `.pptx` in PowerPoint.

The picture above is pikslide's own,
[docs/examples/pipeline.pik](https://github.com/mkyutani/pikslide/blob/main/docs/examples/pipeline.pik):

```pikslide
# Drawing a slide with an LLM and pikslide, with a person in the loop.
# One pass: the LLM writes a .pik, and pikslide renders it to a .pptx
# and, with --png, a .png. The LLM looks at the .png and fixes its .pik;
# you look at it too, and step in where you like: ask the LLM, edit the
# .pik, or edit the .pptx in PowerPoint.

boxwid = 1.2in
boxht = 0.55in
filewid = 0.8in
fileht = 0.55in

LLM: box "LLM"
arrow
Pik: file ".pik"
arrow
Pikslide: box "pikslide" bold fill accent1 lighter 60%
Png: file ".png" with .w at 0.8in right of Pikslide.e + (0, 0.5in)
Pptx: file ".pptx" with .w at 0.8in right of Pikslide.e - (0, 0.5in)
arrow from Pikslide.e right 0.4in then up until even with Png then to Png.w
"--png" small above at 1/2<(Pikslide.e.x + 0.4in, Png.y), Png.w>
arrow from Pikslide.e right 0.4in then down until even with Pptx then to Pptx.w

You: box "You" bold wid (Png.e.x - LLM.w.x) + 0.6in ht 0.45in fill bg1 darker 5% \
    with .nw at (LLM.w.x, Pptx.s.y - 0.6in)
arrow "prompt" ljust from (LLM.x, You.n.y) to LLM.s
arrow "edit" ljust from (Pik.x, You.n.y) to Pik.s
arrow "edit in PowerPoint" rjust from (Pptx.x, You.n.y) to Pptx.s
arrow from Png.e right 0.3in then down until even with You.n
"look" ljust at (Png.e.x + 0.3in, Pptx.y)

arrow from Png.n up 0.4in then left until even with LLM then to LLM.n
"look at the .png, fix the .pik" above at (Pikslide.x, Png.n.y + 0.4in)
```

[docs/examples/japan-capitals.md](https://github.com/mkyutani/pikslide/blob/main/docs/examples/japan-capitals.md)
is a slide Claude Code drew this way, in one run, with the prompt it was
given. [docs/](https://github.com/mkyutani/pikslide/tree/main/docs) has
more examples and a cookbook of diagram recipes.

## Install

pikslide needs Python 3.12+. Install it from PyPI as a standalone
`pikslide` command:

```sh
uv tool install pikslide
# or
pipx install pikslide
# or, into the current virtual environment
pip install pikslide
```

`pikslide --version` prints the version installed.

To work on pikslide itself, clone the repository and use
[uv](https://docs.astral.sh/uv/): `uv run pikslide ...` runs the clone with
no install step, and `uv tool install .` installs it as the `pikslide`
command.

## Usage

```sh
pikslide diagram.pik diagram.pptx                        # a one-slide deck, sized to the diagram
pikslide diagram.pik diagram.pptx --png                  # and diagram.png, drawn by PowerPoint
pikslide diagram.pik --template corporate.potx           # on the template's slide, in its theme
pikslide diagram.pik --check                             # lay it out and report errors, write nothing
```

`--png` (and `--pdf`) use PowerPoint itself, on Windows or from WSL with
a Windows install, and fall back to LibreOffice otherwise: good for a
quick look, but not for checking exact layout against PowerPoint.

`pikslide --help` lists every flag. The language reference is built in,
so neither you nor an LLM needs this repository to write a diagram:

- `pikslide --help intro`: the language in one page, the place to start
- `pikslide --help box`: a keyword's synopsis, attributes and defaults
- `pikslide --help colors`, `shapes`, `keywords`, …: the lists
- `pikslide --help template`: drawing on a template's slide
- `pikslide --help spec`, `grammar`: the full manuals,
  [spec.md](https://github.com/mkyutani/pikslide/blob/main/src/pikslide/docs/spec.md)
  and
  [grammar.md](https://github.com/mkyutani/pikslide/blob/main/src/pikslide/docs/grammar.md)

## Status

The language's v1 is implemented. Not in it yet: drawing into an existing
deck's slide, connectors, auto-layout, and multi-slide decks, among others
([spec.md §7](https://github.com/mkyutani/pikslide/blob/main/src/pikslide/docs/spec.md#7-not-in-v1)).

## Development

```sh
uv run pytest
```

The layout stage's simplifications are listed in the docstring of
`src/pikslide/pik/layout.py`.

## Acknowledgments

pikslide descends from Brian Kernighan's `pic` (1984), which placed named
objects one after another instead of at coordinates, and D. Richard Hipp's
[pikchr](https://pikchr.org/), which carried that idea into a modern
language emitting SVG. pikslide's tokenizer, grammar, macro expansion and
layout engine began as a port of pikchr's own, default sizes, placement
and edge geometry included, and its test fixtures under
`tests/fixtures/examples/` are pikchr's example diagrams. pikchr is
released under the Zero-Clause BSD license; see
[NOTICE](https://github.com/mkyutani/pikslide/blob/main/NOTICE).

## License

[0BSD](https://github.com/mkyutani/pikslide/blob/main/LICENSE)
