# pikslide `.pik` grammar (BNF)

This is the grammar pikslide's own parser (`src/pikslide/pik/parser.py`)
implements, restated as BNF/EBNF. It's derived from pikchr's own
LALR(1) grammar (`pikchr.y`, built with the Lemon parser generator), but
pikslide uses a hand-written recursive-descent parser instead of a
generated LALR table. A few local ambiguities that Lemon resolves via
`%left`/`%right` precedence declarations and 1-token lookahead are
instead resolved here by rule ordering or small bounded backtracking;
those spots are called out below. For the authoritative upstream
grammar (and for the full lexical grammar, which this document doesn't
restate), see pikchr's own
[grammar documentation](https://pikchr.org/home/doc/trunk/doc/grammar.md)
and [`pikchr.y`](https://pikchr.org/home/doc/tip/pikchr.y).

## Notation

- `::=` defines a rule; `|` separates alternatives.
- `[ x ]` — `x` is optional.
- `{ x }` — zero or more repetitions of `x`.
- `"literal"` — a literal token or keyword.
- `UPPERCASE` names are terminals produced by the lexer
  (`src/pikslide/pik/tokens.py`); e.g. `NUMBER`, `STRING`, `PLACENAME`
  (an identifier starting with an uppercase letter), `ID` (starting
  lowercase), `EDGEPT` (a compass abbreviation like `ne`, `sw`).
- Other terminals are pikchr keywords, written as their lowercase
  spelling in quotes.

## Macros

`#define NAME { ... }` and its invocations (`NAME` or `NAME(arg, ...)`)
are expanded by a separate pass (`pikslide.pik.macros`) *before* parsing,
so they never appear in the grammar below — by the time the parser
runs, every macro invocation has already been replaced by its expanded
body.

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

direction       ::= "up" | "down" | "left" | "right"

lvalue          ::= ID | "fill" | "color" | "thickness"

print-item      ::= "fill" | "color" | "thickness" | STRING | rvalue
```

A `PLACENAME ":"` label is followed by either an *object*
(`unnamed-statement`, when the next token is `CLASSNAME`/`STRING`/`"["`)
or a bare *position* (naming a point in space) — there's no ambiguity
between the two, since no `position` alternative starts with those three
tokens.

## Objects

```
unnamed-statement ::= basetype { attribute }

basetype        ::= CLASSNAME
                   | STRING { text-flag }
                   | "[" statement-list "]"

text-flag       ::= "center" | "ljust" | "rjust" | "above" | "below"
                   | "italic" | "bold" | "mono" | "aligned" | "big" | "small"
```

An `attribute` list may optionally start with one leading `relexpr` and
no keyword — e.g. the `150%` in `arrow 150%` — meaning "move this far in
the current direction":

```
attribute-list  ::= [ relexpr ] { attribute }

attribute       ::= numprop relexpr
                   | dashprop [ expr ]
                   | colorprop rvalue
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

numprop         ::= "width" | "height" | "radius" | "diameter" | "thickness"
dashprop        ::= "dashed" | "dotted"
colorprop       ::= "fill" | "color"
boolprop        ::= "cw" | "ccw" | "invis" | "thick" | "thin" | "solid"
arrowdir        ::= "<-" | "->" | "<->"

relexpr         ::= expr [ "%" ]
optrelexpr      ::= [ relexpr ]
rvalue          ::= PLACENAME               (* a color name, unless followed by "." *)
                   | expr
```

`"then"` with nothing following (no amount, no heading/edge point) is a
complete attribute on its own: it marks a new path segment without
moving yet.

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

## Known deviations from pikchr's own grammar

- pikchr's grammar also lists `expr "on" "heading" ...` position forms,
  but `"on"` isn't a keyword in pikchr's own tokenizer
  (`pik_keywords`), so the upstream lexer never actually produces that
  token either — those rules are unreachable in *real* pikchr, and are
  deliberately not supported here.
- `#define` macro parameter substitution (`$1`..`$9`) doesn't reach
  inside `STRING` tokens — an already-tokenized string is opaque to
  macro expansion. This matches upstream pikchr's own behavior exactly;
  it isn't a pikslide gap.
- This document covers *parsing* only. The *layout* stage (turning the
  parsed tree into concrete coordinates) is a separate, deliberately
  narrower approximation of pikchr's own layout engine — see the module
  docstring in `src/pikslide/pik/layout.py` for what it does and doesn't
  reproduce.
