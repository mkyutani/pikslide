# pikslide language grammar (BNF)

This document defines the pikslide language: its lexical grammar, its
syntax in BNF/EBNF, and a short account of what the constructs mean. For
*why* the constructs exist and how they map to PowerPoint, see
[spec.md](spec.md).

This document describes the target language. Every rule here is
implemented, with one reserved-but-inactive exception: `connector`, a word
held for a future object class ([spec.md](spec.md) §3.2/§7) that parses as
a reserved word but nothing more yet.

## Notation

- `::=` defines a rule; `|` separates alternatives.
- `[ x ]` — `x` is optional.
- `{ x }` — zero or more repetitions of `x`.
- `( x | y )` — grouping.
- `"literal"` — a literal token or keyword.
- `(* ... *)` — a comment.
- `UPPERCASE` names are terminals produced by the lexer (see
  [Lexical grammar](#lexical-grammar)); e.g. `NUMBER`, `STRING`, `PLACENAME`
  (an identifier starting with an uppercase letter), `ID` (starting
  lowercase), `EDGEPT` (a compass abbreviation like `ne`, `sw`).
- Other terminals are keywords, written as their lowercase spelling in
  quotes.

## Lexical grammar

The lexer (`pikslide.pik.tokens.Lexer`) turns raw source text into a flat
list of tokens. Whitespace and comments are discarded; everything else
becomes a token.

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
                   | "0" ( "x" | "X" ) { hexdigit }        (* no unit; a color literal *)
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
  number is already inches. A hex number is a color literal.
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
  Substitution doesn't reach inside `STRING` tokens: an already-tokenized
  string is opaque to macro expansion, so `$1` written inside a quoted
  string stays literal text, not a substitution.
- Recursion is an error; nesting is limited to 50 levels.
- **A macro name must not already be a variable.** A reserved word can
  never collide, since only an `ID` can start a `macro-definition`, and no
  reserved word lexes as one. An ordinary `ID` can: without this check,
  `define boxwid { 99 }` would fail only downstream and confusingly
  (`boxwid = 2` expands to `99 = 2`, a syntax error at `99`, not at the
  real cause), and `define legend { fill }` then `legend = 5` would not
  fail at all — it would silently expand to `fill = 5`, changing the
  default fill color instead of setting a variable named `legend`
  (checked, before this guard existed). Because a diagram may be written
  by an LLM, and the prelude (§3.7) defines many names, this is checked at
  the `define` itself — against every variable already assigned by the
  prelude, a settings file, an earlier `include`, or earlier in the same
  program — instead of only surfacing, unreliably, at each later use.

### Includes

`include "path"` is resolved in this same pass, before parsing, so the
`include` statement never reaches the parser either. Macros defined by the
included file join the same macro table and are visible from the `include`
line onward. An included file is not a full `document`; it has its own,
narrower start symbol:

```
include-file    ::= [ include-item { EOL include-item } ]

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
the document. It defines the color names, the built-in default variables
(`boxwid`, `linewid`, …) and the text sizes ([spec.md](spec.md) §3.7). A
template's settings file ([spec.md](spec.md) §3.8) is read the same way,
after the prelude.

## Document

```
document        ::= statement-list

statement-list  ::= statement { EOL statement }

statement       ::= direction
                   | lvalue ASSIGN value
                   | PLACENAME ":" unnamed-statement
                   | PLACENAME ":" position
                   | unnamed-statement
                   | "print" print-item { "," print-item }
                   | "assert" "(" expr "==" expr ")"
                   | "assert" "(" position "==" position ")"
                   | "include" STRING                (* resolved before parsing, see Macros *)

direction       ::= "up" | "down" | "left" | "right"

lvalue          ::= ID | "fill" | "color" | "thickness"
                   | "small" | "medium" | "large"    (* the text sizes *)

print-item      ::= "fill" | "color" | "thickness" | STRING | rvalue
```

A `PLACENAME ":"` label is followed by either an *object*
(`unnamed-statement`, when the next token is `CLASSNAME`/`STRING`/`"["`,
or `shape`/`image`) or a bare *position* (naming a point in space) —
there's no ambiguity between the two, since no `position` alternative
starts with those tokens.

## Objects

```
unnamed-statement ::= basetype { attribute }

basetype        ::= CLASSNAME
                   | STRING { text-flag }
                   | "[" statement-list "]"
                   | "shape" preset-name
                   | "image" STRING

preset-name     ::= ID | CLASSNAME                   (* an OOXML preset geometry name,
                                                        e.g. chevron, roundRect, ellipse *)

text-flag       ::= "center" | "ljust" | "rjust" | "above" | "below"
                   | "italic" | "bold" | "mono" | "aligned" | "big" | "small"
                   | "major" | "medium" | "large"
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
                   | "alt" STRING                    (* image only *)

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

## Colors

```
value           ::= STRING
                   | color-value

color-value     ::= color-base [ ( "lighter" | "darker" ) expr "%" ]

color-base      ::= "theme" STRING
                   | "none" | "off"
                   | rvalue

rvalue          ::= expr                             (* a color name is an ID *)
```

A color is a value of its own type, distinct from a number. It is a hex
literal (`0xff0000`), a theme color (`theme "accent1"`), `none` or `off`, or
the value of a variable that holds one. `lighter` and `darker` apply to any
color. The names of the theme's slots (`accent1`, `text1`, …) are ordinary
variables defined by the prelude, not words of the language: the language has
only `theme`, which takes a slot name as a string, so the set of slots is data
([spec.md](spec.md) §3.3).

Color names are ordinary variables (`ID`) defined by the prelude, which is
read as an `include-file` before the document (see [spec.md](spec.md)
§3.7). `red`, `lightblue` and the other CSS names can be overridden
(`red = 0xcc0000`) and added to, and are lowercase like every variable. The
words `none` and `off` mean *no color* and are reserved. An undefined name is
an error.

A variable can hold a color (`primary = accent1 lighter 60%`, then
`box fill primary`); arithmetic on a color (`primary + 1`) is an error.

A variable can also hold a string (`typeface = "BIZ UDPゴシック"`). A
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
tries `place [(+|-) (dx,dy)]` instead (`Parser.parse_position()`).

## Reserved words

The words below are reserved: they cannot be used as variable or macro
names.

| Word | Used for |
|---|---|
| `shape`, `image` | object classes |
| `include` | the include statement |
| `alt` | an attribute of `image` |
| `major`, `medium`, `large` | text flags |
| `theme` | builds a theme color from a slot name, `theme "accent1"` |
| `lighter`, `darker` | color modifiers |
| `none`, `off` | the *no color* value |
| `connector` | reserved for a future object class ([spec.md](spec.md) §3.2); not used yet |

Semantic constraints the grammar cannot express (each is an error):

- a statement in an included file that is not an `include-item`;
- `alt` on anything other than an `image`;
- arithmetic on a color (`primary + 1`);
- a `preset-name` that is not a known OOXML preset geometry;
- a `theme` string that names no known slot;
- an unknown color name;
- assigning to `layout` outside a settings file ([spec.md](spec.md) §3.8).

A name that merely looks like a theme slot but is not one (`accent7`) is an
ordinary name and fails as an undefined variable.

## Meaning of the constructs

This summarizes what the layout stage (`src/pikslide/pik/layout.py`) does
— a deliberately narrower approximation than a full CAD-style layout
engine, covering common diagrams well rather than every case; see that
module's own docstring for exactly what it does and doesn't reproduce —
and is not exhaustive.

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
`color` set the interior and stroke color; `thick`/`thin` scale the
stroke by 1.5/0.67, `solid` resets stroke and dashing, `invis` hides the
outline; `cw`/`ccw` set an arc's direction; `<-`/`->`/`<->` add arrowheads;
`fit` sizes the object to its text; `chop` shortens a line's ends to the
outlines of the objects it joins; `close` closes a path; `behind X` places
the object immediately below `X` in z-order.

**Text.** Each `STRING` is a line of text on the object. Placement flags
are `center`, `ljust`, `rjust`, `above`, `below`, and `aligned` (rotate
along a line); style flags are `bold`, `italic`, `mono`. Size flags select
one of three sizes: `small`, `medium` (the default), and `large` or
`big`. Their values are set by assigning to the words themselves, as
`fill`, `color` and `thickness` set theirs; the prelude gives `small = 9pt`,
`medium = 10.5pt` and `large = 12pt`. The last size flag on a string wins.
See [spec.md](spec.md) §3.3.

**Why some words are reserved and others aren't.** A word is reserved
exactly when the grammar needs it as a literal token somewhere — an object
class, a statement, an attribute, a text flag, a modifier — regardless of
whether its *value* also comes from the prelude or a settings file.
`small`/`medium`/`large` are reserved because they are text flags
(`"Label" large`), not because their values are prelude-supplied; the
same is true of `fill`/`color`/`thickness`, which are attribute keywords
and lvalues both. Names that are never used as syntax —
`content_left`, `layout`, `typeface`, `primary`, `accent1`, the CSS color
names, … — are ordinary `ID`s and are never reserved, however important
their value is.

**Variables.** `name = expr` (and `+=`, `-=`, `*=`, `/=`; dividing by zero
leaves the value unchanged) assigns a number, a color or a string. The
built-in variables above are ordinary variables and can be reassigned to
change every later default; they are defined by the prelude (see
[spec.md](spec.md) §3.7). `fill`, `color` and `thickness` set the defaults
for later objects, and `small`, `medium` and `large` set the three text
sizes. `print` and `assert` are parsed but have no effect on the drawing.

## Acknowledgments

pikslide's grammar began as a port of pikchr's own (`pikchr.y`, by D.
Richard Hipp), itself a descendant of Brian Kernighan's `pic`: sequential,
relative placement of named objects, rather than absolute coordinates, is
`pic`'s idea, carried through pikchr into a full language that pikslide
then built its own design on top of. The port goes beyond syntax — default
sizes, chaining and edge geometry, precedence and associativity all trace
back to it — down to a handful of spots (the position grammar above, in
particular) where a hand-written recursive-descent parser has to resolve
with backtracking an ambiguity pikchr's own Lemon-generated LALR(1) parser
resolves with one-token lookahead. Where pikslide's own design calls for a
different answer, it has one; see [spec.md](spec.md) for why.
