# pikslide docs

The manuals:

- [spec.md](../src/pikslide/docs/spec.md): the language specification
- [grammar.md](../src/pikslide/docs/grammar.md): the grammar, in BNF

Writing a diagram takes neither: `pikslide --help` lists the help topics
built in, and `pikslide --help llm` is all of it in one text, for an LLM.

This directory holds what only the repository has: diagrams, with the
pictures they render to.

- [tutorial/](tutorial/): one diagram drawn in six steps, an idea at a
  time, each with its picture: the place to start
- [examples/](examples/): example diagrams, each `.pik` with the `.pptx`
  and `.png` it renders to (`pikslide x.pik x.pptx --png`)
  ([japan-capitals.md](examples/japan-capitals.md) is one drawn by
  Claude Code, with the prompt it was given)
- [shapes.md](shapes.md): every preset shape `shape NAME` draws, as a
  picture. Written by `scripts/gen_shape_gallery.py` (`--png` to render
  the pictures, with PowerPoint)
- [cookbook/](cookbook/): one recipe per kind of diagram, to copy and
  adapt: its source, its picture, and how it's drawn

Every `.pik` here, and every ` ```pikslide ` block in this directory's
Markdown and in the top-level README, must parse and lay out
(`tests/test_docs.py`).
