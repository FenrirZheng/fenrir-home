#!/usr/bin/env bash
# PreToolUse: deny file tools on paths outside $CLAUDE_JAIL_ROOT. Written by claude-jail.
set -uo pipefail
root="${CLAUDE_JAIL_ROOT:?}"
input="$(cat)"
p="$(jq -r '.tool_input | (.file_path // .notebook_path // .path // empty)' <<<"$input")"
[[ -z "$p" ]] && exit 0                      # Glob/Grep default to cwd
cwd="$(jq -r '.cwd // empty' <<<"$input")"
[[ "$p" == "~"* ]] && p="$HOME${p:1}"
[[ "$p" != /* ]] && p="${cwd:-$root}/$p"
abs="$(realpath -m -- "$p")"
if [[ "$abs" == "$root" || "$abs" == "$root"/* ]]; then exit 0; fi
echo "claude-jail: access outside $root is blocked ($abs)" >&2
exit 2
