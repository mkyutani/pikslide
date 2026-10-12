# Benchmarks

What it takes an LLM, in tokens, to finish a slide three ways: with
pikslide, with python-pptx, and by writing the .pptx's XML by hand. Each
run is a `claude -p` in a fresh directory outside `$HOME` and this
repository, with Claude Code's own config directory for the benchmark (no
CLAUDE.md, settings, hooks, plugins, skills or memory of yours, and auto
memory off) and only Bash, Read, Write and Edit for tools, given
[tasks/](tasks/)`TASK.md` with [methods/](methods/)`METHOD.md` in it. It
renders with PowerPoint, and ends when the LLM, having looked at its own
PNG, says it's done.

The task, [fizzbuzz](tasks/fizzbuzz.md), is the flowchart of
[docs/cookbook/flowchart.md](../docs/cookbook/flowchart.md), every shape,
text and arrow of it given, so that the runs differ by method, not by what
each LLM decides to draw.

```sh
sh bench/setup.sh                         # $BENCH_HOME: a venv with this pikslide, render-png;
                                          # the first time, it says how to log in for the runs
python3 bench/run.py --check-isolation    # one short run: what a run is given
python3 bench/run.py                      # fizzbuzz: three runs of each method
python3 bench/summarize.py > summary.md   # the tables, from each run's run.json
python3 bench/check.py                    # each fizzbuzz deck against the task
```

`--task` picks the task, and `--runs METHOD=N ...` how many runs. The
runs use the Claude subscription logged in there. A run stops at
`--budget` USD at API rates (20) or `--timeout` minutes (45), and the
benchmark stops at an API error (a usage limit, say) without keeping that
run; runs already made are kept. A run's prompt (`prompt.md`), its
statistics (`run.json`: tokens, cost, turns, renders, minutes, the
versions it ran, and anything it shouldn't have done) and what it made,
its program (`.pik`, `make_slide.py`) and the deck, are in
`results/TASK/METHOD/NN/`. What Claude Code printed during the run is
read for the statistics and not kept. `BENCH_HOME` defaults to
`~/.cache/pikslide-bench`, `BENCH_RUNS`, where the runs work, to
`$TMPDIR/pikslide-bench-runs`.

## Checking the slides

For fizzbuzz, `check.py` checks each deck against the task from the
.pptx itself: one slide, the twelve shapes each of its kind and with its
text, four "yes" and four "no" labels, and nothing else on it. What the
deck can't tell is for looking at its picture, which
`render-png DECK.pptx`, in `$BENCH_HOME/bin`, draws: each arrow going
where the task says, the three prints joining, the loop back, no line
crossing a shape or another line, and no text overlapping a line or
running out of its shape.

A run whose render fell back to LibreOffice, PowerPoint not answering, is
flagged by `summarize.py`, and is made again.
