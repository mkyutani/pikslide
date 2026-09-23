# pikslide language specification — draft 0.1

Status: **draft for review.** v1 (§1) is fully implemented; every syntax
example here runs as shown (checked against `src/pikslide/pik/parser.py`).
The language itself is defined, in BNF, in [grammar.md](grammar.md). Like
the rest of `docs/`, this document is written in English; keywords are
English in any case.

## 1. What pikslide is

pikslide is a text language for drawing **diagrams that live inside Office
slides**. You don't write coordinates: you place objects one after another
in a direction, and refer to earlier objects by name. A diagram becomes
**native, editable PowerPoint objects**: shapes a person can select,
restyle and move after the fact. (pikslide's own design traces back
through two earlier languages; see Acknowledgments, §8.)

The target is one *diagram*, not a deck. Deck structure (titles, ordering,
body text) belongs to whatever assembles the deck; pikslide writes a diagram
as a one-slide deck, sized to it, whose shapes are copied or moved into the
real deck from there.

### Scope of v1

v1 covers theme colors and fonts (§3.3), an editable structure of shape
names, groups and z-order (§3.1), preset shapes (§3.4), and images and icons (§3.5). What v1 leaves out is
listed in §7.

Placement is sequential and relative: objects are placed one after another
and relative to one another, and there is no auto-layout. Humans and LLMs
both write pikslide, so the language is kept deterministic, unambiguous and
short to write, and errors point at exact positions (§5).

Where a diagram goes (which deck, slide and region, and which theme) is never
written in a `.pik`; see §4.

## 2. Design principles

- **Colors are a type of their own.** A color is not a number. It is an RGB
  value (a hex literal such as `0xff0000`) or a theme color (§3.3), and
  variables can hold colors. Color names such as `red` are not built into
  the language: they are ordinary variables defined by a prelude that is read
  first (§3.7), so a program can override them. An undefined name is an
  error. Arithmetic on a color (`primary + 1`) is an error too.
- **New words are reserved.** The words `shape`, `image`, `include`, `alt`,
  `theme`, `major`, `medium`, `large`, `lighter`, `darker`, `none`, `off`,
  and `connector` (for later) are ordinary reserved words: they cannot be
  used as variable or macro names. Names such as `accent1` are not among
  them; the prelude defines those as ordinary variables (§3.7). See
  [grammar.md](grammar.md), *Reserved words*.
- **Text size** is in points, not a percentage (§3.3).
- **File extension.** Source files use `.pik`, for the syntax-highlighting
  and editor support that extension already carries in the wild.

## 3. Features added in v1

### 3.1 Object identity: names, groups, z-order

Goal: the Selection Pane in PowerPoint reads like the source.

- **Shape name.** A label names the shape: `Web: box "Web"` produces a
  shape named `Web`. Unlabeled objects are named `<class> <n>`, where `n` is
  the object's ordinal among that class in its scope (the same ordinal a
  `2nd box` reference would address).
- **Z-order** follows source order. `behind X` is honoured: the object is
  placed immediately below `X`.
- **Blocks are flattened, not grouped.** A `[ ... ]` block is a grouping
  construct in the *source* only: pikslide never emits a PowerPoint group for
  it (or anywhere else). Its children become ordinary, individually-
  selectable top-level shapes, each keeping its own name; the block's own
  label has no shape of its own. (PowerPoint's own group-resize math was
  found to silently distort a group's *children*'s sizes, so pikslide's
  output never contains a group at all.)
- **Line labels.** A PowerPoint line cannot hold text, so a line's strings
  become text boxes named `<line name> text <k>`.
- `invis` objects are still emitted (no fill, no outline): they are legitimate
  text anchors.

### 3.2 Lines and arrows; `connector` is deferred

**v1 has no connectors.** `line`, `arrow`, `spline` and `arc` are *lines
drawn with fixed geometry*. They are emitted as plain PowerPoint lines (a
two-point path as a line, a longer path as a freeform), with `dashed`,
`dotted`, `thick`, `thin` and `<-`, `->`, `<->` mapped to dash style,
weight and arrowheads.

They are **never attached to shapes**, even when an endpoint lies exactly on
a shape's edge. Moving a box in PowerPoint leaves the line where it was.

**`connector` will be a separate object class, not something `arrow` turns
into.** In Office a connector is a *link between two objects*: it names its
two ends, follows them when they move, and chooses its own route. That is a
different idea from `arrow`, which is only geometry, drawn once and never
re-routed — inferring a link from where an arrow's endpoint happens to fall
would be implicit and surprising. So:

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

### 3.3 Theme colors and fonts

Colors can refer to a **theme color** instead of an RGB value, so the
diagram follows whatever theme the slide uses. The language has one word for
this, `theme`, which takes the name of a slot in the theme: `theme "accent1"`.
The usual slot names are defined for you as variables (§3.7), so programs
write:

```pikslide
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
- **Modifiers** `lighter N%` / `darker N%` apply to any color: a theme
  color, a hex color, or a variable holding one. They follow the PowerPoint
  palette ("Lighter 40%" = `lumMod 60 / lumOff 40`; "Darker 25%" =
  `lumMod 75`); on an RGB color they are emitted as the same transforms on
  `srgbClr`.
- Emitted as `schemeClr`, **never** as resolved RGB, so swapping the theme
  restyles the diagram. RGB (`0xRRGGBB`) and the CSS color names (from the
  prelude, §3.7) remain available.
- **Colors are a type of their own** (§2). A variable can hold one, so a
  house style is plain variables: `primary = accent1 lighter 60%`, then
  `box fill primary`. A color is not a number: `primary + 1` is an error.
- **Fonts.** Text uses the theme's minor font (Latin `+mn-lt`, East Asian
  `+mn-ea`), not a hard-coded family. A new text flag `major` selects the
  heading font (`+mj-lt` / `+mj-ea`). A specific family is set with the
  string variable `typeface` (`typeface = "BIZ UDPゴシック"`), normally in the
  template's settings file (§3.8); the prelude gives it the empty string,
  which means the theme's font. This is the point that matters for Japanese:
  the deck's theme decides the CJK face.
- **Size.** PowerPoint needs points, not a percentage of the viewer's own
  font. pikslide has three sizes: `small` = 9 pt, `medium` = 10.5 pt (the
  default, so no flag is needed), and `large` or `big` = 12 pt (`big` is a
  synonym for `large`). Like `fill`, `color` and `thickness`, the words
  themselves can be assigned to set their values; the prelude (§3.7) has
  `small = 9pt`, `medium = 10.5pt`, `large = 12pt`. Assign to them to
  change the sizes, or set them in the template's settings file (§3.8). If
  a string carries more than one size flag, the last one wins. `fit` sizing
  measures with the size in effect.

**Where the theme comes from.** The tool reads it from the template named
on the command line; the language never names a theme file.

1. `--template FILE` (`.pptx` or `.potx`): the theme of the master that owns
   the slide layout named by `--layout` or its settings file's `layout`
   (§3.8), or of its first master when there is none.
2. Otherwise the built-in Office theme, with a warning that colors and
   fonts are stand-ins.

Facts this rests on (checked): a valid theme always defines all 12 color
slots (`dk1 lt1 dk2 lt2 accent1`–`6 hlink folHlink`) and both the major and
minor font, so **a valid slot name is never undefined**. What can go wrong
is only (a) no theme was supplied → rule 2; (b) a name is not defined, e.g.
`accent7` → an ordinary undefined-variable error, with a "did you mean
`accent1`?" hint; (c) `theme "accent7"` names no slot → an error that lists
the slots the tool knows.

Colors and fonts are both emitted as symbolic references (`schemeClr`,
`+mn-lt`/`+mj-lt`, …), never resolved here, so no theme file's *content*
ever needs reading for either to be correct: PowerPoint itself resolves
the reference once the diagram sits inside a `--template`'s own theme
(rule 1), or inside a real deck its shapes are copied into. Writing is
the one place a `.potx` needs touching directly: python-pptx refuses one
as-is (it raises `ValueError`, checked), so a `.potx` used as a
`--template` base is first normalized to a presentation content type and
stripped of its sample slides.

`fit` sizing measures with a fixed substitute font file on the machine,
independent of the theme (whose actual font *name* is never read), so
widths are approximate for a face that is not installed.

### 3.4 Preset shapes: `shape`

One new class keyword instead of ~180 reserved words:

```pikslide
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

  | Class | PowerPoint |
  |---|---|
  | `box` | `rect` (`roundRect` when `rad > 0`) |
  | `circle`, `ellipse`, `oval`, `dot` | `ellipse` |
  | `diamond` | `diamond` |
  | `cylinder` | `can` |
  | `file` | `foldedCorner` (a page with a corner folded down) |
  | `text` | text box (no fill, no outline) |

### 3.5 Images and icons: `image`

```pikslide
Logo: image "logo.png" width 0.6in
      image "icons/db.svg" height 0.4in alt "Database"   # an SVG icon
```

- A new class. The string is a **path relative to the
  source file**.
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
  so the SVG picture is hand-written XML (checked against real PowerPoint:
  it renders the SVG itself, not the fallback, when they're made to differ).

### 3.6 Shared definitions: `include`

A deck typically holds many diagrams that share a house style — colors,
macros, defaults — so pikslide provides `include` to define these once and
bring them into each diagram, rather than copying them everywhere:

```pikslide
include "house.pik"
Web: box "Web" fill primary card            # a color variable, a macro
```

```pikslide
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
- **House colors are variables** holding colors (§3.3); macros are for
  bundles of attributes such as `card`.
- **Resolution.** The path is relative to the file containing the `include`,
  then to each `--include-path DIR`.
- **Local and contained.** Only local files are read, never URLs. The
  resolved path must lie under the including file's directory or under an
  `--include-path` directory: absolute paths and `..` escapes are rejected.
  Diagnostics never quote the source line of an included file that failed
  the definitions-only check beyond the offending token. This matters
  because a diagram may be written by an LLM.
- Cycles are an error; nesting is limited to 50 levels (as for macros).
- **A macro cannot shadow a variable.** `define` and variable assignment
  share the token-substitution pass, so a macro named after an existing
  variable (a prelude color or default, a settings-file name, or one
  from an earlier `include`) would silently replace every later use of
  that name, including as an assignment target. `define <name> { … }` is
  an error when `<name>` is already a variable; see
  [grammar.md](grammar.md), *Macros*.

### 3.7 The prelude

Before every program, pikslide reads a **prelude**: a file of definitions that
ships with it (`src/pikslide/prelude.pik`). It follows the rules of an
included file (§3.6): definitions only.

```pikslide
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

- **It defines the CSS color names** as variables holding colors. Nothing
  about color names is special in the language: `red` is a variable, like
  `boxwid`.
- **It defines the theme-color names** `accent1`–`accent6`, `text1`, `text2`,
  `bg1`, `bg2`, `link` and `followed`, with `theme` (§3.3). They are ordinary
  variables, so a template's settings file can redefine or add them.
- **It defines the built-in defaults.** Default object sizes and drawing
  style (`boxwid`, `linewid`, `charwid`, `thickness`, `fill`, `color`, and
  so on) are defined here, so the defaults are readable and changeable in
  one place.
- **It defines the three text sizes** (§3.3). Lengths are inches internally,
  so `9pt` is 9/72 in; the PowerPoint writer converts back to points.
- **It defines `layout` and `typeface`**, both empty strings: the slide layout
  for a new slide and the font family (§3.3, §3.8). The PowerPoint writer
  reads them, not the layout stage.
- **It defines the standard accent-color names** `primary` and `emphasis`,
  so a diagram that uses them runs with any template; a template's settings
  file (§3.8) gives them that template's own colors.
- **Everything in it can be overridden.** The prelude comes first, so an
  assignment in the program, or in an `include`d file, wins: `red = 0xcc0000`,
  `boxwid = 1.2`, `medium = 11pt`, or a project's house file that
  redefines a palette. New names are added the same way (`brand = 0x123456`).
- **It cannot be switched off.** The layout reads these variables, so a run
  without them would fail. A project's own definitions are layered on top of
  it, by an `include` (§3.6) or by a settings file (§3.8), which `--settings
  FILE` supplies from outside the program.
- **Names are lowercase**, like every variable. A capitalized name (`Red`,
  `DarkBlue`) is not a color — capitalization means an object label.
- **A hex literal is a color.** `0xRRGGBB` is a color value, not a number;
  decimal numbers are numbers.
- **`none` and `off`** (*no color*) cannot be written as a value, so they
  remain reserved words ([grammar.md](grammar.md), *Reserved words*).

### 3.8 Template settings

Which theme, which slide layout and which accent colors suit a diagram
depend on the template it goes into, and so do sensible text sizes. These
choices therefore belong to the template, not to the diagram and not to the
tool. Each `.potx` or `.pptx` used with `--template` can have a **settings
file**, found beside it or named with `--settings FILE`, which holds:

- the slide layout for a new slide (`layout`), which also fixes the master
  and so the theme (§3.3);
- the font (`typeface`, §3.3);
- the accent colors: which of the theme's colors the diagram uses for
  emphasis. `primary` and `emphasis` are the standard names (§3.7); a
  template may define others;
- the default text sizes (`small`, `medium`, `large`, §3.7).

The settings file is read after the prelude and before the program, so its
definitions override the prelude's, and the program's override its own. A
template without one gets the prelude's defaults and its first master's blank
layout. A
`.pik` still never names the file: the tool finds it from the template, or
the caller names it (§4).

```pikslide
# corporate.theme.pik (beside corporate.potx)
layout        = "1_本文"   # the layout for a new slide; fixes the master too
typeface      = "BIZ UDPゴシック"
medium        = 12pt       # this template's diagram text size
primary       = text2      # the standard accent-color names
emphasis      = accent1
warning       = accent5    # any further names the template wants
```

- **Format.** The prelude's own: a file of definitions only, as in §3.6. It
  is read by the tool, not through `include`, so the path rules of §3.6 do not
  apply to finding it; the definitions-only rule does apply to its content.
- **Location.** Beside the template by default. `--settings FILE`
  names it explicitly, wherever it is (a shared folder, say); nothing is then
  looked for beside the template. The caller names it, so the path rules of
  §3.6 do not apply. A named file that does not exist is an error.
  `--settings` also works when no template is given, to set text sizes and
  accent colors for the built-in theme.
- **Name.** `<template name>.theme.pik` beside the template
  (`corporate.potx` → `corporate.theme.pik`).
- **`layout`** is the name of a slide layout, used when pikslide makes a new
  slide from the template. A layout belongs to one master, so naming it also chooses the master and
  the theme. The prelude gives it the empty string, which means the first
  layout of type `blank` in the first master, or that master's first layout
  if it has none. If two masters have a layout of that name, the first one
  found wins. A name that no layout has is an error that lists the names it
  does have. `layout` can be set only in a settings file: assigning it in a
  program is an error, because a `.pik` never chooses the deck's structure.
  The caller can also name it with `--layout NAME`, which overrides the
  settings file's (so a script choosing a layout per template needs no
  settings file written for it); it needs `--template`.
- **Strings.** A variable can hold a string, written as in text
  (`typeface = "…"`). A string is not a number and cannot be used in an
  expression; in v1 strings serve settings only, and a string variable is not
  accepted as the text of an object.
- **Accent colors** are ordinary color variables (§3.3) whose values are
  theme colors: `primary = text2`, or `primary = accent2 lighter 40%`. A
  value that is a theme color stays linked to the theme, so switching the
  template's theme restyles the diagram.

## 4. Output model

A `.pik` never names a deck, slide or theme file. Those come from the command
line or the caller, so the same diagram can be reused in any deck.

```sh
pikslide diagram.pik [OUTPUT.pptx] [--template FILE] [--layout NAME] [--settings FILE] [--png [PATH]] [--pdf [PATH]] [--renderer R]
```

`OUTPUT` omitted, the parsed tree is dumped instead of writing anything
(unless `--template` is given, see below). Otherwise a new one-slide
presentation is written there, sized to the diagram plus a margin, and an
existing file is overwritten. `--template deck.pptx` (or a `.potx`) starts
from that file's theme instead of the built-in Office theme, so theme colors
and fonts resolve the way the real deck will (see §3.3); when `OUTPUT` is
omitted but `--template` is given, it defaults to `INPUT` with its extension
changed to `.pptx` (`diagram.pik` → `diagram.pptx`).

A diagram is never scaled: the text sizes and line widths are the author's.

`OUTPUT` is always a `.pptx`. `--png` and `--pdf` are a post-processing
step on top of it: after the deck is written, its slide is also rendered
to a PNG or a PDF, at `PATH`, or when `PATH` is omitted at `OUTPUT` with
its extension changed (`diagram.pptx` → `diagram.png`). Both need a deck
to be written, so they are errors with no `OUTPUT` (and no `--template`)
or with `--check`, and `PATH` must end in `.png`/`.pdf`. Rendering uses
PowerPoint through COM automation when it is reachable (Windows, or WSL
with a Windows PowerPoint install), since that is the renderer the output
is meant for; otherwise LibreOffice, with a note (not a warning: it says
how the image was made, not that anything is wrong with the diagram, so
`--strict` leaves it alone) that its rendering is not PowerPoint's. With
neither, it is an error. `--renderer powerpoint|libreoffice` uses only
that one; the default, `auto`, is the order above.

## 5. Diagnostics

Humans and LLMs both need errors they can act on.

- Every error carries `file:line:column`, the source line, and a caret; the
  file is the included one when the error is inside an `include` (§3.6).
- Using the built-in theme because none was supplied is a **warning** (§3.3).
- Unknown names (color, theme slot, preset, image path) are
  **errors with suggestions**, not silent fallbacks. `--strict` turns
  warnings into errors.
- A `define` naming an already-defined variable is an **error** (§3.6).
- `--check` parses and lays out without writing; `--format json` emits
  diagnostics as JSON for tooling.

## 6. Use from other tools

- The diagram is written as native shapes directly, so a caller need not
  render a PNG, or convert a rendered diagram to shapes afterwards.

## 7. Not in v1

Inserting into an existing deck's slide · ` ```pikslide ` blocks in
Markdown · connectors (a future `connector` class, §3.2) · SVG *output* (SVG *images*
are supported, §3.5) · auto-layout and declarative graph syntax (a large
piece of work of its own) · tables, charts, SmartArt · animation,
transitions, speaker notes · multi-slide or whole-deck authoring · true
Bézier curves (`spline`/`arc` stay polylines) · shape adjustment handles ·
arithmetic on colors.

## 8. Acknowledgments

pikslide traces its lineage through two earlier languages. Brian
Kernighan's `pic` (1984) introduced sequential, relative placement of
named objects — draw one thing, then the next one relative to it — rather
than absolute coordinates. D. Richard Hipp's [pikchr](https://pikchr.org/)
carried that idea into a full, modern language, emitting SVG. pikslide's
parser and layout engine began as a direct port of pikchr's own
(`pikchr.y`), and the port goes well beyond syntax — default object sizes,
placement and chaining math, and edge geometry are all inherited from it,
not rebuilt from scratch. pikslide's own design departs from there where a
diagram that lives inside a PowerPoint slide, rather than becoming an SVG
picture, calls for a different answer: native, editable, themed shapes
instead of drawn paths, among the other choices this specification
describes.
