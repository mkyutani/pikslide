# Cookbook

One recipe per kind of diagram: the `.pik` source, the PNG it renders
to, and notes on how it's drawn, to copy and adapt.

- [Data flow diagrams (DFD)](dfd.md)

A recipe is `NAME.md` beside `NAME.pik` and `NAME.png`. The Markdown shows
the `.pik` file in a ` ```pikslide ` block, which `tests/test_docs.py`
checks is the file as it is. To render the PNG, with PowerPoint:

```sh
uv run pikslide docs/cookbook/NAME.pik /tmp/NAME.pptx --png docs/cookbook/NAME.png --renderer powerpoint
```
