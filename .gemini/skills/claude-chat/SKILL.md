---
name: claude-chat
description: Spawn a SEPARATE Claude Agent SDK session via the local `claude-chat` Node binary when you need a fresh-context sub-Claude with persistent session memory across daemon restarts, optional tool access, or token streaming. Triggers on phrases like "spawn a claude session", "fire up claude-chat", "side claude with tools", "persistent sub-claude", "ask claude-chat", "open a claude-chat daemon", and explicit `/claude-chat`. Use this when you need Claude's specific reasoning or tool-use capabilities in an isolated, stateful side-channel.
---

# claude-chat

A four-mode CLI wrapping the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-typescript). Symlinked at `~/.local/bin/claude-chat`. This skill allows Gemini to orchestrate persistent side-conversations with Claude.

## When to invoke this skill

Use `claude-chat` when you want:

- **Side conversation that survives daemon restarts** — daemon persists the session id to a pointer file under `${XDG_STATE_HOME:-~/.local/state}/claude-chat/` (`last-session` for the default socket; a per-instance `last-session-<socket>-<hash>` for a non-default `--socket`; or exactly `--state-file <path>`) and auto-resumes it on next launch. The resolved path is echoed in the startup banner. See the per-user-singleton caveat under [Don't](#dont) before running a second concurrent daemon.
- **Side agent with tool use** — `--allow-tools` enables Read/Write/Bash/MCP. Permission mode defaults to `bypassPermissions` (every tool call auto-approved including Bash); tighten with `--permission-mode acceptEdits` / `plan` / `default`.
- **Structured JSON output** — Use `--json` for machine-parseable responses (one JSON line per reply).
- **Multi-turn dialogue from inside a tool call** — Daemon amortizes spawn cost.

## Invocation patterns

### One-shot — for quick consultations

```bash
# Human-readable output
claude-chat "Analyze this logic: ..."

# Machine-parseable JSON
claude-chat --json "Extract the interface from src/types.ts"
```

### Daemon Mode — for persistent state

```bash
# Start the daemon
claude-chat --daemon --quiet &

# Connect and send prompts
claude-chat --connect --json "First question..."
claude-chat --connect --json "Follow-up question..."

# Shutdown
claude-chat --connect --shutdown

# A SECOND, isolated persistent daemon (another agent session on the same box):
# pick a distinct socket — the state file is derived from it automatically
claude-chat --daemon --socket /tmp/claude-chat-side2.sock --quiet &
claude-chat --connect --socket /tmp/claude-chat-side2.sock --json "..."
claude-chat --connect --socket /tmp/claude-chat-side2.sock --shutdown
```

### Tool-Enabled Side Agent

```bash
# Allow Claude to use tools autonomously (bypassPermissions — the default with --allow-tools)
claude-chat --allow-tools --json "Refactor src/utils.ts to use the new API."

# Plan mode (read-only investigation)
claude-chat --allow-tools --permission-mode plan --json "What changes are needed?"
```

## Comparisons

- **claude-code (Existing Skill)**: Uses the official `claude` binary. Best for high-effort delegation.
- **claude-chat (This Skill)**: Uses the SDK-based binary. Best for persistent daemon-based side-conversations and custom tool configurations.

## Don't

- Don't use `--permission-mode bypassPermissions` casually — note it's the *default* with `--allow-tools`, so tighten to `acceptEdits` / `plan` when the prompt is open-ended AND the inputs include external/untrusted content.
- Don't assume the daemon is per-session — it's a **per-user singleton at the default socket** (`/tmp/claude-chat-$USER.sock`). If another agent session on this machine already runs a `claude-chat` daemon, a plain `claude-chat --daemon &` either refuses (live socket owned) or resumes whatever conversation that other daemon last touched. For a second persistent daemon, pass a distinct `--socket <path>` (the resume-pointer file is then auto-derived from it, so no cross-contamination and no `--fresh` dance; `--state-file <path>` pins it explicitly). For a one-off side-task with no persistence, prefer one-shot (`claude-chat --json "Q"`) — it touches neither the socket nor any state file.
- Don't auto-spawn a daemon from `--connect` if none is running.
- Don't ask the side-Claude to operate on paths outside its launch cwd (SDK allowlist will block it).
