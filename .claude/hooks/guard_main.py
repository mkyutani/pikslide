"""A Claude Code PreToolUse hook on Bash (.claude/settings.json): stop a
command that would take a change into main other than through a pull
request, before main's ruleset on GitHub refuses it -- a commit, merge,
cherry-pick, revert, am or rebase on main, a push to main, a pull request
merged with a merge commit or --admin -- and one that would change the
ruleset, the branch protection or the repository's merge settings.
CONTRIBUTING.md says how a change does reach main.

It reads the command, not what it does: each `git` and `gh` in it, the
words after them, and the directory a `cd` or `git -C` and the branch a
`git switch` or `git checkout` before them leave it on. What it can't
read it lets through: the ruleset is what stops it."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

MAIN = "main"
FLOW = ("main takes changes only through a pull request: work on a branch for an issue, open a pull "
        "request whose description says `Closes #N`, and rebase-merge it once CI passes (CONTRIBUTING.md).")
# what makes a commit on the branch checked out, and how to stop doing it
COMMITTING = {"commit", "merge", "cherry-pick", "revert", "am", "rebase"}
STOPPING = {"--abort", "--quit", "--skip"}
PUNCTUATION = "();<>|&\n"
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
# the REST API's ruleset, branch protection and repository (its merge settings) paths
PROTECTION = re.compile(r"(^|/)rulesets(/|$)|/branches/[^/]+/protection(/|$)|^repos/[^/]+/[^/]+/?$")
GRAPHQL_PROTECTION = re.compile(r"(?i)ruleset|branchprotection|updaterepository")
WRAPPERS = {"env", "command", "builtin", "exec", "time", "nohup", "sudo"}
SHELLS = {"sh", "bash", "zsh", "dash"}


def commands(text: str) -> list[list[str]]:
    """The words of each simple command in `text`, a heredoc's body and a
    redirection's target left out."""
    text = HEREDOC.sub(lambda m: m.group(3), text).replace("\\\n", " ")
    lex = shlex.shlex(text, posix=True, punctuation_chars=PUNCTUATION)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:  # a quote left open: words between spaces, then
        tokens = text.split()
    out: list[list[str]] = []
    words: list[str] = []
    skip = False
    for token in tokens:
        if skip:
            skip = False
        elif token and not set(token) - set(PUNCTUATION):
            if set(token) & set("<>"):  # a redirection: its target too, and its descriptor
                if words and words[-1].isdigit():
                    words.pop()
                skip = True
            elif words:
                out.append(words)
                words = []
        else:
            words.append(token)
    if words:
        out.append(words)
    return out


def current_branch(directory: str, switched: dict[str, str]) -> str | None:
    key = os.path.realpath(directory)
    if key in switched:
        return switched[key]
    try:
        done = subprocess.run(["git", "-C", directory, "branch", "--show-current"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def switched_to(sub: str, rest: list[str]) -> str | None:
    """The branch `git switch` or `git checkout` with `rest` checks out."""
    if "--" in rest:  # git checkout [<commit>] -- <path>: files, not a branch
        return None
    for flag in ("-c", "-C", "-b", "-B", "--create", "--force-create", "--orphan"):
        if flag in rest and rest.index(flag) + 1 < len(rest):
            return rest[rest.index(flag) + 1]
    names = [w for w in rest if not w.startswith("-")]
    return names[0] if names else None


def check_git(args: list[str], cwd: str, switched: dict[str, str]) -> str | None:
    directory, i = cwd, 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] == "-C" and i + 1 < len(args):
            directory = os.path.join(directory, os.path.expanduser(args[i + 1]))
            i += 2
        elif args[i] in ("-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(args):
            i += 2
        else:
            i += 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub in ("switch", "checkout"):
        branch = switched_to(sub, rest)
        if branch:
            switched[os.path.realpath(directory)] = branch
        return None
    branch = current_branch(directory, switched)
    if sub in COMMITTING and branch == MAIN and not set(rest) & STOPPING \
            and not (sub == "merge" and "--ff-only" in rest):
        return f"`git {sub}` on {MAIN}: {FLOW}"
    if sub == "push":
        return check_push(rest, branch)
    return None


def check_push(rest: list[str], branch: str | None) -> str | None:
    if "--all" in rest or "--mirror" in rest or "--branches" in rest:
        return f"`git push --all` pushes {MAIN} too: {FLOW}"
    positional, skip = [], False
    for word in rest:
        if skip:
            skip = False
        elif word in ("-o", "--push-option", "--receive-pack", "--exec", "--repo"):
            skip = True
        elif not word.startswith("-"):
            positional.append(word)
    refspecs = positional[1:]
    if not refspecs:  # the branch checked out
        return f"`git push` from {MAIN}: {FLOW}" if branch == MAIN else None
    for spec in refspecs:
        source, colon, destination = spec.lstrip("+").partition(":")
        target = destination if colon else source
        if target in ("HEAD", "@") and not colon:
            target = branch or ""
        if target.removeprefix("refs/heads/") == MAIN:
            return f"`git push` to {MAIN}: {FLOW}"
    return None


def check_gh(args: list[str]) -> str | None:
    if args[:2] == ["pr", "merge"]:
        rest = args[2:]
        if "--merge" in rest or "-m" in rest:
            return (f"`gh pr merge --merge`: {MAIN} keeps a straight history; merge with --rebase, or "
                    "--squash a branch whose commits are steps on the way (CONTRIBUTING.md).")
        if "--admin" in rest:
            return f"`gh pr merge --admin` would go round {MAIN}'s ruleset: {FLOW}"
    if args[:2] == ["repo", "edit"] and ("--enable-merge-commit" in args or "--enable-merge-commit=true" in args):
        return f"merge commits stay off: {MAIN} keeps a straight history (CONTRIBUTING.md)."
    if args[:1] == ["api"]:
        method, path, fields, i = None, None, [], 1
        while i < len(args):
            word = args[i]
            if word in ("-X", "--method") and i + 1 < len(args):
                method, i = args[i + 1].upper(), i + 2
                continue
            if word.startswith("--method=") or (word.startswith("-X") and len(word) > 2):
                method = word.split("=", 1)[1].upper() if "=" in word else word[2:].upper()
            elif word in ("-f", "-F", "--field", "--raw-field", "--input") and i + 1 < len(args):
                fields.append(args[i + 1])
                i += 2
                continue
            elif word.startswith(("--field=", "--raw-field=", "--input=")):
                fields.append(word.split("=", 1)[1])
            elif word in ("-H", "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache",
                          "-p", "--preview") and i + 1 < len(args):
                i += 2
                continue
            elif not word.startswith("-") and path is None:
                path = word.lstrip("/")
            i += 1
        method = method or ("POST" if fields else "GET")  # as gh sends it
        if path == "graphql":
            if any("mutation" in f and GRAPHQL_PROTECTION.search(f) for f in fields):
                return f"that mutation changes how {MAIN} is protected, which only the maintainer does."
        elif path and method != "GET" and PROTECTION.search(path):
            return f"`gh api -X {method} {path}` changes how {MAIN} is protected, which only the maintainer does."
    return None


def check(command: str, cwd: str, switched: dict[str, str] | None = None) -> str | None:
    """Why `command`, run in `cwd`, may not run, or None."""
    switched = {} if switched is None else switched
    for words in commands(command):
        while words and (re.match(r"^\w+=", words[0]) or words[0] in WRAPPERS):
            words = words[3:] if words[0] == "env" and words[1:2] == ["-u"] else words[1:]
        if not words:
            continue
        name = os.path.basename(words[0])
        if name == "cd" and len(words) > 1:
            cwd = os.path.join(cwd, os.path.expanduser(os.path.expandvars(words[1])))
            continue
        if name in SHELLS and "-c" in words and words.index("-c") + 1 < len(words):
            reason = check(words[words.index("-c") + 1], cwd, switched)
        elif name == "git":
            reason = check_git(words[1:], cwd, switched)
        elif name == "gh":
            reason = check_gh(words[1:])
        else:
            continue
        if reason:
            return reason
    return None


def main() -> None:
    event = json.load(sys.stdin)
    command = (event.get("tool_input") or {}).get("command") or ""
    reason = check(command, event.get("cwd") or os.getcwd())
    if reason:
        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                          "permissionDecisionReason": reason}}, sys.stdout)


if __name__ == "__main__":
    main()
