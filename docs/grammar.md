# pikslide language grammar (BNF)

This document defines the pikslide language: its lexical grammar, its
syntax in BNF/EBNF, and a short account of what the constructs mean. For
*why* the extensions exist and how they map to PowerPoint, see
[spec.md](spec.md).

The language has two layers:

- **pikchr core.** Every rule that carries no marker is implemented today by
  pikslide's hand-written recursive-descent parser
  (`src/pikslide/pik/parser.py`, tokenizer in `src/pikslide/pik/tokens.py`).
  It is derived from pikchr's own LALR(1) grammar (`pikchr.y`, built with the
  Lemon parser generator). A few local ambiguities that Lemon resolves with
  `%left`/`%right` precedence declarations and 1-token lookahead are resolved
  here by rule ordering or small bounded backtracking; those spots are called
  out below. For the authoritative upstream grammar see pikchr's
  [grammar documentation](https://pikchr.org/home/doc/trunk/doc/grammar.md)
  and [`pikchr.y`](https://pikchr.org/home/doc/tip/pikchr.y).
- **pikslide additions.** Rules and alternatives marked `(* ext *)` (prose:
  `(ext)`) are pikslide's own additions, not part of pikchr's grammar.
  pikslide is its own language ([spec.md](spec.md) §2): it starts from
  pikchr's grammar and departs from it where its design calls for it. Every
  difference is listed in [Differences from pikchr](#differences-from-pikchr),
  at the end.

**This document describes the target language, not today's code.** Most
`(ext)` rules are implemented already; a few are still only a proposal, and
the parser rejects them. Which is which changes as work continues, so it is
tracked separately, in
[docs/implementation-plan.md](implementation-plan.md), rather than marked
per rule here.

## Notation

- `::=` defines a rule; `|` separates alternatives.
- `[ x ]` — `x` is optional.
- `{ x }` — zero or more repetitions of `x`.
- `( x | y )` — grouping.
- `"literal"` — a literal token or keyword.
- `(* ... *)` — a comment; `(* ext *)` marks a pikslide extension.
- `UPPERCASE` names are terminals produced by the lexer (see
  [Lexical grammar](#lexical-grammar)); e.g. `NUMBER`, `STRING`, `PLACENAME`
  (an identifier starting with an uppercase letter), `ID` (starting
  lowercase), `EDGEPT` (a compass abbreviation like `ne`, `sw`).
- Other terminals are pikchr keywords, written as their lowercase spelling
  in quotes.

## Lexical grammar

The lexer (`pikslide.pik.tokens.Lexer`) is a port of pikchr's
`pik_token_length()`. Whitespace and comments are discarded; everything
else becomes a token.

```
blank           ::= " " | TAB | FF | CR
                   | comment
                   | "\" { " " | TAB | CR } NEWLINE        (* line continuation *)
comment         ::= "#" { not-newline }
                   | "//" { not-newline }
                   | "/*" { any } "*/"

EOL             ::= NEWLINE | ";"

STRING          ::= '"' { not-quote-or-backslash | "\" any } '"'

NUMBER          ::= decimal [ unit ]
                   | "0" ( "x" | "X" ) { hexdigit }        (* no unit; a colour literal (ext) *)
decimal         ::= ( digit { digit } [ "." { digit } ] | "." digit { digit } )
                    [ ( "e" | "E" ) [ "+" | "-" ] digit { digit } ]
unit            ::= "in" | "cm" | "mm" | "pt" | "px" | "pc"

NTH             ::= digit { digit } ( "st" | "nd" | "rd" | "th" )
                   | "first"

ID              ::= lower { alnum | "_" }                   (* not a keyword or CLASSNAME *)
                   | ( "_" | "$" | "@" ) { alnum | "_" }
PLACENAME       ::= upper { alnum | "_" }
PARAMETER       ::= "$" ( "1" | … | "9" )                   (* only inside macro bodies *)

CLASSNAME       ::= "arc" | "arrow" | "box" | "circle" | "cylinder" | "diamond"
                   | "dot" | "ellipse" | "file" | "line" | "move" | "oval"
                   | "spline" | "text"

ASSIGN          ::= "=" | "+=" | "-=" | "*=" | "/="
LARROW/RARROW/LRARROW
                ::= "<-" | "->" | "<->"                     (* also "←" "→" "↔" and
                                                               "&larr;" "&rarr;" "&leftrightarrow;" … *)
punctuation     ::= "(" | ")" | "[" | "]" | "," | ":" | "+" | "-" | "*" | "/"
                   | "%" | "<" | ">" | "=="
CODEBLOCK       ::= "{" { any-balanced } "}"                (* only after "define" ID *)
```

Notes:

- **Lengths are inches.** A `NUMBER` with a unit is converted to inches
  (`px` = 1/96 in, `pt` = 1/72 in, `pc` = 1/6 in, `cm` = 1/2.54 in). A bare
  number is already inches. A hex number is a colour literal (ext).
- **`ID` vs `PLACENAME`.** An identifier starting with a lowercase letter is
  looked up first among the keywords, then among `CLASSNAME`s, and is an
  `ID` otherwise. An identifier starting with an uppercase letter is always a
  `PLACENAME`: an object label.
- **The `.` token.** The lexer looks at what follows a `.` and yields one of
  four tokens, all written `"."` in the grammar below: before a lowercase
  edge/`start`/`end` keyword (`.e`, `.start`), before `x`/`y` (`.x`), before
  any other lowercase word (a property such as `.width`), and before an
  uppercase letter (a sub-object: `Outer.Inner`).
- **Keyword aliases.** `wid`=`width`, `ht`=`height`, `rad`=`radius`,
  `invis`=`invisible`, `mono`=`monospace`, `previous`=`last`; compass
  words `north`/`south`/`east`/`west` = `n`/`s`/`e`/`w`; `bot` = `bottom`;
  `t` = `top`; `c` = `center`.

## Macros

`define NAME { ... }` and its invocations (`NAME` or `NAME(arg, ...)`) are
expanded by a separate pass (`pikslide.pik.macros`) *before* parsing, so
they never appear in the grammar below — by the time the parser runs,
every macro invocation has already been replaced by its expanded body.

```
macro-definition ::= "define" ID CODEBLOCK
macro-call       ::= ID [ "(" [ macro-arg { "," macro-arg } ] ")" ]
```

- The macro name is an `ID`, so it starts with a **lowercase** letter
  (`define box2 { … }`).
- The `(` of an invocation must touch the name. `pair (a)` invokes `pair`
  with no arguments, then continues with `(a)`.
- Inside the body, `$1`…`$9` are the arguments; up to nine are allowed.
- Recursion is an error; nesting is limited to 50 levels.
- **A macro name must not already be a variable** (ext). A reserved word
  can never collide, since only an `ID` can start a `macro-definition`,
  and no reserved word lexes as one. An ordinary `ID` can: without this
  check, `define boxwid { 99 }` would fail only downstream and
  confusingly (`boxwid = 2` expands to `99 = 2`, a syntax error at `99`,
  not at the real cause), and `define legend { fill }` then `legend = 5`
  would not fail at all — it would silently expand to `fill = 5`,
  changing the default fill colour instead of setting a variable named
  `legend` (checked, before this guard existed). Because a diagram may be
  written by an LLM, and pikslide's prelude (§3.7) makes many more names
  collision-prone than pikchr's own, this is checked at the `define`
  itself — against every variable already assigned by the prelude, a
  settings file, an earlier `include`, or earlier in the same
  program — instead of only surfacing, unreliably, at each later use.

### Includes (ext)

`include "path"` is resolved in this same pass, before parsing, so the
`include` statement never reaches the parser either. Macros defined by the
included file join the same macro table and are visible from the `include`
line onward. An included file is not a full `document`; it has its own,
narrower start symbol:

```
include-file    ::= [ include-item { EOL include-item } ]      (* ext *)

include-item    ::= lvalue ASSIGN value                         (* fill = …, boxwid = 1.2 *)
                   | "include" STRING
                   | (* empty *)
```

together with `define` blocks, which the macro pass consumes wherever they
appear. Anything else in an included file — an object, a label, a
`direction` — is an error, so an include can change *definitions* but can
never place anything. Path resolution, containment and cycle rules are in
[spec.md §3.6](spec.md#36-shared-definitions-include).

The **prelude** is read the same way, as an implicit `include-file` before
the document. It defines the colour names, the built-in default variables
(`boxwid`, `linewid`, …) and the text sizes ([spec.md](spec.md) §3.7). A
template's settings file ([spec.md](spec.md) §3.8) is read the same way,
after the prelude.

## Document

```
document        ::= statement-list

statement-list  ::= statement { EOL statement }

statement       ::= direction
                   | lvalue ASSIGN value             (* value: ext *)
                   | PLACENAME ":" unnamed-statement
                   | PLACENAME ":" position
                   | unnamed-statement
                   | "print" print-item { "," print-item }
                   | "assert" "(" expr "==" expr ")"
                   | "assert" "(" position "==" position ")"
                   | "include" STRING                (* ext: resolved before parsing, see Macros *)

direction       ::= "up" | "down" | "left" | "right"

lvalue          ::= ID | "fill" | "color" | "thickness"
                   | "small" | "medium" | "large"    (* ext: the text sizes *)

print-item      ::= "fill" | "color" | "thickness" | STRING | rvalue
```

A `PLACENAME ":"` label is followed by either an *object*
(`unnamed-statement`, when the next token is `CLASSNAME`/`STRING`/`"["`,
or, with the extensions, `shape`/`image`) or a bare *position* (naming a
point in space) — there's no ambiguity between the two, since no
`position` alternative starts with those tokens.

## Objects

```
unnamed-statement ::= basetype { attribute }

basetype        ::= CLASSNAME
                   | STRING { text-flag }
                   | "[" statement-list "]"
                   | "shape" preset-name             (* ext *)
                   | "image" STRING                  (* ext *)

preset-name     ::= ID | CLASSNAME                   (* ext: an OOXML preset geometry name,
                                                        e.g. chevron, roundRect, ellipse *)

text-flag       ::= "center" | "ljust" | "rjust" | "above" | "below"
                   | "italic" | "bold" | "mono" | "aligned" | "big" | "small"
                   | "major" | "medium" | "large"    (* ext *)
```

`preset-name` allows `CLASSNAME` because some preset names (`ellipse`,
`diamond`, `line`, `arc`) are also class names and lex as such.

An `attribute` list may optionally start with one leading `relexpr` and
no keyword — e.g. the `150%` in `arrow 150%` — meaning "move this far in
the current direction":

```
attribute-list  ::= [ relexpr ] { attribute }

attribute       ::= numprop relexpr
                   | dashprop [ expr ]
                   | colorprop color-value
                   | [ "go" ] direction optrelexpr
                   | [ "go" ] direction ( "until" "even" | "even" ) "with" position
                   | "go" optrelexpr ( "heading" expr | EDGEPT )
                   | "then" [ optrelexpr ( "heading" expr | EDGEPT ) ]
                   | "close"
                   | "chop"
                   | "from" position
                   | "to" position
                   | boolprop
                   | arrowdir
                   | "at" position
                   | "with" [ "." ] edge "at" position
                   | "same" [ "as" object ]
                   | STRING { text-flag }
                   | "fit"
                   | "behind" object
                   | "alt" STRING                    (* ext: image only *)

numprop         ::= "width" | "height" | "radius" | "diameter" | "thickness"
dashprop        ::= "dashed" | "dotted"
colorprop       ::= "fill" | "color"
boolprop        ::= "cw" | "ccw" | "invis" | "thick" | "thin" | "solid"
arrowdir        ::= "<-" | "->" | "<->"

relexpr         ::= expr [ "%" ]
optrelexpr      ::= [ relexpr ]
```

`"then"` with nothing following (no amount, no heading/edge point) is a
complete attribute on its own: it marks a new path segment without
moving yet.

## Colours

```
value           ::= STRING                           (* ext *)
                   | color-value

color-value     ::= color-base [ ( "lighter" | "darker" ) expr "%" ]     (* ext *)

color-base      ::= "theme" STRING                   (* ext *)
                   | "none" | "off"                  (* ext *)
                   | rvalue

rvalue          ::= expr                             (* a colour name is an ID (ext) *)
```

A colour is a value of its own type, distinct from a number (ext). It is a hex
literal (`0xff0000`), a theme colour (`theme "accent1"`), `none` or `off`, or
the value of a variable that holds one. `lighter` and `darker` apply to any
colour. The names of the theme's slots (`accent1`, `text1`, …) are ordinary
variables defined by the prelude, not words of the language: the language has
only `theme`, which takes a slot name as a string, so the set of slots is data
([spec.md](spec.md) §3.3).

Colour names are ordinary variables (`ID`) defined by the prelude, which is
read as an `include-file` before the document (ext; see [spec.md](spec.md)
§3.7). `red`, `lightblue` and the other CSS names can be overridden
(`red = 0xcc0000`) and added to, and are lowercase like every variable. The
words `none` and `off` mean *no colour* and are reserved. An undefined name is
an error.

A variable can hold a colour (`primary = accent1 lighter 60%`, then
`box fill primary`); arithmetic on a colour (`primary + 1`) is an error.

A variable can also hold a string (`typeface = "BIZ UDPゴシック"`; ext). A
string is not a number and cannot be used in an expression. Strings serve the
template's settings ([spec.md](spec.md) §3.8); a string variable is not
accepted as the text of an object.

## Expressions

```
expr            ::= expr ( "+" | "-" ) expr
                   | expr ( "*" | "/" ) expr
                   | ( "-" | "+" ) expr
                   | "(" expr ")"
                   | "(" ( "fill" | "color" | "thickness" ) ")"
                   | NUMBER
                   | ID
                   | FUNC1 "(" expr ")"
                   | FUNC2 "(" expr "," expr ")"
                   | "dist" "(" position "," position ")"
                   | place2 "." ( "x" | "y" )
                   | object "." dotprop

dotprop         ::= numprop | dashprop | colorprop

FUNC1           ::= "abs" | "cos" | "int" | "sin" | "sqrt"
FUNC2           ::= "max" | "min"
```

`+`/`-` are left-associative and bind looser than `*`/`/`, which are
also left-associative; unary `-`/`+` bind tighter than either.

## Positions, places, and object references

```
position        ::= "(" position [ "," position ] ")"
                   | expr "," expr
                   | expr ( "above" | "below" ) position
                   | expr ( "left" | "right" ) "of" position
                   | expr "heading" ( edge "of" | expr "from" ) position
                   | expr edge "of" position
                   | expr ( "way" "between" | "between" | "of" "the" "way" "between" )
                       position "and" position
                   | expr "<" position "," position ">"
                   | place [ ( "+" | "-" ) [ "(" ] expr "," expr [ ")" ] ]

place           ::= edge "of" object
                   | place2

place2          ::= NTH "vertex" "of" object
                   | object [ "." edge ]

edge            ::= "center" | EDGEPT | "top" | "bottom" | "start" | "end"
                   | "right" | "left"

object          ::= nth [ ( "of" | "in" ) object ]
                   | objectname

nth             ::= NTH [ "last" ] ( CLASSNAME | "[" "]" )
                   | "last" [ CLASSNAME | "[" "]" ]

objectname      ::= "this"
                   | PLACENAME { "." PLACENAME }
```

The `expr`-led alternatives of `position` are all tried before the
`place`-led one; if none of the former match, the parser backtracks and
tries `place [(+|-) (dx,dy)]` instead
(`Parser.parse_position()`). This is exactly the kind of local
ambiguity pikchr's LALR(1) table resolves deterministically with
1-token lookahead; a hand-written recursive-descent parser has to fall
back to bounded backtracking for it instead.

## Reserved words (ext)

The additions introduce these words. They are ordinary reserved words, like
the other keywords: they cannot be used as variable or macro names.

| Word | Used for |
|---|---|
| `shape`, `image` | object classes |
| `include` | the include statement |
| `alt` | an attribute of `image` |
| `major`, `medium`, `large` | text flags |
| `theme` | builds a theme colour from a slot name, `theme "accent1"` |
| `lighter`, `darker` | colour modifiers |
| `none`, `off` | the *no colour* value |
| `connector` | reserved for a future object class ([spec.md](spec.md) §3.2); not used yet |

Semantic constraints the grammar cannot express (each is an error):

- a statement in an included file that is not an `include-item`;
- `alt` on anything other than an `image`;
- arithmetic on a colour (`primary + 1`);
- a `preset-name` that is not a known OOXML preset geometry;
- a `theme` string that names no known slot;
- an unknown colour name;
- assigning to `layout` outside a settings file ([spec.md](spec.md) §3.8).

A name that merely looks like a theme slot but is not one (`accent7`) is an
ordinary name and fails as an undefined variable.

## Meaning of the constructs

This summarises what the layout stage (`src/pikslide/pik/layout.py`) does; it
is not exhaustive.

**Placement.** There is a *current direction* (initially `right`). Each
object is placed so that its entry edge — the edge opposite the current
direction — meets the previous object's exit point. A bare `direction`
statement changes the direction. `at position` and
`with edge at position` override chaining; `from`/`to`/`then`/`go` shape a
line's path; `same` copies size and style from the previous object of the
same class (or from the one named by `same as`).
Objects are addressed by label (`Web`), by ordinal (`2nd box`, `last box`),
or through a block (`Outer.Inner`), and points on them by edge (`Web.ne`,
`start of last line`).

**Object classes.** Default sizes come from built-in variables, in inches.

| Class | Default size | Notes |
|---|---|---|
| `box` | `boxwid` × `boxht` (0.75 × 0.5) | corner radius `boxrad` (0) |
| `circle` | diameter `2 × circlerad` (0.5) | |
| `ellipse` | `ellipsewid` × `ellipseht` (0.75 × 0.5) | |
| `oval` | `ovalwid` × `ovalht` (1 × 0.5) | |
| `diamond` | `diamondwid` × `diamondht` (1 × 0.75) | |
| `cylinder` | `cylwid` × `cylht` (0.75 × 0.5) | end radius `cylrad` |
| `file` | `filewid` × `fileht` (0.5 × 0.75) | corner radius `filerad` |
| `dot` | radius `dotrad` (0.015) | filled |
| `text` | 0 × 0 | sized by its strings |
| `line`, `spline` | `linewid` × `lineht` (0.5 × 0.5) | |
| `arrow` | as `line` | with a right arrowhead |
| `move` | `movewid` × `lineht` | draws nothing |
| `arc` | `arcrad` (0.25) | |
| `[ … ]` | its contents' bounding box | a block with its own name scope |
| `"text"` | 0 × 0 | shorthand for a `text` object |

**Lines are geometry.** `line`, `arrow`, `spline` and `arc` are drawn at
fixed coordinates. They are never attached to the objects they touch, in the
language or in any output format. A link between two named objects is a
different concept, planned as a separate `connector` object class (see
[spec.md](spec.md) §3.2).

**Attributes.** `width`/`height`/`radius`/`diameter`/`thickness` set a
size (a `relexpr` with `%` is a percentage of the current value);
`dashed`/`dotted` take an optional length (default `dashwid`); `fill` and
`color` set the interior and stroke colour; `thick`/`thin` scale the
stroke by 1.5/0.67, `solid` resets stroke and dashing, `invis` hides the
outline; `cw`/`ccw` set an arc's direction; `<-`/`->`/`<->` add arrowheads;
`fit` sizes the object to its text; `chop` shortens a line's ends to the
outlines of the objects it joins; `close` closes a path; `behind X` (ext)
places the object immediately below `X` in z-order.

**Text.** Each `STRING` is a line of text on the object. Placement flags
are `center`, `ljust`, `rjust`, `above`, `below`, and `aligned` (rotate
along a line); style flags are `bold`, `italic`, `mono`. Size flags select
one of three sizes (ext): `small`, `medium` (the default), and `large` or
`big`. Their values are set by assigning to the words themselves, as
`fill`, `color` and `thickness` set theirs; the prelude gives `small = 9pt`,
`medium = 10.5pt` and `large = 12pt`. The last size flag on a string wins.
See [spec.md](spec.md) §3.3.

**Why some added words are reserved and others aren't.** A word is
reserved exactly when the grammar needs it as a literal token somewhere
— an object class, a statement, an attribute, a text flag, a modifier —
regardless of whether its *value* also comes from the prelude or a
settings file. `small`/`medium`/`large` are reserved because they are
text flags (`"Label" large`), not because their values are
prelude-supplied; the same is true of `fill`/`color`/`thickness` in
pikchr itself, which are attribute keywords *and* lvalues. Names that are
never used as syntax — `content_left`, `layout`, `typeface`, `primary`,
`accent1`, the CSS colour names, … — are ordinary `ID`s and are never
reserved, however important their value is.

**Variables.** `name = expr` (and `+=`, `-=`, `*=`, `/=`; dividing by zero
leaves the value unchanged) assigns a number, a colour or a string (ext). The built-in
variables above are ordinary variables and can be reassigned to change every
later default; they are defined by the prelude (ext; see [spec.md](spec.md)
§3.7). `fill`, `color` and `thickness` set the defaults for later objects, and
`small`, `medium` and `large` (ext) set the three text sizes. `print` and
`assert` are parsed but have no effect on the drawing.

## Differences from pikchr

pikslide starts from pikchr's grammar and departs from it where its design
calls for it ([spec.md](spec.md) §2). This is the complete list; the sections
above describe pikslide only. Rows marked (ext) are pikslide additions, not
part of pikchr; most are implemented already (docs/implementation-plan.md
tracks which).

| Topic | pikchr | pikslide |
|---|---|---|
| Text size | `big` ×1.25 and `small` ×0.8 of the viewer's font size; repeating a flag (`big big`) compounds | three sizes in points, `small` / `medium` (the default) / `large` or `big`, set by assigning to the words themselves, with values from the prelude; the last size flag wins (ext) |
| Variable values | numbers only | numbers, colours and strings (ext) |
| Colour type | a colour is a number (24-bit RGB) | a colour is a value of its own type; arithmetic on a colour is an error (ext) |
| Hex literals | plain numbers | colour literals (ext) |
| Colour names | a fixed table in the code, matched case-insensitively (`Red`, `red`); a variable of the same name takes precedence | ordinary lowercase variables defined by the prelude, overridable; a capitalised name is an object label (ext) |
| Theme colours | none | `theme "accent1"`; the slot names are variables defined by the prelude; `lighter` / `darker` apply to any colour (ext) |
| Built-in defaults (`boxwid`, `linewid`, …) | a table in the code | variables defined by the prelude (ext) |
| Prelude | none | a file of definitions read before every program (ext) |
| `include` | none | brings in definitions only (ext) |
| Object classes | `arc arrow box circle cylinder diamond dot ellipse file line move oval spline text` | adds `shape` and `image` (ext) |
| Attributes and text flags | as in the grammar above | adds `alt` and the text flags `major`, `medium`, `large` (ext) |
| Reserved words | pikchr's keywords | adds the words in [Reserved words](#reserved-words-ext); a pikchr program that uses one as a name (`shape = 3`) does not parse (ext) |
| Connectors | none | the word `connector` is reserved for a future class (ext) |

Where pikslide inherits pikchr's behaviour, and the inheritance is worth
knowing:

- pikchr's grammar also lists `expr "on" "heading" ...` position forms,
  but `"on"` isn't a keyword in pikchr's own tokenizer
  (`pik_keywords`), so the upstream lexer never actually produces that
  token either — those rules are unreachable in *real* pikchr, and are
  deliberately not supported here.
- `define` macro parameter substitution (`$1`..`$9`) doesn't reach
  inside `STRING` tokens — an already-tokenized string is opaque to
  macro expansion. This matches upstream pikchr's own behavior exactly;
  it isn't a pikslide gap.
- The layout stage (turning the parsed tree into concrete coordinates) is
  a deliberately narrower approximation of pikchr's own layout engine —
  see the module docstring in `src/pikslide/pik/layout.py` for what it
  does and doesn't reproduce.
