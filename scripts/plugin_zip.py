"""Zip the plugin, with pikslide's wheel in its skill (issue #33 §3).

    python scripts/plugin_zip.py DIST OUT

The plugin is plugins/pikslide, at the zip's root, plus
skills/pikslide/wheels/ with the wheel `uv build` wrote to DIST for
pyproject.toml's version: in a sandbox, the skill installs pikslide
from it, needing no network. It writes OUT/pikslide-plugin-X.Y.Z.zip
and prints its path. The release workflow attaches it to the GitHub
release; the tree in git has no wheel.
"""

from __future__ import annotations

import pathlib
import sys
import tomllib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "pikslide"
WHEELS = "skills/pikslide/wheels"


def plugin_zip(dist: pathlib.Path, out: pathlib.Path, root: pathlib.Path = ROOT) -> pathlib.Path:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    wheel = dist / f"pikslide-{version}-py3-none-any.whl"
    if not wheel.is_file():
        raise SystemExit(f"plugin_zip: no {wheel}: run `uv build` first")
    plugin = root / "plugins" / "pikslide"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"pikslide-plugin-{version}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(plugin.rglob("*")):
            relative = file.relative_to(plugin).as_posix()
            if file.is_file() and "__pycache__" not in relative and not relative.startswith(WHEELS + "/"):
                z.write(file, relative)
        z.write(wheel, f"{WHEELS}/{wheel.name}")
    return path


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(plugin_zip(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])))
