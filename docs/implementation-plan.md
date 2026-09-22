# pikslide implementation plan

This tracks the gap between [spec.md](spec.md)/[grammar.md](grammar.md) (what
pikslide *should* do) and the current code (what it *does* do today). Unlike
those two, this file is not part of the language definition and is expected
to go stale row by row as each item is implemented — update or delete a row
once its "Needed" column is done, rather than leaving it to describe
already-built behavior.

## Done

- **Colors are a type of their own** (`pik/layout.py` `Color`), not a
  `float` RGB int: `Shape.fill`/`Shape.color`, and any variable, can hold a
  number, a `Color`, or a string. A hex literal (`ast.HexColor`) is a
  color; a decimal literal is a number. Arithmetic on a color or string is
  an error.
- **`theme "slot"`** (`ast.ThemeColor`) and **`lighter`/`darker`**
  (`ast.ColorMod`) are implemented and kept symbolic end to end: rendered as
  `schemeClr` (+ `brightness` for the modifier), never resolved to RGB
  (checked against python-pptx's actual XML output). `none`/`off`
  (`ast.NoColor`) are reserved words, not color-table entries.
- **The prelude** (`src/pikslide/prelude.pik`, `pik/layout.py`
  `_load_prelude`) replaces both `pik/colors.py` `COLOR_NAMES` (deleted) and
  the old `DEFAULTS` dict: CSS color names, the built-in pikchr defaults,
  and the theme-color names (`accent1` … `followed`, via `theme "tx1"`
  etc.) are now `.pik` assignments, read once before every program.
- **Three fixed text sizes** (`small`/`medium`/`large`, prelude-defined,
  9/10.5/12pt): assignable like `fill`/`color`/`thickness` (`lvalue` grammar
  extended). Originally read back from a single document-wide
  `LayoutResult.text_sizes` by `pptx_writer.py`, which turned out stale in
  two ways -- fixed since (`Shape.text_sizes`/`.typeface`, docs/spec.md
  SS3.3, ext):
  - *Rendered* size/family (`run.font.size`, `_apply_run_font`) now reads
    `Shape.text_sizes`/`.typeface`, captured once per object in
    `_layout_object()` -- the value in effect *where that object was
    written*, mirroring exactly how `Shape.fill`/`.color` already worked
    (captured at creation, from `ctx.vars`) -- rather than
    `LayoutResult.text_sizes` (the document's *final* value, read once
    after the whole document ran, so a later override used to apply
    retroactively to the entire diagram: checked, before this fix, `box
    "a" small\nsmall=20pt\nbox "b" small` rendered **both** at 20pt; now
    "a" stays at 9pt).
  - *`fit`-object measurement* (`FontMetrics.text_width`/`.line_height`,
    used during layout to size a `fit` box to its text) gained an
    optional `text_sizes` parameter -- `_autosize_text()` now always
    passes the *object's own* `shape.text_sizes` explicitly, so
    `PilFontMetrics` (which previously measured with a fixed snapshot
    from before the document ran, never tracking any override at all, at
    any position: checked, `medium = 30pt` before a `fit` box changed
    nothing about its measured size) now measures correctly too;
    `_ApproxMetrics` accepts but ignores the new parameter, since it
    already read `ctx.vars` live and so was never actually stale.

  `LayoutResult.text_sizes`/`.typeface` themselves are unchanged (still
  the document's final values, still tested) -- pptx_writer.py just
  doesn't read them for rendering any more, using the more precise
  per-shape fields instead. Checked through real PowerPoint too (a `small`
  override partway through a document, and a `typeface` override): both
  render exactly as the source implies, not as of the document's end.
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
  PNG, JPEG, GIF, and SVG. The path resolves against, and is contained
  under, the source file's own directory (for Markdown, the `.md` file),
  the same containment `include` applies; `main()` computes it from the
  input path and threads it through `resolve_for_pptx(..., base_dir=...)`.
  Sizing follows docs/spec.md SS3.5 exactly: both `width`/`height` given
  -> stretched (no file read at all); one given -> the other follows the
  aspect ratio; neither -> fit inside `boxwid`x`boxht`. Aspect ratio comes
  from an injected `ImageMetrics` (mirrors `FontMetrics`); the default
  reads the file directly with Pillow, since unlike text there's no
  sensible flat estimate. `alt STRING` sets the real saved accessibility
  description -- found the hard way that python-pptx 1.0.2's
  `Shape.alt_text` isn't a real property at all (silently becomes a
  plain, never-saved instance attribute); the actual OOXML attribute,
  `p:cNvPr/@descr`, is set directly. A picture has no `text_frame` (like a
  connector), so text on an image becomes one centred floating textbox,
  not per-string labels.
- **SVG images** (`pik/layout.py` `rasterize_svg`, `pptx_writer.py`
  `_attach_svg_extension`, docs/spec.md SS3.5): via `rsvg-convert` (from
  librsvg) on `PATH` -- a clear error naming the missing tool otherwise,
  checked, not a confusing raw failure. Sizing (when width or height, or
  neither, is given) rasterizes to PNG and reads *that* with Pillow, since
  Pillow itself can't read an SVG's dimensions at all. Embedding: since
  python-pptx cannot add an SVG (`add_picture()` raises `TypeError`,
  checked -- it reads the image with Pillow internally too), the picture
  is added from the *rasterized* PNG (python-pptx's normal path, so it
  becomes the fallback older viewers show), then the real SVG is attached
  by hand: a raw `ImagePart` (content type `image/svg+xml`, bypassing
  python-pptx's own `Image` class, also Pillow-based and unable to read
  SVG) related to the slide, referenced from a hand-written `<a:extLst>`/
  `asvg:svgBlip` extension on the picture's `<a:blip>` -- checked against
  real PowerPoint: with the fallback and the real SVG deliberately made to
  look different (a solid rectangle vs. a vector circle), it renders the
  *circle*, proving the extension is genuinely read, not just tolerated.
- **Markdown diagram names** (`markdown.py` `PikBlock`, `extract_pik_blocks`):
  the `pikslide` fence tag is recognized alongside `pik`/`pikchr`; a fence
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
  reader, with every flag docs/spec.md §4/§5/§6 names wired up:
  - `--into DECK --slide N (--region NAME | --rect X,Y,W,H) [--id ID]
    (--in-place | -o OUT) [--align ALIGN]` calls `insert_into_pptx()`;
    omitting both `--in-place` and `-o` saves to the `deck.pikslide.pptx`
    default (SS4.2), checked (including that the original deck is left
    untouched in that case). `--id` defaults to the Markdown fence name,
    else the source file's stem (SS4.2/SS6), checked for both a named and
    an unnamed single-block `.md` file.
  - `--template FILE` (standalone only -- an error alongside `--into`,
    SS3.3 rule 2) calls the new `write_pptx_from_template()`; `--block
    NAME` picks one diagram out of a multi-diagram Markdown file for
    either (SS6) -- without it, such a file is a clear error naming
    `--block`, rather than picking one arbitrarily; standalone rendering
    of a multi-block file with *no* `--into`/`--template` is unaffected
    (every block still gets its own numbered output, as before).
  - `--settings FILE` (SS3.8) finds a settings file beside the `--into`
    deck or `--template` file by default (`<name>.theme.pik`), or reads
    the named one directly, including with neither `--into` nor
    `--template` (SS3.8: "also works when no template is given"); a named
    file that doesn't exist is an error.
  - `--include-path DIR` (repeatable) is `parse()`'s existing
    `include_paths` plumbing, finally with a flag that sets it.
  - `--strict` turns the "no `--template` given" warning (SS3.3 rule 3)
    into an error instead, before anything is written.
  - `--check` parses and lays out without writing (SS5) -- literally
    that: `parse()` + `resolve_for_pptx()` alone, stopping *before*
    `write_pptx()`/`insert_into_pptx()`/`write_pptx_from_template()`, so
    it validates the `.pik` source itself, not a specific deck/slide/
    region target.
  - `--format json` (SS5) emits one JSON object (`{"ok", "errors",
    "warnings", ...}`) to stdout instead of `error:`/`warning:` lines to
    stderr and a plain success line to stdout; a `PikSyntaxError`'s entry
    carries real `file`/`line`/`column` (see below), a `LayoutError`'s
    does not (known gap, see Diagnostics below).

  Combining flags that don't make sense together (`--slide`/`--align`
  without `--into`, `--into` with `--template`, `-o` and `--in-place`
  together, `-o` given both positionally and as `-o`, an unrecognized
  `--align`) are `argparse`-level errors (exit 2), same as an unparsable
  `--rect`. Verified end-to-end via real PowerPoint rendering (WSL ->
  Windows COM), not just python-pptx introspection: title and the region
  shape both survive an `--into`, the diagram lands at the region's
  top-left (or wherever `--align` says), a second run replaces it in
  place.
- **Fonts follow the theme, not a hard-coded family** (`pptx_writer.py`
  `_apply_run_font`, docs/spec.md SS3.3): every run's Latin and East Asian
  font slots (`<a:latin>`/`<a:ea>`) get a *symbolic* theme reference by
  default -- the minor font (`+mn-lt`/`+mn-ea`), or the major (heading)
  font (`+mj-lt`/`+mj-ea`) where the `major` text flag is used -- never a
  literal name, exactly like a `theme` color. This needs no theme file
  read at all, for either output path: a fresh standalone deck already has
  the built-in Office theme these symbols resolve against (same as any new
  PowerPoint file), and `--into` writes straight into the target deck, so
  the reference resolves against *its* own theme once the file is reopened
  -- checked by patching a saved deck's theme XML to distinct major/minor
  families and rendering it through real PowerPoint (COM): each slot
  picked its own family, Latin and CJK text both correct. `typeface`
  (prelude, empty by default) overrides with one literal family for both
  slots regardless of `major`, per SS3.3 ("a specific family"). Removed
  `font_name`/`FONT_NAME` from the whole rendering call chain (`write_pptx`,
  `insert_into_pptx`, `_add_all_shapes` and everything under them) since it
  had no remaining purpose there -- `PilFontMetrics`/`resolve_for_pptx` keep
  choosing a real font *file* for `fit` measurement independently (see the
  `text_sizes` note above; unaffected by this). python-pptx's `Font.name`
  only ever touches `<a:latin>` -- `<a:ea>` has no public API, so it's set
  directly on the run's `rPr` (checked: round-trips through a save/reopen).
  Reading a template's *actual* theme content (real font names, only for
  more accurate `fit` measurement now that `--template` exists too, below,
  without needing it) is still not done -- see the table below; staying
  symbolic sidesteps it entirely for correctness, so this is a pure
  accuracy nice-to-have, not a gap in what's emitted.
- **Object identity: names, groups, z-order** (`pik/layout.py`
  `_layout_statements`, `pptx_writer.py` `_add_all_shapes`, docs/spec.md
  SS3.1, ext -- previously not implemented at all despite being listed as
  v1 scope, found while working through the rest of this list):
  - **Shape names**: a pik label becomes the saved shape's real PowerPoint
    name; an unlabeled object gets `"<class> <n>"`, `n` counting *every*
    object of that kind in its scope, labeled or not (checked: `box "a"\n
    Web: box "b"\nbox "c"` names the third one `"box 3"`, not `"box 2"` --
    matches `resolve_object()`'s own `NthRef` pool-filter-by-kind, so a
    default name's number always agrees with what `"Nth box"` would
    address). A line's floating labels are named `"<line name> text <k>"`,
    `k` 1-based among that line's own labels.
  - **`behind X`**: places the object immediately before `X` in its
    scope's shape list -- draw order *is* z-order, so this is a plain
    list insert (`_layout_object()` now returns the resolved target
    too, alongside the shape, since it isn't in any pool yet when `behind`
    is applied). Found and fixed while implementing: `list.index()` uses
    `Shape`'s generated `==`, not identity, so two structurally-identical
    shapes (e.g. two bare `box`es) could resolve to the wrong one --
    `_index_by_identity()` uses `is` instead.
  - **Blocks are groups**: `LayoutResult.shapes` is now the shape *tree*
    (a "block" shape keeps its children under `.sublist` rather than being
    flattened away) -- `flatten_shapes()` (renamed, public; was the
    private `_flatten()`) is now for callers that want every eventual
    on-slide shape regardless of nesting (bounding-box math, mainly), not
    what a renderer draws. `_add_all_shapes()` draws a block as a real
    nested PowerPoint group, recursively, each with a fresh
    `_LocalTransform` scoped to *that* block's own bbox. Found and fixed
    while implementing: a python-pptx group's own `off`/`ext` (and
    `chOff`/`chExt`, its children's local coordinate frame) are
    recalculated from its actual contents on every `add_X()` call
    (checked against python-pptx's own source and docstring) -- so
    setting `.left`/`.top`/`.width`/`.height` *before* adding children
    (as seemed natural) just gets silently overwritten once they're
    added; children must be added first. Even then, a plain assignment
    (`group.left = Inches(x)`) is only safe when the block's own children
    never extend past its geometric bbox's corner -- true for shapes, but
    not always for a line's floating label, since `_LocalTransform` (unlike
    the top-level `_Transform`, via `_content_bbox()`) doesn't pad for
    that -- so the fix repositions by the *delta* to the target position
    (`group.left = Inches(target_left) + group.left`), not a replacement;
    checked with a deliberately overhanging label inside a block, and
    against real PowerPoint (nested and doubly-nested blocks, positioned
    correctly, `behind` ordering correct, both via direct python-pptx
    introspection and COM rendering).
- **`--template` and template settings files** (docs/spec.md SS3.3 rule 2,
  SS3.8, SS4.1): a settings file is a full, independent `parse()` of its
  own (`pik/layout.py` `_load_settings`) -- unlike an `include`, it is
  never merged into the *program*'s macro-expansion pass, so it needs no
  token-shape scan the way `include`'s definitions-only check does; the
  same "definitions only" rule is still enforced (every resulting
  statement must be an `AssignStatement`, exactly like the prelude's own
  assert, but a real diagnostic here since this file is user-authored).
  Layered prelude -> settings -> program, each overriding the last
  (`_Ctx.__init__`); `layout` (a new prelude default, `""`) can be
  assigned only while loading the prelude or a settings file, never a
  program (`_eval_assignment`'s `_layout_assignment_allowed` flag) --
  "a `.pik` never chooses the deck's structure". `content_left`/`_top`/
  `_right`/`_bottom` become `LayoutResult.content_area` (a `(left, top,
  width, height)` tuple) only when a settings file defines all four; it's
  `--into`'s default target when neither `--region` nor `--rect` is given.
  `primary`/`emphasis` (standard accent-color names) and `layout`/
  `typeface` are now real prelude defaults too (docs/spec.md SS3.7's own
  excerpt already specified them; they just hadn't been added to
  `prelude.pik` yet).

  `write_pptx_from_template()` (`pptx_writer.py`) builds the actual new
  deck: strips every existing slide (SS3.3: "stripped of its sample
  slides" -- generalized to any `--template`, not just a `.potx`, since
  standalone output is one new slide, not the template's own N plus one),
  resolves `layout` to a slide layout (named, found in any master, first
  match wins; empty, the first `blank`-type layout of the first master,
  or that master's own first layout if it has none -- checked: a
  real-world template's layouts commonly don't set the `type` attribute
  at all, so this fallback is the *common* case in practice, not a rare
  corner), and adds one new diagram-sized slide from it, so the new
  slide's theme (and, if `layout` was named explicitly, its placeholder
  shapes) come from the *right* master. A `.potx` is normalized first
  (`_normalize_potx`): python-pptx refuses one as-is (`ValueError`,
  checked) since the only actual difference from a `.pptx` is the content
  type declared for `/ppt/presentation.xml`, rewritten in a temp copy.
  Since colors and fonts are both emitted symbolically regardless (see
  their own bullets above), `--template` needed no theme-*content*
  reading at all to be correct -- the new slide's own theme reference
  resolves once the file is reopened, exactly like `--into`'s does against
  its target deck.

  Checked: a real multi-master `.potx` (Japanese layout names, no `type`
  attributes on any layout) opens, strips (already empty here), resolves
  its fallback layout correctly, and renders with correct symbolic
  colors/fonts; a synthetic `.potx` (an ordinary `.pptx` with its content
  type rewritten to simulate one, so tests don't depend on a real `.potx`
  file existing anywhere) round-trips the same way.
- **Diagnostics** (docs/spec.md SS5): `Token`/`PikSyntaxError` now carry
  `pos` (a character offset) and `file` (`pik/tokens.py`) -- `None` means
  the main source; an included file's resolved path otherwise, set once
  per `Lexer.tokenize()` call (the same for every token from one lex
  pass), not per-token, and threaded through every `include`-related
  `PikSyntaxError` site in `macros.py` (previously folded the path into
  the message *text* by hand only for a couple of them; the rest had no
  file information at all). `column_at(text, pos)` and
  `format_syntax_error(err, main_path, main_text)` (new) produce the
  `file:line:col: message`, the source line, and a caret docs/spec.md SS5
  asks for -- reading `err.file` again from disk for its own line when set
  (not cached: a diagnostic is the rare path). Checked: an error inside a
  *nested* `include` names the innermost file, not the outer one or the
  main source, since every token already carries whichever file its own
  lexer pass actually stamped it with.

  A `LayoutError` (undefined name, diagram larger than its region, and so
  on) still carries no position at all -- unlike a `PikSyntaxError`, it
  isn't raised from one token, and attaching real positions to every
  layout error would need line/col threaded through the whole `ast`
  module and most of `layout.py`'s ~1500 lines, not a small addition.
  Known gap against SS5's "every error carries file:line:column"; `main()`
  reports a `LayoutError` as a plain message either way.

  SS5 also promises "unknown names (color, theme slot, preset, image
  path, region) are errors with suggestions, not silent fallbacks" --
  found, on a re-check prompted directly by "did you actually finish
  this", not true for three of the five: only the preset-shape error
  (`_resolve_preset_name`, already had `difflib`-based suggestions) and
  the theme-slot error (`_resolve_theme_slot`, which lists *all* known
  slots rather than the closest ones -- correct as-is, since SS3.3's own
  text asks for exactly that for this one case, not a "did you mean")
  matched the promise. An undefined variable -- SS3.3's own example,
  `accent7` should get "did you mean `accent1`?" -- an unfound `image`
  path, and an unknown `--region` name all just raised a bare "not
  found"/"no such" error, no hint at all. Fixed with one shared helper
  (`_did_you_mean(name, candidates)`, `pik/layout.py`, the same
  `difflib.get_close_matches` the preset-shape error already used, now
  shared instead of inlined there only); `image`'s candidates are the
  filenames actually in the resolved directory, `--region`'s are the
  other named shapes on that slide.
- Tests: `box fill Red`/`box color DarkBlue` → lowercase (`red`/`darkblue`);
  coverage for colors, text sizes, the macro-shadow guard, Markdown
  names, preset shapes, images (including SVG), `include`, inserting into
  a deck, fonts, object identity (names/groups/z-order), templates and
  settings files, and diagnostics
  (`tests/test_layout.py`, `tests/test_pik_parser.py`,
  `tests/test_pptx_writer.py`, `tests/test_markdown.py`,
  `tests/test_cli.py`).

## Not yet started

Everything docs/spec.md marks as v1 scope (§1: theme colors and fonts,
object identity, insertion into an existing slide, preset shapes, images)
is implemented, along with the output model (§4), diagnostics (§5) and
Markdown integration (§6) built around it. What's left is smaller, and
each row is independent of the others:

| Area | Today | Needed |
|---|---|---|
| *(new)* theme reader | not needed for correctness -- colors and fonts both stay symbolic and resolve against whatever theme the target deck (or `--template`) actually has | only a `fit`-measurement accuracy improvement: real font *names* (not just `+mn-lt` symbols) would let `PilFontMetrics` pick a closer installed substitute; read `ppt/theme/*.xml`'s `<a:fontScheme>` (via the already-open `Presentation` for `--into`/`--template`, no raw zip work needed there) |
| `pik/layout.py` `LayoutError` | no position at all | `file`/`line`/`column`, matching what `PikSyntaxError` now has -- needs it threaded through `ast` and most of `layout.py`, not a small change (see the Diagnostics bullet above) |
| Docs | README's *Status* section | keep it in step with this file as items are implemented |
