"""The Claude Code hook that stops what main's ruleset would refuse,
.claude/hooks/guard_main.py: what it stops, on main and on a branch, and
what it lets through."""

from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "guard_main.py"
_spec = importlib.util.spec_from_file_location("guard_main", HOOK)
guard_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard_main)


@pytest.fixture
def repos(tmp_path):
    """A repository on main and one on a branch, each with no commit yet."""
    made = {}
    for name, branch in (("on_main", "main"), ("on_branch", "56-a-change")):
        path = tmp_path / name
        subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
        made[name] = str(path)
    return made


@pytest.mark.parametrize("command", [
    "git commit -m 'Fix it'",
    "git commit --amend --no-edit",
    "git merge 56-a-change",
    "git cherry-pick abc123",
    "git revert abc123",
    "git rebase origin/main",
    "git push",
    "git push origin HEAD",
    "git push -u origin main",
    "git add -A && git commit -m x",
    "GIT_EDITOR=true git commit",
    "bash -c 'git push origin main'",
])
def test_stops_on_main(repos, command):
    assert guard_main.check(command, repos["on_main"])


@pytest.mark.parametrize("command", [
    "git status",
    "git pull --ff-only",
    "git merge --ff-only origin/main",
    "git rebase --abort",
    "git push origin v0.8.0",
    "git push origin 56-a-change",
    "git switch -c 57-another && git commit -m x",
    "git fetch origin && git log origin/main",
])
def test_lets_through_on_main(repos, command):
    assert guard_main.check(command, repos["on_main"]) is None


@pytest.mark.parametrize("command", [
    "git commit -m x",
    "git push",
    "git push --force-with-lease",
    "git push -u origin 56-a-change",
    "git rebase origin/main",
    'git commit -m "a && git push origin main"',
    "git commit -F - <<'EOF'\nDon't git push origin main; git commit on main\nEOF\n",
    'git commit -m "$(cat <<\'EOF\'\nSay why, not git merge\nEOF\n)" && git push -u origin HEAD',
    "git push 2>&1 | tail -3",
])
def test_lets_through_on_a_branch(repos, command):
    assert guard_main.check(command, repos["on_branch"]) is None


@pytest.mark.parametrize("command", [
    "git push origin 56-a-change:main",
    "git push origin +HEAD:refs/heads/main",
    "git push origin --delete main",
    "git push --all",
    "git switch main && git commit -m x",
    "git checkout main\ngit merge 56-a-change",
    "git push origin main 2>&1",
])
def test_stops_on_a_branch(repos, command):
    assert guard_main.check(command, repos["on_branch"])


def test_follows_cd_and_git_c(repos):
    main_repo = shlex.quote(repos["on_main"])
    assert guard_main.check(f"cd {main_repo} && git commit -m x", repos["on_branch"])
    assert guard_main.check(f"git -C {main_repo} merge 56-a-change", repos["on_branch"])
    assert guard_main.check(f"cd {shlex.quote(repos['on_branch'])} && git commit -m x", repos["on_main"]) is None


@pytest.mark.parametrize("command", [
    "gh pr merge 58 --merge",
    "gh pr merge 58 --rebase --admin",
    "gh repo edit --enable-merge-commit",
    "gh api -X DELETE repos/{owner}/{repo}/rulesets/1",
    "gh api repos/{owner}/{repo}/rulesets -f name=loose",
    "gh api --method PUT repos/o/r/branches/main/protection --input protection.json",
    "gh api -X PATCH repos/o/r -F allow_merge_commit=true",
    "gh api graphql -f query='mutation { deleteRepositoryRuleset(input: {repositoryRulesetId: \"x\"}) { clientMutationId } }'",
])
def test_stops_gh(repos, command):
    assert guard_main.check(command, repos["on_branch"])


@pytest.mark.parametrize("command", [
    "gh pr merge 58 --rebase --delete-branch",
    "gh pr merge --squash",
    "gh pr create --fill",
    "gh api repos/{owner}/{repo}/rulesets",
    "gh api repos/o/r/rulesets/1 --jq .rules",
    "gh api -X POST repos/o/r/issues -f title=x",
    "gh repo edit --delete-branch-on-merge",
    "gh api graphql -f query='query { viewer { login } }'",
])
def test_lets_gh_through(repos, command):
    assert guard_main.check(command, repos["on_branch"]) is None


def test_hook_denies_as_claude_code_reads_it(repos):
    event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "cwd": repos["on_main"]}
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                          check=True)
    decision = json.loads(done.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "CONTRIBUTING.md" in decision["permissionDecisionReason"]
    event["cwd"] = repos["on_branch"]
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                          check=True)
    assert done.stdout == ""
