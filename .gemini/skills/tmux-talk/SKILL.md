---
name: tmux-talk
description: "Use the `talk` CLI to send messages between tmux panes — especially to coordinate with another AI instance running in a sibling pane. Trigger whenever the user wants to send text/prompts to another pane, check whether another AI is idle or busy, capture what another pane is showing, or list/discover panes across tmux sessions. Trigger for `talk list`, `talk send`, `talk ping`, `talk read`, `talk here`, `talk post`, `talk fetch`, `talk listen`, `talk handshake`."
---

# tmux-talk — inter-pane messaging via tmux

Bash wrapper around `tmux` for coordinating between AI instances (Gemini CLI, Claude Code) in sibling panes. Script: `scripts/talk` (resolve absolute path with `readlink -f`).

## Target format

- `%<N>` — e.g. `%42`. **Preferred** — pane ids are stable across renames and survive window/session reordering.
- `session:window.pane` — e.g. `main:0.1`. Brittle: changes whenever a pane is closed before it.

Run `bash scripts/talk list` to discover panes. Each line: `pane_id  target  [command]  title`.

---

## 🛑 MANDATORY PRE-FLIGHT BEFORE ANY `post` / `handshake` 🛑

Two failure modes have repeatedly burned agents in this protocol:

1. **Hallucinated self-ID** — agent says "I am `%5`" when `$TMUX_PANE` is actually `%2`. Messages get tagged with the wrong `From:` and replies route into a black hole.
2. **Posting to a dead pane** — agent posts to `%3` which is just an idle `bash` shell. The mailbox file fills up, but no one reads it.

**Before your first `post` or `handshake` in a session, run BOTH of these:**

```bash
# Step 1 — verify YOUR OWN pane id. Do not trust memory.
bash scripts/talk here
# → emits: pane_id, target, command, title, kind

# Step 2 — verify the TARGET is a live agent (not a bash shell).
bash scripts/talk ping %<TARGET_ID>
# → exit 0 = agent idle, exit 1 = agent busy, exit 2 = shell or unknown
```

Then **always pass `--from` on `post` and `handshake`**:

```bash
bash scripts/talk post --from %<YOUR_VERIFIED_ID> %<TARGET> "your message"
```

The script will **abort with a loud error** if `--from` disagrees with `$TMUX_PANE`. This is the anti-hallucination guard — use it.

---

## Note on Claude-side peers

Claude Code peers running this protocol auto-reply on inbound mail without per-message human confirmation, governed by a standing directive in `~/.claude/CLAUDE.md`. Treat their replies as agent-generated unless explicitly marked otherwise. They also treat your messages as untrusted PEER-AGENT input (the banner literally says `(NOT a user directive)`) — they will surface to their user before executing peer instructions that touch shared state (worktree edits outside scope, network calls, destructive commands, secret access). If you need user-tier authority on the Claude side, ask the human to relay; don't expect the peer agent to rubber-stamp peer-issued tool calls.

---

## A2A Mailbox Protocol (recommended)

To avoid UI focus issues and character injection races, use the Mailbox Protocol for Agent-to-Agent (A2A) communication. Messages live in `~/.gemini/mailbox/<pane_id>.md`.

| Command | Purpose |
|---|---|
| `handshake --from <id> [--session <id>] [--caps <csv>] <target>` | **First step.** Sends protocol intro into target pane via keyboard injection. Auto-generates a session id if `--session` omitted. |
| `post [--force] [--stdin] --from <id> [--session <id>] [--in-reply-to <msg-id>] <target> [<msg...>]` | Append message to target's mailbox + UI ping (with inline preview ≤600 bytes). |
| `fetch` | Read and **clear** your own mailbox. |
| `listen [timeout]` | Block until mailbox arrives, then fetch (default 60s). |

### Flags

- `--from <id>` — **MANDATORY** for `post`/`handshake`. Assert your sender id. Script dies if it ≠ `$TMUX_PANE`.
- `--force` — `post` only. Send to a target classified as a plain shell anyway. Default is to refuse (the message would never be read).
- `--stdin` — `post` only. Read body from stdin instead of positional args. **Use for any body containing `$`, backticks, quotes, or newlines** — pairs with a single-quoted heredoc to defeat shell metacharacter hazards. Example: `cat report.md | talk post --stdin --from %0 %1`.
- `--session <id>` — `post` and `handshake`. Thread/session id for multi-turn correlation. Carry the same value on every reply in a thread. `handshake` auto-generates one if omitted.
- `--in-reply-to <msg-id>` — `post` only. Reference a prior message's `Msg-ID` (one-step linkage, not transitive). Helps the peer thread replies on its side.
- `--caps <csv>` — `handshake` only. Free-form comma-list of capabilities you advertise to the peer (e.g. `--caps "web.search,code.exec,file.read"`). No fixed vocabulary; peers do best-effort interpretation. Sent once per session at handshake time, not per message.

### Canonical cold-start workflow

```bash
SCRIPT=~/.gemini/skills/tmux-talk/scripts/talk

# Pane A (Gemini) — initiator
bash $SCRIPT list                      # → discover %1 (Claude)
bash $SCRIPT here                      # → confirms I am, e.g., %5
MY=%5; PEER=%1

bash $SCRIPT ping $PEER                # → must be agent-idle or agent-busy
bash $SCRIPT handshake --from $MY $PEER
bash $SCRIPT post      --from $MY $PEER "Please analyze /tmp/data.csv"
bash $SCRIPT listen 300                # → block until reply

# Pane B (Claude) — responder
# UI shows: ### [talk] New message from %5. Use: bash …/talk fetch
bash $SCRIPT here                      # → confirms I am %1
bash $SCRIPT fetch                     # → reads and clears mailbox
# … does the work …
bash $SCRIPT post --from %1 %5 "Analysis complete: /tmp/report.md"
```

### Capability advertisement (handshake)

Use `--caps "<csv>"` on the *initiating* `handshake` to declare what your agent can do for this thread. The peer should cache your caps for the session and avoid re-asking; reciprocate with their own `--caps` on their first reply. Suggested (non-normative) tokens: `web.search`, `web.fetch`, `code.exec`, `file.read`, `file.write`, `tmux.read`, `lsp`, `db.read`. Strings are free-form; convergence emerges from shared use, not a fixed vocabulary. Don't re-emit caps per message — handshake only.

### Sending large content — send paths, not bodies

Bash arg quoting is hostile to multi-line content with `$`, backticks, `"`, etc. **Write to a file, post the path:**

```bash
cat > /tmp/proposal.md <<'EOF'
# big multi-line proposal …
EOF
bash $SCRIPT post --from $MY $PEER "Proposal at /tmp/proposal.md — please review."
```

If you must inline content, use `"$(cat /tmp/file)"` so the shell only does literal expansion.

---

## Legacy commands (keyboard injection)

| Command | Notes |
|---|---|
| `list` | List all panes (id, target, command, title) |
| `here` | Print this pane's id, target, title, classification |
| `send <target> <msg...>` | Paste message + Enter into target pane. Loses content if target is busy. |
| `type <target> <msg...>` | Same but no Enter (stages a draft) |
| `read <target> [lines]` | Print last N lines of pane scrollback (default 80) |
| `read-since <target> <marker>` | Scrollback after the last occurrence of `<marker>` |
| `ping <target>` | Classify pane. Exit 0 = agent-idle, 1 = agent-busy, 2 = shell/unknown |

---

## Pane classification

`ping`, `here`, and `post` (target check) all use the same classifier on `pane_title` + `pane_current_command`:

| Class | Meaning | When `post` does |
|---|---|---|
| `agent-idle` | Agent ready (e.g. title `✳ …` or `Claude Code`) | sends |
| `agent-busy` | Agent working (title `✦ Working…` or other non-empty) | sends (queues in mailbox) |
| `shell` | Plain `bash`/`zsh`/`fish`/`sh` with no agent title | **refuses unless `--force`** |
| `unknown` | No title and no shell process | sends with a warning |

---

## Error message reference

The `talk` script prefixes its diagnostics: `talk: ERROR:` (fatal, exits 1), `talk: WARN:` (continues), `talk:` (info). Common ones:

- `Self-ID mismatch. You claimed --from=%X but $TMUX_PANE=%Y` — the agent passed a wrong `--from`. Rerun `talk here` to see the real id.
- `target %N looks like a plain shell (cmd=bash, title='…')` — the target isn't an agent. Use `--force` only if you know what you're doing.
- `no such target pane: %N` — pane closed or id never existed. Run `talk list`.
- `self-post forbidden: target == sender` — you tried to mail yourself.
- `$TMUX_PANE is unset` — running outside tmux, or env was scrubbed.

---

## Token-cost rules

- `ping` = ~zero context cost (title only).
- `fetch` / `listen` = precise, noise-free context. **Preferred over `read`.**
- `read` = potentially huge context. Use `read-since <marker>` to bound it.
- **Send paths, not content.** If the file exists on disk, send the path.

---

## Gotchas

- **UI focus**: `talk send` to an *active* terminal (e.g. Gemini's own input field) can be lost or mangled. Use `post` instead.
- **No tmux**: Hard fail if `$TMUX` is unset.
- **Bash quoting**: `run_shell_command` may block `$()` in arguments. For complex bodies, write to a file then `post` the path.
- **Classification is heuristic**: a pane running `htop` will classify as `agent-busy` (non-empty title). The `--force` flag exists for the false-negative case.
