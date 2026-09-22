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
  now real keyword tokens (`pik/tokens.py`) — but only `theme`/`none`/`off`/
  `lighter`/`darker`/`medium`/`large` have actual parsing+evaluation
  behind them (colours, text sizes). `shape`, `image`, `include`,
  `connector` are reserved (can't be used as a variable/macro name) but
  parsing them as real constructs is not implemented (`shape roundRect`,
  `image "x.png"`, `include "x.pik"` are still syntax errors).
- **Markdown diagram names** (`markdown.py` `PikBlock`, `extract_pik_blocks`):
  the `pikslide` fence tag is recognised alongside `pik`/`pikchr`; a fence
  may be named (` ```pikslide architecture `); a file with more than one
  diagram must name every one, uniquely, or `MarkdownDiagramError`.
  `--block NAME` (to select one diagram for `--into`) is not implemented —
  there is no `--into` yet either.
- Tests: `box fill Red`/`box color DarkBlue` → lowercase (`red`/`darkblue`);
  new coverage for colours, text sizes, the macro-shadow guard, and
  Markdown names (`tests/test_layout.py`, `tests/test_pik_parser.py`,
  `tests/test_pptx_writer.py`, `tests/test_markdown.py`).

## Not yet started

| Area | Today | Needed |
|---|---|---|
| `pik/tokens.py` `Token`, `PikSyntaxError` | carry a line number only | carry the source file and column, so errors inside an `include` point at the right file |
| `pik/macros.py` | no `include` statement | resolve `include "path"` in the same pass as `define` (shared macro table, definitions-only check, path containment, cycle/depth limits) |
| `pik/parser.py`, `pik/layout.py` | `shape`/`image` are reserved words only | `shape preset-name` and `image STRING` as real object classes (basetype parsing, layout defaults, `alt`) |
| *(new)* theme reader | none; theme colours always render against python-pptx's built-in Office theme | read `ppt/theme/*.xml` from a `.pptx`/`.potx` with `zipfile`; slide → layout → master → theme lookup; `.potx` normalisation for use as a base |
| *(new)* template settings | none | find the settings file beside a template or deck and read it after the prelude; `layout`, `typeface`, accent colours, text sizes, content area |
| `pptx_writer.py` `FONT_NAME` | hard-coded `"Arial"`; no `typeface` variable | read `typeface` (once settings files exist) or the theme's own font |
| `pik/layout.py` `_flatten` | flattens `[ ]` blocks, losing the tree | keep the hierarchy so groups can be written |
| `pik/layout.py` `behind` | parsed, ignored | affects z-order |
| `pptx_writer.py` | always a new blank presentation | open an existing deck, insert group, replace by name, check that the diagram fits its region |
| `pptx_writer.py` | no pictures | `p:pic` for `image`; SVG picture (`svgBlip` + PNG fallback, hand-written XML) |
| `__init__.py` | `pikslide <in> [<out>]` only | `--into --slide --region/--rect --id --template --settings --block --include-path --align --strict --check --format` |
| Docs | README's *Status* section | keep it in step with this file as items are implemented |
