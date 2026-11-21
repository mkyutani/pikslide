"""Set the version pikslide, pikslide-mcp and the plugin share.

    python scripts/bump_version.py X.Y.Z

It writes X.Y.Z as pikslide's and pikslide-mcp's versions, pikslide-mcp's
pin on pikslide, both plugin manifests' versions and both MCP configs'
`pikslide-mcp@` pins; then run `uv lock`. tests/test_plugin.py fails
where any of them differs.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Each file, and the patterns whose one group is the version.
FILES = {
    "pyproject.toml": [r'(?m)^version = "([^"]+)"'],
    "pikslide-mcp/pyproject.toml": [r'(?m)^version = "([^"]+)"', r'"pikslide==([^"]+)"'],
    "plugins/pikslide/.claude-plugin/plugin.json": [r'"version": "([^"]+)"'],
    "plugins/pikslide/plugin.json": [r'"version": "([^"]+)"'],
    "plugins/pikslide/.mcp.json": [r'"pikslide-mcp@([^"]+)"'],
    "plugins/pikslide/mcp.json": [r'"pikslide-mcp@([^"]+)"'],
}


def bump(version: str, root: pathlib.Path = ROOT) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"bump_version: {version!r} isn't X.Y.Z")
    for name, patterns in FILES.items():
        path = root / name
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            found = list(re.finditer(pattern, text))
            if len(found) != 1:
                raise SystemExit(f"bump_version: {name}: {len(found)} matches of {pattern}, not 1")
            start, end = found[0].span(1)
            text = text[:start] + version + text[end:]
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    bump(sys.argv[1])
