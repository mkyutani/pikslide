"""The plugin in plugins/pikslide, for Claude and OpenAI hosts, and this
repository as a Claude plugin marketplace (issue #33 §3)."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import shutil
import tomllib
import zipfile

import pytest

from pikslide import _parser

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "pikslide"
SKILL = PLUGIN / "skills" / "pikslide" / "SKILL.md"


def script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def load(name: str) -> dict:
    return json.loads((PLUGIN / name).read_text(encoding="utf-8"))


def frontmatter() -> dict[str, str]:
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    head = text[4:text.index("\n---\n")]
    return dict(line.split(": ", 1) for line in head.splitlines())


def test_its_versions_are_pikslides():
    # A release's tag checks pikslide's version, so the plugin's follow it:
    # scripts/bump_version.py sets them all.
    v = version()
    assert load(".claude-plugin/plugin.json")["version"] == v
    assert load("plugin.json")["version"] == v
    assert load(".mcp.json")["mcpServers"]["pikslide"]["args"][0] == f"pikslide-mcp@{v}"
    assert load("mcp.json")["mcpServers"]["pikslide"]["args"][0] == f"pikslide-mcp@{v}"


def test_its_manifests_say_the_same():
    claude, portable = load(".claude-plugin/plugin.json"), load("plugin.json")
    assert portable.pop("$schema") == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert claude == portable
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert claude["license"] == project["license"]


def test_its_mcp_servers_run_pikslide_mcp_in_the_workspace():
    claude = load(".mcp.json")["mcpServers"]["pikslide"]
    assert claude["command"] == "uvx" and claude["args"][1:] == ["--root", "${CLAUDE_PROJECT_DIR}"]
    portable = load("mcp.json")
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    assert portable["mcpServers"]["pikslide"]["type"] == "stdio"
    assert portable["mcpServers"]["pikslide"]["command"] == "uvx"


def test_this_repository_is_a_marketplace_of_it():
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    [entry] = marketplace["plugins"]
    assert entry["name"] == load(".claude-plugin/plugin.json")["name"]
    assert (ROOT / entry["source"]).resolve() == PLUGIN


def test_the_skill_keeps_to_the_agent_skills_fields():
    # claude.ai and OpenAI refuse a skill with other fields.
    fields = frontmatter()
    assert set(fields) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    assert fields["name"] == SKILL.parent.name and re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"])
    assert 0 < len(fields["description"]) <= 1024
    assert all(": " not in value and not value.startswith(("'", '"', "[", "{")) for value in fields.values())


def test_the_flags_the_skill_names_are_the_commands():
    flags = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", SKILL.read_text(encoding="utf-8")))
    known = {option for action in _parser()._actions for option in action.option_strings}
    assert flags and flags <= known


def test_plugin_zip_holds_the_plugin_and_the_wheel(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / f"pikslide-{version()}-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    path = script("plugin_zip").plugin_zip(dist, tmp_path / "out")
    assert path.name == f"pikslide-plugin-{version()}.zip"
    names = zipfile.ZipFile(path).namelist()
    assert {".claude-plugin/plugin.json", ".mcp.json", "plugin.json", "mcp.json",
            "skills/pikslide/SKILL.md", f"skills/pikslide/wheels/{wheel.name}"} == set(names)


def test_plugin_zip_wants_the_wheel(tmp_path):
    with pytest.raises(SystemExit, match="run `uv build` first"):
        script("plugin_zip").plugin_zip(tmp_path, tmp_path / "out")


def test_bump_version_sets_every_version(tmp_path):
    for name in script("bump_version").FILES:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, tmp_path / name)
    script("bump_version").bump("9.8.7", tmp_path)
    for name in script("bump_version").FILES:
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert version() not in text and "9.8.7" in text, name
    with pytest.raises(SystemExit, match="isn't X.Y.Z"):
        script("bump_version").bump("v1", tmp_path)
