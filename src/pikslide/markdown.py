"""Extract pikchr source embedded in Markdown fenced code blocks.

Recognizes fences tagged ```pik``` or ```pikchr``` (either backtick or
tilde fences, per CommonMark), so pikslide can be pointed directly at a
``.md`` document that contains one or more pikchr diagrams.
"""

from __future__ import annotations

import re

_PIK_LANGS = {"pik", "pikchr"}

# A CommonMark-style fenced code block: an opening fence of 3+ backticks or
# tildes, an info string (the first word of which is the language tag), the
# body, and a closing fence identical to the opening one. This does not
# implement the CommonMark allowance for a closing fence *longer* than the
# opening one, which is rare in practice.
_FENCE_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>[A-Za-z0-9_+-]*)[^\n]*\n"
    r"(?P<body>.*?)"
    r"^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def extract_pik_blocks(text: str) -> list[str]:
    """Return the source text of every ```pik``` / ```pikchr``` fenced code
    block in ``text``, in document order."""
    return [
        m.group("body")
        for m in _FENCE_RE.finditer(text)
        if m.group("lang").lower() in _PIK_LANGS
    ]
