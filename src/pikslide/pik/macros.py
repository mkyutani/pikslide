"""Macro (``#define``) expansion for pikchr source.

Ported from ``pik_tokenize()`` / ``pik_parse_macro_args()`` / ``pik_add_macro()``
in pikchr's ``pikchr.y``. Upstream pikchr expands macros token-by-token while
feeding an LALR parser; here expansion runs as a separate pass that consumes
the flat token list from :class:`pikslide.pik.tokens.Lexer` and produces a new,
fully-expanded flat token list for :mod:`pikslide.pik.parser` to consume.

Substantially ported from pikchr, Copyright (C) 2020-09-01 by
D. Richard Hipp <drh@sqlite.org>, released under the Zero-Clause BSD
license. See the NOTICE file at the root of this repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ast import MacroDefinition
from .tokens import Lexer, PikSyntaxError, Token, TokType

MAX_MACRO_DEPTH = 50
TOKEN_LIMIT = 100_000
MAX_MACRO_ARGS = 9


@dataclass
class _Macro:
    name: str
    body: str
    in_use: bool = False


@dataclass
class _State:
    macros: dict[str, _Macro] = field(default_factory=dict)
    out: list[Token] = field(default_factory=list)


def expand_macros(text: str) -> tuple[list[Token], list[MacroDefinition]]:
    """Tokenize ``text`` and expand all ``#define`` macro invocations."""
    tokens = Lexer(text).tokenize()
    state = _State()
    _expand(tokens, 0, len(tokens), None, state, depth=0)
    defs = [MacroDefinition(m.name, m.body) for m in state.macros.values()]
    return state.out, defs


def _expand(
    tokens: list[Token],
    start: int,
    end: int,
    params: list[list[Token]] | None,
    state: _State,
    depth: int,
) -> None:
    if depth > MAX_MACRO_DEPTH:
        line = tokens[start].line if start < end else 0
        raise PikSyntaxError("macros nested too deep", line)

    i = start
    while i < end:
        tok = tokens[i]

        if tok.type == TokType.PARAMETER:
            if params is not None and tok.code < len(params):
                sub = params[tok.code]
                _expand(sub, 0, len(sub), None, state, depth + 1)
            i += 1
            continue

        if (
            tok.type == TokType.DEFINE
            and i + 2 < end
            and tokens[i + 1].type == TokType.ID
            and tokens[i + 2].type == TokType.CODEBLOCK
        ):
            name = tokens[i + 1].text
            body = tokens[i + 2].text[1:-1]  # strip the outer { }
            state.macros[name] = _Macro(name, body)
            i += 3
            continue

        if tok.type == TokType.ID and tok.text in state.macros:
            mac = state.macros[tok.text]
            if mac.in_use:
                raise PikSyntaxError(f"recursive macro definition: {tok.text}", tok.line)
            j = i + 1
            args: list[list[Token]] | None = None
            if j < end and tokens[j].type == TokType.LP and tokens[j].pos == tok.pos + len(tok.text):
                args, j = _parse_macro_args(tokens, j, end, params)
            mac.in_use = True
            try:
                body_tokens = Lexer(mac.body).tokenize()
                _expand(body_tokens, 0, len(body_tokens), args, state, depth + 1)
            finally:
                mac.in_use = False
            i = j
            continue

        state.out.append(tok)
        if len(state.out) > TOKEN_LIMIT:
            raise PikSyntaxError("script is too complex", tok.line)
        i += 1


def _parse_macro_args(
    tokens: list[Token],
    lp_index: int,
    end: int,
    outer_params: list[list[Token]] | None,
) -> tuple[list[list[Token]], int]:
    """Parse ``(arg1, arg2, ...)`` starting at ``tokens[lp_index]`` (the '(').

    Returns the list of argument token-slices and the index just past the
    matching ')'. A bare ``$N`` argument is resolved against ``outer_params``
    immediately (macro-argument pass-through); any other ``$N`` occurring
    inside a multi-token argument is left as-is, matching upstream pikchr
    (which re-tokenizes each argument with no parameter context).
    """
    if tokens[lp_index + 1].type == TokType.RP:
        return [[]], lp_index + 2

    args: list[list[Token]] = []
    current: list[Token] = []
    depth = 0
    i = lp_index + 1
    while i < end:
        t = tokens[i]
        if t.type == TokType.RP and depth == 0:
            args.append(current)
            i += 1
            break
        if t.type == TokType.COMMA and depth == 0:
            args.append(current)
            current = []
            i += 1
            continue
        if t.type in (TokType.LP, TokType.LB):
            depth += 1
        elif t.type in (TokType.RP, TokType.RB):
            depth -= 1
        current.append(t)
        i += 1
    else:
        raise PikSyntaxError("unterminated macro argument list", tokens[lp_index].line)

    if len(args) > MAX_MACRO_ARGS:
        raise PikSyntaxError("too many macro arguments - max 9", tokens[lp_index].line)

    resolved: list[list[Token]] = []
    for a in args:
        if len(a) == 1 and a[0].type == TokType.PARAMETER:
            idx = a[0].code
            if outer_params is not None and idx < len(outer_params):
                resolved.append(outer_params[idx])
            else:
                resolved.append([])
        else:
            resolved.append(a)
    return resolved, i
