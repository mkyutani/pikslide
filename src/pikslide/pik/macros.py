"""Macro (``#define``) expansion for diagram source.

Expansion runs as a separate pass that consumes the flat token list from
:class:`pikslide.pik.tokens.Lexer` and produces a new, fully-expanded flat
token list for :mod:`pikslide.pik.parser` to consume.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import resources

from .ast import MacroDefinition
from .tokens import Lexer, PikSyntaxError, Token, TokType, unescape_string

MAX_MACRO_DEPTH = 50
TOKEN_LIMIT = 100_000
MAX_MACRO_ARGS = 9

# lvalue keyword tokens (docs/grammar.md: `lvalue`) besides a plain ID --
# fill/color/thickness, and the small/medium/large ext.
_LVALUE_KEYWORD_TYPES = {
    TokType.FILL, TokType.COLOR, TokType.THICKNESS,
    TokType.SMALL, TokType.MEDIUM, TokType.LARGE,
}

_prelude_var_names_cache: frozenset[str] | None = None


def _scan_assigned_names(tokens: list[Token]) -> set[str]:
    """Names assigned via `name = ...`/`+=`/`-=`/`*=`/`/=` anywhere in
    `tokens` -- a flat scan, since pikslide variables are never scoped to a
    `[...]` block (docs/grammar.md, Variables)."""
    return {
        tokens[i].text
        for i in range(len(tokens) - 1)
        if (tokens[i].type == TokType.ID or tokens[i].type in _LVALUE_KEYWORD_TYPES)
        and tokens[i + 1].type == TokType.ASSIGN
    }


def _prelude_variable_names() -> frozenset[str]:
    """Names the prelude (docs/spec.md SS3.7) assigns -- cached, and read
    directly with `Lexer` (not `expand_macros`/`parse`, which would recurse
    back into this module) since prelude.pik itself never uses `define`."""
    global _prelude_var_names_cache
    if _prelude_var_names_cache is None:
        text = resources.files("pikslide").joinpath("prelude.pik").read_text(encoding="utf-8")
        _prelude_var_names_cache = frozenset(_scan_assigned_names(Lexer(text).tokenize()))
    return _prelude_var_names_cache


def _resolve_include_path(raw_path: str, current_dir: str, include_paths: list[str], path_tok: Token) -> str:
    """Resolve an `include "path"` (docs/spec.md SS3.6): relative to
    `current_dir` (the including file's own directory) first, then to
    each `include_paths` entry in order.

    Rejects an absolute path, and any resolution that escapes its own
    base directory: a diagram may be written by an LLM, and must not be
    able to reach, or reveal the existence of, arbitrary local files.

    `path_tok` (the `include` statement's own STRING token) supplies
    `line`/`pos`/`file` for the error (docs/spec.md SS5): this error is
    about the `include` line itself, in whichever file contains it --
    which, for a nested `include`, is `path_tok.file`, not necessarily
    the outermost source (`path_tok` already carries the right one, set
    when *its own* file was lexed)."""
    line, pos, file = path_tok.line, path_tok.pos, path_tok.file
    if os.path.isabs(raw_path) or raw_path.startswith("~"):
        raise PikSyntaxError(f"include path must be relative, not {raw_path!r}", line, raw_path, pos=pos, file=file)
    tried = []
    for base_dir in (current_dir, *include_paths):
        base = os.path.realpath(base_dir)
        resolved = os.path.realpath(os.path.join(base, raw_path))
        if os.path.commonpath([base, resolved]) != base:
            tried.append(f"{base_dir} (escapes it)")
            continue
        if os.path.isfile(resolved):
            return resolved
        tried.append(base_dir)
    raise PikSyntaxError(
        f"include file not found: {raw_path!r} (tried: {', '.join(tried)})", line, raw_path, pos=pos, file=file
    )


def _validate_definitions_only(tokens: list[Token]) -> None:
    """Check that `tokens` -- an included file's own already-expanded
    output -- match the include-file grammar (docs/grammar.md, Includes):
    each EOL-separated statement must be `lvalue ASSIGN ...`. `define`
    blocks need no check here: the macro pass above has already consumed
    them, so none remain in `tokens` by this point.

    Anything else -- an object, a label, a direction, `print`, `assert`
    -- is an error, so an include can change *definitions* but never
    place anything. The offending token's own `.file` (docs/spec.md SS5)
    names the file with the violation directly -- correct even for a
    deeper nested `include`, since every token here already carries
    whichever file its own lexer pass actually stamped it with."""
    i, n = 0, len(tokens)
    while i < n:
        if tokens[i].type == TokType.EOL:
            i += 1
            continue
        if (tokens[i].type == TokType.ID or tokens[i].type in _LVALUE_KEYWORD_TYPES) \
                and i + 1 < n and tokens[i + 1].type == TokType.ASSIGN:
            i += 2
            while i < n and tokens[i].type != TokType.EOL:
                i += 1
            continue
        raise PikSyntaxError(
            "only definitions are allowed in an included file "
            "(an assignment, or define) -- not an object, a label, or anything else",
            tokens[i].line, tokens[i].text, pos=tokens[i].pos, file=tokens[i].file,
        )


@dataclass
class _Macro:
    name: str
    body: str
    in_use: bool = False


@dataclass
class _State:
    macros: dict[str, _Macro] = field(default_factory=dict)
    out: list[Token] = field(default_factory=list)


def expand_macros(
    text: str, base_dir: str = ".", include_paths: list[str] | None = None
) -> tuple[list[Token], list[MacroDefinition]]:
    """Tokenize ``text`` and expand all macro invocations and `include`
    statements (ext; docs/spec.md SS3.6). `base_dir` is the source file's
    own directory, against which an `include "path"` resolves first;
    `include_paths` (ext, for a future `--include-path`) are tried next,
    in order, if it isn't found there."""
    tokens = Lexer(text).tokenize()
    state = _State()
    _expand(tokens, 0, len(tokens), None, state, depth=0,
            current_dir=base_dir, include_paths=include_paths or [], include_stack=())
    defs = [MacroDefinition(m.name, m.body) for m in state.macros.values()]
    return state.out, defs


def _expand(
    tokens: list[Token],
    start: int,
    end: int,
    params: list[list[Token]] | None,
    state: _State,
    depth: int,
    current_dir: str,
    include_paths: list[str],
    include_stack: tuple[str, ...],
) -> None:
    if depth > MAX_MACRO_DEPTH:
        tok = tokens[start] if start < end else None
        raise PikSyntaxError(
            "include/macro nesting too deep", tok.line if tok else 0,
            pos=tok.pos if tok else 0, file=tok.file if tok else None,
        )

    i = start
    while i < end:
        tok = tokens[i]

        if tok.type == TokType.PARAMETER:
            if params is not None and tok.code < len(params):
                sub = params[tok.code]
                _expand(sub, 0, len(sub), None, state, depth + 1,
                        current_dir, include_paths, include_stack)
            i += 1
            continue

        if tok.type == TokType.INCLUDE and i + 1 < end and tokens[i + 1].type == TokType.STRING:
            path_tok = tokens[i + 1]
            raw_path = unescape_string(path_tok.text)
            resolved = _resolve_include_path(raw_path, current_dir, include_paths, path_tok)
            if resolved in include_stack:
                chain = " -> ".join((*include_stack, resolved))
                raise PikSyntaxError(f"include cycle: {chain}", path_tok.line, raw_path, pos=path_tok.pos, file=path_tok.file)
            try:
                included_text = open(resolved, encoding="utf-8").read()
            except OSError as e:
                raise PikSyntaxError(
                    f"cannot read included file: {e}", path_tok.line, raw_path, pos=path_tok.pos, file=path_tok.file
                ) from e
            included_tokens = Lexer(included_text, file=resolved).tokenize()
            out_start = len(state.out)
            _expand(
                included_tokens, 0, len(included_tokens), None, state, depth + 1,
                current_dir=os.path.dirname(resolved),
                include_paths=include_paths,
                include_stack=(*include_stack, resolved),
            )
            _validate_definitions_only(state.out[out_start:])
            i += 2
            continue

        if (
            tok.type == TokType.DEFINE
            and i + 2 < end
            and tokens[i + 1].type == TokType.ID
            and tokens[i + 2].type == TokType.CODEBLOCK
        ):
            name = tokens[i + 1].text
            # A macro name must not already be a variable (docs/spec.md
            # SS3.6, docs/grammar.md Macros): otherwise it would silently
            # shadow every later use of that name, including as an
            # assignment target -- checked: `define legend { fill }` then
            # `legend = 5` expands to `fill = 5` with no error at all.
            if name in _prelude_variable_names() or name in _scan_assigned_names(state.out):
                raise PikSyntaxError(
                    f"'{name}' is already a variable; a macro cannot shadow it", tokens[i + 1].line, name,
                    pos=tokens[i + 1].pos, file=tokens[i + 1].file,
                )
            body = tokens[i + 2].text[1:-1]  # strip the outer { }
            state.macros[name] = _Macro(name, body)
            i += 3
            continue

        if tok.type == TokType.ID and tok.text in state.macros:
            # The reverse direction of the same guard: `define legend {...}`
            # *then* `legend = 5` -- without this, `legend` here would
            # macro-expand before the parser ever sees it as an assignment
            # target (checked: it silently becomes e.g. `fill = 5`).
            nxt = tokens[i + 1] if i + 1 < end else None
            if nxt is not None and nxt.type == TokType.ASSIGN:
                raise PikSyntaxError(
                    f"'{tok.text}' is already a macro; it cannot be used as a variable", tok.line, tok.text,
                    pos=tok.pos, file=tok.file,
                )
            mac = state.macros[tok.text]
            if mac.in_use:
                raise PikSyntaxError(f"recursive macro definition: {tok.text}", tok.line, pos=tok.pos, file=tok.file)
            j = i + 1
            args: list[list[Token]] | None = None
            if j < end and tokens[j].type == TokType.LP and tokens[j].pos == tok.pos + len(tok.text):
                args, j = _parse_macro_args(tokens, j, end, params)
            mac.in_use = True
            try:
                body_tokens = Lexer(mac.body).tokenize()
                _expand(body_tokens, 0, len(body_tokens), args, state, depth + 1,
                        current_dir, include_paths, include_stack)
            finally:
                mac.in_use = False
            i = j
            continue

        state.out.append(tok)
        if len(state.out) > TOKEN_LIMIT:
            raise PikSyntaxError("script is too complex", tok.line, pos=tok.pos, file=tok.file)
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
    inside a multi-token argument is left as-is.
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
        lp = tokens[lp_index]
        raise PikSyntaxError("unterminated macro argument list", lp.line, pos=lp.pos, file=lp.file)

    if len(args) > MAX_MACRO_ARGS:
        lp = tokens[lp_index]
        raise PikSyntaxError("too many macro arguments - max 9", lp.line, pos=lp.pos, file=lp.file)

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
