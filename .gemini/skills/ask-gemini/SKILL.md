---
name: ask-gemini
description: Consult a fresh instance of Google Gemini via the local `gemini-chat` ACP CLI. Use when you need a clean context window for a second opinion, want to sandbox-test a premise without polluting the current session, or the user explicitly asks for a "fresh Gemini" or "second Gemini opinion". Triggers on phrases like "ask another Gemini", "fresh Gemini", "second Gemini opinion", "clean context Gemini", "consult a fresh Gemini", and Chinese equivalents "問另一個 Gemini", "開個乾淨的 Gemini", "找子 Gemini", "fresh-context Gemini", "Gemini 二號".
---

# Ask Gemini (Fresh Context)

Wraps the local `gemini-chat` Rust binary to spawn a separate Gemini session. This is useful for cross-checking reasoning in a clean context or performing isolated side-tasks without context bloat.

## Overview

While you are Gemini, sometimes a fresh perspective without the current conversation's history is useful for verification. It uses a persistent daemon to avoid repeated ~14s cold starts.

## Binary Invocation

Use `gemini-chat` — a symlink at `~/.local/bin/gemini-chat` points to the release build.

**Default model:** `gemini-3.1-pro-preview`. Pass via `--model gemini-3.1-pro-preview` on the `--daemon` call.

## Daemon Mode

Default to spawning the daemon on the first call.

**Mandatory socket-namespacing rule:** ALWAYS pass `--socket /tmp/gemini-chat-ask-gemini-$USER.sock` — never the binary's default `/tmp/gemini-chat-$USER.sock`, which belongs to the user's own daemon (stepping on it refuses-to-start or hijacks their socket).

Note: that socket is per-*skill*, not per-*session* — two concurrent `/ask-gemini` sessions on the same machine share one Gemini daemon (hence one conversation), because the second's `if [ ! -S ]` check connects to the first's daemon. Usually fine (amortises the cold start). If you need isolation for this topic, append a short fixed token chosen once on the first spawn — `SKILL_SOCK=/tmp/gemini-chat-ask-gemini-$USER-7f3a.sock` — not a per-call `$(rand)`, since the `if [ ! -S ]` block re-evaluates each call. (`gemini-acp` keeps no on-disk resume pointer, so the socket is the only shared resource.)

```bash
SKILL_SOCK=/tmp/gemini-chat-ask-gemini-$USER.sock

# Start once (idempotent)
if [ ! -S "$SKILL_SOCK" ]; then
  gemini-chat --model gemini-3.1-pro-preview --daemon --socket "$SKILL_SOCK" 2>/tmp/gemini-chat-ask-gemini-daemon.log &
  for i in $(seq 1 20); do [ -S "$SKILL_SOCK" ] && break; sleep 0.5; done
fi

# Query turn
gemini-chat --connect --socket "$SKILL_SOCK" --json "Your question here"

# Shutdown when the topic ends
gemini-chat --connect --socket "$SKILL_SOCK" --shutdown
```

## Presentation Rules

- Quote the fresh Gemini's reply under a **`**Sub-Gemini says:**`** header.
- Clearly separate it from your own context-aware reasoning.
- Use this for "clean-room" verification of complex logic.
