# Security

Report a vulnerability privately, through GitHub's
[private vulnerability reporting](https://github.com/mkyutani/pikslide/security/advisories/new),
not in a public issue. Say what it lets someone do and how to make it
happen: the `.pik`, the command or the MCP tool call that shows it.

A fix goes into the latest release only. Upgrade to it to have the fix:
`pip install -U pikslide`, and `pikslide-mcp` with it if you use that.

## What pikslide guards

A diagram may be written by an LLM, so pikslide reads a `.pik` as text
it doesn't trust:

- `include` and `image` read only files under the directory of the file
  they're in (and, for `include`, under the include paths given and the
  files pikslide ships). An absolute path, or one that leads out, is an
  error that doesn't say whether the file exists.
- pikslide-mcp reads and writes only in its workspace: `--root`, else
  the directory it was started in.

A way round either is a vulnerability.
