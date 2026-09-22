"""Extract pikchr/pikslide source embedded in Markdown fenced code blocks.

Recognizes fences tagged ```pik```, ```pikchr```, or ```pikslide``` (either
backtick or tilde fences, per CommonMark), so pikslide can be pointed
directly at a ``.md`` document that contains one or more diagrams.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PIK_LANGS = {"pik", "pikchr", "pikslide"}

# A CommonMark-style fenced code block: an opening fence of 3+ backticks or
# tildes, an info string (the first word of which is the language tag,
# optionally followed by a diagram name -- docs/spec.md SS6), the body, and
# a closing fence identical to the opening one. This does not implement the
# CommonMark allowance for a closing fence *longer* than the opening one,
# which is rare in practice.
_FENCE_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>[A-Za-z0-9_+-]*)"
    r"(?:[ \t]+(?P<name>[A-Za-z0-9_-]+))?[^\n]*\n"
    r"(?P<body>.*?)"
    r"^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


class MarkdownDiagramError(Exception):
    """A Markdown file's fenced diagrams don't follow the naming rules
    (docs/spec.md SS6): more than one block with no name, or two blocks
    sharing a name."""


@dataclass
class PikBlock:
    """One fenced diagram extracted from a Markdown file: `name` is the
    word after the language tag (``` ```pikslide architecture ```)``,
    ``None`` if the fence gave none -- allowed only when the file has a
    single diagram (docs/spec.md SS6). `name` is also the diagram's id
    (SS4.2) and what ``--block`` selects."""

    name: str | None
    text: str


def extract_pik_blocks(markdown_text: str) -> list[PikBlock]:
    """Return every ```pik```/```pikchr```/```pikslide``` fenced code
    block in ``markdown_text``, in document order. Raises
    :class:`MarkdownDiagramError` if the file has more than one diagram
    and any is unnamed, or two share a name."""
    blocks = [
        PikBlock(m.group("name"), m.group("body"))
        for m in _FENCE_RE.finditer(markdown_text)
        if m.group("lang").lower() in _PIK_LANGS
    ]
    if len(blocks) > 1:
        _require_unique_names(blocks)
    return blocks


def _require_unique_names(blocks: list[PikBlock]) -> None:
    unnamed = [i for i, b in enumerate(blocks, start=1) if b.name is None]
    if unnamed:
        raise MarkdownDiagramError(
            f"{len(blocks)} diagrams found, but block {unnamed[0]} has no name -- "
            'a file with more than one diagram must name every one, e.g. "```pikslide name"'
        )
    seen: dict[str, int] = {}
    for i, b in enumerate(blocks, start=1):
        if b.name in seen:
            raise MarkdownDiagramError(
                f"diagram name {b.name!r} is used by both block {seen[b.name]} and block {i}"
            )
        seen[b.name] = i
