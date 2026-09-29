"""Find the font files a deck's text will actually be drawn with, so `fit`
can measure with them (docs/spec.md SS3.3).

A family name -- a theme's `<a:latin typeface="Calibri"/>`, or the
`typeface` variable, which may be a localized name like "BIZ UDPゴシック" --
is looked up in the fonts installed on this machine, read from each font
file's own `name` table (every language's family names, so a Japanese
name finds its file too). On WSL the Windows fonts are searched as well,
since those are the ones PowerPoint draws with.
"""

from __future__ import annotations

import glob
import json
import os
import struct
import unicodedata
from dataclasses import dataclass

from lxml import etree

_FONT_EXTENSIONS = (".ttf", ".ttc", ".otf", ".otc")


def _font_dirs() -> list[str]:
    home = os.path.expanduser("~")
    dirs = [
        # Windows (native, then under WSL)
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
        "/mnt/c/Windows/Fonts",
        *glob.glob("/mnt/c/Users/*/AppData/Local/Microsoft/Windows/Fonts"),
        # macOS
        "/System/Library/Fonts",
        "/Library/Fonts",
        os.path.join(home, "Library", "Fonts"),
        # Linux
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.join(home, ".local", "share", "fonts"),
        os.path.join(home, ".fonts"),
    ]
    return [d for d in dict.fromkeys(dirs) if d and os.path.isdir(d)]


@dataclass(frozen=True)
class FontFace:
    path: str
    index: int  # within a .ttc/.otc collection; 0 for a single font
    bold: bool
    italic: bool


def _normalize(name: str) -> str:
    # NFKC folds full-width letters ("ＭＳ Ｐゴシック") to their plain forms.
    return unicodedata.normalize("NFKC", name).casefold().strip()


def _decode_name(platform_id: int, encoding_id: int, raw: bytes) -> str | None:
    if platform_id in (0, 3):
        return raw.decode("utf-16-be", errors="replace")
    if platform_id == 1 and encoding_id == 0:
        return raw.decode("mac_roman", errors="replace")
    return None


def _read_face(f, offset: int) -> tuple[list[str], bool, bool] | None:
    """One font's family names (name ID 1, every language) and whether it
    is bold/italic (OS/2 fsSelection, else head macStyle), from the table
    directory at `offset` of the open file `f`. Reads only what it needs:
    fonts can be large, and slow to read whole (over WSL's /mnt/c)."""

    def read(at: int, size: int) -> bytes:
        f.seek(at)
        data = f.read(size)
        if len(data) < size:
            raise struct.error("truncated font file")
        return data

    num_tables = struct.unpack(">H", read(offset + 4, 2))[0]
    directory = read(offset + 12, 16 * num_tables)
    tables = {}
    for i in range(num_tables):
        tag, _checksum, t_offset, t_length = struct.unpack_from(">4sIII", directory, 16 * i)
        tables[tag] = (t_offset, t_length)
    if b"name" not in tables:
        return None
    name_offset, name_length = tables[b"name"]
    name = read(name_offset, name_length)
    _fmt, count, string_offset = struct.unpack_from(">HHH", name, 0)
    families = set()
    for i in range(count):
        platform_id, encoding_id, _lang, name_id, length, str_offset = struct.unpack_from(">HHHHHH", name, 6 + 12 * i)
        if name_id != 1:
            continue
        start = string_offset + str_offset
        decoded = _decode_name(platform_id, encoding_id, name[start : start + length])
        if decoded:
            families.add(_normalize(decoded))
    bold = italic = False
    if b"OS/2" in tables:
        fs_selection = struct.unpack(">H", read(tables[b"OS/2"][0] + 62, 2))[0]
        bold, italic = bool(fs_selection & 0x20), bool(fs_selection & 0x01)
    elif b"head" in tables:
        mac_style = struct.unpack(">H", read(tables[b"head"][0] + 44, 2))[0]
        bold, italic = bool(mac_style & 0x01), bool(mac_style & 0x02)
    return sorted(families), bold, italic


def _read_font_file(path: str) -> list[tuple[int, list[str], bool, bool]]:
    try:
        with open(path, "rb") as f:
            header = f.read(12)
            if header[:4] == b"ttcf":
                num_fonts = struct.unpack_from(">I", header, 8)[0]
                offsets = struct.unpack(f">{num_fonts}I", f.read(4 * num_fonts))
            else:
                offsets = (0,)
            out = []
            for index, offset in enumerate(offsets):
                face = _read_face(f, offset)
                if face is not None:
                    out.append((index, *face))
            return out
    except (OSError, struct.error):
        return []


def _cache_path() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "pikslide", "fonts.json")


class FontIndex:
    """Every installed font face, by normalized family name. Built on
    first lookup, since it reads every font file's name table."""

    def __init__(self, dirs: list[str] | None = None):
        self._dirs = dirs
        self._faces: dict[str, list[FontFace]] | None = None

    def _build(self) -> dict[str, list[FontFace]]:
        """Reads each font file's names once, then keeps them in a cache
        file (`_cache_path()`), by directory: a directory whose
        modification time is unchanged -- no font added or removed -- is
        not read again at all, since even listing and stat()ing every
        file is slow over WSL's /mnt/c."""
        cache_path = _cache_path() if self._dirs is None else None
        cached: dict = {}
        if cache_path is not None:
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
            except (OSError, ValueError):
                cached = {}
        dirs = {}
        for font_dir in self._dirs if self._dirs is not None else _font_dirs():
            for root, _subdirs, files in os.walk(font_dir):
                try:
                    stamp = os.stat(root).st_mtime_ns
                except OSError:
                    continue
                entry = cached.get(root)
                if entry is None or entry["stamp"] != stamp:
                    fonts = {}
                    for file in sorted(files):
                        if file.lower().endswith(_FONT_EXTENSIONS):
                            path = os.path.join(root, file)
                            fonts[path] = _read_font_file(path)
                    entry = {"stamp": stamp, "fonts": fonts}
                dirs[root] = entry
        if cache_path is not None and dirs != cached:
            try:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(dirs, f, ensure_ascii=False)
            except OSError:
                pass
        faces: dict[str, list[FontFace]] = {}
        for entry in dirs.values():
            for path, file_faces in entry["fonts"].items():
                for index, families, bold, italic in file_faces:
                    for family in families:
                        faces.setdefault(family, []).append(FontFace(path, index, bold, italic))
        return faces

    def find(self, family: str, bold: bool = False, italic: bool = False) -> FontFace | None:
        """The face of `family` closest to the style asked for: an exact
        bold/italic match first, then one that at least matches bold."""
        if self._faces is None:
            self._faces = self._build()
        candidates = self._faces.get(_normalize(family))
        if not candidates:
            return None

        def score(face: FontFace) -> int:
            return 2 * (face.bold == bold) + (face.italic == italic)

        return max(candidates, key=score)


_installed: FontIndex | None = None


def installed_fonts() -> FontIndex:
    """The fonts installed on this machine, indexed once per process."""
    global _installed
    if _installed is None:
        _installed = FontIndex()
    return _installed


# ---------------------------------------------------------------------------
# Theme fonts
# ---------------------------------------------------------------------------

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


@dataclass(frozen=True)
class ThemeFonts:
    """A theme's heading (major) and body (minor) fonts, as family names:
    Latin, and East Asian. An empty `<a:ea>` -- the usual case -- means
    the theme's per-script choice; the Japanese one (`Jpan`) is taken."""

    major_latin: str = ""
    major_ea: str = ""
    minor_latin: str = ""
    minor_ea: str = ""


def theme_fonts_from_xml(theme_xml: bytes) -> ThemeFonts:
    root = etree.fromstring(theme_xml)
    found = {}
    for which in ("major", "minor"):
        font = root.find(f".//{{{_A}}}fontScheme/{{{_A}}}{which}Font")
        latin = ea = ""
        if font is not None:
            el = font.find(f"{{{_A}}}latin")
            latin = el.get("typeface", "") if el is not None else ""
            el = font.find(f"{{{_A}}}ea")
            ea = el.get("typeface", "") if el is not None else ""
            if not ea:
                for el in font.findall(f"{{{_A}}}font"):
                    if el.get("script") == "Jpan":
                        ea = el.get("typeface", "")
        found[f"{which}_latin"], found[f"{which}_ea"] = latin, ea
    return ThemeFonts(**found)
