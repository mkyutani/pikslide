# Responding to an outage

[incident-response.pik](incident-response.pik) was drawn by Claude Code: the prompt below, given
as it is to a new Claude Code session at the repository's root
(`claude -p`), in one run. That run checked it with `--check` and looked
at the pictures `--renderer direct` drew; [incident-response.pptx](incident-response.pptx) and
the PNG below were rendered afterwards, the PNG by PowerPoint.

![incident-response.png: a flowchart: an alert fires, is acknowledged and its severity assessed; for SEV1 or SEV2 the incident commander is paged and the status page posted on; then mitigate, and until the service has recovered, mitigate again; then resolve the incident and write the postmortem](incident-response.png)

## The prompt

```text
Draw a slide with pikslide: a flowchart of how an on-call engineer
responds when a web service goes down.

1. An alert fires; the engineer acknowledges it and assesses the
   severity.
2. A decision: is it SEV1 or SEV2? If so, page the incident commander and
   post on the status page; if not, go straight on.
3. Then mitigate, and verify that the service has recovered: if it
   hasn't, back to mitigate. Then resolve the incident and write the
   postmortem.

Save the diagram as docs/examples/incident-response.pik, and render it with
`uv run pikslide docs/examples/incident-response.pik docs/examples/incident-response.pptx --png --renderer direct`.

Start with `uv run pikslide --help llm`, and use `--help KEYWORD` for
anything else you need. Fix every warning `--check` gives. Look at the
PNG yourself before you finish: text that overlaps or overflows, arrows
that miss what they join, anything out of place. Fix it and render again.
```
