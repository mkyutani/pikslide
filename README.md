# pikslide

pikslide draws a diagram written as text into a PowerPoint slide.

The text, a `.pik` file, places shapes one after another and refers to
them by name, with no coordinates to work out. The slide it becomes is
made of **native, editable PowerPoint shapes**, colored by the deck's
theme: a person can select, move and restyle each one afterwards.

Text an LLM can write, and a slide a person can finish: pikslide is made
for drawing with an LLM, with you in the loop.

![pipeline.png: You prompt an LLM, which writes a .pik; pikslide renders it to a .pptx and, with --png, a .png. You can also edit the .pik in a text editor, or edit the .pptx in PowerPoint and ask the LLM to apply your edits to the .pik. The LLM, dashed, is optional](https://raw.githubusercontent.com/mkyutani/pikslide/main/docs/examples/pipeline.png)

1. You prompt the LLM, and it writes a `.pik`.
2. pikslide renders the `.pik` to a `.pptx` and, with `--png`, to a
   `.png` as well.
3. You edit the `.pptx` in PowerPoint and hand it back to the LLM with
   your next prompt. The LLM carries your edits into the `.pik`, so the
   next render keeps them: each shape in the `.pptx` is named after its
   label in the `.pik`, so the two match up.
4. Or skip PowerPoint: tell the LLM what to change, or edit the `.pik`
   yourself.

The picture above is pikslide's own,
[docs/examples/pipeline.pik](https://github.com/mkyutani/pikslide/blob/main/docs/examples/pipeline.pik):

```pikslide
# Drawing a slide with an LLM and pikslide, with a person in the loop.
# The LLM writes a .pik, and pikslide renders it to a .pptx and, with
# --png, a .png. You step in where you like: prompt the LLM, edit the
# .pik in a text editor, or edit the .pptx in PowerPoint and ask the LLM
# to apply your edits to the .pik. The LLM is optional, so it and its
# arrows are dashed: you can write the .pik yourself. What pikslide does,
# from the .pik to the files it writes, is drawn twice as thick.

boxwid = 1.2in
boxht = 0.55in

# A file: PowerPoint's flowchart document, a page with a wavy bottom.
# The middle of the wave is a fifteenth of its height above the bottom
# of its box, where .s is: a line up to a file ends there.
define doc { shape flowChartDocument $1 bold wid 0.8in ht 0.55in fill accent2 lighter 60% }

LLM: box "LLM" bold rad 0.1in fill accent1 lighter 60% stroke dashed
arrow 1.5in stroke dashed
Pik: doc(".pik")
arrow stroke thickness 200%
Pikslide: box "pikslide" bold color bg1 rad 0.1in fill accent1
Png: doc(".png") with .w at 0.8in right of Pikslide.e + (0, 0.5in)
Pptx: doc(".pptx") with .w at 0.8in right of Pikslide.e - (0, 0.5in)
arrow from Pikslide.e right 0.4in then up until even with Png then to Png.w stroke thickness 200%
"--png" small above at 1/2<(Pikslide.e.x + 0.4in, Png.y), Png.w>
arrow from Pikslide.e right 0.4in then down until even with Pptx then to Pptx.w stroke thickness 200%

You: box "You" bold wid (Pptx.e.x - LLM.w.x) ht 0.45in fill bg1 darker 5% \
    with .nw at (LLM.w.x, Pptx.s.y - 0.6in)
arrow "prompt" "e.g. “draw how Japan's capital moved”" small "or “apply my edits in the .pptx to the .pik”" small ljust stroke dashed from (LLM.x, You.n.y) to LLM.s
wave = Pik.ht / 15
arrow "edit in a text editor" ljust from (Pik.x, You.n.y) to Pik.s + (0, wave)
arrow "edit in PowerPoint" rjust from (Pptx.x, You.n.y) to Pptx.s + (0, wave)
```

[docs/examples/japan-capitals.md](https://github.com/mkyutani/pikslide/blob/main/docs/examples/japan-capitals.md)
is a slide Claude Code drew this way, in one run, with the prompt it was
given. [docs/](https://github.com/mkyutani/pikslide/tree/main/docs) has
a [tutorial](https://github.com/mkyutani/pikslide/tree/main/docs/tutorial),
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
pikslide diagram.pik --check                             # lay it out, write nothing: errors, warnings and where each object went, as JSON
```

`--png` (and `--pdf`) use PowerPoint itself, on Windows or from WSL with
a Windows install, and fall back to LibreOffice otherwise: good for a
quick look, but not for checking exact layout against PowerPoint.

A tool that assembles a deck with python-pptx can instead draw a diagram
onto a slide of its own, with `pikslide.parse()`, `pikslide.layout()` and
`pikslide.render_into()`: see
[spec.md §6](https://github.com/mkyutani/pikslide/blob/main/src/pikslide/docs/spec.md#6-use-from-other-tools).

`pikslide --help` lists every flag. The language reference is built in,
so neither you nor an LLM needs this repository to write a diagram:

- `pikslide --help intro`: the language in one page, the place to start
- `pikslide --help box`: a keyword's synopsis, attributes and defaults
- `pikslide --help colors`, `shapes`, `keywords`, …: the lists
- `pikslide --help template`: drawing on a template's slide
- `pikslide --help llm`: the reference in one text, for an LLM to read
  once: short enough to come back whole from one command, and the same
  bytes from the same version, so a prompt that holds it can be cached

The full manuals, the language's design and its grammar, are in this
repository:
[spec.md](https://github.com/mkyutani/pikslide/blob/main/src/pikslide/docs/spec.md)
and
[grammar.md](https://github.com/mkyutani/pikslide/blob/main/src/pikslide/docs/grammar.md).

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
