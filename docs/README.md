# pikslide docs

The manuals:

- [spec.md](../src/pikslide/docs/spec.md): the language specification
- [grammar.md](../src/pikslide/docs/grammar.md): the grammar, in BNF

Writing a diagram takes neither: `pikslide --help` lists the help topics
built in, and `pikslide --help llm` is all of it in one text, for an LLM.
`pikslide --help recipes` lists a recipe for each kind of diagram: a
flowchart, a system architecture, a data flow diagram.

This directory holds what only the repository has: diagrams, with the
pictures they render to.

- [tutorial/](tutorial/): one diagram drawn in six steps, an idea at a
  time, each with its picture: the place to start
- [examples/](examples/): example diagrams, each `.pik` with the `.pptx`
  and `.png` it renders to (`pikslide x.pik x.pptx --png`). Four were
  drawn by Claude Code, each from one prompt, shown with it:
  [an expense claim's approval](examples/expense-approval.md),
  [a product launch](examples/product-launch.md),
  [an outage's response](examples/incident-response.md) and
  [the citric acid cycle](examples/citric-acid-cycle.md)
- [figures.md](figures.md): the macros pikslide ships for diagrams whose
  shape is the point (`include "figures.pik"`), each with a picture.
  Written by `scripts/gen_figure_gallery.py` (`--png` to render the
  pictures, with PowerPoint)
- [dfd.md](dfd.md): the macros pikslide ships for a data flow diagram's
  parts (`include "dfd.pik"`), and a whole DFD in each notation,
  DeMarco/Yourdon and Gane-Sarson, each with a picture. Written by
  `scripts/gen_dfd_gallery.py` (`--png` to render the pictures, with
  PowerPoint)
- [shapes.md](shapes.md): every preset shape `shape NAME` draws, as a
  picture. Written by `scripts/gen_shape_gallery.py` (`--png` to render
  the pictures, with PowerPoint)

Every `.pik` here, and every ` ```pikslide ` block in this directory's
Markdown and in the top-level README, must parse and lay out
(`tests/test_docs.py`).
