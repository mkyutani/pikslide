# pikslide implementation plan

This tracks the gap between [spec.md](spec.md)/[grammar.md](grammar.md) (what
pikslide *should* do) and the current code (what it *does* do today). Unlike
those two, this file is not part of the language definition and is expected
to go stale row by row as each item is implemented — update or delete a row
once its "Needed" column is done, rather than leaving it to describe
already-built behaviour.

| Area | Today | Needed |
|---|---|---|
| `pik/tokens.py` `CLASS_NAMES` | fixed 14 pikchr classes | reserved words `shape`, `image`, `include`, `alt`, `lighter`/`darker`, `major`, `medium`, `large`, `theme`, `none`/`off`, and `connector` (reserved for later) |
| `pik/tokens.py` `Token`, `PikSyntaxError` | carry a line number only | carry the source file and column, so errors inside an `include` point at the right file |
| `pik/macros.py` `expand_macros` | one source text, one macro table; a macro name can silently shadow an existing variable (checked: `define legend { fill }` then `legend = 5` expands to `fill = 5`) | resolve `include` in the same pass (shared macro table, definitions-only check, path containment, cycle/depth limits); a `define` whose name is already a variable is an error |
| *(new)* theme reader | none | read `ppt/theme/*.xml` from a `.pptx`/`.potx` with `zipfile`; slide → layout → master → theme lookup; `.potx` normalisation for use as a base |
| `pik/layout.py` `_flatten` | flattens `[ ]` blocks, losing the tree | keep the hierarchy so groups can be written |
| `pik/layout.py` `Shape.fill` / `color`, `_Ctx.vars` | colours are `float` RGB ints; variables hold numbers only | a colour type: `none` \| RGB \| theme colour + modifiers; variables can hold colours and strings; an unknown colour name is an error |
| `pik/colors.py` `COLOR_NAMES` | a table the layout stage consults before variables, case-insensitively; an unknown name silently gives black (pikchr itself lets a variable win, and reports an unknown name as an error) | replaced by `src/pikslide/prelude.pik`, read first as an implicit include; no special lookup |
| *(new)* template settings | none | find the settings file beside a template or deck and read it after the prelude; use its `layout` |
| `pik/layout.py` `DEFAULTS` | the 33 built-in variables are a Python dict | defined in `prelude.pik` with the colour names and the text sizes; `_Ctx.vars` starts from the prelude |
| `pik/parser.py` `parse_rvalue` | a bare `PLACENAME` is a colour name | removed: a colour name is an ordinary variable (`ID`) |
| `tests/` | `box fill Red`, `box color DarkBlue` | lowercase names (`red`, `darkblue`) |
| `pik/layout.py` `behind` | parsed, ignored | affects z-order |
| `pptx_writer.py` `FONT_NAME`, `_BASE_FONT_PT` | hard-coded `"Arial"`, 9 pt | theme fonts; text sizes read from the prelude variables, default `medium` (10.5 pt) |
| `pik/layout.py` `_font_scale` | port of pikchr's `pik_font_scale()`: `big` ×1.25, `small` ×0.8 | three sizes taken from the prelude variables (`small` 9 / `medium` 10.5 / `large`=`big` 12 pt by default) |
| `pptx_writer.py` | always a new blank presentation | open an existing deck, insert group, replace by name, check that the diagram fits its region |
| `pptx_writer.py` | `_AUTOSHAPE` fixed map; no pictures | preset map, `p:pic`, SVG picture (`svgBlip` + PNG fallback, hand-written XML), `schemeClr` |
| `__init__.py` | `pikslide <in> [<out>]` only | `--into --slide --region/--rect --id --template --settings --block --include-path --align --strict --check --format` |
| `markdown.py` | `pik`, `pikchr` fences; blocks are numbered | add `pikslide`; read the name after the tag; require names when a file has several diagrams |
| Docs | README and `pyproject.toml` describe the target language (done) | keep the README's *Status* section in step with this table as items are implemented |
