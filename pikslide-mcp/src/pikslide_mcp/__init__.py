"""pikslide as an MCP server (issue #33): an LLM host that gives the LLM
no shell, or would rather call tools, draws with pikslide through it.

    uvx pikslide-mcp [--root DIR] [--font SOURCE ...]

Its tools, named in the command's words (a host puts the server's name
in front: mcp__pikslide__render):

- help(topic="llm"): `pikslide --help TOPIC`.
- check(source or path, template, layout): `pikslide --check`'s JSON.
- render(out, source or path, template, layout, renderer): the deck
  written to `out`, a .pptx, and a PNG of it beside it; what was
  written, the warnings, what drew the picture, and the picture itself,
  for the LLM to look at.

Paths are relative to the workspace, `--root`, else the directory the
server was started in, and nothing is read or written outside it. A
`source`'s includes and images are found there too.

A host's MCP roots aren't asked for: the roots capability is deprecated
as of the 2026-07-28 protocol, and a local host starts its server in the
project's directory anyway.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from importlib.metadata import version

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pikslide.api import BuildError, build
from pikslide.fonts import FontInstallError, install_fonts
from pikslide.help import _Style
from pikslide.help import render as render_help

INSTRUCTIONS = (
    "pikslide draws a diagram, written as text in its language, into a PowerPoint slide of native, editable "
    "shapes. Read help() (topic llm) once: it is all it takes to write one. check() lays a diagram out, with "
    "its warnings and where each object went; render() writes the deck and returns a picture of it to look at."
)

# PowerPoint renders one deck at a time.
_RENDERING = threading.Lock()


class Workspace:
    """The directory the tools' paths are relative to, which nothing is
    read from or written to outside of."""

    def __init__(self, root: str):
        self.root = os.path.realpath(root)

    def path(self, relative: str) -> str:
        """`relative` as an absolute path in the workspace; a ToolError if it
        leads out of it."""
        path = os.path.realpath(os.path.join(self.root, relative))
        if os.path.commonpath([path, self.root]) != self.root:
            raise ToolError(f"{relative} is outside the workspace, {self.root}")
        return path

    def relative(self, path: str) -> str:
        return os.path.relpath(path, self.root)


def create_server(root: str = ".") -> MCPServer:
    """The server, its paths relative to `root`."""
    workspace = Workspace(root)
    server = MCPServer(name="pikslide", instructions=INSTRUCTIONS, version=version("pikslide-mcp"))

    def source_of(source: str | None, path: str | None) -> tuple[str, str, str]:
        """The diagram's text, the name its errors give it, and the directory
        its includes and images are found from."""
        if (source is None) == (path is None):
            raise ToolError("give the diagram as source (its text) or as path (a .pik in the workspace), one of them")
        if source is not None:
            return source, "<source>", workspace.root
        full = workspace.path(path)
        try:
            with open(full, encoding="utf-8") as f:
                return f.read(), path, os.path.dirname(full)
        except OSError as e:
            raise ToolError(f"could not read {path}: {e.strerror}") from None

    def warnings_of(built) -> list[dict]:
        return [{"message": w.message, "objects": list(w.objects)} for w in built.warnings]

    @server.tool(name="help")
    def help_(topic: str = "llm") -> str:
        """`pikslide --help TOPIC`. Topic llm is all it takes to write a diagram, in one text: read it first.
        Otherwise a keyword (box, arrow, fill, ...), a list (keywords, shapes, colors, variables), a preset
        shape's name, or template (drawing on a template's slide)."""
        text = render_help(topic, _Style(tty=False))
        if text is None:
            raise ToolError(f"no help on {topic!r}: try llm, keywords, shapes, colors or template")
        return text

    @server.tool()
    def check(source: str | None = None, path: str | None = None, template: str | None = None,
              layout: str | None = None) -> str:
        """`pikslide --check`: lay the diagram out, writing nothing, and give its errors, its warnings (each
        with the objects it names), the slide and where each object went (inches, y up). The diagram is
        `source`, its text, or `path`, a .pik in the workspace; `template`, a .pptx or .potx in the
        workspace, and `layout`, a slide layout of it, as --template and --layout."""
        text, input_path, base_dir = source_of(source, path)
        try:
            built = build(text, input_path, base_dir=base_dir, template=template and workspace.path(template),
                          layout_name=layout, check=True)
        except BuildError as e:
            return _json({"ok": False, "errors": [e.to_dict()]})
        return _json({"ok": True, "errors": [], "warnings": warnings_of(built), **built.check})

    @server.tool()
    def render(out: str, source: str | None = None, path: str | None = None, template: str | None = None,
               layout: str | None = None, renderer: str = "auto") -> list:
        """Write the diagram's deck to `out`, a .pptx in the workspace, and a PNG of it beside it (`out` with
        .png), and return what was written, the warnings (each with the objects it names), what drew the
        picture, and the picture, to look at. The diagram is `source`, its text, or `path`, a .pik in the
        workspace; `template` and `layout` as for check(). `renderer` as --renderer: auto (PowerPoint if
        reachable, else pikslide itself), powerpoint, direct or libreoffice. A picture pikslide drew never
        shows text overflowing: the warnings say where it does."""
        text, input_path, base_dir = source_of(source, path)
        deck = workspace.path(out)
        if not deck.endswith(".pptx"):
            raise ToolError(f"out is a .pptx, not {out}")
        picture = deck[: -len(".pptx")] + ".png"
        try:
            with _RENDERING:
                built = build(text, input_path, base_dir=base_dir, output=deck, png=picture,
                              template=template and workspace.path(template), layout_name=layout, renderer=renderer)
        except BuildError as e:
            return [_json({"ok": False, "errors": [e.to_dict()]})]
        result = {
            "ok": True,
            "wrote": [{"path": workspace.relative(p), **({"drawn_by": d} if d else {})} for p, d in built.written],
            "warnings": warnings_of(built),
            "notes": built.notes,
        }
        return [_json(result), Image(path=picture)]

    return server


def _json(value) -> str:
    """`value` as JSON, compact: what an LLM reads, not a person."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser(prog="pikslide-mcp", description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('pikslide-mcp')}")
    parser.add_argument("--root", metavar="DIR", default=".",
                        help="the workspace the tools' paths are relative to (default: the current directory)")
    parser.add_argument("--font", metavar="SOURCE", action="append", default=[],
                        help="install fonts from SOURCE, a font file, a directory or zip of them, or a URL, when "
                        "the server starts, for `fit` and the pictures (pikslide --install-font); repeatable")
    args = parser.parse_args()
    for source in args.font:
        # stdout is the protocol's: anything to say goes to stderr.
        try:
            for font_path, families, already in install_fonts(source):
                state = "already installed" if already else "installed"
                print(f"pikslide-mcp: {state} {font_path}: {' / '.join(families)}", file=sys.stderr)
        except FontInstallError as e:
            print(f"pikslide-mcp: could not install {source}: {e}", file=sys.stderr)
    create_server(args.root).run("stdio")
