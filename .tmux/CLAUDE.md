# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Scope

This directory is `~/.tmux/` — only tmux plugin storage. The actual config lives one level up at [`~/.tmux.conf`](../.tmux.conf); edits to behavior almost always happen there, not here.

## Plugin manager

Plugins are managed by **TPM** (Tmux Plugin Manager). [`plugins/`](./plugins/) holds clones of declared plugins:

- `tpm` — the manager itself. *(TPM-managed, untracked.)*
- `tmux-sensible` — sensible defaults. *(TPM-managed, untracked.)*
- `tmux-thumbs` — `prefix + Space` to grab regex matches into clipboard. *(TPM-managed, untracked.)*
- `tmux-jump-rust` — `prefix + j` ace-jump (Rust port; binary built under `tmux-jump-rust/target/`). *(Git submodule → `git@github.com:FenrirZheng/tmux-ace-jump.git`.)*

In-tmux keys: `prefix + I` install, `prefix + U` update, `prefix + alt+u` clean. After editing `~/.tmux.conf`: `tmux source-file ~/.tmux.conf` to reload without restarting.

## Plugin tracking policy: TPM-managed by default, one submodule

[`plugins/`](./plugins/) has a **mixed policy** in the parent dotfiles repo:

- **Default — not tracked.** Most plugins (`tpm`, `tmux-sensible`, `tmux-thumbs`) are excluded by [root `.gitignore`](../.gitignore) line `/.tmux/plugins/*`. They're owned end-to-end by TPM: `prefix + I` populates them after a fresh checkout, `prefix + U` updates them silently, and they never appear in `git status`. Local edits are throwaway — the next `prefix + U` erases them.
- **Exception — `tmux-jump-rust` is a git submodule** registered in [root `.gitmodules`](../.gitmodules), pointing at the user's own Rust port `git@github.com:FenrirZheng/tmux-ace-jump.git`. Submodule git data is absorbed into `<parent>/.git/modules/.tmux/plugins/tmux-jump-rust/`; the inner `.git` is a `gitdir:` pointer file. The whitelist `!/.tmux/plugins/tmux-jump-rust` in root `.gitignore` is documentation — submodule entries are tracked through the index regardless of gitignore.

Earlier history had mode-`160000` gitlinks for **all** plugins **without** a `.gitmodules` (the broken half-submodule state) and was briefly converted to "vendor everything as plain content." Both extremes were wrong; the current split keeps each plugin under the cheapest mechanism that fits. See [project-root `CLAUDE.md`](../CLAUDE.md) for the full rationale.

Consequences for editing plugins:

- **TPM plugins** — hand edits do not survive `prefix + U`. If you need a permanent local patch, fork upstream, point TPM at the fork, or convert it to a submodule like `tmux-jump-rust`.
- **`tmux-jump-rust` submodule** — `prefix + U` updates the inner repo's HEAD; the parent then shows `modified: .tmux/plugins/tmux-jump-rust` (gitlink SHA changed). To accept: `git -C ~ add .tmux/plugins/tmux-jump-rust && git -C ~ commit`. To revert: `git -C ~ submodule update`. Hand edits inside the submodule should be committed inside it (`git -C ~/.tmux/plugins/tmux-jump-rust commit ...`) and pushed to the fork separately, then bump the gitlink in the parent.
- `tmux-jump-rust` requires `cargo build --release` after the first clone (the `target/` dir is excluded by its own `.gitignore`); the wrapper [`tmux-jump.tmux`](./plugins/tmux-jump-rust/) auto-discovers the binary.

## Config quirks worth knowing

From [`~/.tmux.conf`](../.tmux.conf):

- **Clipboard is Wayland-only.** `@thumbs-command` pipes to `wl-copy`; needs `sudo apt install wl-clipboard`. On X11 / macOS this silently no-ops the system clipboard half.
- **Copy mode does not auto-exit.** `@copy_mode_exit 0` + the `M-w` rebind to `copy-selection-no-clear` lets you keep selecting after the first yank — different from upstream defaults.
- **`history-limit 100000`** — large scrollback. Affects memory per pane; don't shrink without checking what consumes it.
- **Plugin var ordering matters.** `@thumbs-command`, `@thumbs-regexp-1`, `@jump-keys-position` must be set *before* their `run-shell` line, because plugins read those vars at load time. TPM's own `run '~/.tmux/plugins/tpm/tpm'` stays at the very bottom per upstream contract.
- **Custom thumbs regex**: `@thumbs-regexp-1` matches `file.ext:line` patterns (e.g. `interview.vue:181`). Earlier custom regexes were removed (commit `bf79440`) — don't add new ones without verifying they don't shadow upstream defaults.

## Git hygiene

The git repo root is `$HOME` (not `~/.tmux/`); this dir is just a subtree. `~/.tmux/plugins/` is **mostly untracked** (TPM owns it) — the only entry visible to the parent repo is the `tmux-jump-rust` gitlink and its `.gitmodules` registration. See "Plugin tracking policy" above for the split. Each plugin's own `.gitignore` still excludes its build artifacts (`target/`, etc.), so even inside `tmux-jump-rust` you won't accidentally commit binaries. Don't push or open PRs without being asked.
