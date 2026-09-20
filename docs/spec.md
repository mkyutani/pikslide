# pikslide language specification — draft 0.1

Status: **draft for review.** Every syntax example below marked *(proposed)*
is not implemented yet; examples without the mark run on today's parser
(checked against `src/pikslide/pik/parser.py`). The language itself is
defined, in BNF, in [grammar.md](grammar.md). Like the rest of `docs/`, this
document is written in English; keywords are English in any case.

## 1. What pikslide is

pikslide is a text language for drawing **diagrams that live inside Office
slides**. It descends from the *pic → pik (pikchr)* line: you don't write
coordinates, you place objects one after another in a direction and refer to
earlier objects by name. Where pikchr emits an SVG picture, pikslide emits
**native, editable PowerPoint objects**: shapes a person can select, restyle
and move after the fact.

The target is one *diagram*, not a deck. Deck structure (titles, ordering,
body text) belongs to whatever assembles the deck; pikslide places a diagram
into a slide that already exists.

### Scope of v1

v1 covers theme colours and fonts (§3.3), an editable structure of shape
names, groups and z-order (§3.1), insertion into an existing slide (§4.2),
preset shapes (§3.4), and images and icons (§3.5). What v1 leaves out is
listed in §7.

Placement stays pik's own: objects are placed one after another and relative
to one another, and there is no auto-layout. Humans and LLMs both write
pikslide, so the language is kept deterministic, unambiguous and short to
write, and errors point at exact positions (§5).

Where a diagram goes (which deck, slide and region, and which theme) is never
written in a `.pik`; see §4.

## 2. Compatibility contract with pikchr

1. **A valid pikchr program means the same thing in pikslide.** The existing
   parser/layout port and the official examples in `tests/fixtures/examples/`
   stay the regression suite. This is why pikslide is a superset rather than
   a derived dialect (which would break existing `.pik`) or an independent
   language (which would rewrite most of the parser). The one deliberate
   exception is **text size**
   (§3.3): pikchr gives it as a percentage of the viewer's font, pikslide as
   fixed sizes in points, so text (and `fit` objects sized to it) can differ
   from pikchr's output.
2. **Extensions are contextual.** A word is an extension keyword only in a
   position where pikchr would reject it (syntax error, or an undefined
   variable in a colour position). Evidence, on today's parser:
   - `shape = 3` is a valid pik assignment, so `shape` must **not** become a
     reserved word. It is an object class only when *not* followed by `=`.
   - `box fill accent1 lighter 40%` is a syntax error today
     (`unexpected trailing tokens near 'lighter'`), so `lighter` is free to
     claim.
3. **A user variable beats an extension name.** If a program defines
   `accent1 = 0xff0000`, `fill accent1` keeps meaning that variable, because
   otherwise a valid program would change meaning. This is deliberately
   *unlike* the existing CSS colour names: today the colour table is checked
   before variables (`white = 0xff0000` then `box fill white` is still
   white), and that behaviour is left as is.
4. **Portability check.** `pikslide --pikchr file.pik` rejects any extension,
   so an author can confirm a file still runs on real pikchr.
5. **File extension.** Source files keep `.pik`, whether or not they use
   extensions. Editor support for pik keeps working, and since most files use
   no extension, a separate extension would split things for little gain.

## 3. Extensions in v1

### 3.1 Object identity: names, groups, z-order

Goal: the Selection Pane in PowerPoint reads like the source.

- **Shape name.** A pik label names the shape: `Web: box "Web"` produces a
  shape named `Web`. Unlabelled objects are named `<class> <n>`, where `n` is
  the object's ordinal among that class in its scope (mirrors pik's `2nd box`).
- **Z-order** follows source order. `behind X` (already parsed, currently
  ignored) is honoured: the object is placed immediately below `X`.
- **Blocks are groups.** A `[ ... ]` block becomes a PowerPoint group named by
  its label (or `block <n>`); nesting is preserved.
- **Line labels.** A PowerPoint line cannot hold text, so a line's strings
  become text boxes named `<line name> text <k>`.
- `invis` objects are still emitted (no fill, no outline): they are legitimate
  text anchors.

### 3.2 Lines and arrows; `connector` is deferred

**v1 has no connectors.** `line`, `arrow`, `spline` and `arc` keep their
pikchr meaning: *a line drawn with fixed geometry*. They are emitted as plain
PowerPoint lines (a two-point path as a line, a longer path as a freeform),
with `dashed`, `dotted`, `thick`, `thin` and `<-`, `->`, `<->` mapped to dash
style, weight and arrowheads as today.

They are **never attached to shapes**, even when an endpoint lies exactly on
a shape's edge. Moving a box in PowerPoint leaves the line where it was.

**`connector` will be a separate object class, not something `arrow` turns
into.** In Office a connector is a *link between two objects*: it names its
two ends, follows them when they move, and chooses its own route. That is a
different idea from pik's arrow, which is only geometry, and inferring it
from where an arrow's endpoint happens to fall would be implicit and
surprising. So:

- `arrow` and `line` stay geometry, forever; nothing turns them into links.
- When links are added, they get their own word, `connector`, with explicit
  ends. Its syntax is not designed yet.

Groundwork already checked, for when `connector` is designed (python-pptx
1.0.2, drawn in PowerPoint):

- python-pptx creates straight and elbow (horizontal-first) connectors and
  attaches them to connection sites 0–3 (rectangle top, left, bottom, right).
- An elbow that must leave *vertically* needs hand-written `rot`/`flipV`
  (verified for one orientation). Sites 4 and up (an ellipse has eight)
  need hand-written `stCxn`/`endCxn`; the helper raises `KeyError`.
- A freeform does **not** follow when a shape moves; an attached connector
  does, and PowerPoint re-routes an attached elbow itself when that happens.

### 3.3 Theme colours and fonts

Colours can name a **theme slot** instead of an RGB value, so the diagram
follows whatever theme the slide uses.

```pik
box "Primary"  fill accent1                 # (proposed)
box "Soft"     fill accent1 lighter 40%     # (proposed)
box "Outline"  fill bg1 color text1         # (proposed)
```

- Slots: `accent1`–`accent6`, `text1`, `text2`, `bg1`, `bg2`, `link`,
  `followed`. They map to OOXML `schemeClr` values (`tx1`, `tx2`, `bg1`,
  `bg2`, `accent1`–`accent6`, `hlink`, `folHlink`).
- Modifiers: `lighter N%` / `darker N%`, following the PowerPoint palette
  ("Lighter 40%" = `lumMod 60 / lumOff 40`; "Darker 25%" = `lumMod 75`).
- Emitted as `schemeClr`, **never** as resolved RGB, so swapping the theme
  restyles the diagram. RGB (`0xRRGGBB`) and CSS names remain available.
- **Theme colours are direct operands of `fill` / `color` only.** They are
  not numbers: `x = accent1`, `accent1 + 1` and `print accent1` are errors.
  Reuse goes through macros, which are textual:
  `define primary { fill accent1 }`.
- **Fonts.** Text uses the theme's minor font (Latin `+mn-lt`, East Asian
  `+mn-ea`), not a hard-coded family. A new text flag `major` selects the
  heading font (`+mj-lt` / `+mj-ea`). A specific family is chosen outside the
  language (`--font`). This is the point that matters for Japanese: the
  deck's theme decides the CJK face.
- **Size.** Text size does **not** follow pikchr. pikchr states it as a
  percentage of whatever font the viewer uses (`big` = 125 %, `small` =
  80 %); PowerPoint needs points. pikslide has three sizes: `small` = 9 pt,
  `medium` = 10.5 pt (the default, so no flag is needed), and `large` or
  `big` = 12 pt (`big` is a synonym for `large`). The three values can be
  changed; where and how is not decided yet (open question 1). If a string
  carries more than one size flag, the last one wins, so pikchr's repeated
  `big big` has no extra effect. `fit` sizing measures with the size in
  effect.

**Where the theme comes from.** The tool reads it straight out of the file
the diagram is going into; the language never names a theme file.

1. `--into deck.pptx --slide N`: the theme of slide N's master
   (slide → layout → master → theme part). A deck with several masters has
   several themes, and the slide's own master decides.
2. Otherwise `--template FILE` (`.pptx` or `.potx`): the theme of its first
   master (provisional; see open question 1). Giving both `--into` and
   `--template` is an error, since the deck is already the template.
3. Otherwise the built-in Office theme, with a warning that colours and
   fonts are stand-ins.

Facts this rests on (checked): a valid theme always defines all 12 colour
slots (`dk1 lt1 dk2 lt2 accent1`–`6 hlink folHlink`) and both the major and
minor font, so **a valid slot name is never undefined**. What can go wrong
is only (a) no theme was supplied → rule 3; (b) the name is not a slot, e.g.
`accent7` → an ordinary undefined-variable error, with a "did you mean
`accent1`?" hint; (c) the program defines a variable of that name → the
variable wins (see the grammar's contextual-keyword rule).

Reading the theme needs only the zip (`ppt/theme/*.xml`), not python-pptx.
Writing is different: python-pptx refuses a `.potx` as-is (it raises
`ValueError`, checked), so a `.potx` used as a base is first normalised to a
presentation content type and stripped of its sample slides.

The theme yields font *names* only. `fit` sizing still measures with a
substitute font file on the machine, so widths are approximate for a face
that is not installed.

### 3.4 Preset shapes: `shape`

One new class keyword instead of ~180 reserved words:

```pik
shape chevron "Step 1" fit                  # (proposed)
shape roundRect "Card" fill accent2         # (proposed)
shape wedgeRectCallout "Note" fit           # (proposed)
```

- The name is an OOXML preset geometry (`prstGeom prst=…`, ECMA-376
  `ST_ShapeType`), matched case-insensitively. Unknown names are an error that
  lists the nearest matches.
- Behaves like `box`: default size `boxwid × boxht`; `width`, `height`, `fit`,
  `at`, `with`, `same`, text, `fill`, `color`, `dashed`, `thickness` all work.
  Edge names (`.n`, `.ne`, …) and `chop` refer to the **bounding rectangle**.
- No adjustment handles in v1 (default geometry), except `rad` on `roundRect`,
  already supported for `box`.
- Existing classes map onto presets as follows:

  | pik class | PowerPoint |
  |---|---|
  | `box` | `rect` (`roundRect` when `rad > 0`) |
  | `circle`, `ellipse`, `oval`, `dot` | `ellipse` |
  | `diamond` | `diamond` |
  | `cylinder` | `can` |
  | `file` | `flowChartDocument` (a document with a wavy bottom edge; it does not reproduce pikchr's folded top-right corner; chosen after comparing `snip1Rect` and `foldedCorner` rendered in PowerPoint) |
  | `text` | text box (no fill, no outline) |

### 3.5 Images and icons: `image`

```pik
Logo: image "logo.png" width 0.6in           # (proposed)
      image "icons/db.svg" height 0.4in alt "Database"   # (proposed) SVG icon
```

- A new class (contextual, as in §2). The string is a **path relative to the
  source file** (for Markdown, the `.md` file).
- Size: `width` and/or `height` given → the missing one follows the aspect
  ratio; both given → stretched; neither → fit inside `boxwid × boxht`,
  aspect preserved.
- Placed and referenced like any other object (edges, `at`, `with`; a
  picture is a rectangle).
- `alt "text"` sets the accessibility description (image only, v1).
- Text strings on an image are drawn as a separate text box centred on it.
- Formats: PNG, JPEG, GIF, and **SVG** (for icons, which stay sharp at any
  size). An SVG is embedded as PowerPoint's SVG picture together with a PNG
  fallback for older versions.
  Making that fallback needs an external rasteriser (for example
  `rsvg-convert`, from librsvg) on `PATH`; without it, an `.svg` is an error
  that names the missing tool. PNG, JPEG and GIF never need the tool.
  python-pptx cannot add an SVG (`add_picture` raises `TypeError`, checked),
  so the SVG picture is hand-written XML, **not yet checked in PowerPoint**.

### 3.6 Shared definitions: `include`

pikchr has no `include`, so a shared house style would have to be copied
into every diagram. A deck holds many diagrams, so pikslide adds one.

```pik
include "house.pik"                          # (proposed)
Web: box "Web" primary card                  # macros expand to attributes
```

```pik
# house.pik: definitions only
boxwid = 1.2
define primary { fill accent1 lighter 60% }
define card    { rad 8px color text1 }
```

- **Definitions only.** An included file may contain `define` macros,
  variable assignments (including `fill =`, `thickness =` …) and further
  `include`s. Any statement that draws an object, or a label, is an error.
  Placement, names and z-order therefore stay predictable, and reusable
  parts are written as macros (`define legend { [ … ] }`).
- **Same scope, in order.** Macros and variables defined by the file are
  visible from the `include` line onward, exactly as if written there.
- **Because theme colours are not numbers (§3.3), house colours are
  macros**, not variables.
- **Resolution.** The path is relative to the file containing the `include`
  (for a Markdown fence: to the `.md` file), then to each `--include-path DIR`.
- **Local and contained.** Only local files are read, never URLs. The
  resolved path must lie under the including file's directory or under an
  `--include-path` directory: absolute paths and `..` escapes are rejected.
  Diagnostics never quote the source line of an included file that failed
  the definitions-only check beyond the offending token. This matters
  because a diagram may be written by an LLM.
- Cycles are an error; nesting is limited to 50 levels (as for macros).

## 4. Output model

A `.pik` never names a deck, slide, region or theme file. Those come from the
command line or the caller, so the same diagram can be reused in any deck.

### 4.1 Standalone

Today's behaviour: a new one-slide presentation sized to the diagram plus a
margin. Kept, for previews and for producing a file to copy from.
`--template deck.pptx` (or a `.potx`) starts from that file's theme instead
of the built-in Office theme, so theme colours and fonts resolve the way the
real deck will (see §3.3).

### 4.2 Insert into an existing deck

```sh
pikslide diagram.pik --into deck.pptx --slide 5 --region "Figure" -o out.pptx
```

- `--slide` is 1-based. `--region` is the name of a shape or placeholder on
  that slide whose rectangle is the target; `--rect x,y,w,h` (inches) is the
  explicit alternative. When the region is an *empty placeholder*, it is
  deleted after the diagram is placed (an empty prompt left behind is clutter
  in edit view); any other shape used as a region is left alone. The theme is
  the deck's own (§3.3), so `--template` is not allowed alongside `--into`.
- The input deck is never modified in place unless `--in-place` is given.
- **Fit policy.** Uniform scale `s = min(1, region_w / w, region_h / h)`:
  shrink to fit, never enlarge. `s` is applied to **geometry, font size and
  line width at emit time** (a group transform would not scale text). Default
  alignment is top-left, under the slide title and in line with body text;
  `--align` overrides. If `s` pushes text below a floor size, warn.
- **Idempotent.** The whole diagram is emitted as one top-level group named
  `pikslide:<id>` (`<id>` = `--id`, else the source file's stem). Running
  again *replaces the group with the same name in place*, keeping its z-index
  and leaving everything else on the slide untouched.

## 5. Diagnostics

Humans and LLMs both need errors they can act on.

- Every error carries `file:line:column`, the source line, and a caret; the
  file is the included one when the error is inside an `include` (§3.6).
- Using the built-in theme because none was supplied is a **warning** (§3.3).
- Unknown extension names (theme slot, preset, `major`, image path, region)
  are **errors with suggestions**, not silent fallbacks. Today an unknown
  colour name silently becomes black; for legacy pik constructs that stays,
  as a warning, and `--strict` turns warnings into errors.
- `--check` parses and lays out without writing; `--format json` emits
  diagnostics as JSON for tooling.

## 6. Use from Markdown and from other tools

- Markdown fence tags: `pik` and `pikchr` as today, plus **`pikslide`**. A
  block that uses an extension fails under a plain pikchr renderer, so such
  blocks are tagged `pikslide`; a toolchain can then send ` ```pikchr `
  blocks to pikchr and ` ```pikslide ` blocks to pikslide.
- Slide and region come from the caller (command-line options), not from the
  block, per the placement decision.
- The diagram is written as native shapes directly, so a caller need not
  render a PNG, or convert a rendered diagram to shapes afterwards.
  `scripts/pptx_to_png.ps1` remains as the way to check the result.

## 7. Not in v1

Connectors (a future `connector` class, §3.2) · SVG *output* · auto-layout
and declarative graph syntax · tables, charts, SmartArt · animation,
transitions, speaker notes · multi-slide or whole-deck authoring · true
Bézier curves (`spline`/`arc` stay polylines) · shape adjustment handles ·
theme colours in variables and arithmetic.

SVG *images* are supported (§3.5); SVG *output* is left out because SVG
cannot express native shapes or theme colours. The layout result does not
depend on the output format, so SVG output can be added later. Auto-layout is
a large piece of work of its own.

## 8. Delta from the current implementation

| Area | Today | Needed |
|---|---|---|
| `pik/tokens.py` `CLASS_NAMES` | fixed 14 pikchr classes | contextual `shape`, `image`, `include`; `alt`, `lighter`/`darker`, `major`, `medium`, `large`; theme-slot names |
| `pik/tokens.py` `Token`, `PikSyntaxError` | carry a line number only | carry the source file and column, so errors inside an `include` point at the right file |
| `pik/macros.py` `expand_macros` | one source text, one macro table | resolve `include` in the same pass (shared macro table, definitions-only check, path containment, cycle/depth limits) |
| *(new)* theme reader | none | read `ppt/theme/*.xml` from a `.pptx`/`.potx` with `zipfile`; slide → layout → master → theme lookup; `.potx` normalisation for use as a base |
| `pik/layout.py` `_flatten` | flattens `[ ]` blocks, losing the tree | keep the hierarchy so groups can be written |
| `pik/layout.py` `Shape.fill` / `color` | `float` RGB ints | a paint value: `none` \| RGB \| theme slot + modifiers |
| `pik/layout.py` `behind` | parsed, ignored | affects z-order |
| `pptx_writer.py` `FONT_NAME`, `_BASE_FONT_PT` | hard-coded `"Arial"`, 9 pt | theme fonts; the three text sizes, default `medium` (10.5 pt) |
| `pik/layout.py` `_font_scale` | port of pikchr's `pik_font_scale()`: `big` ×1.25, `small` ×0.8 | three absolute sizes (`small` 9 / `medium` 10.5 / `large`=`big` 12 pt) |
| `pptx_writer.py` | always a new blank presentation | open an existing deck, insert group, replace by name, scale to fit |
| `pptx_writer.py` | `_AUTOSHAPE` fixed map; no pictures | preset map, `p:pic`, SVG picture (`svgBlip` + PNG fallback, hand-written XML), `schemeClr` |
| `__init__.py` | `pikslide <in> [<out>]` only | `--into --slide --region/--rect --id --template --include-path --font --align --strict --check --format --pikchr` |
| `markdown.py` | `pik`, `pikchr` fences | add `pikslide` |
| Docs | README states "pikslide doesn't define its own diagram language"; `pyproject.toml` mentions SVG | rewrite Scope; extend `docs/grammar.md` with an extensions section |

## 9. Open questions

1. **Settings.** How the three text sizes and other defaults are changed is
   not designed yet, and is to be considered as a whole. The defaults
   concerned are the text sizes (§3.3), the font, and which slide master a
   `--template` uses when it has several (§3.3 uses the first master
   meanwhile; that is provisional). The options are a configuration file,
   command-line options, or variables in the language.
