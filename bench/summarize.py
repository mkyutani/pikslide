"""Summarize a task's runs, bench/results/TASK, as Markdown, from each
run's run.json: per method, what a run took -- input tokens, cache
writes, cache reads, output tokens and their total, the cost, turns,
renders and minutes -- as mean, sd, median, min and max; how many runs
finished; and each thing a run shouldn't have done, or that went wrong
round it (a render that fell back to LibreOffice)."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

BENCH = Path(__file__).resolve().parent
RESULTS = BENCH / "results"
METHODS = ("pikslide", "python-pptx", "raw-xml")
METRICS = (("input", "input tokens"), ("cache_write", "cache writes"), ("cache_read", "cache reads"),
           ("output", "output tokens"), ("total", "total tokens"), ("cost", "cost (USD, API rates)"),
           ("turns", "turns"), ("renders", "renders"), ("minutes", "minutes"))


def read_run(path: Path) -> dict:
    run = json.loads((path / "run.json").read_text(encoding="utf-8"))
    tokens = {"input": run["input_tokens"], "cache_write": run["cache_write_tokens"],
              "cache_read": run["cache_read_tokens"], "output": run["output_tokens"]}
    return {**run, **tokens, "total": sum(tokens.values()), "cost": run["cost_usd"], "minutes": run["seconds"] / 60}


def fmt(key: str, x: float) -> str:
    if key == "cost":
        return f"{x:.2f}"
    if key in ("turns", "renders", "minutes"):
        return f"{x:.1f}"
    return f"{x:,.0f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--task", default="fizzbuzz", help="the task (default: fizzbuzz)")
    results = RESULTS / parser.parse_args().task
    runs = sorted((read_run(p) for p in results.glob("*/[0-9][0-9]") if (p / "run.json").exists()),
                  key=lambda r: (METHODS.index(r["method"]), r["round"]))
    if not runs:
        raise SystemExit(f"no runs in {results}")
    by_method = {m: [r for r in runs if r["method"] == m] for m in METHODS}
    by_method = {m: rs for m, rs in by_method.items() if rs}

    print("## Runs\n")
    print("| method | runs | finished | timed out |")
    print("|---|---:|---:|---:|")
    for m, rs in by_method.items():
        print(f"| {m} | {len(rs)} | {sum(r['finished'] for r in rs)} | {sum(r['timed_out'] for r in rs)} |")

    print("\n## Per run (mean ± sd; median; min–max)\n")
    print("| | " + " | ".join(by_method) + " |")
    print("|---|" + "---:|" * len(by_method))
    for key, label in METRICS:
        cells = []
        for rs in by_method.values():
            xs = [r[key] for r in rs]
            sd = statistics.stdev(xs) if len(xs) > 1 else 0.0
            cells.append(f"{fmt(key, statistics.mean(xs))} ± {fmt(key, sd)}; {fmt(key, statistics.median(xs))}; "
                         f"{fmt(key, min(xs))}–{fmt(key, max(xs))}")
        print(f"| {label} | " + " | ".join(cells) + " |")

    if "pikslide" in by_method and len(by_method) > 1:
        print("\n## Against pikslide (ratio of means)\n")
        base = by_method["pikslide"]
        print("| | " + " | ".join(m for m in by_method if m != "pikslide") + " |")
        print("|---|" + "---:|" * (len(by_method) - 1))
        for key, label in METRICS:
            b = statistics.mean(r[key] for r in base)
            cells = [f"{statistics.mean(r[key] for r in rs) / b:.2f}×" if b else "–"
                     for m, rs in by_method.items() if m != "pikslide"]
            print(f"| {label} | " + " | ".join(cells) + " |")

    flagged = [r for r in runs if r["flags"]]
    print("\n## Flags\n")
    if not flagged:
        print("none")
    for r in flagged:
        for flag in r["flags"]:
            print(f"- {r['method']} {r['round']:02d}: {flag}")


if __name__ == "__main__":
    main()
