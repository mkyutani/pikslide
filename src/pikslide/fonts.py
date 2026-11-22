"""Find the font files a deck's text will actually be drawn with, so `fit`
can measure with them (docs/spec.md SS3.3).

A family name -- a theme's `<a:latin typeface="Calibri"/>`, or the
`typeface` variable, which may be a localized name like "BIZ UDPゴシック" --
is looked up in the fonts installed on this machine, read from each font
file's own `name` table (every language's family names, so a Japanese
name finds its file too). On WSL the Windows fonts are searched as well,
since those are the ones PowerPoint draws with; on Windows and WSL, so
are the cloud fonts Office downloads, which it draws with too.
"""

from __future__ import annotations

import functools
import glob
import io
import json
import os
import platform
import struct
import sys
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field

from lxml import etree

_FONT_EXTENSIONS = (".ttf", ".ttc", ".otf", ".otc")

# Where in %LOCALAPPDATA%\Microsoft Office keeps the cloud fonts it
# downloads, a folder for each family.
_CLOUD_FONTS = ("FontCache", "4", "CloudFonts")


def _font_dirs() -> list[str]:
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA")
    dirs = [
        # Windows (native, then under WSL): the system's fonts, the user's,
        # and the cloud fonts Office downloads for the documents that use
        # them, which PowerPoint draws with too
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
        *(os.path.join(local, "Microsoft", *sub) for sub in (("Windows", "Fonts"), _CLOUD_FONTS) if local),
        "/mnt/c/Windows/Fonts",
        *glob.glob("/mnt/c/Users/*/AppData/Local/Microsoft/Windows/Fonts"),
        *glob.glob("/mnt/c/Users/*/AppData/Local/Microsoft/" + "/".join(_CLOUD_FONTS)),
        # macOS
        "/System/Library/Fonts",
        "/Library/Fonts",
        os.path.join(home, "Library", "Fonts"),
        # Linux
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        user_font_dir(),
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


def _read_face(f, offset: int, normalize: bool = True) -> tuple[list[str], bool, bool] | None:
    """One font's family names (name ID 1, every language; normalized
    for lookup unless `normalize` is false) and whether it is bold/italic
    (OS/2 fsSelection, else head macStyle), from the table directory at
    `offset` of the open file `f`. Reads only what it needs: fonts can be
    large, and slow to read whole (over WSL's /mnt/c)."""

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
            families.add(_normalize(decoded) if normalize else decoded.strip())
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
            return _read_faces(f)
    except OSError:
        return []


def _read_faces(f, normalize: bool = True) -> list[tuple[int, list[str], bool, bool]]:
    """Each face in the open font file `f` (one, or a collection's): its
    index, family names (_read_face()), and whether bold and italic."""
    try:
        header = f.read(12)
        if header[:4] == b"ttcf":
            num_fonts = struct.unpack_from(">I", header, 8)[0]
            offsets = struct.unpack(f">{num_fonts}I", f.read(4 * num_fonts))
        else:
            offsets = (0,)
        out = []
        for index, offset in enumerate(offsets):
            face = _read_face(f, offset, normalize)
            if face is not None:
                out.append((index, *face))
        return out
    except struct.error:
        return []


def baseline_ratio(path: str, index: int = 0) -> float:
    """Where PowerPoint sets the baseline in a line of single-spaced text
    in the font at `path` (`index` in a collection), as a multiple of the
    text size below the line's top: the line is 1.2 times the size
    (pptx_writer._LINE_PITCH), split between the font's OS/2 winAscent and
    winDescent. Checked against PowerPoint in Calibri, Arial, Meiryo and
    MS PGothic, to within a hundredth; Yu Gothic, two. 0.96 when the font
    can't be read."""
    try:
        with open(path, "rb") as f:
            offset = 0
            if f.read(4) == b"ttcf":
                f.seek(12 + 4 * index)
                offset = struct.unpack(">I", f.read(4))[0]
            f.seek(offset + 4)
            num_tables = struct.unpack(">H", f.read(2))[0]
            f.seek(offset + 12)
            directory = f.read(16 * num_tables)
            for i in range(num_tables):
                tag, _checksum, t_offset, _length = struct.unpack_from(">4sIII", directory, 16 * i)
                if tag == b"OS/2":
                    f.seek(t_offset + 74)
                    ascent, descent = struct.unpack(">HH", f.read(4))
                    if ascent + descent:
                        return 1.2 * ascent / (ascent + descent)
    except (OSError, struct.error):
        pass
    return 0.96


def _read_tables(path: str, index: int, tags: tuple[bytes, ...]) -> dict[bytes, bytes]:
    """The tables named `tags` the font at `path` (`index` in a collection)
    has, by tag. Raises OSError or struct.error where it can't be read."""
    out = {}
    with open(path, "rb") as f:
        offset = 0
        if f.read(4) == b"ttcf":
            f.seek(12 + 4 * index)
            offset = struct.unpack(">I", f.read(4))[0]
        f.seek(offset + 4)
        num_tables = struct.unpack(">H", f.read(2))[0]
        f.seek(offset + 12)
        directory = f.read(16 * num_tables)
        for i in range(num_tables):
            tag, _checksum, t_offset, t_length = struct.unpack_from(">4sIII", directory, 16 * i)
            if tag in tags:
                f.seek(t_offset)
                out[tag] = f.read(t_length)
    return out


def _char_glyphs(cmap: bytes) -> dict[int, int]:
    """Each code point's glyph, from the `cmap` table `cmap`: its
    full-repertoire subtable (format 12) if it has one, else its BMP one
    (format 4). Raises struct.error where it can't be read."""
    _version, count = struct.unpack_from(">HH", cmap, 0)
    subtables = {}
    for i in range(count):
        platform_id, encoding_id, sub_offset = struct.unpack_from(">HHI", cmap, 4 + 8 * i)
        fmt = struct.unpack_from(">H", cmap, sub_offset)[0]
        subtables.setdefault((fmt, platform_id, encoding_id), sub_offset)
    for (fmt, platform_id, encoding_id), sub_offset in subtables.items():
        if fmt == 12 and (platform_id, encoding_id) in ((3, 10), (0, 4), (0, 6)):
            return dict(_format12(cmap, sub_offset))
    for (fmt, platform_id, encoding_id), sub_offset in subtables.items():
        if fmt == 4 and (platform_id == 0 or (platform_id, encoding_id) == (3, 1)):
            return dict(_format4(cmap, sub_offset))
    return {}


def glyph_coverage(path: str, index: int = 0) -> frozenset[int]:
    """The code points the font at `path` (`index` in a collection) has a
    glyph for, from its `cmap` table (_char_glyphs()). Empty when the font
    can't be read."""
    try:
        tables = _read_tables(path, index, (b"cmap",))
        return frozenset(_char_glyphs(tables[b"cmap"])) if b"cmap" in tables else frozenset()
    except (OSError, struct.error):
        return frozenset()


def _format12(cmap: bytes, at: int):
    """Each (code point, glyph) of the format 12 cmap subtable at `at`."""
    n_groups = struct.unpack_from(">I", cmap, at + 12)[0]
    for g in range(n_groups):
        start, end, glyph = struct.unpack_from(">III", cmap, at + 16 + 12 * g)
        for c in range(start + (glyph == 0), end + 1):
            yield c, glyph + c - start


def _format4(cmap: bytes, at: int):
    """Each (code point, glyph) of the format 4 cmap subtable at `at`."""
    seg_count = struct.unpack_from(">H", cmap, at + 6)[0] // 2
    ends = struct.unpack_from(f">{seg_count}H", cmap, at + 14)
    starts = struct.unpack_from(f">{seg_count}H", cmap, at + 16 + 2 * seg_count)
    deltas = struct.unpack_from(f">{seg_count}h", cmap, at + 16 + 4 * seg_count)
    range_at = at + 16 + 6 * seg_count
    range_offsets = struct.unpack_from(f">{seg_count}H", cmap, range_at)
    for i, (start, end, delta, range_offset) in enumerate(zip(starts, ends, deltas, range_offsets)):
        for c in range(start, min(end, 0xFFFE) + 1):
            if range_offset == 0:
                glyph = (c + delta) & 0xFFFF
            else:
                glyph = struct.unpack_from(">H", cmap, range_at + 2 * i + range_offset + 2 * (c - start))[0]
                glyph = (glyph + delta) & 0xFFFF if glyph else 0
            if glyph:
                yield c, glyph


# ---------------------------------------------------------------------------
# How far glyphs advance, as PowerPoint sets text (issue #49)
# ---------------------------------------------------------------------------


class GlyphMetrics:
    """How far the glyphs of one font advance, as PowerPoint sets them,
    in ems: each glyph's own advance, unrounded (`hmtx`), and the kerning
    between two, from the `kern` feature of the font's GPOS table, or
    where that has none its `kern` table; no ligatures, which PowerPoint
    doesn't set (checked). Set vertically, a character's vertical form
    (GSUB's `vert` feature) and its advance (`vmtx`, or with none the
    font's height, as FreeType has it), unkerned, as raqm sets it.
    Read with glyph_metrics()."""

    def __init__(self, tables: dict[bytes, bytes]):
        self._upem = struct.unpack_from(">H", tables[b"head"], 18)[0]
        self._glyphs = _char_glyphs(tables[b"cmap"])
        self._h = _long_metrics(tables[b"hhea"], tables[b"hmtx"])
        if b"vhea" in tables and b"vmtx" in tables:
            self._v = _long_metrics(tables[b"vhea"], tables[b"vmtx"])
        else:
            height = _font_height(tables.get(b"OS/2"), tables[b"hhea"])
            self._v = lambda _glyph: height
        gpos, gsub = tables.get(b"GPOS"), tables.get(b"GSUB")
        self._kerning = _Kerning(gpos, tables.get(b"kern"))
        try:
            self._vertical_forms = _single_substitutions(gsub, _EAST_ASIAN, b"vert") if gsub else {}
        except struct.error:
            self._vertical_forms = {}

    def advances(self, text: str, kern: bool) -> list[float]:
        """How far each character of `text` advances, in ems, with the
        kerning between it and the next added to it if `kern`."""
        glyphs = [self._glyphs.get(ord(ch), 0) for ch in text]
        units = [self._h(g) for g in glyphs]
        if kern:
            for i, (left, right) in enumerate(zip(glyphs, glyphs[1:])):
                units[i] += self._kerning(left, right)
        return [u / self._upem for u in units]

    def vertical_advances(self, text: str) -> list[float]:
        """How far each character of `text` advances set upright in a
        column, in ems, in its vertical form."""
        glyphs = [self._glyphs.get(ord(ch), 0) for ch in text]
        return [self._v(self._vertical_forms.get(g, g)) / self._upem for g in glyphs]


# The scripts a feature is taken from, the first a font has: for Latin
# text, and for East Asian text set vertically.
_LATIN = (b"latn", b"DFLT")
_EAST_ASIAN = (b"kana", b"hani", b"hang", b"DFLT")


def _long_metrics(header: bytes, metrics: bytes):
    """A glyph's advance from an `hmtx` (or `vmtx`) table, whose `hhea`
    (`vhea`) table is `header`: the glyphs after the last long metric
    advance as far as it."""
    count = struct.unpack_from(">H", header, 34)[0]
    advances = struct.unpack_from(f">{2 * count}H", metrics)[0::2]  # (advance, side bearing) pairs

    def advance(glyph: int) -> int:
        return advances[min(glyph, count - 1)] if count else 0

    return advance


def _font_height(os2: bytes | None, hhea: bytes) -> int:
    """How far a glyph advances set vertically in a font with no vertical
    metrics, as FreeType has it: its OS/2 typographic ascender less its
    descender, else its `hhea` ones."""
    try:
        if os2:
            ascender, descender = struct.unpack_from(">hh", os2, 68)
            return ascender - descender
    except struct.error:
        pass
    ascender, descender = struct.unpack_from(">hh", hhea, 4)
    return ascender - descender


class _Kerning:
    """The kerning between two glyphs, in font units: the pair adjustments
    (lookup type 2) of the `kern` feature of the GPOS table `gpos`, for
    Latin text; where it has none, the horizontal pairs of the `kern`
    table `kern`, as HarfBuzz does. A table that can't be read kerns
    nothing."""

    def __init__(self, gpos: bytes | None, kern: bytes | None):
        self._gpos = gpos or b""
        self._lookups: list[list[tuple]] = []
        self._pairs: dict[tuple[int, int], int] = {}
        self._cache: dict[tuple[int, int], int] = {}
        try:
            if gpos:
                self._lookups = [[_pair_subtable(gpos, at) for at in _subtables(gpos, index, 2, 9)]
                                 for index in _feature_lookups(gpos, _LATIN, b"kern")]
            if not self._lookups and kern:
                self._pairs = _kern_table_pairs(kern)
        except struct.error:
            self._lookups, self._pairs = [], {}

    def __call__(self, first: int, second: int) -> int:
        key = (first, second)
        if key not in self._cache:
            if self._lookups:
                try:
                    self._cache[key] = sum(_pair_adjustment(self._gpos, subtables, first, second)
                                           for subtables in self._lookups)
                except struct.error:
                    self._cache[key] = 0
            else:
                self._cache[key] = self._pairs.get(key, 0)
        return self._cache[key]


def _feature_lookups(table: bytes, scripts: tuple[bytes, ...], feature: bytes) -> list[int]:
    """The lookups, in order, of `feature` in the GSUB or GPOS `table`,
    for the default language of the first of `scripts` it has."""
    _major, _minor, script_list, feature_list, _lookup_list = struct.unpack_from(">HHHHH", table, 0)
    found = {}
    for i in range(struct.unpack_from(">H", table, script_list)[0]):
        tag, offset = struct.unpack_from(">4sH", table, script_list + 2 + 6 * i)
        found[tag] = script_list + offset
    features = ()
    for tag in scripts:
        if tag in found and (default := struct.unpack_from(">H", table, found[tag])[0]):
            lang_sys = found[tag] + default
            count = struct.unpack_from(">H", table, lang_sys + 4)[0]
            features = struct.unpack_from(f">{count}H", table, lang_sys + 6)
            break
    lookups = set()
    for index in features:
        tag, offset = struct.unpack_from(">4sH", table, feature_list + 2 + 6 * index)
        if tag == feature:
            count = struct.unpack_from(">H", table, feature_list + offset + 2)[0]
            lookups.update(struct.unpack_from(f">{count}H", table, feature_list + offset + 4))
    return sorted(lookups)


def _subtables(table: bytes, index: int, kind: int, extension: int) -> list[int]:
    """Where the subtables of lookup `index` of the GSUB or GPOS `table`
    are, those of lookup type `kind`, an `extension` lookup's included."""
    lookup_list = struct.unpack_from(">H", table, 8)[0]
    lookup = lookup_list + struct.unpack_from(">H", table, lookup_list + 2 + 2 * index)[0]
    lookup_type, _flag, count = struct.unpack_from(">HHH", table, lookup)
    out = []
    for k in range(count):
        at = lookup + struct.unpack_from(">H", table, lookup + 6 + 2 * k)[0]
        this = lookup_type
        if this == extension:  # the subtable is further on
            _format, this, offset = struct.unpack_from(">HHI", table, at)
            at += offset
        if this == kind:
            out.append(at)
    return out


def _single_substitutions(gsub: bytes, scripts: tuple[bytes, ...], feature: bytes) -> dict[int, int]:
    """The glyph each glyph becomes under `feature`'s single substitutions
    (GSUB lookup type 1) -- the first lookup's that has it."""
    out: dict[int, int] = {}
    for index in _feature_lookups(gsub, scripts, feature):
        for at in _subtables(gsub, index, 1, 7):
            fmt, coverage = struct.unpack_from(">HH", gsub, at)
            covered = _coverage(gsub, at + coverage)
            if fmt == 1:
                delta = struct.unpack_from(">h", gsub, at + 4)[0]
                substitutes = {glyph: (glyph + delta) & 0xFFFF for glyph in covered}
            else:
                count = struct.unpack_from(">H", gsub, at + 4)[0]
                array = struct.unpack_from(f">{count}H", gsub, at + 6)
                substitutes = {glyph: array[i] for glyph, i in covered.items() if i < count}
            for glyph, substitute in substitutes.items():
                out.setdefault(glyph, substitute)
    return out


def _pair_subtable(gpos: bytes, at: int) -> tuple:
    """A pair adjustment subtable: its format, the glyphs it covers, its
    two value formats and its offset, and for format 2 its two class
    definitions and its second class count."""
    fmt, coverage, value1, value2 = struct.unpack_from(">HHHH", gpos, at)
    covered = _coverage(gpos, at + coverage)
    if fmt == 2:
        class_def1, class_def2, _class1_count, class2_count = struct.unpack_from(">HHHH", gpos, at + 8)
        return (2, covered, value1, value2, at, _class_def(gpos, at + class_def1), _class_def(gpos, at + class_def2),
                class2_count)
    return (fmt, covered, value1, value2, at, None, None, 0)


def _pair_adjustment(gpos: bytes, subtables: list[tuple], first: int, second: int) -> int:
    """How much one lookup's subtables change the advance between `first`
    and `second`: the first subtable that has the pair, or for format 2
    covers `first`, gives both glyphs' XAdvance."""
    for fmt, covered, value1, value2, at, classes1, classes2, class2_count in subtables:
        if first not in covered:
            continue
        size1, size2 = _value_size(value1), _value_size(value2)
        if fmt == 1:
            pair_set = at + struct.unpack_from(">H", gpos, at + 10 + 2 * covered[first])[0]
            record = 2 + size1 + size2
            for r in range(struct.unpack_from(">H", gpos, pair_set)[0]):
                here = pair_set + 2 + record * r
                if struct.unpack_from(">H", gpos, here)[0] == second:
                    return _x_advance(gpos, here + 2, value1) + _x_advance(gpos, here + 2 + size1, value2)
        elif fmt == 2:
            here = at + 16 + (classes1.get(first, 0) * class2_count + classes2.get(second, 0)) * (size1 + size2)
            return _x_advance(gpos, here, value1) + _x_advance(gpos, here + size1, value2)
    return 0


def _value_size(value_format: int) -> int:
    return 2 * bin(value_format & 0xFF).count("1")


def _x_advance(data: bytes, at: int, value_format: int) -> int:
    """The XAdvance of the value record at `at`, of `value_format`."""
    if not value_format & 0x4:
        return 0
    return struct.unpack_from(">h", data, at + 2 * bin(value_format & 0x3).count("1"))[0]


def _coverage(data: bytes, at: int) -> dict[int, int]:
    """A coverage table: each glyph it covers, and its index."""
    fmt, count = struct.unpack_from(">HH", data, at)
    if fmt == 1:
        return {glyph: i for i, glyph in enumerate(struct.unpack_from(f">{count}H", data, at + 4))}
    out = {}
    for r in range(count):
        start, end, first = struct.unpack_from(">HHH", data, at + 4 + 6 * r)
        for glyph in range(start, end + 1):
            out[glyph] = first + glyph - start
    return out


def _class_def(data: bytes, at: int) -> dict[int, int]:
    """A class definition table: each glyph's class, but class 0's."""
    fmt = struct.unpack_from(">H", data, at)[0]
    out = {}
    if fmt == 1:
        start, count = struct.unpack_from(">HH", data, at + 2)
        for i, value in enumerate(struct.unpack_from(f">{count}H", data, at + 6)):
            out[start + i] = value
    elif fmt == 2:
        for r in range(struct.unpack_from(">H", data, at + 2)[0]):
            start, end, value = struct.unpack_from(">HHH", data, at + 4 + 6 * r)
            for glyph in range(start, end + 1):
                out[glyph] = value
    return out


def _kern_table_pairs(kern: bytes) -> dict[tuple[int, int], int]:
    """The horizontal kerning pairs of a `kern` table's format 0
    subtables (the OpenType version; Apple's is passed over)."""
    version, count = struct.unpack_from(">HH", kern, 0)
    if version != 0:
        return {}
    pairs: dict[tuple[int, int], int] = {}
    at = 4
    for _ in range(count):
        _sub_version, length, coverage = struct.unpack_from(">HHH", kern, at)
        # horizontal, not minimum values nor cross-stream, format 0
        if coverage & 0x7 == 0x1 and coverage >> 8 == 0:
            n_pairs = struct.unpack_from(">H", kern, at + 6)[0]
            for p in range(n_pairs):
                left, right, value = struct.unpack_from(">HHh", kern, at + 14 + 6 * p)
                pairs[(left, right)] = pairs.get((left, right), 0) + value
        at += length
    return pairs


@functools.lru_cache(maxsize=64)
def glyph_metrics(path: str, index: int = 0) -> GlyphMetrics | None:
    """The GlyphMetrics of the font at `path` (`index` in a collection);
    None where it can't be read."""
    tags = (b"head", b"cmap", b"hhea", b"hmtx", b"vhea", b"vmtx", b"OS/2", b"GPOS", b"GSUB", b"kern")
    try:
        return GlyphMetrics(_read_tables(path, index, tags))
    except (OSError, struct.error, KeyError):
        return None


def powerpoint_sees(path: str) -> bool:
    """Whether PowerPoint on this machine draws with the font at `path`,
    as far as pikslide can tell: on Windows, one installed in Windows or
    one of Office's cloud fonts, not one --install-font put in pikslide's
    own directory; under WSL, one in Windows (under /mnt), not one in
    WSL's own directories. Elsewhere, any: PowerPoint for Mac uses the
    user's fonts, and on Linux there is no PowerPoint to tell about."""
    if sys.platform == "win32":
        own = os.path.normcase(os.path.abspath(user_font_dir()))
        return not os.path.normcase(os.path.abspath(path)).startswith(own)
    if on_windows():
        return os.path.abspath(path).startswith("/mnt/")
    return True


# ---------------------------------------------------------------------------
# --install-font (issue #37): a font this machine lacks, for `fit` and
# --renderer direct to use
# ---------------------------------------------------------------------------

# How a font file starts: TrueType (1.0 or Apple's `true`), CFF
# OpenType, or a collection.
_FONT_MAGIC = (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf")
# The most --install-font downloads, or takes from one zip.
_MAX_FONT_BYTES = 200_000_000


class FontInstallError(Exception):
    pass


def user_font_dir() -> str:
    """Where --install-font puts fonts, and FontIndex looks: the user's
    own font directory, `~/Library/Fonts` on macOS, `$XDG_DATA_HOME/fonts`
    (`~/.local/share/fonts`) on Linux and WSL; on Windows, pikslide's own,
    `%LOCALAPPDATA%\\pikslide\\fonts`, Windows' being Windows' to install
    fonts in (PowerPoint draws with those)."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Fonts")
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"), "pikslide", "fonts")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"), "fonts")


def on_windows() -> bool:
    """Windows, or WSL, where PowerPoint draws with the fonts installed in
    Windows, not with those --install-font installs."""
    return sys.platform == "win32" or "microsoft" in platform.uname().release.lower()


def install_fonts(source: str, dest: str | None = None) -> list[tuple[str, list[str], bool]]:
    """Put the fonts `source` names in `dest` (user_font_dir()), where
    FontIndex finds them by name: a font file (.ttf, .otf, .ttc, .otc), a
    directory of them, a zip of them, or a URL of a font file or a zip.
    Returns each font's path there, its family names, and whether it was
    there already. pikslide fetches what it is told to and ships no font:
    a font's license is its user's to see to.

    PowerPoint on Windows (and WSL) doesn't draw with a font installed so
    (on_windows()): that is installed in Windows, by its user.

    Raises FontInstallError where `source` can't be had or has no font."""
    if source.startswith(("http://", "https://")):
        name, data = _download(source)
        fonts = _fonts_in(name, data)
    elif os.path.isdir(source):
        fonts = []
        for root, _subdirs, files in os.walk(source):
            for file in sorted(files):
                if file.lower().endswith(_FONT_EXTENSIONS + (".zip",)):
                    with open(os.path.join(root, file), "rb") as f:
                        fonts += _fonts_in(file, f.read())
    elif os.path.isfile(source):
        with open(source, "rb") as f:
            fonts = _fonts_in(os.path.basename(source), f.read())
    else:
        raise FontInstallError(f"no such file or directory: {source}")
    if not fonts:
        raise FontInstallError(f"no font in {source} (a .ttf, .otf, .ttc or .otc, or a zip of them)")
    dest = dest or user_font_dir()
    os.makedirs(dest, exist_ok=True)
    out = []
    for name, data, families in fonts:
        path = os.path.join(dest, name)
        try:
            with open(path, "rb") as f:
                already = f.read() == data
        except OSError:
            already = False
        if not already:
            # Written aside, then moved into place: the directory's time
            # changes, so FontIndex's cache reads it again (_build()).
            temp = path + ".part"
            with open(temp, "wb") as f:
                f.write(data)
            os.replace(temp, path)
        out.append((path, families, already))
    return out


def _download(url: str) -> tuple[str, bytes]:
    """The file at `url`: its name, from the URL's path, and its bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": "pikslide"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(_MAX_FONT_BYTES + 1)
            final = response.geturl()
    except (OSError, ValueError) as e:
        raise FontInstallError(f"could not download {url}: {e}") from None
    if len(data) > _MAX_FONT_BYTES:
        raise FontInstallError(f"{url} is bigger than {_MAX_FONT_BYTES // 1_000_000} MB")
    name = os.path.basename(urllib.request.url2pathname(urllib.parse.urlsplit(final).path)) or "font"
    return name, data


def _fonts_in(name: str, data: bytes) -> list[tuple[str, bytes, list[str]]]:
    """The fonts in a file named `name`, a font or a zip of them: each
    one's file name, bytes and family names. Anything else in a zip, or
    a file that isn't a font, is passed over."""
    if data[:4] == b"PK\x03\x04":
        out = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    base = os.path.basename(member.filename)
                    # Only fonts, by name alone (never a path in the zip), and
                    # not macOS's ._ resource files.
                    if member.is_dir() or base.startswith("._") or not base.lower().endswith(_FONT_EXTENSIONS):
                        continue
                    if member.file_size > _MAX_FONT_BYTES:
                        raise FontInstallError(f"{base} in {name} is bigger than {_MAX_FONT_BYTES // 1_000_000} MB")
                    out += _fonts_in(base, archive.read(member))
        except zipfile.BadZipFile as e:
            raise FontInstallError(f"{name} is not a zip that can be read: {e}") from None
        return out
    if data[:4] not in _FONT_MAGIC:
        return []
    faces = _read_faces(io.BytesIO(data), normalize=False)
    families = sorted({family for _index, names, _bold, _italic in faces for family in names})
    if not families:
        return []
    if not name.lower().endswith(_FONT_EXTENSIONS):
        name += {b"ttcf": ".ttc", b"OTTO": ".otf"}.get(data[:4], ".ttf")
    return [(name, data, families)]


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


# The scripts a theme names an East Asian font for (`<a:font script>`)
# that PowerPoint takes by a run's language: Japanese, Korean, and
# simplified and traditional Chinese.
EAST_ASIAN_SCRIPTS = ("Jpan", "Hang", "Hans", "Hant")


@dataclass(frozen=True)
class ThemeFonts:
    """A theme's heading (major) and body (minor) fonts, as family names:
    Latin; East Asian, as `<a:ea>` has it; and the East Asian one for each
    of EAST_ASIAN_SCRIPTS the theme names one for. An empty `<a:ea>` --
    the usual case -- means the one for the script of the text's language
    (east_asian())."""

    major_latin: str = ""
    major_ea: str = ""
    minor_latin: str = ""
    minor_ea: str = ""
    major_scripts: Mapping[str, str] = field(default_factory=dict, hash=False)
    minor_scripts: Mapping[str, str] = field(default_factory=dict, hash=False)

    def east_asian(self, major: bool, script: str) -> str:
        """The heading (`major`) or body font East Asian text in `script`
        (EAST_ASIAN_SCRIPTS) is set in: `<a:ea>`'s, else the script's;
        empty where the theme names neither."""
        ea, scripts = (self.major_ea, self.major_scripts) if major else (self.minor_ea, self.minor_scripts)
        return ea or scripts.get(script, "")


def theme_fonts_from_xml(theme_xml: bytes) -> ThemeFonts:
    root = etree.fromstring(theme_xml)
    found = {}
    for which in ("major", "minor"):
        font = root.find(f".//{{{_A}}}fontScheme/{{{_A}}}{which}Font")
        latin = ea = ""
        scripts = {}
        if font is not None:
            el = font.find(f"{{{_A}}}latin")
            latin = el.get("typeface", "") if el is not None else ""
            el = font.find(f"{{{_A}}}ea")
            ea = el.get("typeface", "") if el is not None else ""
            for el in font.findall(f"{{{_A}}}font"):
                if el.get("script") in EAST_ASIAN_SCRIPTS and el.get("typeface"):
                    scripts[el.get("script")] = el.get("typeface")
        found[f"{which}_latin"], found[f"{which}_ea"], found[f"{which}_scripts"] = latin, ea, scripts
    return ThemeFonts(**found)
