# pikslide-mcp

An MCP server for [pikslide](https://github.com/mkyutani/pikslide): an
LLM host draws diagrams, written in pikslide's language, as native,
editable PowerPoint slides.

```sh
uvx pikslide-mcp [--root DIR] [--font SOURCE ...]
```

Its tools: `help` (`pikslide --help TOPIC`; `llm` is all it takes to
write a diagram), `check` (`pikslide --check`'s JSON) and `render` (the
deck, and a picture of it to look at). Paths are relative to `--root`,
else the directory it was started in, and nothing is written outside
it. `--font` installs fonts when it starts (`pikslide --install-font`).

Its version is pikslide's, which it pins.
