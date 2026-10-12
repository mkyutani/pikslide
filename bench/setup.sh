#!/bin/sh
# Prepare $BENCH_HOME, outside the repository so a run can't find
# docs/cookbook/flowchart.pik, fizzbuzz's own diagram: a venv with this
# checkout of pikslide (and python-pptx, its dependency), the render-png
# command, and claude/, the runs' own Claude Code config directory.
set -eu

repo=$(cd "$(dirname "$0")/.." && pwd)
home=${BENCH_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/pikslide-bench}

mkdir -p "$home/bin" "$home/claude"
uv venv --quiet --allow-existing --python ">=3.12" "$home/venv"
uv pip install --quiet --reinstall-package pikslide --python "$home/venv/bin/python" "$repo"

{
    echo "#!$home/venv/bin/python"
    cat "$repo/bench/render_png.py"
} > "$home/bin/render-png"
chmod 755 "$home/bin/render-png"

echo "$home: $("$home/venv/bin/pikslide" --version)"
# (with no API key in the way: it would win over the login)
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN CLAUDE_CONFIG_DIR="$home/claude" \
    claude auth status 2>/dev/null | grep -q '"loggedIn": true' \
    || echo "log in for the runs: env -u ANTHROPIC_API_KEY CLAUDE_CONFIG_DIR=$home/claude claude auth login"
