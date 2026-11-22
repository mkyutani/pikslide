"""The paths a diagram names, `include "PATH"` and `image "PATH"`, kept in
their directory the same way on every platform (docs/spec.md SS3.5,
SS3.6): a diagram may be written by an LLM, and must not reach, or reveal
the existence of, arbitrary local files. pikslide-mcp keeps its tools'
paths in its workspace with within() too."""

from __future__ import annotations

import ntpath
import os


def is_absolute(path: str) -> bool:
    """Whether `path` leads from somewhere of its own rather than from the
    directory it is found from, whatever the platform (issue #50): one
    with a drive, `C:\\x` or `D:x` (relative to D:'s own current
    directory, which os.path.isabs() doesn't call absolute), one from a
    root, `/x` or `\\x` (on Windows the current drive's, which
    os.path.isabs() doesn't call absolute either, since Python 3.13), or
    a UNC path, and one from a home directory, `~`."""
    return os.path.isabs(path) or path.startswith(("/", "\\", "~")) or bool(ntpath.splitdrive(path)[0])


def within(base: str, path: str) -> bool:
    """Whether `path` is `base` or under it, both absolute and resolved
    (os.path.realpath()). One on another drive isn't, on Windows, where
    os.path.commonpath() raises ValueError for it (issue #50)."""
    try:
        return os.path.commonpath([base, path]) == base
    except ValueError:
        return False
