Draw a flowchart of FizzBuzz on a slide: for i from 1 to 100, print
"FizzBuzz" for a multiple of 15, "Fizz" for a multiple of 3, "Buzz" for a
multiple of 5, and i otherwise. The slide holds the flowchart and nothing
else: no title, no notes.

Shapes, each with exactly the text between the backquotes:

- ovals: `Start`, `End`
- rectangles: `i = 1`, `i = i + 1`
- diamonds: `i <= 100`, `i % 15 == 0`, `i % 3 == 0`, `i % 5 == 0`
- parallelograms: `print i`, `print "FizzBuzz"`, `print "Fizz"`,
  `print "Buzz"`

Layout:

- One column, top to bottom, joined by arrows: `Start`, `i = 1`,
  `i <= 100`, `i % 15 == 0`, `i % 3 == 0`, `i % 5 == 0`, `print i`,
  `i = i + 1`. Label the arrow out of `i <= 100` "yes", and those out of
  the other three diamonds "no".
- `End` is to the right of `i <= 100`, joined by an arrow labeled "no".
- From each of `i % 15 == 0`, `i % 3 == 0` and `i % 5 == 0`, an arrow
  labeled "yes" goes right to its own print: `print "FizzBuzz"`,
  `print "Fizz"`, `print "Buzz"`.
- The three prints join into one line down the right side, ending in an
  arrow into `i = i + 1`.
- From `i = i + 1`, an arrow goes round the left side, back into
  `i <= 100`.
- Arrows end on the outlines of the shapes they join. No line crosses a
  shape or another line, and no text overlaps a line or runs out of its
  shape.

Draw it with pikslide, a command that turns a diagram written as text into
a .pptx: write fizzbuzz.pik and render it with
`pikslide fizzbuzz.pik fizzbuzz.pptx --png`, which also writes fizzbuzz.png.
Start with `pikslide --help llm`, the language reference in one text.

Look at the PNG yourself before you finish, and fix anything above it
doesn't meet, then render again. Keep every file in the current directory.
