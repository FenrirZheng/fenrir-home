# CLAUDE.md

Project-level guidance for `/home/fenrir`, a single-machine **home-directory dotfiles repo** (working tree = `$HOME`).

## Repo shape

- Working tree is the entire home directory. Multiple independent git repos live under `$HOME` (`.claude/`, `.tmux/`, `.emacs.d/`, `fenrir-tools/`, plus unrelated clones in `code/`, `WebstormProjects/`, `Documents/`). **None are submodules** — they are standalone clones, and they show up as untracked entries in `git status`. [`GITS.org`](GITS.org) is the authoritative list of related repos (remotes, paths, build instructions).
- **The git dir is `~/.dotfiles.git`, not `~/.git`, and the repo is driven through [`dotgit`](.local/bin/dotgit)** (2026-11-12). `$HOME` deliberately holds no `.git` entry: while it did, every non-git folder under `$HOME` resolved to `/home/fenrir` as its git root (probe: `git -C ~/plans rev-parse --show-toplevel`), so git, editors and search tools treated `plans/`, `Documents/`, `code/` as part of this repo. `dotgit` is `git --git-dir=~/.dotfiles.git --work-tree=~`; wherever this file or the docs say `git` for the dotfiles repo, run `dotgit`. Plain `git` at `$HOME` or in a tracked subfolder (`docs/`, `.shell.d/`) answers "not a git repository" — that is the intended state. Don't use `git init --separate-git-dir`: it leaves a `.git` *file* in `$HOME`, which is discovered just the same.
- **Strategy: `status.showUntrackedFiles=normal` + slim deny-then-whitelist `.gitignore`** (user decision 2026-09-02; it was `no` from the 2026-05-09 rebuild, root commit `e5d70b7`, until then). The repo's history before that commit was discarded — only one user, no collaborators, so the rebuild was free.
  - **`$HOME` root noise** (caches, creds, IDE state, language toolchains, nested project repos, app state) is left visible as untracked, NOT covered by `.gitignore` rules. `git status` collapses whole untracked directories, so it lists **327 top-level `??` entries in 0.016 s** (2026-11-27); `-uall` expands the same tree to **1,250,405 entries in 12.7 s** (2026-09-02, git 2.47.3; probe for both: `dotgit status --porcelain [-uall] | grep -c '^??'`). Only the collapsed form is usable day to day — don't make `-uall` the default.
  - **`.local/`, `.config/`, `.gemini/`, `.claude-jail/`, `.cargo/`**: deny-then-whitelist. These dirs need positive containment so `git add <dir>` doesn't sweep in credential siblings — `.gemini/oauth_creds.json`, `.claude-jail/.credentials.json` (OAuth token), `.cargo/credentials.toml` (crates.io token), `.config/gh/`, `.config/sops/`. Explicit `!`-rule per file/subdir we want. `.config/` is covered in [`.config/`: tracked by the dotfiles repo](#config-tracked-by-the-dotfiles-repo).
  - **Keep this repo private** (remote `FenrirZheng/fenrir-home`): it tracks `.config/openfortivpn/config`, which holds a plaintext VPN password.
  - **`.ssh/`** has no `.gitignore` rule of its own and stays untracked — it simply appears in `git status` as `?? .ssh/`. `~/.ssh/config` still has ~25 plaintext password comments + production hostnames across multiple work clients; the deferred follow-up is to split it via `Include ~/.ssh/config.local` (sanitized main file tracked, sensitive lines in untracked `.local`). Until that split happens, `.ssh/` stays out of the repo.
- For nested whitelist patterns under `.local/`, `.gemini/` etc., open **each level** (`!/.foo/`, `!/.foo/bar/`, `!/.foo/bar/**`) — git won't re-include children of an ignored parent even with `**`. See the `.gemini/` block in [`.gitignore`](.gitignore).
- To allow a single child of an otherwise-ignored directory, exclude the **contents** with `dir/*` (not the directory itself with `dir/`), then add `!dir/child`. The trailing `/` form excludes the directory entry and git stops walking, so child whitelists silently lose. The `.gemini/bin/` and `.local/bin/` blocks use `/*` for this reason.

## `.tmux/`: tmux config repo

`.tmux/` is an independent git repo (remote: `FenrirZheng/config-tmux`; see [`GITS.org`](GITS.org)). The parent dotfiles repo does NOT track it. `~/.tmux.conf` is a symlink to [`.tmux/tmux.conf`](.tmux/tmux.conf) and shows up as an untracked entry in `dotgit status`.

Inside that repo, three kinds of content:

- **TPM-managed plugins (untracked)** — `tpm`, `tmux-sensible`. Declared with `set -g @plugin` in [`tmux.conf`](.tmux/tmux.conf) and excluded **one line per plugin** in [`.tmux/.gitignore`](.tmux/.gitignore) (there's no `plugins/*` blanket — the in-repo plugin below has to stay visible). TPM re-clones them on `prefix + I`; local edits are throwaway, `prefix + U` overwrites them.
- **In-repo plugin (tracked as ordinary files)** — [`plugins/tmux-ace-window/`](.tmux/plugins/tmux-ace-window), the user's own bash ace-window port (`prefix + o` select / `prefix + O` swap). Not TPM-managed: `tmux.conf` loads it with an explicit `run-shell`, because its `@ace-window-*` options must be set before the loader runs.
- **Toolset (Rust, plus six C++ tools)** — [`tools/`](.tmux/tools) is a tracked cargo workspace (`cc-attend`, `cc-beacon`, `cc-fleet`, `cc-launch`, `cc-layout`, `cc-tape`, `seek`, `talk-fleet`, `to-claude`, `to-emacs`, `tmuxlib`, `win-order`) **plus `sift` and `pane-jump`, which are C++ and build with cmake** (user directive, 2026-08-27), **`tmux-bar` (status bar) and `win-pick` (`prefix w` window picker), also cmake, built with clang++**, **`cc-main-menu`, C++ + FTXUI built with Meson** (user directive, 2026-11-11; the `prefix m` command palette), **and `tmux-zhuyin`, built by its own `scripts/build.sh`**. [`claude.conf`](.tmux/claude.conf) binds keys straight at `tools/target/release/<bin>`, so those keys are dead until every build has run. One command runs them all — also the recovery after `cargo clean`: `bash ~/.tmux/tools/build-all.sh`. The sift steps by hand:

  ```bash
  cd ~/.tmux/tools
  cargo build --release
  cd sift && cmake --preset release && cmake --build --preset release
  ```

  The cmake half goes through [`sift/CMakePresets.json`](.tmux/tools/sift/CMakePresets.json),
  which pins the Ninja generator and the build directory. Ninja is a
  convenience, not a requirement — it does **not** speed up this compile (one
  translation unit: ninja 2523 ms vs make 2325 ms, clean build, measured 2026-09-02 by
  configuring each generator into a scratch dir and timing `cmake --build` with
  `date +%s%N`), it makes the *no-op* rebuild 11 ms instead of 56 ms (same probe).
  Without `ninja`, or on cmake < 3.21, the
  generator-less form builds the identical binary:

  ```bash
  cmake -S sift -B target/cmake-build -DCMAKE_BUILD_TYPE=Release && cmake --build target/cmake-build
  ```

  cmake deliberately writes its binary into the same `target/release/` as cargo, so `claude.conf` keeps one path shape for every tool. The cost of sharing that directory: **`cargo clean` deletes `sift` too** — re-run the cmake line, not just `cargo build`. `target/` is excluded by [`tools/.gitignore`](.tmux/tools/.gitignore), which already covers the cmake build tree and output — no new ignore rule, and don't duplicate the rule in the root one. Read [`tools/ARCHITECTURE.org`](.tmux/tools/ARCHITECTURE.org) before editing any crate; it has a per-tool atlas at [`tools/atlas/`](.tmux/tools/atlas) to read first.

Operational consequences:
- **Reload after editing config**: `tmux source-file ~/.tmux.conf` — re-runs TPM plus the explicit `run-shell` loaders (ace-window, `claude.conf`).
- **Adding an upstream plugin**: add the `@plugin` line, `prefix + I`, **then add its directory to [`.tmux/.gitignore`](.tmux/.gitignore)** — the exclusions are per-plugin, so a newly cloned one shows up as untracked in `git -C ~/.tmux status` until you list it.
- **Fresh machine**: clone the tmux config repo to `~/.tmux/`, then `ln -sfn ~/.tmux/tmux.conf ~/.tmux.conf`, `prefix + I`, and run `bash ~/.tmux/tools/build-all.sh` — `cargo build --release` alone leaves `prefix /`, `prefix g`, `prefix m` and `prefix w` bound to "not built" stubs and the `tmux-bar` status bar unapplied. See [`GITS.org`](GITS.org) for the remote URL.
- tmux-side documentation lives in that repo — [`README.md`](.tmux/README.md), [`runbooks/`](.tmux/runbooks), [`docs/adr/`](.tmux/docs/adr).

## fenrir-tools/: locally-developed CLI tools

`fenrir-tools/` holds the user's own ACP helper CLIs as independent git repos (see [`GITS.org`](GITS.org) for remotes and build instructions). The parent dotfiles repo does NOT track them.

A helper binary that exists for the Emacs config (run by `~/.emacs.d/lisp/`) does **not** go here: it goes in [`~/.emacs.d/rust/`](.emacs.d/rust/README.md) and deploys to `rust/lib/` (precedents: `libsrc-classes`, and `git-subtree-status` in the `git-tools/` workspace). Read that README's scope rule before creating a new tool.

`~/.local/bin/{claud-chat,claude-chat}` are symlinks into these checkouts' build outputs. The symlinks are **not tracked** (`.local/bin/` is deny-then-whitelist and they aren't whitelisted) — recreate them after a fresh clone + build:

```bash
ln -sfn ~/fenrir-tools/claud-chat-acp/target/release/claud-chat  ~/.local/bin/claud-chat
ln -sfn ~/fenrir-tools/claude-agentic-chat/dist/index.js         ~/.local/bin/claude-chat
```

`~/.local/bin/{claude-editor,claude-editor-gui}` — the targets of `EDITOR` / `VISUAL` in [`.bashrc`](.bashrc) — are untracked symlinks of the same kind (untracked 2026-11-27): both point at the `open-emacs` binary in `~/code/fenrir-claude-plugin/open-emacse-rust/target/release/`, which picks its TUI or GUI mode from the name it is called by. One script builds it and recreates both links, also after a `cargo clean` there:

```bash
bash ~/code/fenrir-claude-plugin/open-emacse-rust/install.sh
```

Each inner repo's own `.gitignore` handles its build artefacts — don't duplicate those in the root [`.gitignore`](.gitignore). Some carry their own `CLAUDE.md` — that's the place for tool-internal guidance, not this file.

## `.claude/`: Claude Code config + skills

`.claude/` (i.e. `~/.claude/`) is an independent git repo (remote: `FenrirZheng/claude-for-fenrir`; see [`GITS.org`](GITS.org)). The parent dotfiles repo does NOT track it.

Tool/skill-internal guidance belongs in `.claude/`'s own docs (its `CLAUDE.md`, per-skill `SKILL.md`), not this file. **Hooks**: inventoried in the [Active hooks section of global `CLAUDE.md`](.claude/CLAUDE.md#active-hooks-claudehooks); wired in [`settings.json`](.claude/settings.json).

## `.config/`: tracked by the dotfiles repo

`.config/` (i.e. `~/.config/`) is **not** a git repo of its own. Until 2026-11-19 it was an independent clone (remote `FenrirZheng/linux-user-home-.config`); commit `b443285` merged its tracked files into this dotfiles repo, and `~/.config/.git` no longer exists — `git -C ~/.config …` answers "not a git repository". Every `.config` file is now driven through `dotgit`. The merge commit has a single parent, so the old repo's history was not brought in.

- **Deny-then-whitelist in the root [`.gitignore`](.gitignore)** (the `/.config/*` block): everything under `~/.config` is denied except the opened subtrees `alacritty/`, `alarm-services/IG-PRD-02/`, `autostart/`, `environment.d/`, `keyd/`, `openfortivpn/config`, `systemd/`. 16 tracked files (probe: `dotgit ls-files .config | wc -l`, 2026-11-28; `fcitx5/` was dropped that day when the input method moved to IBus). Tracking a new app's config takes its own `!`-rule per level — never widen `/.config/*`. `~/.config` itself has 107 top-level entries (2026-11-27), the rest being app state and credentials (`gh/`, `age/`, `sops/`, browser profiles).
- **Older history**: the six per-app repos that were folded into the `.config` repo on 2026-09-03 (`alacritty`, `autostart`, `environment.d`, `fcitx5`, `keyd`, `systemd`) are archived as `git bundle` files in `~/config-repo-archive/`.
- **`openfortivpn/config` holds a plaintext VPN password** — which is why the dotfiles repo must stay private (see [Repo shape](#repo-shape)).
- **The per-directory `.gitignore` files stay where they are** — [`autostart/.gitignore`](.config/autostart/.gitignore), [`environment.d/.gitignore`](.config/environment.d/.gitignore). A leading `/` in them anchors to the directory holding the file, so they keep working inside the dotfiles repo: `autostart/.gitignore:3:/*` matches `autostart/mimeinfo.cache` (probe: `dotgit check-ignore -v .config/autostart/mimeinfo.cache`, 2026-11-28). Hoisting those `/*` rules into the root `.gitignore` would deny the wrong tree — don't.
- **Two tracked entries are symlinks** (mode `120000`): `.config/systemd/user/default.target.wants/emacs.service` and `.config/systemd/user/graphical-session.target.wants/emacs-x-env.service`. These are the `.wants/` links `systemctl --user enable` writes, so the units under `systemd/user/` are managed with `systemctl --user`; check them on a fresh checkout with `systemctl --user status emacs.service`.
- **`keyd/default.conf` is deployed outside the repo** — copied to `/etc/keyd/default.conf`, which is where keyd reads it. The repo copy is the source of truth; the deploy command and the drift rule are in [Keyboard remapping](#keyboard-remapping-keyd).

## Keyboard remapping (keyd)

Physical keys are remapped by keyd; `~/.config/keyd/default.conf` is the source of truth and `/etc/keyd/default.conf` a deployed copy. **Read [`docs/keyd.org`](docs/keyd.org) before touching keyd, the input method (IBus + chewing-rs) or the RightAlt IME toggle** — it has the deploy command and the key map.

## Commit conventions

`git log --oneline` shows a preference for **small, system-scoped commits that bundle config + service** together (e.g. `ab99e2b` adds zoxide-seed shell config and the emacs daemon systemd unit in one commit). Don't split a feature's client and service halves into separate commits unless they truly are independent.

Subject line: `<area>: <verb> <thing>` (`tmux: add TPM plugin scaffolding`). History holds free-form subjects (`goood`, `sh tool`); match the area prefix of surrounding commits, don't add more free-form ones.

## Git pre-commit guard

> ⚠️ **NOT CURRENTLY WIRED — this guard does not run.** Measured 2026-08-18:
> `core.hooksPath` was **`/home/fenrir/.git/hooks`**, not `.githooks`, and that
> directory held only `*.sample`. On 2026-11-12 the git dir moved to
> `~/.dotfiles.git` and the setting was unset (the absolute path would dangle), so
> git falls back to `~/.dotfiles.git/hooks` — the same samples (probe:
> `dotgit config --get core.hooksPath` prints nothing). So no pre-commit
> check runs on this clone today, and nothing below is in force until the wiring
> command is re-run. The rest of this section describes the hook's *design*, kept
> because the file is still tracked and still works if re-enabled.
>
> **A hook's failure mode is silence** — same shape as the `$CLAUDE_TOOL_INPUT`
> incident (described in the header comment of
> [`.claude/hooks/selftest.sh`](.claude/hooks/selftest.sh) and in
> [`.claude/hooks/rg-guard.sh`](.claude/hooks/rg-guard.sh)), where two hooks blocked
> nothing for months while a table claimed they did. A
> document asserting a guard is active is not evidence that it is; only reading
> the config is.

Tracked at [`.githooks/pre-commit`](.githooks/pre-commit), wired per-clone via `dotgit config core.hooksPath .githooks`. After a fresh clone you must re-run that command — `core.hooksPath` is a local config, not tracked in `.git/config` outside the clone. **That is exactly how it came to be un-wired here**: the setting is per-clone and nothing re-applies it.

The hook resolves its scanner as `$repo_root/.local/bin/gitleaks`, i.e. *relative to the repo it runs in*, and `exit 1`s if that path is not executable. It therefore only works in this `$HOME` clone — pointing another repo's `core.hooksPath` at it would not scan anything, it would **block every commit there** with a "not found" failure.

One check, fatal:

- **`gitleaks git --staged`** (binary at `~/.local/bin/gitleaks`, installed manually from upstream releases — not tracked) — content-based scan for credential patterns (OAuth tokens, AWS keys, private keys, GitHub PATs). Nothing under `$HOME` is ever staged by accident from a `git status` glance, so the main risk is "I deliberately `git add`ed a file that contains a token I forgot about" — gitleaks is the last-mile defense against that.

Coverage caveat: gitleaks regex catches **high-confidence patterns** like `password: 6Qr...`, `AKIA...`, `ghp_...`. It does NOT catch free-form password comments (`# pwd: foo`, `## user x/y`). Don't rely on gitleaks alone — keep secrets out of tracked files entirely. `.ssh/config` holds such free-form leaks (count in [Repo shape](#repo-shape)); that file remains untracked — visible as `?? .ssh/`, with no ignore rule of its own — pending the `Include ~/.ssh/config.local` split.

If the hook blocks a commit: read the failure mode and fix the underlying issue. Do not reach for `--no-verify`.

## Fresh-clone bootstrap

Setting up a new machine: follow [`docs/fresh-clone.org`](docs/fresh-clone.org) (8 steps — git config, related repos, tmux toolset build, fenrir-tools, gitleaks, keyd, Nerd Font — and the hook-wiring verification).

## Don't

- **Never `git add .` or `git add -A` at `$HOME`** — which now means `dotgit add .` / `dotgit add -A`; the wrapper changes nothing about the danger. `add .` walks the actual filesystem and would stage every one of the ~1.25M items the slim `.gitignore` doesn't deny — and it only denies app-state regions and build artefacts; vast tracts of `$HOME` (caches, creds, history files, downloads) are NOT in the deny list. The untracked noise being visible in `git status` is not containment. `git add <specific-path>` always; never the cwd shortcut.
- **Never widen the `/.config/*` whitelist to a whole-directory or `**` rule at the `.config/` level.** `~/.config` is no longer its own repo (see [`.config/`: tracked by the dotfiles repo](#config-tracked-by-the-dotfiles-repo)); the deny rule is all that keeps `dotgit add .config/` from staging `gh/`, `age/`, `sops/`, browser profiles and the rest of the app state next to the 22 tracked files. Open one `!`-rule per app and level.
- Don't repopulate the old `$HOME`-root deny list in `.gitignore`. It was deliberately deleted in the `e5d70b7` rebuild because it was unmaintainable — every new app drops a new dir to chase. The user chose visible untracked noise over hiding or chasing it (2026-09-02), so a `??` line for `/.someapp/` is the expected state, not a bug to fix with a new ignore rule.
- Don't edit `/etc/keyd/default.conf` and forget to mirror it back to `~/.config/keyd/default.conf` — the copy tracked by the dotfiles repo is the source of truth, the `/etc/` one is a deploy target. See the [Keyboard remapping section](#keyboard-remapping-keyd).
- Don't add submodule tracking back. All related repos are standalone clones listed in [`GITS.org`](GITS.org) — the parent dotfiles repo deliberately does not track them.
