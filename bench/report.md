# What a slide costs an LLM: pikslide, python-pptx and hand-written XML

An LLM (Claude Opus 5.5, in Claude Code) drew the same flowchart onto a
PowerPoint slide three ways, three times each, until it had looked at its
own rendering and judged it done:

- **pikslide**: write a `.pik` and render it with `pikslide`
- **python-pptx**: write a Python script that uses python-pptx
- **raw XML**: write the `.pptx` package's XML parts by hand and `zip` them

| per run (mean of 3) | pikslide | python-pptx | raw XML |
|---|---:|---:|---:|
| cost, at API rates | **$0.37** | $0.54 | $1.97 |
| output tokens | **7,315** | 15,267 | 59,841 |
| all tokens | **186,334** | 218,048 | 937,550 |
| turns | **8.7** | 14.7 | 34.3 |
| minutes | **1.5** | 2.6 | 9.0 |

With pikslide the run cost 31% less than with python-pptx and took a
little over half the time, writing less than half the output. It reads a
reference python-pptx needs none of, yet with fewer turns it read less in
all.

## The task

[tasks/fizzbuzz.md](tasks/fizzbuzz.md), a flowchart of FizzBuzz whose
every shape, text and arrow the task gives: ovals `Start` and `End`,
rectangles `i = 1` and `i = i + 1`, four diamonds, four parallelograms,
and thirteen arrows with their labels, the three `print`s joining into
one line down the right and a loop back round the left. Arrows end on
outlines, no line crosses a shape or another line, and no text overlaps
a line or runs out of its shape. Nothing else goes on the slide.

A task this fully specified leaves nothing to the LLM's taste, so runs
differ by method rather than by what each decides to draw, and it needs
neither an image to read nor anything to know. Its bent and joining lines
are where placing shapes by coordinates is hardest.

The method paragraph that goes into the task, by method
([methods/](methods/)):

- pikslide: *write fizzbuzz.pik and render it with
  `pikslide fizzbuzz.pik fizzbuzz.pptx --png` … Start with
  `pikslide --help llm`, the language reference in one text.*
- python-pptx: *write make_slide.py, a Python script that uses
  python-pptx (installed) … Render the slide with `render-png`.*
- raw XML: *build fizzbuzz.pptx by hand, with no Python or other program
  generating it: write each part of the package … and zip the parts …*

Each ends: *Look at the PNG yourself before you finish, and fix anything
above it doesn't meet, then render again.*

## How it was measured

- **The run.** `claude -p` (Claude Code 2.1.296), model
  `claude-opus-5-5`, effort `xhigh`, logged in with a Claude subscription.
  Each run starts in a new directory outside `$HOME` and this repository,
  with a Claude Code config directory of its own: no CLAUDE.md, settings,
  hooks, plugins, skills or memory, auto memory off, no MCP servers, and
  only the Bash, Read, Write and Edit tools. The raw XML runs may not run
  Python, Node, Perl, Ruby or uv. All three render with PowerPoint
  (`pikslide --png`, or `render-png`, which calls the same code).
- **Done** is when the LLM, having looked at its PNG, says so; every run
  got there, none hit the 45-minute or $20 cap. One python-pptx run was
  made again: PowerPoint hadn't answered within two minutes, and its
  render had fallen back to LibreOffice.
- **Tokens** are Claude Code's own count for the run: input, cache writes,
  cache reads and output (thinking included). Their total is dominated by
  cache reads, each turn reading the conversation so far again, so it
  overstates what the reading costs.
- **Cost** is Claude Code's `total_cost_usd` at Opus 5.5's API list rates,
  which reproduce every run's figure exactly: per million tokens, $4
  input, $8 cache write (one-hour cache), $0.20 cache read and $20 output.
  The runs themselves were on a subscription.
- The methods were interleaved, their order rotated each round.
  [run.py](run.py) runs them, [summarize.py](summarize.py) tabulates
  them, and each run's prompt, statistics (`run.json`), program and deck
  are in `results/fizzbuzz/METHOD/NN/`.

## 1. pikslide

| run | cost | turns | output | cache writes | cache reads | all tokens | minutes |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | $0.39 | 7 | 7,976 | 25,752 | 131,874 | 165,616 | 1.5 |
| 2 | $0.42 | 12 | 8,658 | 24,979 | 237,319 | 270,978 | 1.7 |
| 3 | $0.29 | 7 | 5,310 | 21,081 | 96,005 | 122,408 | 1.1 |
| mean | $0.37 | 8.7 | 7,315 | 23,937 | 155,066 | 186,334 | 1.5 |

A run reads the reference, `pikslide --help llm` (11,525 tokens), looks
up the parallelogram presets once, writes the `.pik` (1,200 to 1,700
characters), checks it with `--check`, renders it once and looks at the
PNG; one run also zoomed in where lines meet.

## 2. python-pptx

| run | cost | turns | output | cache writes | cache reads | all tokens | minutes |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | $0.52 | 12 | 15,295 | 23,384 | 131,763 | 170,458 | 2.6 |
| 2 | $0.55 | 14 | 15,826 | 24,976 | 187,090 | 227,912 | 2.7 |
| 3 | $0.55 | 18 | 14,679 | 27,218 | 213,855 | 255,774 | 2.6 |
| mean | $0.54 | 14.7 | 15,267 | 25,193 | 177,569 | 218,048 | 2.6 |

A run writes a script of 6,800 to 7,500 characters, the coordinates of
every shape and every bend worked out in it, runs it, renders, and looks.

## 3. Raw XML

| run | cost | turns | output | cache writes | cache reads | all tokens | minutes |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | $1.74 | 30 | 54,111 | 68,079 | 564,490 | 686,706 | 7.4 |
| 2 | $2.21 | 38 | 67,702 | 85,546 | 877,938 | 1,031,226 | 11.6 |
| 3 | $1.97 | 35 | 57,709 | 77,614 | 959,356 | 1,094,717 | 7.9 |
| mean | $1.97 | 34.3 | 59,841 | 77,080 | 800,595 | 937,550 | 9.0 |

A run writes the package part by part, sixteen files: content types,
relationships, presentation, master, layout, theme and the slide, then
zips them.

## 4. Comparison

| per run (mean of 3) | pikslide | python-pptx | raw XML |
|---|---:|---:|---:|
| cost | **$0.37** | $0.54 | $1.97 |
| output tokens | **7,315** | 15,267 | 59,841 |
| cache writes | 23,937 | 25,193 | 77,080 |
| cache reads | **155,066** | 177,569 | 800,595 |
| all tokens | **186,334** | 218,048 | 937,550 |
| turns | **8.7** | 14.7 | 34.3 |
| minutes | **1.5** | 2.6 | 9.0 |

Where the cost goes, per run:

| | pikslide | python-pptx | raw XML |
|---|---:|---:|---:|
| output, $20/M | $0.15 | $0.31 | $1.20 |
| cache writes, $8/M | $0.19 | $0.20 | $0.62 |
| cache reads, $0.20/M | $0.03 | $0.04 | $0.16 |

- **Output is where pikslide wins.** A `.pik` places shapes relative to
  each other, so it is a fifth the length of a python-pptx script that
  spells out every coordinate, and the output, thinking included, less
  than half.
- **The reference is what pikslide pays.** Its 11,500 tokens are written
  to the cache once (about $0.09) and read again every turn after; with
  fewer turns, pikslide still reads less in all than python-pptx.
- **Raw XML** spends the most of everything: it writes a whole package
  by hand, and its turns are many.

### Quality

All nine slides are as the task says. [check.py](check.py) read every
deck: one slide, the twelve shapes each of its kind and with its text,
four "yes" and four "no" labels, and nothing else on it, no other text,
placeholder or notes. Every final PNG, looked at when its run was made,
has each arrow where the task says, the three prints joining one line
into `i = i + 1` and the loop going back round the left, with no line
crossing a shape or another line, and no text overlapping a line. The
PNGs aren't kept; `render-png` draws one again from a run's deck. No
method bought its cost with a worse slide.

## Caveats

- One task, one model, one effort setting, three runs a method. Runs
  vary: pikslide's ranged from $0.29 to $0.42, python-pptx's from $0.52
  to $0.55.
- What isn't specified is up to the LLM: the python-pptx and raw XML runs
  colored their shapes and the pikslide runs didn't, which took the
  pikslide runs a little less output.
- Cost is at API list rates; the runs were on a subscription.
