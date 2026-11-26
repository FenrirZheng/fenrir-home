#!/usr/bin/env bash
# Launch Claude Code on Sonnet 5.5 (model id claude-sonnet-5-5).
# Usage: claude-sonnet5-5-launch.sh [any claude arguments]
#   claude-sonnet5-5-launch.sh                 interactive session
#   claude-sonnet5-5-launch.sh -p "question"   one-shot, prints the answer
# Extra arguments are passed through to claude unchanged.
#
# Why three settings, not just --model: `/model` in any other session saves its choice as the
# default in ~/.claude/settings.json, which every session shares and reloads. The model is
# therefore pinned three ways:
#   --model                  this session's model at start
#   --settings '{"model"}'   command-line settings, which rank above user and project
#                            settings, so a default saved by another session does not win
#   ANTHROPIC_MODEL          the environment fallback for this process
# Not covered: running `/model` inside the launched session itself still switches it.
set -euo pipefail

MODEL="claude-sonnet-5-5"

if ! command -v claude >/dev/null 2>&1; then
  echo "claude: command not found (is Claude Code installed and on PATH?)" >&2
  exit 127
fi

export ANTHROPIC_MODEL="$MODEL"
exec claude --model "$MODEL" --settings "{\"model\":\"$MODEL\"}" "$@"
