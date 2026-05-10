# CLAUDE.md

Project-level guidance for `/home/fenrir`, a single-machine **home-directory dotfiles repo** (working tree = `$HOME`).

## Repo shape

- Working tree is the entire home directory. ~20 nested independent git repos live under `code/`, `WebstormProjects/`, `Documents/` — they are not submodules, just unrelated clones the parent repo deliberately ignores. The one exception is `fenrir-tools/` (locally-developed CLI tools registered as real submodules — see the [fenrir-tools section](#fenrir-tools-locally-developed-cli-tools-as-submodules) below).
- **Strategy: `status.showUntrackedFiles=no` + slim deny-then-whitelist `.gitignore`** (rebuilt 2026-05-09, root commit `e5d70b7`). The repo's history before that commit was discarded — only one user, no collaborators, so the rebuild was free.
  - **`$HOME` root noise** (caches, creds, IDE state, language toolchains, nested project repos, app state) is hidden by `git config status.showUntrackedFiles no`, NOT by `.gitignore` rules. The previous `$HOME`-root deny list was unmaintainable: `git status -uall` shows ~1M untracked items, every new app drops a new dir to chase. The config-based hide makes that whole problem disappear.
  - **`.config/`, `.local/`, `.gemini/`**: deny-then-whitelist. Even with untracked-hidden, these dirs need positive containment so `git add <dir>` doesn't sweep in `oauth_creds.json`-style siblings. Explicit `!`-rule per file/subdir we want.
  - **`.ssh/`** stays untracked because `showUntrackedFiles=no` hides it — there's no longer an explicit `/.ssh/` rule in `.gitignore`. `~/.ssh/config` still has ~25 plaintext password comments + production hostnames across multiple work clients; the deferred follow-up is to split it via `Include ~/.ssh/config.local` (sanitized main file tracked, sensitive lines in untracked `.local`). Until that split happens, `.ssh/` remains opaque to the repo.
  - **To inspect what's hidden**: `git status -uall` is the one-shot opt-in. Don't make it the default — it dumps a million entries.
  - Earlier history: a prior 2026-05-09 morning pivot (commit `48b4bec`, now in discarded history) moved from `*` deny-by-default to allow-by-default-with-deny-list. That intermediate strategy still required chasing every new app's state dir; the evening `e5d70b7` rebuild replaced the chase with a single config setting.
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

## fenrir-tools/: locally-developed CLI tools as submodules

`fenrir-tools/` at the repo root holds the user's own Agent-Client-Protocol (ACP) helper CLIs, each a separate GitHub repo registered as a submodule in [`.gitmodules`](.gitmodules). All three use the **absorbed git-dir layout** (same as `tmux-jump-rust`): the inner `.git` is a `gitdir:` pointer into `.git/modules/fenrir-tools/<name>/`, so `rm -rf` on a checkout doesn't destroy its history.

| path | upstream remote | what it is | build |
|---|---|---|---|
| `fenrir-tools/claud-chat-acp` | `FenrirZheng/claud-chat-acp` | Rust ACP client (`claud-chat` binary) | `cargo build --release` |
| `fenrir-tools/claude-agentic-chat` | `FenrirZheng/claude-agentic-chat` | Node Claude Agent SDK chat (`dist/index.js`) | `npm install && npm run build` |
| `fenrir-tools/gemini-acp` | `FenrirZheng/gemini-chat` | Rust Gemini ACP client (`gemini-chat` binary) — **path ≠ repo name** | `cargo build --release` |

Why these are submodules and the `code/` / `Documents/` clones are not: these are actively developed locally and the parent repo pins a blessed SHA for each — identical rationale to the `tmux-jump-rust` exception. Plain unrelated clones get no value from a parent-tracked SHA, so they stay untracked noise.

`~/.local/bin/{claud-chat,claude-chat,gemini-chat}` are symlinks into these checkouts' build outputs. The symlinks are **not tracked** (`.local/bin/` is deny-then-whitelist and they aren't whitelisted) — recreate them after a fresh clone + build:

```bash
ln -sfn ~/fenrir-tools/claud-chat-acp/target/release/claud-chat  ~/.local/bin/claud-chat
ln -sfn ~/fenrir-tools/claude-agentic-chat/dist/index.js         ~/.local/bin/claude-chat
ln -sfn ~/fenrir-tools/gemini-acp/target/release/gemini-chat     ~/.local/bin/gemini-chat
```

Operational consequences:
- **Fresh parent clone**: `git -C ~ submodule update --init` populates all submodules (these three + `tmux-jump-rust`); then run each repo's build (table above) and recreate the symlinks.
- **Editing inside one**: commit in the inner repo first, then the parent shows `modified: fenrir-tools/<name>` (gitlink SHA changed). To bless the new SHA: `git -C ~ add fenrir-tools/<name> && git -C ~ commit`. To revert to the pinned SHA: `git -C ~ submodule update fenrir-tools/<name>`.
- Each inner repo's own `.gitignore` handles its build artefacts (`/target`, `/dist`, `node_modules/`) — don't duplicate those in the root [`.gitignore`](.gitignore).
- Some of these carry their own `CLAUDE.md` (e.g. `fenrir-tools/claude-agentic-chat/CLAUDE.md`) — that's the place for tool-internal guidance, not this file.

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

- **`gitleaks git --staged`** (binary at `~/.local/bin/gitleaks`, installed manually from upstream releases — not tracked) — content-based scan for credential patterns (OAuth tokens, AWS keys, private keys, GitHub PATs). With `showUntrackedFiles=no` hiding most of `$HOME`, the main risk shifts to "I deliberately `git add`ed a file that contains a token I forgot about" — gitleaks is the last-mile defense against that.

Coverage caveat: gitleaks regex catches **high-confidence patterns** like `password: 6Qr...`, `AKIA...`, `ghp_...`. It does NOT catch free-form password comments (`# pwd: foo`, `## user x/y`). Don't rely on gitleaks alone — keep secrets out of tracked files entirely. The original audit of `.ssh/config` found ~20 such free-form leaks; that file remains untracked (now via `showUntrackedFiles=no` rather than an explicit ignore rule) pending the `Include ~/.ssh/config.local` split.

If the hook blocks a commit: read the failure mode and fix the underlying issue. Per global rule, do not reach for `--no-verify`.

## Fresh-clone bootstrap

After cloning into `$HOME` on a new machine:

1. `git -C ~ config status.showUntrackedFiles no` — hide the ~1M `$HOME` items the repo doesn't track. Without this, `git status` is unusable.
2. `git -C ~ config core.hooksPath .githooks` — wire up pre-commit (`core.hooksPath` is local config, not tracked).
3. `git -C ~ submodule update --init` — populate all submodules: `.tmux/plugins/tmux-jump-rust` plus the three under `fenrir-tools/` (see the [fenrir-tools section](#fenrir-tools-locally-developed-cli-tools-as-submodules)).
4. Inside tmux: `prefix + I` — let TPM clone the rest of `.tmux/plugins/`.
5. `cd ~/.tmux/plugins/tmux-jump-rust && cargo build --release` — build the jump binary.
6. Build the `fenrir-tools/` CLIs (`cargo build --release` in the two Rust repos, `npm install && npm run build` in `claude-agentic-chat`) and recreate the `~/.local/bin/{claud-chat,claude-chat,gemini-chat}` symlinks — see the [fenrir-tools section](#fenrir-tools-locally-developed-cli-tools-as-submodules) for the exact `ln` commands.
7. Install gitleaks to `~/.local/bin/gitleaks` from [upstream releases](https://github.com/gitleaks/gitleaks/releases) (binary, not tracked) — required by the pre-commit hook.

Verify with `git -C ~ status` (should be clean, with the `(use -u to show untracked files)` hint) and an empty commit through the hook (`git -C ~ commit --allow-empty -m test && git -C ~ reset --soft HEAD~1`).

## Don't

- Don't `git push` or open PRs (per global rule).
- Don't `git submodule add` for TPM-managed plugins (everything under `.tmux/plugins/` except `tmux-jump-rust`) — they're intentionally untracked so TPM owns them end-to-end. The tracked submodules are exactly `tmux-jump-rust` and the three under `fenrir-tools/`; see the "tmux plugins" and "fenrir-tools" sections above.
- Don't run `git submodule add` from inside an existing inner repo's working tree. The Bash tool's CWD persists across calls, so use `git -C /home/fenrir submodule add ...` to lock the parent repo as cwd. Otherwise the submodule registration lands in the wrong repo and clones a nested copy under that inner repo (e.g. `<inner>/fenrir-tools/<name>/`).
- Don't add a fallback `.tmux/plugins/*/target/` exclude to root `.gitignore` — sub-gitignores already handle it.
- **Never `git add .` or `git add -A` at `$HOME`.** Under `showUntrackedFiles=no` it's tempting because `git status` looks clean, but `add .` ignores that config — it walks the actual filesystem and would try to stage everything not gitignored. The slim `.gitignore` only denies app-state regions and build artefacts; vast tracts of `$HOME` (caches, creds, history files, downloads) are NOT in the deny list — they were untracked-by-config, not untracked-by-rule. `git add <specific-path>` always; never the cwd shortcut.
- Don't repopulate the old `$HOME`-root deny list in `.gitignore`. It was deliberately deleted in the `e5d70b7` rebuild — the config-based hide replaces it. If you find yourself wanting to add `/.someapp/` to ignore-noise, the answer is "it's already hidden, you're looking at `git status -uall` output".
- Don't restore `/.config/fcitx5/conf/cached_layouts` to tracked. fcitx5 rewrites it on every run; the rebuild intentionally dropped it. If `git status -uall` shows it as untracked, that's correct — let fcitx5 own it.
