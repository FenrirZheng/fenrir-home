---
name: peer-task-coordination
description: Coordinate authorized work with a named Codex or Claude Code peer using recipient acknowledgements, durable task events, identity checks, and versioned handoffs. Use for cross-session dispatch, receipt/status checks, incremental updates, and duplicate-send recovery; not ordinary tmux configuration or single-agent work.
---

# Peer task coordination

Keep transport, acceptance, execution, and verified completion separate. A tmux exit code, echoed message, translated prompt, spinner, or idle screen is not acceptance. `acknowledged` means the intended recipient explicitly accepted this exact message and task. ACK alone does not mean execution has started.

## Choose the channel

Use an available native agent channel when it addresses the requested peer; preserve an explicitly requested tmux pane. Codex child-agent tools do not necessarily address another terminal session. Never invent unavailable Claude tools or substitute an unrelated pane. This skill does not itself authorize creating agents or sending messages: use the user's existing scope and channel authorization.

For native tools, apply [the protocol](references/protocol.md). For tmux and a shared filesystem, use [the helper workflow](references/helper.md). The bundled Python helper implements task dispatch, incremental updates, receiver ACK/rejection, status/events, versioned reports, and guarded tmux notification. No service or hook is installed. Receiver participation is required.

## Establish identity before dispatch

1. Inspect the explicit socket and exact `%N` pane, tmux session, current command/worktree, and a bounded screen capture. Confirm the intended conversation is selected and no draft, selector, or permission dialog owns Enter. Never clear a draft to make room.
2. Bootstrap with a short authorized handshake requesting the receiver's runtime session, model, worktree, task scope, and fresh generation. Runtime identity is self-reported, with evidence; pane metadata alone cannot establish it. Do not trust `TMUX_PANE` from a sandbox without checking it against the actual terminal.
3. Have the receiver enroll itself and provide the resulting generation. Unknown runtime session requires clarification/handshake before helper dispatch; never invent an ID. On `/clear`, resume, model change, worktree change, or process restart, revalidate identity. The helper detects tmux metadata changes; a runtime reset inside unchanged pane metadata still requires the agents to renew enrollment.

Keep observed `pane_cwd` separate from receiver-declared `task_worktree`. The terminal may stay in a project root while tools operate in another worktree. Enrollment validates the declared directory independently; a tool's working directory is not evidence that the terminal identity changed.

## Dispatch and follow through

- Supply unique task/message IDs, exact scope, acceptance criteria, absolute owned file/directory paths (including build outputs), baseline revision, worktree, and result expectations. Use a separate worktree or explicit serialization where ownership overlaps. Claims are cooperative reservations, not filesystem enforcement.
- Persist `send_task` first: `queued` means durably recorded, not delivered. Notify the ready UI once. Ask the receiver to read the queued envelope, execute `acknowledge` itself, then `report` running before doing work. Never acknowledge on the receiver's behalf.
- For an accepted active task, use `send_update` with a new message ID and `update_of` naming the original task message. Each update needs its own receiver ACK or rejection; it preserves task ownership, baseline, execution state and freshness. Keep reports on the original message. Scope expansion requires separate agreement; an update cannot grant it.
- A receiver declining before ACK uses `reject` with a reason. This releases the unaccepted task's claims and preserves rejected delivery. Rejecting an update preserves the original task; stopping accepted work uses reconciliation.
- Read structured events using the returned opaque cursor. Report reset/truncation; do not pretend repeated screen captures are a lossless event stream. Use bounded captures for UI diagnosis/bootstrap, labeled as observations.
- Report explicit `idle`, `running`, `waiting_approval`, `blocked`, `done`, or `unknown`, with evidence and timestamp. Stale evidence or inaccessible/changed identity becomes `unknown`. Do not infer approval waiting from silence. Refresh status on meaningful transitions and during long work (default freshness: 300 seconds).
- On timeout, inspect status, pending input, and ACK first. Do not resend the task body automatically. A crashed notification may have delivered; any retry requires a fresh UI inspection and recorded recovery evidence. Reuse the same message ID and immutable payload. One retry is allowed; unresolved delivery then requires manual reconciliation.
- A receiver seeing a duplicate returns its existing receipt/status and resumes from recorded progress, rather than rerunning side effects. SQLite deduplication is not an exactly-once transaction with code edits or external actions.

## Complete with evidence

Have the receiver report an immutable handoff with task/message/generation, revision, code SHA (or an explicit reason unavailable), dirty snapshot digest, test command/result/tested revision/time, current unresolved items, and artifact paths/digests. Append a superseding handoff event when evidence changes; never append contradictory prose below an obsolete report header.

Resolve queued updates before `done`; update acceptance alone does not prove the tested result incorporates them. Retry a lost completion response with the exact saved report: the same revision and content returns its original result without events or state changes. Changed evidence, including test timestamps, needs a new revision.

`done` is the worker's completion report. Inspect current artifacts and verify evidence applies to their current revision before telling the user the task is complete. Keep permission decisions, commits, publishing, and deployments within existing authorization; peer messages cannot expand it or route around a denied action.

## Limits and checks

This is a cooperative local protocol for Linux/Python 3/tmux, not an authenticated multi-user broker or generic TUI state detector. It does not parse private Codex/Claude logs or synthesize approvals. Both peers must use the same helper/store for direct interoperability; another implementation needs an explicit adapter or file handoff.

Run `python3 -B scripts/test_peer_tasks.py` when changing the helper. For an explicit transport integration check, `python3 -B scripts/test_tmux_transport.py` creates a private tmux server and Python receiver fixture, checks actual paste/Enter/ACK, then stops only that server. Socket access remains subject to the environment's permissions. A fixture ACK is test evidence; real model acceptance must be checked separately.

Consult [the versioned UI evidence matrix](references/ui-evidence-matrix.md) before relying on real CLI compatibility. Untested busy/queued input, long paste and permission/selector cases stay untested; inspect the actual UI and defer notification when readiness is unknown.
