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
- **pikslide extensions.** Rules and alternatives marked `(* ext *)` are
  pikslide additions. **They are a proposal and are not implemented yet**;
  the current parser rejects them. Every extension is *contextual*: it is
  recognised only where the pikchr core would report an error, so a valid
  pikchr program never changes meaning (see
  [Contextual keywords](#contextual-keywords-ext)).

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
                   | "0" ( "x" | "X" ) { hexdigit }        (* no unit; a colour or plain number *)
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
  number is already inches. A hex number is taken as-is, which is what makes
  `fill 0xff0000` work.
- **`ID` vs `PLACENAME`.** An identifier starting with a lowercase letter is
  looked up first among the keywords, then among `CLASSNAME`s, and is an
  `ID` otherwise. An identifier starting with an uppercase letter is always a
  `PLACENAME`: an object label or a colour name.
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
  (`define box2 { … }` works; `define Box2 { … }` does not). `#define` is
  *not* the syntax: `#` starts a comment.
- The `(` of an invocation must touch the name. `pair (a)` invokes `pair`
  with no arguments, then continues with `(a)`.
- Inside the body, `$1`…`$9` are the arguments; up to nine are allowed.
- Recursion is an error; nesting is limited to 50 levels.

### Includes (ext)

`include "path"` is resolved in this same pass, before parsing, so the
`include` statement never reaches the parser either. Macros defined by the
included file join the same macro table and are visible from the `include`
line onward. An included file is not a full `document`; it has its own,
narrower start symbol:

```
include-file    ::= [ include-item { EOL include-item } ]      (* ext *)

include-item    ::= lvalue ASSIGN rvalue                        (* fill = …, boxwid = 1.2 *)
                   | "include" STRING
                   | (* empty *)
```

together with `define` blocks, which the macro pass consumes wherever they
appear. Anything else in an included file — an object, a label, a
`direction` — is an error, so an include can change *definitions* but can
never place anything. Path resolution, containment and cycle rules are in
[spec.md §3.6](spec.md#36-shared-definitions-include).

## Document

```
document        ::= statement-list

statement-list  ::= statement { EOL statement }

statement       ::= direction
                   | lvalue ASSIGN rvalue
                   | PLACENAME ":" unnamed-statement
                   | PLACENAME ":" position
                   | unnamed-statement
                   | "print" print-item { "," print-item }
                   | "assert" "(" expr "==" expr ")"
                   | "assert" "(" position "==" position ")"
                   | "include" STRING                (* ext: resolved before parsing, see Macros *)

direction       ::= "up" | "down" | "left" | "right"

lvalue          ::= ID | "fill" | "color" | "thickness"

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
`diamond`, `line`, `arc`) are also pikchr class names and lex as such.

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
color-value     ::= theme-color                      (* ext *)
                   | rvalue

rvalue          ::= PLACENAME                        (* a colour name, unless followed by "." *)
                   | expr

theme-color     ::= THEME-SLOT [ ( "lighter" | "darker" ) expr "%" ]     (* ext *)

THEME-SLOT      ::= "accent1" | "accent2" | "accent3" | "accent4"
                   | "accent5" | "accent6"
                   | "text1" | "text2" | "bg1" | "bg2"
                   | "link" | "followed"             (* ext: lexed as ID, see below *)
```

A colour is an ordinary number: a 24-bit RGB value. `fill 0xff0000`,
`fill Red`, `fill red` and `fill lightblue` all denote such a number; the
CSS colour names live in `pikslide.pik.colors` and are matched
case-insensitively. A lowercase name such as `lightblue` lexes as an `ID`,
so the layout stage checks the colour table before treating it as a
variable. `"none"` and `"off"` mean *no colour*.

A `theme-color` is **not a number**. It is accepted only as the direct
operand of `fill`/`color`; it cannot be assigned to a variable, used in
arithmetic, or printed.

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

## Contextual keywords (ext)

The extensions add words that are not reserved. Each is recognised only in
the one position given below, and only where the pikchr core has no valid
reading of that token sequence:

| Word | Recognised as | Only when |
|---|---|---|
| `shape` | object class, followed by a `preset-name` | at the start of a `basetype`, and the next token is not `ASSIGN` |
| `image` | object class, followed by a `STRING` | at the start of a `basetype`, and the next token is not `ASSIGN` |
| `include` | statement, followed by a `STRING` | at the start of a statement, and the next token is a `STRING` (so `include = 1` stays an assignment) |
| `alt` | attribute, followed by a `STRING` | inside an attribute list |
| `major`, `medium`, `large` | text flag | directly after a `STRING` |
| `accent1`…`accent6`, `text1`, `text2`, `bg1`, `bg2`, `link`, `followed` | `THEME-SLOT` | as the operand of `fill`/`color`, and **no variable of that name is defined** |
| `lighter`, `darker` | theme-colour modifier | directly after a `THEME-SLOT` |

So `shape = 3` stays an assignment and `accent1 = 0xff0000` followed by
`box fill accent1` keeps meaning that variable: **a user-defined variable
always beats an extension word.** A file that uses no extension parses
identically under the core grammar alone; `pikslide --pikchr` is meant to
check exactly that.

Semantic constraints the grammar cannot express (each is an error):

- a statement in an included file that is not an `include-item`;
- `alt` on anything other than an `image`;
- a theme colour used anywhere but as the operand of `fill`/`color`;
- a `preset-name` that is not a known OOXML preset geometry.

A name that merely looks like a theme slot but is not one (`accent7`) is
not special: it follows the ordinary variable rule and fails as an
undefined variable.

## Meaning of the core constructs

This is a summary of the pikchr semantics that pikslide's layout stage
implements (`src/pikslide/pik/layout.py`); it is not exhaustive.

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
different concept: it is planned as a separate `connector` object class and
is not part of this grammar (see [spec.md](spec.md) §3.2).

**Attributes.** `width`/`height`/`radius`/`diameter`/`thickness` set a
size (a `relexpr` with `%` is a percentage of the current value);
`dashed`/`dotted` take an optional length (default `dashwid`); `fill` and
`color` set the interior and stroke colour; `thick`/`thin` scale the
stroke by 1.5/0.67, `solid` resets stroke and dashing, `invis` hides the
outline; `cw`/`ccw` set an arc's direction; `<-`/`->`/`<->` add arrowheads;
`fit` sizes the object to its text; `chop` shortens a line's ends to the
outlines of the objects it joins; `close` closes a path; `behind X` asks
for drawing below `X` (parsed, not yet applied).

**Text.** Each `STRING` is a line of text on the object. Placement flags
are `center`, `ljust`, `rjust`, `above`, `below`, and `aligned` (rotate
along a line); style flags are `bold`, `italic`, `mono`. Size flags: in
pikchr `big`/`small` scale the font by ×1.25/×0.8, and that is what the code
does today. pikslide **replaces this** with three fixed sizes (ext, not yet
implemented): `small` = 9 pt, `medium` = 10.5 pt (the default), `large` or
`big` = 12 pt; the last size flag on a string wins. See
[spec.md](spec.md) §3.3.

**Variables.** `name = expr` (and `+=`, `-=`, `*=`, `/=`; dividing by zero
leaves the value unchanged) assigns a number. The built-in variables above
are ordinary variables and can be reassigned to change every later default;
`fill`, `color` and `thickness` set the defaults for later objects. `print`
and `assert` are parsed but have no effect on the drawing.

## Known deviations from pikchr's own grammar

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
