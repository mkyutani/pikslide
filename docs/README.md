# pikslide docs

The manuals ship inside the package, so an installed pikslide can show
them (`pikslide --help grammar`, `pikslide --help spec`):

- [spec.md](../src/pikslide/docs/spec.md): the language specification
- [grammar.md](../src/pikslide/docs/grammar.md): the grammar, in BNF

`pikslide --help` lists every help topic.

This directory holds what only the repository has: diagrams, with the
pictures they render to.

- [examples/](examples/): example diagrams, each `.pik` with the `.pptx`
  and `.png` it renders to (`pikslide x.pik x.pptx --png`)
- [shapes.md](shapes.md): every preset shape `shape NAME` draws, as a
  picture. Written by `scripts/gen_shape_gallery.py` (`--png` to render
  the pictures, with PowerPoint)
- [cookbook/](cookbook/): one recipe per kind of diagram, to copy and
  adapt: its source, its picture, and how it's drawn

Every `.pik` here, and every ` ```pikslide ` block in this directory's
Markdown and in the top-level README, must parse and lay out
(`tests/test_docs.py`).
