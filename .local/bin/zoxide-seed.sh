#!/usr/bin/env bash
# zoxide-seed [root] [max-depth]
# Seeds zoxide with all directories under <root> up to <max-depth>.
set -euo pipefail

root="${1:-.}"
depth="${2:-5}"

command -v zoxide >/dev/null || { echo "zoxide not installed" >&2; exit 1; }
command -v fdfind >/dev/null || { echo "fdfind not installed (apt install fd-find)" >&2; exit 1; }

count=0
while IFS= read -r -d '' dir; do
  zoxide add -- "$dir"
  count=$((count + 1))
done < <(fdfind --type d --max-depth "$depth" --print0 . "$root")

echo "seeded $count directories under $root (depth $depth)"