# What a slide costs an LLM: pikslide, python-pptx and hand-written XML

## Introduction

Drawing a diagram for a slide is two jobs. One is saying what it means:
the steps, the decisions, what leads to what. The other is the design:
where each shape goes, how the lines bend round the others, what lines
up with what. By hand, the second takes most of the time.

With an LLM, the two can be split. A person says what the diagram means,
in natural language, and leaves the design to the LLM. What the LLM
hands back should then be something both can work on: not a picture,
and not a program, but a short text the LLM writes and a person can
read, which turns into a slide of native PowerPoint shapes.

Ask an LLM for a slide, though, and it makes the `.pptx` itself. A
`.pptx` is a zip of XML parts, and the LLM writes them: by hand, every
shape's position in the slide's XML, or, with a library such as
python-pptx, through a Python program that writes them for it. Either
way the LLM works out where everything goes, in coordinates, and what it
hands back is the deck, or a program.

pikslide is the text. A `.pik` places shapes one after another and
relative to one another, with no coordinates to work out, and pikslide
renders it into editable shapes in the deck's theme.

What does each cost the LLM? Claude Opus 5.5, in Claude Code, drew the
same flowchart three ways, five times each, each time until it had
looked at its own rendering and judged it done:

| per run, mean ± sd (n = 5) | pikslide | python-pptx | raw XML |
|---|---:|---:|---:|
| cost, at API rates | **$0.34** ± 0.03 | $0.54 ± 0.05 | $1.66 ± 0.07 |
| output tokens | **6,556** ± 914 | 15,974 ± 1,585 | 51,711 ± 1,326 |
| minutes | **1.3** ± 0.1 | 2.6 ± 0.3 | 7.5 ± 1.0 |
| turns | **8.4** ± 1.7 | 11.0 ± 1.6 | 29.4 ± 2.7 |
| renders | **1.0** ± 0.0 | 2.4 ± 0.5 | 2.4 ± 0.5 |
| what it wrote | **1.2–2.0 KB**: 40–51 lines of `.pik` | 7.0–8.0 KB: 220–264 lines of Python | 36.9–40.6 KB: 14–16 XML parts |

- **Against having the LLM write the `.pptx` itself**, the first thing
  one would try, pikslide costs a fifth as much, writes an eighth of the
  output, and is done in under a fifth of the time, in under a third of
  the turns.
- **Against python-pptx**, the closest of the two, pikslide costs 37%
  less, writes 59% less output, takes half the time, and renders once.

On each of these, the five runs of one method don't overlap the five of
another, but for two: python-pptx's turns overlap pikslide's, and
python-pptx and raw XML rendered as often as each other. All fifteen
slides are as the task says.

## The task

[tasks/fizzbuzz.md](tasks/fizzbuzz.md), a flowchart of FizzBuzz whose
every shape, text and arrow the task gives: ovals `Start` and `End`,
rectangles `i = 1` and `i = i + 1`, four diamonds, four parallelograms,
and thirteen arrows with their labels, the three `print`s joining into
one line down the right and a loop back round the left. Arrows end on
outlines, no line crosses a shape or another line, and no text overlaps
a line or runs out of its shape. Nothing else goes on the slide.

A task this fully specified leaves the LLM nothing to decide about what
the diagram says, only how to draw it, so runs differ by method rather
than by what each chose to draw. Its bent and joining lines are where
placing shapes by coordinates is hardest.

The method paragraph that goes into the task ([methods/](methods/)):

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

- **The run.** `claude -p` (Claude Code 2.1.330), model
  `claude-opus-5-5`, effort `xhigh`, logged in with a Claude
  subscription, with pikslide 0.7.0. Each run starts in a new directory
  outside `$HOME` and this repository, with a Claude Code config
  directory of its own: no CLAUDE.md, settings, hooks or memory, auto
  memory off, skills off, no MCP servers, and only the Bash, Read, Write
  and Edit tools. The raw XML runs may not run Python, Node, Perl, Ruby
  or uv. All three render with PowerPoint (`pikslide --png`, or
  `render-png`, which calls the same code).
- **Done** is when the LLM, having looked at its PNG, says so; every run
  got there, none hit the 45-minute or $20 cap. One python-pptx run was
  made again: PowerPoint hadn't answered when it rendered.
- **Tokens** are Claude Code's own count for the run: input, cache writes,
  cache reads and output (thinking included). Their total is dominated by
  cache reads, each turn reading the conversation so far again, so it
  overstates what the reading costs.
- **Cost** is Claude Code's `total_cost_usd` at Opus 5.5's API list rates,
  which reproduce every run's figure: per million tokens, $4 input, $8
  cache write (one-hour cache), $0.20 cache read and $20 output. The runs
  themselves were on a subscription.
- The methods were interleaved, their order rotated each round.
  [run.py](run.py) runs them, [summarize.py](summarize.py) tabulates
  them, and each run's prompt, statistics (`run.json`), program and deck
  are in `results/fizzbuzz/METHOD/NN/`.

## Results

### pikslide

| run | cost | turns | output | cache writes | cache reads | all tokens | renders | minutes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | $0.38 | 9 | 7,379 | 24,630 | 164,600 | 196,627 | 1 | 1.4 |
| 2 | $0.31 | 7 | 5,509 | 22,578 | 113,925 | 142,026 | 1 | 1.2 |
| 3 | $0.36 | 8 | 7,443 | 23,141 | 146,894 | 177,494 | 1 | 1.4 |
| 4 | $0.35 | 11 | 6,754 | 22,322 | 176,505 | 205,599 | 1 | 1.4 |
| 5 | $0.31 | 7 | 5,695 | 21,703 | 117,544 | 144,956 | 1 | 1.1 |

### python-pptx

| run | cost | turns | output | cache writes | cache reads | all tokens | renders | minutes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | $0.47 | 9 | 13,304 | 21,792 | 134,783 | 169,895 | 2 | 2.2 |
| 2 | $0.55 | 12 | 16,392 | 23,025 | 177,288 | 216,723 | 2 | 2.7 |
| 3 | $0.55 | 10 | 15,955 | 26,216 | 107,894 | 150,077 | 2 | 2.6 |
| 4 | $0.57 | 11 | 16,824 | 25,123 | 182,063 | 224,028 | 3 | 2.9 |
| 5 | $0.58 | 13 | 17,396 | 25,531 | 155,968 | 198,911 | 3 | 2.9 |

### Raw XML

| run | cost | turns | output | cache writes | cache reads | all tokens | renders | minutes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | $1.58 | 26 | 49,778 | 62,677 | 430,074 | 542,551 | 2 | 6.7 |
| 2 | $1.69 | 29 | 53,235 | 65,313 | 523,033 | 641,605 | 2 | 7.3 |
| 3 | $1.76 | 33 | 52,524 | 71,513 | 676,244 | 800,313 | 3 | 9.3 |
| 4 | $1.65 | 28 | 51,850 | 62,227 | 562,950 | 677,053 | 2 | 7.2 |
| 5 | $1.62 | 31 | 51,169 | 62,231 | 511,194 | 624,620 | 3 | 7.0 |

### Comparison

| per run: mean ± sd (min–max) | pikslide | python-pptx | raw XML |
|---|---:|---:|---:|
| cost | **$0.34** ± 0.03 (0.31–0.38) | $0.54 ± 0.05 (0.47–0.58) | $1.66 ± 0.07 (1.58–1.76) |
| output tokens | **6,556** ± 914 (5,509–7,443) | 15,974 ± 1,585 (13,304–17,396) | 51,711 ± 1,326 (49,778–53,235) |
| cache writes | 22,875 ± 1,109 (21,703–24,630) | 24,337 ± 1,856 (21,792–26,216) | 64,792 ± 3,970 (62,227–71,513) |
| cache reads | 143,894 ± 27,810 (113,925–176,505) | 151,599 ± 30,822 (107,894–182,063) | 540,699 ± 89,844 (430,074–676,244) |
| all tokens | 173,340 ± 29,096 (142,026–205,599) | 191,927 ± 31,349 (150,077–224,028) | 657,228 ± 93,974 (542,551–800,313) |
| turns | 8.4 ± 1.7 (7–11) | 11.0 ± 1.6 (9–13) | 29.4 ± 2.7 (26–33) |
| renders | **1.0** ± 0.0 (1–1) | 2.4 ± 0.5 (2–3) | 2.4 ± 0.5 (2–3) |
| minutes | **1.3** ± 0.1 (1.1–1.4) | 2.6 ± 0.3 (2.2–2.9) | 7.5 ± 1.0 (6.7–9.3) |

Where the cost goes, per run:

| | pikslide | python-pptx | raw XML |
|---|---:|---:|---:|
| output, $20/M | $0.13 | $0.32 | $1.03 |
| cache writes, $8/M | $0.18 | $0.19 | $0.52 |
| cache reads, $0.20/M | $0.03 | $0.03 | $0.11 |
| all | $0.34 | $0.54 | $1.66 |

- **Writing the `.pptx` by hand costs the most of everything.** A raw
  XML run writes the whole package: content types, relationships,
  presentation, slide master, layout, theme and the slide, 14 to 16
  parts, about 25 KB of XML for the slide alone, every shape's position
  and every bend of every line in coordinates. That is $1.03 of output, and 29
  turns whose conversation grows with all it has written, read again
  each turn.
- **python-pptx writes the package, but the LLM still places every
  shape.** Every python-pptx run wrote a small layout engine before it
  drew anything: 9 to 16 functions of its own to place a shape by its
  center, find where a parallelogram's slanted side is, draw a polyline,
  put a label beside a line, and a running `y` down the column. Only
  then could it place each shape.
- **pikslide is that engine already**, so a `.pik` says only what goes
  where, relative to what:

  ```
  End: oval "End" same as Start with .w at Cond.e + (side, 0)
  arrow from Cond.e to End.w "no" above
  ```

  It is a fifth the length of the python-pptx script and under a
  twentieth of the hand-written XML. Output, thinking included, is where pikslide
  saves most: $0.19 of the $0.20 between it and python-pptx.
- **One render.** Every pikslide run rendered once and was done. The
  reference tells it to check a diagram with `--check`, which prints
  where every object went, and any overlap, as JSON, without a picture
  to make and read. The python-pptx and raw XML runs rendered two or
  three times, looking at a PNG each time to see what they had drawn.
- **What pikslide pays is the reference**, `pikslide --help llm` (24.5
  KB), read once a run and cached. Even so, its cache writes come out
  about the same as python-pptx's: python-pptx reads no reference, but
  its longer script and its extra renders go into the conversation
  instead.
- **Not told apart from python-pptx in five runs: all tokens and
  turns.** Both are mostly cache reads, the conversation read again each
  turn, and their ranges overlap: pikslide's means are lower, but five
  runs can't say that they are. Against raw XML they can: a quarter of
  the tokens, and under a third of the turns.

### Quality

All fifteen slides are as the task says. [check.py](check.py) read every
deck: one slide, the twelve shapes each of its kind and with its text,
four "yes" and four "no" labels, and nothing else on it, no other text,
placeholder or notes. Every PNG, rendered again from its deck with
PowerPoint and looked at, has each arrow where the task says, the three
prints joining one line into `i = i + 1` and the loop going back round
the left, with no line crossing a shape or another line, and no text
overlapping a line. The PNGs aren't kept; `render-png` draws one again
from a run's deck. pikslide drew `Start` and `End` as pills, as its
`oval` is; the other runs drew ellipses. No method bought its cost with
a worse slide.

## Discussion: beyond the benchmark

The benchmark counts one diagram, drawn once. A diagram outlives that:
it is changed, kept, reused. There, what pikslide gives is not in the
figures above.

- **Editing without an LLM costs no tokens.** The `.pik` is the diagram,
  in some fifty lines a person can read. A label, a color or a new step
  is a line or two to change, and the rest follows, since each shape is
  placed by the ones before it. Adding a step after `i = 1` to a run's
  `.pik` took two lines; every shape below it moved down, the prints'
  line and the loop followed, and `--check` found nothing wrong.
  pikslide renders it again in about a second. Changing a python-pptx
  slide means changing a Python program of 220 lines or more, and knowing
  python-pptx; changing a hand-written one, 25 KB of slide XML.
- **Editing with an LLM costs little.** Asked for a change, the LLM
  reads and rewrites a `.pik` a fifth the size of the script, under a
  twentieth of the XML, and changes the lines it is about, not the
  coordinates below them.
- **Editing in PowerPoint, and back.** The deck is native shapes, each
  named after its label in the `.pik` (`Start`, `Init`, `Cond`, … where
  python-pptx's are `Oval 1`, `Rectangle 2`, …). A person can finish the
  slide in PowerPoint, and an LLM given the edited deck can match each
  shape to its line and carry the edits into the `.pik`.
- **Reproducible.** The same `.pik` renders the same deck. A run's
  `.pik`, rendered again hours later, wrote every part of the `.pptx`
  byte for byte as the run had; only the zip's file times differ. The
  `.pik` is what to keep, in git, and what a diff shows. (With the same
  pikslide and fonts: `fit` measures text in the fonts installed.)
- **A diagram is text.** It can be pasted into a chat, an issue, a review
  or a Markdown file, and taken apart and put together: a block,
  `[ … ]`, goes from one diagram into another with its names.
- **Templates, as macros and as decks.** `define` makes a house shape a
  word (`define card { box $1 fill accent1 fit }`), and `include` shares
  such definitions between diagrams; pikslide ships `figures.pik`,
  macros for cycles, chevrons, pyramids, funnels, Venn diagrams, a
  matrix and hubs. `--template` draws in a company deck's theme, its
  colors and fonts, which the shapes keep linked: the diagram recolors
  with the deck.

## Caveats

- One task, one model, one effort setting, five runs a method. Runs
  vary: pikslide's cost from $0.31 to $0.38, python-pptx's from $0.47 to
  $0.58, raw XML's from $1.58 to $1.76.
- What the task doesn't specify is up to the LLM. All ten python-pptx
  and raw XML runs colored their shapes, and six set the shapes' text in
  a monospace font; one pikslide run colored its shapes. Coloring takes
  output: that pikslide run wrote 7,379 output tokens, against 5,509 to
  7,443 for the five.
- Cost is at API list rates; the runs were on a subscription.
