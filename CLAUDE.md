# CLAUDE.md

Project-level guidance for `/home/fenrir`, a single-machine **home-directory dotfiles repo** (working tree = `$HOME`).

## Repo shape

- Working tree is the entire home directory. ~20 nested independent git repos live under `code/`, `WebstormProjects/`, `Documents/` — they are not submodules, just unrelated clones the parent repo deliberately ignores.
- [Root `.gitignore`](.gitignore) uses **allow-by-default with structured denies** (migrated 2026-05-09 from the previous `*` deny-by-default scheme — see commit `48b4bec` for the pivot).
  - **`$HOME` root**: allow-by-default. New `~/.foo-rc`-style files appear in `git status` immediately; the deny list catches known-hostile dirs (caches like `.cache/`, creds like `.aws/` `.gnupg/` `.thunderbird/` `.pki/`, IDE state like `.vscode/` `.jetbrains/`, language toolchains like `.cargo/` `.npm/`, nested project repos like `code/` `Documents/`, etc.).
  - **`.config/`, `.local/`, `.gemini/`**: deny-then-whitelist. These dirs are heavily polluted by app-managed state, so we keep positive containment locally — explicit `!`-rule per file/subdir we want.
  - **`.ssh/`**: untracked entirely. `~/.ssh/config` historically had ~20+ plaintext password comments + production hostnames; gitleaks only caught one. Safer to leave it out of source control — maintain manually.
- For nested whitelist patterns under `.config/` etc., open **each level** (`!/.foo/`, `!/.foo/bar/`, `!/.foo/bar/**`) — git won't re-include children of an ignored parent even with `**`. See the `.tmux/` block in [`.gitignore`](.gitignore).
- To allow a single child of an otherwise-ignored directory, exclude the **contents** with `dir/*` (not the directory itself with `dir/`), then add `!dir/child`. The trailing `/` form excludes the directory entry and git stops walking, so child whitelists silently lose. The `.tmux/plugins/`, `.config/autostart/`, `.gemini/bin/`, `.local/bin/` blocks use `/*` for this reason.

## tmux plugins: TPM-managed by default, one submodule exception

Mixed policy under `.tmux/plugins/`:

- **TPM-managed (default)** — `tpm`, `tmux-sensible`, `tmux-thumbs`, and any other upstream plugin are **not tracked at all**. [`.gitignore`](.gitignore) line `/.tmux/plugins/*` excludes them; TPM re-clones them on `prefix + I` after a fresh checkout. Local edits to these are throwaway — `prefix + U` will overwrite them.
- **Submodule (exception)** — `tmux-jump-rust` is registered in [`.gitmodules`](.gitmodules) pointing at `git@github.com:FenrirZheng/tmux-ace-jump.git` (the user's own Rust port). The whitelist line `!/.tmux/plugins/tmux-jump-rust` in [`.gitignore`](.gitignore) is documentation; submodule entries are tracked via the index regardless of gitignore. The submodule's git data lives in `.git/modules/.tmux/plugins/tmux-jump-rust/` (absorbed canonical layout); the inner `.git` is a `gitdir:` pointer.

Why the asymmetry: TPM-only plugins are upstream code where local divergence has no value (the next `prefix + U` erases it). `tmux-jump-rust` is actively developed locally and benefits from independent history + a parent-tracked "blessed commit" SHA.

Earlier history briefly had mode-`160000` gitlinks for all plugins **without** a `.gitmodules` (the broken half-submodule state). The current setup is the proper version of that intent — but only for the one plugin where it pays off.

Operational consequences:
- **TPM plugins**: never appear in `git status`. After a fresh clone, run `prefix + I` inside tmux to populate them. `prefix + U` updates them silently.
- **`tmux-jump-rust` submodule**: after a fresh parent clone, run `git submodule update --init .tmux/plugins/tmux-jump-rust` to populate it. `prefix + U` updates the inner repo's HEAD → parent shows `modified: .tmux/plugins/tmux-jump-rust` (gitlink SHA changed). To accept: `git add .tmux/plugins/tmux-jump-rust && git commit`. To revert: `git submodule update`.
- Each plugin's own `.gitignore` (e.g. `/target` for the Rust port) still applies — `target/` build artifacts are excluded automatically. Don't add a duplicate rule in the root `.gitignore`.
- `tmux-jump-rust` requires `cargo build --release` after the first clone; the wrapper `tmux-jump.tmux` auto-discovers the binary.
- Plugin-specific notes live in [`.tmux/CLAUDE.md`](.tmux/CLAUDE.md).

## Commit conventions

`git log --oneline` shows a preference for **small, system-scoped commits that bundle config + service** together (e.g. `ab99e2b` adds zoxide-seed shell config and the emacs daemon systemd unit in one commit). Don't split a feature's client and service halves into separate commits unless they truly are independent.

Subject line style is loose: `<area>: <verb> <thing>` for substantive commits (`tmux: add TPM plugin scaffolding`), free-form (`goood`, `sh tool`) for trivial ones. Match the surrounding style of the area you're touching.

## Hooks and multi-agent infra

Five hooks at [`~/.claude/hooks/`](.claude/hooks/) are wired into [`settings.json`](.claude/settings.json) — see the "Active hooks" section in global [`~/.claude/CLAUDE.md`](.claude/CLAUDE.md). Most relevant when editing in this repo:

- **`worktree-guard.sh`** blocks Write/Edit outside the current worktree (exit 2). If it fires, surface the block, do not retry.
- This repo doesn't normally use worktrees, but cross-pane MQ / tmux-talk traffic can route an edit request from another pane into this one.

## Git pre-commit guard

Tracked at [`.githooks/pre-commit`](.githooks/pre-commit), wired per-clone via `git config core.hooksPath .githooks`. After a fresh clone you must re-run that command — `core.hooksPath` is a local config, not tracked in `.git/config` outside the clone.

One check, fatal:

- **`gitleaks git --staged`** (binary at `~/.local/bin/gitleaks`, installed manually from upstream releases — not tracked) — content-based scan for credential patterns (OAuth tokens, AWS keys, private keys, GitHub PATs). With allow-by-default `.gitignore`, gitleaks is the primary defense against accidentally committing a token pasted into a tracked config file.

Coverage caveat: gitleaks regex catches **high-confidence patterns** like `password: 6Qr...`, `AKIA...`, `ghp_...`. It does NOT catch free-form password comments (`# pwd: foo`, `## user x/y`). Don't rely on gitleaks alone — keep secrets out of tracked files entirely. Phase 2 of the migration found ~20 such free-form leaks in `.ssh/config`; that file is now untracked.

If the hook blocks a commit: read the failure mode and fix the underlying issue. Per global rule, do not reach for `--no-verify`.

## Fresh-clone bootstrap

After cloning into `$HOME` on a new machine:

1. `git -C ~ config core.hooksPath .githooks` — wire up pre-commit (`core.hooksPath` is local config, not tracked).
2. `git -C ~ submodule update --init .tmux/plugins/tmux-jump-rust` — populate the one tracked plugin.
3. Inside tmux: `prefix + I` — let TPM clone the rest of `.tmux/plugins/`.
4. `cd ~/.tmux/plugins/tmux-jump-rust && cargo build --release` — build the jump binary.
5. Install gitleaks to `~/.local/bin/gitleaks` from [upstream releases](https://github.com/gitleaks/gitleaks/releases) (binary, not tracked) — required by the pre-commit hook.

Verify with `git -C ~ status` (should be clean) and an empty commit through the hook (`git -C ~ commit --allow-empty -m test && git -C ~ reset --soft HEAD~1`).

## Don't

- Don't `git push` or open PRs (per global rule).
- Don't `git submodule add` for TPM-managed plugins (everything except `tmux-jump-rust`) — they're intentionally untracked so TPM owns them end-to-end. The `tmux-jump-rust` submodule is the deliberate exception; see "tmux plugins" section above.
- Don't run `git submodule add` from inside an existing inner repo's working tree. The Bash tool's CWD persists across calls, so use `git -C /home/fenrir submodule add ...` to lock the parent repo as cwd. Otherwise the submodule registration lands in the wrong repo and clones a nested copy at `<inner>/.tmux/plugins/<name>/`.
- Don't add a fallback `.tmux/plugins/*/target/` exclude to root `.gitignore` — sub-gitignores already handle it.
- Don't `git add .` blindly at `$HOME`. The deny list is comprehensive but not exhaustive — every new app on the system can drop a new untracked dir we haven't seen yet. Prefer `git add <specific-path>` and review `git status` first.
