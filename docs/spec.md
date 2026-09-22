# pikslide language specification — draft 0.1

Status: **draft for review.** A syntax example marked *(proposed)* is not
implemented yet; one without the mark runs on today's parser (checked
against `src/pikslide/pik/parser.py`). Which parts of the language are
implemented changes as work continues, so it is tracked separately, in
[docs/implementation-plan.md](implementation-plan.md), rather than kept in
step with every marker here. The language itself is defined, in BNF, in
[grammar.md](grammar.md). Like the rest of `docs/`, this document is written
in English; keywords are English in any case.

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

## 2. Relation to pikchr

pikslide is its own language. It starts from pikchr's way of drawing
(sequential placement, relative positions, labels, text) and from pikchr's
grammar, but **compatibility with pikchr is not a goal**: a pikchr program may
run unchanged or may not, and where pikslide differs, this specification says
so.

- **Origin.** The parser and layout began as a port of pikchr and are changed
  step by step, not rewritten. pikchr's official example scripts
  (`tests/fixtures/examples/`) stay in the tests as a corpus for behaviour
  pikslide has not deliberately changed; a test that pins a deliberate
  difference is changed along with it.
- **New words are reserved.** The words pikslide adds (`shape`, `image`,
  `include`, `alt`, `theme`, `major`, `medium`, `large`, `lighter`, `darker`,
  `none`, `off`, and `connector` for later) are ordinary reserved words: they
  cannot be used as variable or macro names. Names such as `accent1` are not
  among them; the prelude defines those as ordinary variables (§3.7). See
  [grammar.md](grammar.md), *Reserved words*.
- **Colours are a type of their own.** A colour is not a number. It is an RGB
  value (a hex literal such as `0xff0000`) or a theme colour (§3.3), and
  variables can hold colours. Colour names such as `red` are not built into
  the language: they are ordinary variables defined by a prelude that is read
  first (§3.7), so a program can override them. An undefined name is an
  error.
- **Text size** is in points (§3.3); pikchr gives it as a percentage of the
  viewer's font.
- **File extension.** Source files keep `.pik`: editor support for pik keeps
  working, and the language is close enough to pikchr that a separate
  extension would gain little.

## 3. Features added in v1

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

Colours can refer to a **theme colour** instead of an RGB value, so the
diagram follows whatever theme the slide uses. The language has one word for
this, `theme`, which takes the name of a slot in the theme: `theme "accent1"`.
The usual slot names are defined for you as variables (§3.7), so programs
write:

```pik
box "Primary"  fill accent1
box "Soft"     fill accent1 lighter 40%
box "Outline"  fill bg1 color text1
```

- **`theme "slot"`.** The string is an OOXML `schemeClr` value (`accent1`–
  `accent6`, `tx1`, `tx2`, `bg1`, `bg2`, `dk1`, `lt1`, `dk2`, `lt2`, `hlink`,
  `folHlink`). A value the tool does not know is an error that lists the ones
  it knows. The language does not fix the list of slots: a PowerPoint version
  that adds one needs only a new definition (`dk3 = theme "dk3"`), not a
  language change.
- **Names come from the prelude.** `accent1`–`accent6`, `text1`, `text2`,
  `bg1`, `bg2`, `link` and `followed` are ordinary variables the prelude
  defines (`text1 = theme "tx1"`, `link = theme "hlink"`). They can be
  overridden, and more can be added.
- **Modifiers** `lighter N%` / `darker N%` apply to any colour: a theme
  colour, a hex colour, or a variable holding one. They follow the PowerPoint
  palette ("Lighter 40%" = `lumMod 60 / lumOff 40`; "Darker 25%" =
  `lumMod 75`); on an RGB colour they are emitted as the same transforms on
  `srgbClr`.
- Emitted as `schemeClr`, **never** as resolved RGB, so swapping the theme
  restyles the diagram. RGB (`0xRRGGBB`) and the CSS colour names (from the
  prelude, §3.7) remain available.
- **Colours are a type of their own** (§2). A variable can hold one, so a
  house style is plain variables: `primary = accent1 lighter 60%`, then
  `box fill primary`. A colour is not a number: `primary + 1` is an error.
- **Fonts.** Text uses the theme's minor font (Latin `+mn-lt`, East Asian
  `+mn-ea`), not a hard-coded family. A new text flag `major` selects the
  heading font (`+mj-lt` / `+mj-ea`). A specific family is set with the
  string variable `typeface` (`typeface = "BIZ UDPゴシック"`), normally in the
  template's settings file (§3.8); the prelude gives it the empty string,
  which means the theme's font. This is the point that matters for Japanese:
  the deck's theme decides the CJK face.
- **Size.** Text size does **not** follow pikchr. pikchr states it as a
  percentage of whatever font the viewer uses (`big` = 125 %, `small` =
  80 %); PowerPoint needs points. pikslide has three sizes: `small` = 9 pt,
  `medium` = 10.5 pt (the default, so no flag is needed), and `large` or
  `big` = 12 pt (`big` is a synonym for `large`). Like `fill`, `color` and
  `thickness`, the words themselves can be assigned to set their values; the
  prelude (§3.7) has `small = 9pt`, `medium = 10.5pt`, `large = 12pt`. Assign
  to them to change the sizes, or set them in the template's settings file
  (§3.8). If a string
  carries more than one size flag, the last one wins, so pikchr's repeated
  `big big` has no extra effect. `fit` sizing measures with the size in
  effect.

**Where the theme comes from.** The tool reads it straight out of the file
the diagram is going into; the language never names a theme file.

1. `--into deck.pptx --slide N`: the theme of slide N's master
   (slide → layout → master → theme part). A deck with several masters has
   several themes, and the slide's own master decides.
2. Otherwise `--template FILE` (`.pptx` or `.potx`): the theme of the master
   that owns the slide layout its settings file names with `layout` (§3.8),
   or of its first master when there is none. Giving both `--into` and
   `--template` is an error, since the deck is already the template.
3. Otherwise the built-in Office theme, with a warning that colours and
   fonts are stand-ins.

Facts this rests on (checked): a valid theme always defines all 12 colour
slots (`dk1 lt1 dk2 lt2 accent1`–`6 hlink folHlink`) and both the major and
minor font, so **a valid slot name is never undefined**. What can go wrong
is only (a) no theme was supplied → rule 3; (b) a name is not defined, e.g.
`accent7` → an ordinary undefined-variable error, with a "did you mean
`accent1`?" hint; (c) `theme "accent7"` names no slot → an error that lists
the slots the tool knows.

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
shape chevron "Step 1" fit
shape roundRect "Card" fill accent2
shape wedgeRectCallout "Note" fit
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
Logo: image "logo.png" width 0.6in
      image "icons/db.svg" height 0.4in alt "Database"   # (proposed) SVG icon
```

- A new class. The string is a **path relative to the
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
Web: box "Web" fill primary card            # a colour variable, a macro
```

```pik
# house.pik: definitions only
boxwid = 1.2
primary = accent1 lighter 60%
define card { rad 8px color text1 }
```

- **Definitions only.** An included file may contain `define` macros,
  variable assignments (including `fill =`, `thickness =` …) and further
  `include`s. Any statement that draws an object, or a label, is an error.
  Placement, names and z-order therefore stay predictable, and reusable
  parts are written as macros (`define legend { [ … ] }`).
- **Same scope, in order.** Macros and variables defined by the file are
  visible from the `include` line onward, exactly as if written there.
- **House colours are variables** holding colours (§3.3); macros are for
  bundles of attributes such as `card`.
- **Resolution.** The path is relative to the file containing the `include`
  (for a Markdown fence: to the `.md` file), then to each `--include-path DIR`.
- **Local and contained.** Only local files are read, never URLs. The
  resolved path must lie under the including file's directory or under an
  `--include-path` directory: absolute paths and `..` escapes are rejected.
  Diagnostics never quote the source line of an included file that failed
  the definitions-only check beyond the offending token. This matters
  because a diagram may be written by an LLM.
- Cycles are an error; nesting is limited to 50 levels (as for macros).
- **A macro cannot shadow a variable.** `define` and variable assignment
  share the token-substitution pass, so a macro named after an existing
  variable (a prelude colour or default, a settings-file name, or one
  from an earlier `include`) would silently replace every later use of
  that name, including as an assignment target. `define <name> { … }` is
  an error when `<name>` is already a variable; see
  [grammar.md](grammar.md), *Macros*.

### 3.7 The prelude

Before every program, pikslide reads a **prelude**: a file of definitions that
ships with it (`src/pikslide/prelude.pik`). It follows the rules of an
included file (§3.6): definitions only.

```pik
# prelude.pik (excerpt)
black      = 0x000000
red        = 0xff0000
lightblue  = 0xadd8e6

accent1    = theme "accent1"   # accent2 … accent6 likewise
text1      = theme "tx1"
text2      = theme "tx2"
bg1        = theme "bg1"
bg2        = theme "bg2"
link       = theme "hlink"
followed   = theme "folHlink"

boxwid     = 0.75
linewid    = 0.5
thickness  = 0.015
fill       = none
color      = black

small      = 9pt
medium     = 10.5pt
large      = 12pt

layout     = ""
typeface   = ""

primary    = text2
emphasis   = accent1
```

- **It defines the CSS colour names** as variables holding colours. Nothing
  about colour names is special in the language: `red` is a variable, like
  `boxwid`.
- **It defines the theme-colour names** `accent1`–`accent6`, `text1`, `text2`,
  `bg1`, `bg2`, `link` and `followed`, with `theme` (§3.3). They are ordinary
  variables, so a template's settings file can redefine or add them.
- **It defines the built-in defaults.** The 33 variables that pikchr keeps in
  a table in its code (`boxwid`, `linewid`, `charwid`, `thickness`, `fill`,
  `color`, and so on) are defined here instead, so the defaults are readable
  and changeable in one place.
- **It defines the three text sizes** (§3.3). Lengths are inches internally,
  so `9pt` is 9/72 in; the PowerPoint writer converts back to points.
- **It defines `layout` and `typeface`**, both empty strings: the slide layout
  for a new slide and the font family (§3.3, §3.8). The PowerPoint writer
  reads them, not the layout stage.
- **It defines the standard accent-colour names** `primary` and `emphasis`,
  so a diagram that uses them runs with any template; a template's settings
  file (§3.8) gives them that template's own colours.
- **Everything in it can be overridden.** The prelude comes first, so an
  assignment in the program, or in an `include`d file, wins: `red = 0xcc0000`,
  `boxwid = 1.2`, `medium = 11pt`, or a project's house file that
  redefines a palette. New names are added the same way (`brand = 0x123456`).
- **It cannot be switched off.** The layout reads these variables, so a run
  without them would fail. A project's own definitions are layered on top of
  it, by an `include` (§3.6) or by a settings file (§3.8), which `--settings
  FILE` supplies from outside the program.
- **Names are lowercase**, like every variable. pikchr's capitalised
  spellings (`Red`, `DarkBlue`) are not colours; a capitalised name is an
  object label.
- **A hex literal is a colour.** `0xRRGGBB` is a colour value, not a number;
  decimal numbers are numbers.
- **`none` and `off`** (*no colour*) cannot be written as a value, so they
  remain reserved words ([grammar.md](grammar.md), *Reserved words*).

### 3.8 Template settings

Which theme, which slide layout and which accent colours suit a diagram
depend on the template it goes into, and so do sensible text sizes. These
choices therefore belong to the template, not to the diagram and not to the
tool. Each `.potx` or `.pptx` used with `--template` or `--into` can have a
**settings file**, found beside it or named with `--settings FILE`, which
holds:

- the slide layout for a new slide (`layout`), which also fixes the master
  and so the theme (§3.3);
- the font (`typeface`, §3.3);
- the accent colours: which of the theme's colours the diagram uses for
  emphasis. `primary` and `emphasis` are the standard names (§3.7); a
  template may define others;
- the default text sizes (`small`, `medium`, `large`, §3.7);
- the content area: the rectangle of a slide that a diagram may use, which is
  the default target of `--into` (§4.2).

The settings file is read after the prelude and before the program, so its
definitions override the prelude's, and the program's override its own. A
template without one gets the prelude's defaults and its first master's blank
layout. A
`.pik` still never names the file: the tool finds it from the template or
deck the diagram goes into, or the caller names it (§4).

```pik
# corporate.theme.pik (beside corporate.potx)
layout        = "1_本文"   # the layout for a new slide; fixes the master too
typeface      = "BIZ UDPゴシック"
medium        = 12pt       # this template's diagram text size
primary       = text2      # the standard accent-colour names
emphasis      = accent1
warning       = accent5    # any further names the template wants
content_left   = 15pt       # where a diagram may go on a slide
content_top    = 37.5pt
content_right  = 944.9pt
content_bottom = 534.6pt
```

- **Format.** The prelude's own: a file of definitions only, as in §3.6. It
  is read by the tool, not through `include`, so the path rules of §3.6 do not
  apply to finding it; the definitions-only rule does apply to its content.
- **Location.** Beside the template or deck by default. `--settings FILE`
  names it explicitly, wherever it is (a shared folder, say); nothing is then
  looked for beside the template. The caller names it, so the path rules of
  §3.6 do not apply. A named file that does not exist is an error.
  `--settings` also works when no template is given, to set text sizes and
  accent colours for the built-in theme.
- **Name.** `<template name>.theme.pik` beside the template or deck
  (`corporate.potx` → `corporate.theme.pik`).
- **`layout`** is the name of a slide layout, used when pikslide makes a new
  slide from the template (with `--into` the slide already has its layout).
  A layout belongs to one master, so naming it also chooses the master and
  the theme. The prelude gives it the empty string, which means the first
  layout of type `blank` in the first master, or that master's first layout
  if it has none. If two masters have a layout of that name, the first one
  found wins. A name that no layout has is an error that lists the names it
  does have. `layout` can be set only in a settings file: assigning it in a
  program is an error, because a `.pik` never chooses the deck's structure.
- **Strings.** A variable can hold a string, written as in text
  (`typeface = "…"`). A string is not a number and cannot be used in an
  expression; in v1 strings serve settings only, and a string variable is not
  accepted as the text of an object.
- **Accent colours** are ordinary colour variables (§3.3) whose values are
  theme colours: `primary = text2`, or `primary = accent2 lighter 40%`. A
  value that is a theme colour stays linked to the theme, so switching the
  template's theme restyles the diagram.

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
  explicit alternative. With neither, the target is the content area from
  the settings file (§3.8), and with none of the three it is an error. When
  the region is an *empty placeholder*, it is
  deleted after the diagram is placed (an empty prompt left behind is clutter
  in edit view); any other shape used as a region is left alone. The theme is
  the deck's own (§3.3), so `--template` is not allowed alongside `--into`.
- The input deck is never modified in place unless `--in-place` is given.
- **No scaling.** A diagram is placed at its natural size and is never
  scaled: the text sizes and line widths are the author's, and an automatic
  reduction could leave text too small to read. A diagram that is larger than
  its region is an **error** that reports both sizes (the diagram's bounding
  box, line labels included, and the region's); the source is then adjusted.
  A smaller diagram is placed at the region's top-left, under the slide title
  and in line with body text; `--align` overrides.
- **Idempotent.** The whole diagram is emitted as one top-level group named
  `pikslide:<id>` (`<id>` = `--id`, else the diagram's name in a Markdown fence (§6), else the
  source file's stem). Running
  again *replaces the group with the same name in place*, keeping its z-index
  and leaving everything else on the slide untouched.

## 5. Diagnostics

Humans and LLMs both need errors they can act on.

- Every error carries `file:line:column`, the source line, and a caret; the
  file is the included one when the error is inside an `include` (§3.6).
- Using the built-in theme because none was supplied is a **warning** (§3.3).
- A diagram larger than its region is an **error** (§4.2).
- Unknown names (colour, theme slot, preset, image path, region) are
  **errors with suggestions**, not silent fallbacks. `--strict` turns
  warnings into errors.
- A `define` naming an already-defined variable is an **error** (§3.6).
- `--check` parses and lays out without writing; `--format json` emits
  diagnostics as JSON for tooling.

## 6. Use from Markdown and from other tools

- Markdown fence tag: **`pikslide`** names this language, so a toolchain can
  send ` ```pikchr ` blocks to pikchr and ` ```pikslide ` blocks to pikslide.
  pikslide keeps accepting `pik` and `pikchr` fences as it does today.
- **Diagram names.** A fence may name its diagram with the word after the
  language tag: ` ```pikslide architecture `. A Markdown file with more than
  one diagram must name every one of them; a missing or duplicate name is an
  error. A file with a single diagram needs no name. Names use letters,
  digits, `-` and `_`. The name is the diagram's id (§4.2), and `--block NAME`
  selects one diagram of the file, which `--into` needs because it places one
  diagram.
- Slide and region come from the caller (command-line options), not from the
  block, per the placement decision.
- The diagram is written as native shapes directly, so a caller need not
  render a PNG, or convert a rendered diagram to shapes afterwards.
  `scripts/pptx_to_png.ps1` remains as the way to check the result.

## 7. Not in v1

Connectors (a future `connector` class, §3.2) · SVG *output* (SVG *images*
are supported, §3.5) · auto-layout and declarative graph syntax (a large
piece of work of its own) · tables, charts, SmartArt · animation,
transitions, speaker notes · multi-slide or whole-deck authoring · true
Bézier curves (`spline`/`arc` stay polylines) · shape adjustment handles ·
arithmetic on colours.

## 8. Implementation status

The gap between this specification and the current code is tracked
separately, in [implementation-plan.md](implementation-plan.md), since it
changes on a different schedule than the language itself.
