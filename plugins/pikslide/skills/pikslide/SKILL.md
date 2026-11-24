---
name: pikslide
description: Draw a diagram as a native, editable PowerPoint slide (.pptx) with pikslide, and a PNG of it to check - architecture and system diagrams, flowcharts, data flows, BPMN-like processes, org charts, anything of boxes, shapes and arrows. Use when the user asks for a diagram, figure or chart drawing in PowerPoint, or an editable slide of one.
license: 0BSD
---

# pikslide

pikslide draws a diagram written as text, in its own language (a `.pik`
file), into a one-slide PowerPoint deck of native shapes, colored by
the deck's theme, which a person can select, move and restyle; and a
PNG of the slide, to look at.

## Tools or the command

If the pikslide MCP tools are available, use them: `help`, `check` and
`render`. They do what the command does, with paths relative to the
workspace, and `render` returns the picture.

Otherwise run the `pikslide` command:

1. `pikslide --version` works: use it.
2. Else, if this skill's directory has wheels (`wheels/*.whl`), install
   them, needing no network: `pip install wheels/*.whl`.
3. Else `pip install pikslide`.

## Drawing a diagram

1. Read the language reference once: `pikslide --help llm` (the `help`
   tool, topic `llm`). It is all it takes to write a diagram; don't
   guess the syntax from other diagram languages. For a flowchart, a
   system architecture or a data flow diagram, read its recipe too
   before drawing it: `pikslide --help flowchart` (`architecture`,
   `dfd`), a whole diagram of that kind, to copy and adapt.
2. Write the diagram to a `.pik` file.
3. Check it: `pikslide diagram.pik --check` (the `check` tool). It
   prints JSON: the errors, each with the help topic to read, and the
   warnings, each naming its objects: overlaps, text that overflows its
   shape, fonts that aren't installed. Fix them and check again until
   none is left that the user didn't ask for.
4. Render it: `pikslide diagram.pik diagram.pptx --png` (the `render`
   tool, `out` a .pptx). Look at the PNG, fix what looks wrong, and
   render again.
5. Give the user the `.pptx`, and the PNG if it helps.

## Writing it

- A cycle, a row of chevrons, a pyramid, a funnel, a Venn diagram, a
  two-by-two matrix or a hub with items round it is one macro call,
  after `include "figures.pik"`: `pikslide --help figures` lists them.
  Use one rather than drawing the shape by hand.
- A data flow diagram's processes, data stores and external entities
  are macros too, after `include "dfd.pik"`: `pikslide --help dfd`
  lists them, then gives its recipe. Draw its flows as arrows, labeled
  with the data they carry.
- Lengths are in inches, and the diagram is drawn at the size it is
  written, never scaled. With no template, the slide is sized to it; on
  a template's slide, it goes at the content area's top left (a 16:9
  slide's is about 12 x 4.5 inches), and a warning names what runs past.
- Text is small by default (`small` 9pt, `medium` 10.5pt, `large` 12pt),
  smaller than a slide's body text: for a diagram that fills a slide,
  raise it at the top, `medium = 14pt`.
- Draw what the user gave, in their words: don't drop or reword it to
  make it fit; give it more room.
- Name what you refer to (`A: box "Web"`): the warnings, `--check`'s
  objects and the shapes in PowerPoint carry the names.
- `include "parts.pik"` reads definitions, such as macros, from another
  file; `--include-path DIR` adds where to look for it.
- `pikslide --help TOPIC` explains any keyword, class or preset shape
  (`pikslide --help shapes` lists them all).

## A company's template

- `--template corporate.potx` draws on the template's slide, in its
  theme's colors and fonts. With none, they are the built-in Office
  theme's (a warning says so).
- `--layout NAME` picks the slide layout, by name or id; by default it's
  the first with one content placeholder (Title and Content, mostly).
- `corporate.theme.pik` beside the template, or `--settings FILE`, holds
  what every diagram on it shares: `layout`, `typeface`, the text sizes.
- The tools take `template` and `layout` too. `pikslide --help template`
  tells the rest.

## Good to know

- Where there is no PowerPoint (a sandbox, a server, a Mac or Linux),
  pikslide draws the PNG itself, close to PowerPoint's picture, but it
  never shows text overflowing: `--check`'s warnings are what tell.
- A warning that a font isn't installed means text was measured with
  another: install the font from a file or URL the user gives,
  `pikslide --install-font FONT.ttf`, or set `typeface` to one that is.
- To draw onto a slide of a deck you are building with python-pptx, call
  `pikslide.parse()`, `layout()` and `render_into()` instead of the
  command: section 6 of `docs/spec.md` in the installed package.
