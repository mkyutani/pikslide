"""pikslide-mcp's tools, called through the MCP SDK's own client,
connected in-process (issue #33)."""

from __future__ import annotations

import json
import pathlib
import tomllib

import anyio
import pytest
from mcp import Client

from pikslide_mcp import create_server


def call(root: pathlib.Path, tool: str, arguments: dict):
    async def go():
        async with Client(create_server(str(root))) as client:
            return await client.call_tool(tool, arguments)

    return anyio.run(go)


def test_the_tools_are_named_in_the_commands_words(tmp_path):
    async def go():
        async with Client(create_server(str(tmp_path))) as client:
            return [tool.name for tool in (await client.list_tools()).tools]

    assert anyio.run(go) == ["help", "check", "render"]


def test_help_is_the_commands(tmp_path):
    result = call(tmp_path, "help", {})
    assert result.content[0].text.startswith("PIKSLIDE ")  # topic llm
    assert call(tmp_path, "help", {"topic": "box"}).content[0].text.startswith("BOX — ")
    unknown = call(tmp_path, "help", {"topic": "nosuch"})
    assert unknown.is_error and "no help on 'nosuch'" in unknown.content[0].text


def test_check_gives_check_json_for_source_or_path(tmp_path):
    checked = json.loads(call(tmp_path, "check", {"source": 'A: box "Web"\n'}).content[0].text)
    assert checked["ok"] and [o["name"] for o in checked["objects"]] == ["A"]
    (tmp_path / "d.pik").write_text('B: box "API"\n', encoding="utf-8")
    checked = json.loads(call(tmp_path, "check", {"path": "d.pik"}).content[0].text)
    assert [o["name"] for o in checked["objects"]] == ["B"]
    broken = json.loads(call(tmp_path, "check", {"source": "box\nbox wid\n"}).content[0].text)
    assert not broken["ok"] and broken["errors"][0]["line"] == 2 and broken["errors"][0]["help"]


def test_render_writes_the_deck_and_returns_its_picture(tmp_path):
    (tmp_path / "out").mkdir()
    result = call(tmp_path, "render", {"out": "out/d.pptx", "source": 'box "Web"\narrow\nbox "API"\n',
                                       "renderer": "direct"})
    written = json.loads(result.content[0].text)
    assert written["wrote"] == [{"path": "out/d.pptx"}, {"path": "out/d.png", "drawn_by": "pikslide"}]
    assert any("no --template" in w["message"] for w in written["warnings"])
    assert result.content[1].type == "image" and result.content[1].mime_type == "image/png"
    assert (tmp_path / "out" / "d.pptx").exists() and (tmp_path / "out" / "d.png").exists()


@pytest.mark.parametrize("arguments, message", [
    ({"out": "../d.pptx", "source": "box\n"}, "outside the workspace"),
    ({"out": "d.pptx", "path": "../d.pik"}, "outside the workspace"),
    ({"out": "d.pptx", "source": "box\n", "path": "d.pik"}, "one of them"),
    ({"out": "d.pptx", "path": "missing.pik"}, "could not read missing.pik"),
    ({"out": "d.svg", "source": "box\n"}, "out is a .pptx"),
])
def test_render_refuses_what_it_cant_do_and_says_why(tmp_path, arguments, message):
    result = call(tmp_path, "render", arguments)
    assert result.is_error and message in result.content[0].text
    assert not list(tmp_path.parent.glob("d.pptx"))


def test_it_speaks_over_stdio_with_nothing_else_on_stdout(tmp_path):
    # As a host starts it: its stdout is the protocol's alone.
    import sys

    from mcp.client.stdio import StdioServerParameters

    server = StdioServerParameters(command=sys.executable, args=[
        "-c", "import pikslide_mcp; pikslide_mcp.main()", "--root", str(tmp_path)])

    async def go():
        async with Client(server) as client:
            return await client.call_tool("render", {"out": "d.pptx", "source": "box\n", "renderer": "direct"})

    result = anyio.run(go)
    assert json.loads(result.content[0].text)["ok"] and (tmp_path / "d.png").exists()


def test_its_version_is_pikslides_which_it_pins():
    here = pathlib.Path(__file__).resolve().parents[1]
    mcp_project = tomllib.loads((here / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pikslide_project = tomllib.loads((here.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert mcp_project["version"] == pikslide_project["version"]
    assert f"pikslide=={pikslide_project['version']}" in mcp_project["dependencies"]
