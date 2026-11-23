# Contributing

Every change reaches `main` through a pull request that closes an issue.
`main` takes no direct push: a ruleset on it, which no one bypasses,
merges a pull request only once CI passes on a branch up to date with
`main`, and only by rebasing or squashing it, so that its history stays
a straight line.

1. Open an issue that says what's wrong or wanted, or take an open one.
2. Branch from `main` as it is on GitHub, naming the branch for the
   issue: `git fetch && git switch -c 57-short-name origin/main`.
3. Commit there. A commit message says what changed and why, as the
   history does.
4. Push the branch (`git push -u origin 57-short-name`) and open a pull
   request whose description says `Closes #57`. CI runs the tests on
   Linux, Windows and macOS, and checks that the description closes an
   issue.
5. Once CI passes, rebase-merge it:
   `gh pr merge --rebase --delete-branch`. Squash-merge
   (`--squash`) a branch whose commits are steps on the way rather than
   changes of their own. If `main` has moved on meanwhile, rebase the
   branch onto it first (`git rebase origin/main`, then
   `git push --force-with-lease`).
6. Bring your `main` up to date: `git switch main && git pull --ff-only`.

The tests, as CI runs them:

```sh
uv run --locked pytest
uv run --locked --package pikslide-mcp --group dev pytest pikslide-mcp/tests
```

## Releasing

A release is a change like the others: an issue, a branch that bumps the
version, and its pull request. Once that is merged, tag the commit on
`main` and push the tag:

```sh
git switch main && git pull --ff-only
git tag v0.8.0 && git push origin v0.8.0
```

[release.yml](.github/workflows/release.yml) tests and builds it,
publishes pikslide and pikslide-mcp to TestPyPI and then, once a
reviewer approves the `pypi` environment, to PyPI, and makes the GitHub
release.

## Claude Code

A Claude Code session in this repository runs
[.claude/hooks/guard_main.py](.claude/hooks/guard_main.py) before each
shell command (`.claude/settings.json`). It stops what the ruleset would
refuse, before it is tried: a commit, merge, cherry-pick, revert, am or
rebase on `main`, a push to `main`, a pull request merged with a merge
commit or `--admin`. It also stops changes to the ruleset, the branch
protection and the repository's merge settings, which only the
maintainer makes.
