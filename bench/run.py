"""Run a benchmark task: each method's prompt (tasks/TASK.md with
methods/METHOD.md in it) through `claude -p`, as many times as --runs
says, the methods interleaved and their order rotated each round.

Each run is in a fresh directory outside $HOME, so no CLAUDE.md above it
is read, with Claude Code's own config directory, $BENCH_HOME/claude: no
CLAUDE.md, settings, hooks, plugins, skills or memory of yours, and the
login made there for the benchmark (a Claude subscription). Auto memory
is off, and its tools are Bash, Read, Write and Edit only: no MCP
servers, skills, subagents or web.

A run's prompt, its statistics (run.json) and what it made -- its
program, if it has one, and the deck -- land in
bench/results/TASK/METHOD/NN/; what Claude Code printed is read for the
statistics and not kept. A run already there is skipped, so a stopped
benchmark picks up where it left off. Run setup.sh first."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent
METHODS = ("pikslide", "python-pptx", "raw-xml")
RUNS = {"pikslide": 3, "python-pptx": 3, "raw-xml": 3}
# the tasks, tasks/TASK.md
TASKS = ("fizzbuzz",)
# the only tools a run has (--tools), and may use without asking
ALLOWED = ["Bash", "Read", "Write", "Edit"]
DISALLOWED = ["WebFetch", "WebSearch", "Skill", "Agent", "Task", "NotebookEdit"]
# What else each method may not run: raw-xml writes every part by hand,
# not with a program.
METHOD_DISALLOWED = {
    "raw-xml": [f"Bash({p}:*)" for p in ("python", "python3", "uv", "node", "perl", "ruby")],
}
# What a run keeps of what it made: its program, if it has one, and the deck.
KEPT = {"pikslide": ["{name}.pik", "{name}.pptx"], "python-pptx": ["make_slide.py", "{name}.pptx"],
        "raw-xml": ["{name}.pptx"]}
PROGRAM = re.compile(r"(^|[\s;&|(])(python3?|node|perl|ruby|uv)\b")
RENDER = re.compile(r"render-png|--png")
# what render-png and pikslide --png say when PowerPoint didn't render
FALLBACK = re.compile(r"(render-png|note): PowerPoint COM automation failed")
# An API key would win over the benchmark's subscription login.
AUTH_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")


def bench_home() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(os.environ.get("BENCH_HOME") or os.path.join(cache, "pikslide-bench"))


def runs_root() -> Path:
    return Path(os.environ.get("BENCH_RUNS") or os.path.join(tempfile.gettempdir(), "pikslide-bench-runs"))


def claude_env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in AUTH_VARIABLES}
    return {**env, "CLAUDE_CONFIG_DIR": str(home / "claude"), "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
            "PATH": f"{home / 'venv' / 'bin'}:{home / 'bin'}:{os.environ['PATH']}"}


def prompt(task: str, method: str) -> str:
    text = (BENCH / "methods" / f"{method}.md").read_text(encoding="utf-8").strip().replace("{name}", task)
    return (BENCH / "tasks" / f"{task}.md").read_text(encoding="utf-8").replace("{method}", text)


def command(method: str, args: argparse.Namespace) -> list[str]:
    return ["claude", "-p", "--model", args.model, "--effort", args.effort,
            "--output-format", "stream-json", "--verbose", "--no-session-persistence",
            "--strict-mcp-config", "--permission-mode", "dontAsk",
            "--max-budget-usd", str(args.budget),
            "--tools", ",".join(ALLOWED), "--allowedTools", *ALLOWED,
            "--disallowedTools", *DISALLOWED, *METHOD_DISALLOWED.get(method, [])]


def measure(stream: str, method: str) -> dict:
    """A run's statistics, from what `claude -p --output-format
    stream-json` printed: its tokens, cost, turns and renders, whether it
    ended well, and what it shouldn't have done or what went wrong round
    it (`flags`)."""
    events = [json.loads(line) for line in stream.splitlines() if line.startswith("{")]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    # Every model the run used (modelUsage), else the run's own usage.
    models = (result.get("modelUsage") or {}).values()
    tokens = {k: sum(m.get(f, 0) for m in models) for k, f in
              (("input_tokens", "inputTokens"), ("cache_write_tokens", "cacheCreationInputTokens"),
               ("cache_read_tokens", "cacheReadInputTokens"), ("output_tokens", "outputTokens"))}
    if not any(tokens.values()):
        usage = result.get("usage") or {}
        tokens = {k: usage.get(f, 0) for k, f in
                  (("input_tokens", "input_tokens"), ("cache_write_tokens", "cache_creation_input_tokens"),
                   ("cache_read_tokens", "cache_read_input_tokens"), ("output_tokens", "output_tokens"))}

    renders, flags = 0, []
    for e in events:
        content = (e.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                text = block["content"] if isinstance(block["content"], str) else \
                    "".join(c.get("text", "") for c in block["content"] if isinstance(c, dict))
                if FALLBACK.search(text):
                    flags.append("a render fell back to LibreOffice: PowerPoint didn't answer")
            if block.get("type") != "tool_use":
                continue
            target = block["input"].get("command") or block["input"].get("file_path") \
                or block["input"].get("path") or ""
            first = target.splitlines()[0][:100] if target else ""
            if block["name"] == "Bash":
                renders += bool(RENDER.search(target))
                if PROGRAM.search(target) and method != "python-pptx":
                    flags.append(f"ran a program: `{first}`")
                # pikslide's --check reports where everything went
                if method == "pikslide" and re.search(r"\bunzip\b", target):
                    flags.append(f"took the .pptx apart: `{first}`")
            if str(REPO) in target or "docs/cookbook" in target:
                flags.append(f"reached the repository: {block['name']} `{first}`")
    # an API error still ends in subtype "success", with is_error set
    ended_well = result.get("subtype") == "success" and not result.get("is_error")
    return {"ended_well": ended_well, **tokens, "cost_usd": result.get("total_cost_usd", 0.0),
            "turns": result.get("num_turns", 0), "renders": renders, "flags": flags}


def run_one(task: str, method: str, n: int, args: argparse.Namespace, home: Path, versions: dict) -> None:
    out = BENCH / "results" / task / method / f"{n:02d}"
    if (out / "run.json").exists():
        return
    partial = out.with_name(out.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    runs_root().mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{task}-{method}-{n:02d}-", dir=runs_root()))
    text = prompt(task, method)
    (partial / "prompt.md").write_text(text, encoding="utf-8")

    print(f"{time.strftime('%H:%M:%S')} {task} {method} {n:02d} ...", flush=True)
    start = time.time()
    exit_code, timed_out = None, False
    try:
        done = subprocess.run(command(method, args), input=text, text=True, cwd=work, env=claude_env(home),
                              capture_output=True, timeout=args.timeout * 60)
        exit_code, stream = done.returncode, done.stdout
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stream = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
    seconds = round(time.time() - start, 1)

    # An API error (login, usage limit, overload) says nothing about the
    # method: stop, and leave the run to be made again.
    lines = stream.splitlines()
    result = json.loads(lines[-1]) if lines and lines[-1].startswith("{") else {}
    if result.get("is_error") and result.get("api_error_status"):
        shutil.rmtree(partial)
        sys.exit(f"{task} {method} {n:02d}: API error {result['api_error_status']}: {result.get('result')}")

    stats = measure(stream, method)
    for kept in KEPT[method]:
        if (work / kept.format(name=task)).exists():
            shutil.copy(work / kept.format(name=task), partial)
    finished = (stats.pop("ended_well") and not timed_out
                and (work / f"{task}.pptx").exists() and (work / f"{task}.png").exists())
    run = {"task": task, "method": method, "round": n, "model": args.model, "effort": args.effort,
           "exit_code": exit_code, "timed_out": timed_out, "finished": finished, "seconds": seconds,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start)), **versions, **stats}
    (partial / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    partial.rename(out)
    print(f"{time.strftime('%H:%M:%S')} {task} {method} {n:02d} done in {seconds / 60:.1f} min"
          f"{' (timed out)' if timed_out else ''}", flush=True)


def check_isolation(home: Path) -> None:
    """One short run, to show what a run is given: its tools, MCP servers,
    skills and plugins, and what the model says it was told."""
    root = runs_root()
    root.mkdir(parents=True, exist_ok=True)
    work = tempfile.mkdtemp(prefix="check-", dir=root)
    question = ("Quote the first line of every CLAUDE.md, memory or other instruction file you were "
                "given, and name every skill you can use. Say 'none' for each if there are none.")
    p = subprocess.run(["claude", "-p", "--model", "claude-haiku-5-5", "--output-format", "stream-json",
                        "--verbose", "--no-session-persistence", "--strict-mcp-config", "--permission-mode",
                        "dontAsk", "--tools", ",".join(ALLOWED), "--disallowedTools", *DISALLOWED],
                       input=question, text=True, capture_output=True, cwd=work, env=claude_env(home))
    events = [json.loads(line) for line in p.stdout.splitlines() if line.startswith("{")]
    init = next((e for e in events if e.get("subtype") == "init"), {})
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    for key in ("cwd", "apiKeySource", "tools", "mcp_servers", "skills", "plugins", "agents"):
        if key in init:
            print(f"{key}: {json.dumps(init[key], ensure_ascii=False)}")
    print(f"answer: {result.get('result', p.stderr.strip())}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--task", choices=TASKS, default="fizzbuzz", help="the task (default: fizzbuzz)")
    parser.add_argument("--runs", nargs="+", metavar="METHOD=N",
                        help="runs per method (default: " + " ".join(f"{m}={n}" for m, n in RUNS.items()) + ")")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--budget", type=float, default=20.0,
                        help="USD, at API rates, at which one run is stopped (default: 20)")
    parser.add_argument("--timeout", type=float, default=45.0, help="minutes for one run (default: 45)")
    parser.add_argument("--print-prompt", choices=METHODS, help="print a method's prompt and stop")
    parser.add_argument("--check-isolation", action="store_true",
                        help="make one short run that shows what a run is given, and stop")
    args = parser.parse_args()
    if args.print_prompt:
        print(prompt(args.task, args.print_prompt), end="")
        return
    runs = dict(RUNS)
    if args.runs:
        runs = {m: 0 for m in METHODS}
        for spec in args.runs:
            m, _, n = spec.partition("=")
            if m not in METHODS or not n.isdigit():
                parser.error(f"--runs: {spec!r} is not METHOD=N, METHOD one of {', '.join(METHODS)}")
            runs[m] = int(n)

    home = bench_home()
    if not (home / "venv" / "bin" / "pikslide").exists():
        sys.exit(f"no {home}/venv: run bench/setup.sh first")
    status = json.loads(subprocess.run(["claude", "auth", "status"], capture_output=True, text=True,
                                       env=claude_env(home)).stdout or "{}")
    if not status.get("loggedIn"):
        sys.exit(f"not logged in: env -u ANTHROPIC_API_KEY CLAUDE_CONFIG_DIR={home / 'claude'} claude auth login")
    if args.check_isolation:
        check_isolation(home)
        return

    versions = {
        "claude_version": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
        "pikslide_version": subprocess.run([home / "venv" / "bin" / "pikslide", "--version"],
                                           capture_output=True, text=True).stdout.strip(),
        "auth_method": status.get("authMethod"),
        # which reference the runs read: the version alone doesn't change with every edit
        "help_llm_sha256": hashlib.sha256(subprocess.run(
            [home / "venv" / "bin" / "pikslide", "--help", "llm"], capture_output=True).stdout).hexdigest()[:12],
    }
    methods = [m for m in METHODS if runs[m]]
    for n in range(1, max(runs.values()) + 1):
        k = (n - 1) % len(methods)
        for method in methods[k:] + methods[:k]:
            if n <= runs[method]:
                run_one(args.task, method, n, args, home, versions)


if __name__ == "__main__":
    main()
