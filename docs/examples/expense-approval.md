# How an expense claim is approved

[expense-approval.pik](expense-approval.pik) was drawn by Claude Code: the prompt below, given
as it is to a new Claude Code session at the repository's root
(`claude -p`), in one run. That run checked it with `--check` and looked
at the pictures `--renderer direct` drew; [expense-approval.pptx](expense-approval.pptx) and
the PNG below were rendered afterwards, the PNG by PowerPoint.

![expense-approval.png: a swimlane diagram: lanes Employee, Manager and Finance, named vertically at their left; the claim entered, its receipts attached and submitted; the manager's decision, approving it or sending it back to the employee; Finance checking it and paying it with the next salary](expense-approval.png)

## The prompt

```text
Draw a slide with pikslide: a swimlane diagram of how an expense claim
is approved.

1. Three lanes, top to bottom: Employee, Manager, Finance. Write each
   lane's name vertically at its left end.
2. The employee enters the claim, attaches the receipts and submits it.
   The manager checks it, and approves it or sends it back to the
   employee to fix. Finance checks the approved claim and pays it with
   the next salary.
3. Draw the send-back as an arrow from the manager's decision back to
   the employee, labeled "Send back".

Save the diagram as docs/examples/expense-approval.pik, and render it with
`uv run pikslide docs/examples/expense-approval.pik docs/examples/expense-approval.pptx --png --renderer direct`.

Start with `uv run pikslide --help llm`, and use `--help KEYWORD` for
anything else you need. Fix every warning `--check` gives. Look at the
PNG yourself before you finish: text that overlaps or overflows, arrows
that miss what they join, anything out of place. Fix it and render again.
```
