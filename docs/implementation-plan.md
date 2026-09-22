# pikslide implementation plan

This tracks the gap between [spec.md](spec.md)/[grammar.md](grammar.md) (what
pikslide *should* do) and the current code (what it *does* do today). Unlike
those two, this file is not part of the language definition and is expected
to go stale row by row as each item is implemented — update or delete a row
once its "Needed" column is done, rather than leaving it to describe
already-built behaviour.

## Done

- **Colours are a type of their own** (`pik/layout.py` `Colour`), not a
  `float` RGB int: `Shape.fill`/`Shape.color`, and any variable, can hold a
  number, a `Colour`, or a string. A hex literal (`ast.HexColor`) is a
  colour; a decimal literal is a number. Arithmetic on a colour or string is
  an error.
- **`theme "slot"`** (`ast.ThemeColor`) and **`lighter`/`darker`**
  (`ast.ColorMod`) are implemented and kept symbolic end to end: rendered as
  `schemeClr` (+ `brightness` for the modifier), never resolved to RGB
  (checked against python-pptx's actual XML output). `none`/`off`
  (`ast.NoColor`) are reserved words, not colour-table entries.
- **The prelude** (`src/pikslide/prelude.pik`, `pik/layout.py`
  `_load_prelude`) replaces both `pik/colors.py` `COLOR_NAMES` (deleted) and
  the old `DEFAULTS` dict: CSS colour names, the built-in pikchr defaults,
  and the theme-colour names (`accent1` … `followed`, via `theme "tx1"`
  etc.) are now `.pik` assignments, read once before every program.
- **Three fixed text sizes** (`small`/`medium`/`large`, prelude-defined,
  9/10.5/12pt): assignable like `fill`/`color`/`thickness` (`lvalue` grammar
  extended), read back from `LayoutResult.text_sizes` by `pptx_writer.py`
  instead of a hard-coded `_BASE_FONT_PT`. Not yet live-updated if a program
  overrides `medium` after a `fit` object already measured (rare; see the
  docstring on `PilFontMetrics`).
- **An undefined variable is now an error** (`eval_expr`'s `ast.Var` case),
  matching real pikchr (checked: `box width undefinedvar` → "no such
  variable" in real pikchr too) — the old code silently defaulted to `0.0`.
  `main()` now catches `LayoutError` and prints `error: ...` instead of a
  raw traceback.
- **A macro cannot shadow a variable, in either direction**
  (`pik/macros.py`): `define` errors if the name is already a variable
  (prelude or assigned earlier in the program); assigning to a name already
  used by `define` errors too. Checked: without this, `define legend {fill}`
  then `legend = 5` silently expanded to `fill = 5` with no error at all.
- **Reserved words**: `shape`, `image`, `include`, `alt`, `major`, `medium`,
  `large`, `theme`, `lighter`, `darker`, `none`, `off`, `connector` are all
  real keyword tokens (`pik/tokens.py`). Only `connector` is reserved but
  not parsed as a real construct yet; every other one is fully implemented.
- **`include "path"`** (`pik/macros.py`): resolved in the macro-expansion
  pass, before parsing, exactly as docs/grammar.md's Includes section
  describes -- so it needed no AST node of its own. Macros and variables
  it brings in are merged into the token stream at the `include` line
  ("visible from there onward, exactly as if written there", checked,
  including across nested includes); the definitions-only check
  (`_validate_definitions_only`) rejects any object/label/etc. in the
  included file, naming the failing file. Path resolution tries the
  including file's own directory first, then each `include_paths` entry
  (ext, for a future `--include-path`, plumbed already but nothing sets
  it yet); containment (no absolute paths, no escapes) and cycle
  detection (sharing the same 50-level depth budget as macros) are both
  checked. The macro-shadow guard (above) already covered names an
  include brings in, with no changes needed, since they merge into the
  same token stream the guard already scans.
- **Preset shapes** (`shape preset-name`, `ast.ShapeBase`, `Shape.preset`):
  matched case-insensitively against all 177 OOXML presets python-pptx 1.0.2
  knows (`pik/layout.py` `PRESET_NAMES`); an unknown name is an error with
  "did you mean" suggestions (`difflib`). Behaves like `box` (default size,
  `width`/`height`/`fit`/`at`/`with`/`same`/text/`fill`/`color`/`dashed`/
  `thickness`, edges on the bounding rectangle, checked) -- including
  `rad` on `roundRect` specifically (that preset *is* the same
  `MSO_SHAPE.ROUNDED_RECTANGLE` `box rad>0` already uses; a bare
  `shape roundRect`, `rad` unset, keeps python-pptx's own default corner
  rather than flattening it to square, checked).
- **Images** (`image STRING`, `ast.ImageBase`, `Shape.image_path`/`alt_text`):
  PNG/JPEG/GIF only (SVG errors clearly -- "not supported yet" -- rather
  than a confusing raw `PIL.UnidentifiedImageError`, checked). The path
  resolves against, and is contained under, the source file's own
  directory (for Markdown, the `.md` file), the same containment `include`
  will apply; `main()` computes it from the input path and threads it
  through `resolve_for_pptx(..., base_dir=...)`. Sizing follows
  docs/spec.md SS3.5 exactly: both `width`/`height` given -> stretched (no
  file read at all); one given -> the other follows the aspect ratio;
  neither -> fit inside `boxwid`x`boxht`. Aspect ratio comes from an
  injected `ImageMetrics` (mirrors `FontMetrics`); the default reads the
  file directly with Pillow, since unlike text there's no sensible flat
  estimate. `alt STRING` sets the real saved accessibility description --
  found the hard way that python-pptx 1.0.2's `Shape.alt_text` isn't a
  real property at all (silently becomes a plain, never-saved instance
  attribute); the actual OOXML attribute, `p:cNvPr/@descr`, is set
  directly. A picture has no `text_frame` (like a connector), so text on
  an image becomes one centred floating textbox, not per-string labels.
- **Markdown diagram names** (`markdown.py` `PikBlock`, `extract_pik_blocks`):
  the `pikslide` fence tag is recognised alongside `pik`/`pikchr`; a fence
  may be named (` ```pikslide architecture `); a file with more than one
  diagram must name every one, uniquely, or `MarkdownDiagramError`.
- **Inserting into an existing deck** (`pptx_writer.py` `insert_into_pptx`,
  docs/spec.md SS4.2): opens the deck, resolves `--region` (a shape/
  placeholder found by name) or `--rect` to a target rectangle, errors if
  the diagram is larger than it (never scaled, checked visually via
  PowerPoint), draws into a new group (`_LocalTransform`: `_Transform`
  without the whole-slide minimum-size clamp or margin, since a region
  can be smaller than 1in and doesn't need either), and positions the
  group at the region's top-left. An existing same-named group is removed
  and the new one reinserted at its old position in the slide's shape
  tree, so z-order survives a re-run (checked, including with another
  shape added after the group in between runs). Resolving `--region`
  falls back to an existing `pikslide:<id>` group's own rect if the named
  shape can't be found -- needed for idempotent re-runs specifically when
  the region was an *empty placeholder*: the first run deletes it, so a
  second run naming it again would otherwise fail to find it at all (an
  addition made once this surfaced in testing, not something docs/spec.md
  SS4.2 spells out). `write_pptx()`'s draw loop is now shared
  (`_add_all_shapes`) between a slide and a group, since a python-pptx
  group's own `.shapes` exposes the identical `add_shape`/`add_connector`/
  `add_picture`/`add_textbox`/`build_freeform` API (checked) -- no
  branching needed in the shape-adding functions themselves, just a
  parameter rename (`slide` -> `container`) for clarity.
- **CLI**: `__init__.py` uses `argparse` now, not a hand-rolled `sys.argv`
  reader. `--into DECK --slide N (--region NAME | --rect X,Y,W,H) [--id ID]
  (--in-place | -o OUT)` calls `insert_into_pptx()`; omitting both
  `--in-place` and `-o` saves to the `deck.pikslide.pptx` default
  (docs/spec.md SS4.2), checked (including that the original deck is left
  untouched in that case). `--id` defaults to the Markdown fence name, else
  the source file's stem (SS4.2/SS6), checked for both a named and an
  unnamed single-block `.md` file. A Markdown file with more than one
  diagram and no `--block` (not implemented -- see below) is a clear
  "--block isn't implemented yet" error under `--into`, rather than picking
  one arbitrarily; standalone rendering of a multi-block file is
  unaffected (unchanged from before). Combining flags that don't make
  sense together (`--slide` without `--into`, `-o` and `--in-place`
  together, `-o` given both positionally and as `-o`) are `argparse`-level
  errors (exit 2), same as an unparsable `--rect`. Verified end-to-end via
  real PowerPoint rendering (WSL -> Windows COM), not just python-pptx
  introspection: title and the region shape both survive, the diagram
  lands at the region's top-left, a second run replaces it in place.
  `--template --settings --block --include-path --align --strict --check
  --format` are still not wired up (the last four depend on template
  settings/theme reading, which are separate not-yet-started items).
- Tests: `box fill Red`/`box color DarkBlue` → lowercase (`red`/`darkblue`);
  new coverage for colours, text sizes, the macro-shadow guard, Markdown
  names, preset shapes, images, `include`, and inserting into a deck
  (`tests/test_layout.py`, `tests/test_pik_parser.py`,
  `tests/test_pptx_writer.py`, `tests/test_markdown.py`).

## Not yet started

| Area | Today | Needed |
|---|---|---|
| `pik/tokens.py` `Token`, `PikSyntaxError` | carry a line number, and (since `include`) the right file named in the *message text* | a proper structured `file`/column field, rather than folding the path into the message string by hand at each `include`-related error site |
| `pik/layout.py`, `pptx_writer.py` | SVG `image`s are a clear "not supported yet" error | SVG picture (`svgBlip` + PNG fallback via an external rasteriser, hand-written XML) |
| *(new)* theme reader | none; theme colours always render against python-pptx's built-in Office theme | read `ppt/theme/*.xml` from a `.pptx`/`.potx` with `zipfile`; slide → layout → master → theme lookup; `.potx` normalisation for use as a base |
| *(new)* template settings | none | find the settings file beside a template or deck and read it after the prelude; `layout`, `typeface`, accent colours, text sizes, content area |
| `pptx_writer.py` `FONT_NAME` | hard-coded `"Arial"`; no `typeface` variable | read `typeface` (once settings files exist) or the theme's own font |
| `pik/layout.py` `_flatten` | flattens `[ ]` blocks, losing the tree | keep the hierarchy so groups can be written |
| `pik/layout.py` `behind` | parsed, ignored | affects z-order |
| `__init__.py` | `argparse`, with `--into --slide --region --rect --id --in-place -o` all working | `--template --settings --block --include-path --align --strict --check --format` besides (the last four depend on template settings/theme reading above) |
| Docs | README's *Status* section | keep it in step with this file as items are implemented |
