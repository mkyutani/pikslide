"""The notes for a GitHub release: the body of the message of the commit
its tag points at, the version bump's, which says what the release
brings, and where it is on PyPI.

    python3 scripts/release_notes.py v0.2.1

A release's notes break the line wherever the text does, so each
paragraph and list item, wrapped at 72 columns in the commit, is joined
into one line. A block indented as code is left as it is."""

from __future__ import annotations

import re
import subprocess
import sys

_ITEM = re.compile(r"(?:[-*]|\d+\.) ")


def unwrap(text: str) -> str:
    blocks = []
    for block in re.split(r"\n[ \t]*\n", text.strip()):
        lines = block.split("\n")
        if all(line.startswith("    ") for line in lines):
            blocks.append(block)
            continue
        joined: list[str] = []
        for line in lines:
            if joined and not _ITEM.match(line):
                joined[-1] += " " + line.strip()
            else:
                joined.append(line.rstrip())
        blocks.append("\n".join(joined))
    return "\n\n".join(blocks)


def notes(tag: str, body: str) -> str:
    version = tag.removeprefix("v")
    return f"{unwrap(body)}\n\nOn PyPI: https://pypi.org/project/pikslide/{version}/\n"


def main() -> None:
    tag = sys.argv[1]
    body = subprocess.run(["git", "log", "-1", "--format=%b", tag],
                          check=True, capture_output=True, text=True).stdout
    sys.stdout.write(notes(tag, body))


if __name__ == "__main__":
    main()
