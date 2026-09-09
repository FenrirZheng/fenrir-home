# peer-task/v1 semantic contract

This is a cooperative same-user coordination convention, not a Codex or Claude product API. The Codex helper's SQLite/JSON shape and the Claude helper's JSONL shape are independent implementations. Matching protocol labels do not imply that either helper can read the other's store.

## Minimal exchange

| Record | Required meaning |
| --- | --- |
| Identity handshake | Exact server/socket/session/pane/process, runtime session/model/worktree, evidence, fresh enrollment generation |
| Task envelope | Worker generation, globally unique task/message IDs, immutable body/scope, acceptance criteria, baseline revision, owned resources |
| Queue | Sender durably recorded dispatch intent; does not assert transport or recipient acceptance |
| Received (optional) | Recipient read/stored the envelope; does not assert acceptance |
| ACK | Recipient explicitly accepts the exact task/message/generation; refusal never maps to acknowledged |
| Status | Task/message/generation, state, source-qualified evidence, observed time and freshness |
| Event cursor | Storage epoch, enrollment generation and sequence; explicit reset/truncation on continuity loss |
| Handoff | Task/message/generation, increasing revision, source SHA/dirty snapshot, tested revision/command/result/time, unresolved items, artifact paths/digests, update time |
| Reconciliation | Evidence old writers stopped and partial effects were inspected before claims are reassigned; does not mean successful completion |

`idle / running / waiting_approval / blocked / done / unknown` describe worker state. Preserve delivery state separately. An accepted task can remain execution-unknown until the receiver reports running. An idle parent may still have active children: completion and stopping evidence must cover the writers owning the resources.

Only the intended receiver authors acceptance and work reports. A same-user file or runtime-session string is not authentication. State this limitation rather than promising security against another process with the same access. Sender-written simulated receipts are useful only in explicitly labeled tests.

## Identity and continuity

A tmux pane is a route. Include server start time/PID, session/pane/PID, command/worktree and runtime identity; check again before terminal actions. Runtime IDs and model evidence are self-reported unless independently available. Pane shell PID can outlive the model process. A title is not a session or model identifier.

Use a fresh enrollment nonce, optionally included in a canonical identity hash, to invalidate old receipts even after a context reset that preserves all other fields. Independently renew the storage epoch on store replacement. Never silently preserve an old epoch while truncating/restoring history. The current helper does not prune history or support active snapshot rollback.

Stale work-state evidence becomes current `unknown`; old completion remains a historical report about a named revision. A current hook/ticker event can supply new evidence only if it is actually correlated to the task and relevant state. Generic activity does not refresh an old approval or completion claim.

## Retry and ownership

Persist dispatch and notification attempts separately. Before a retry, consume new events, inspect ACK/current identity and pending input. Do not resend a staged/queued task or treat time as proof of loss. Same ID plus different payload is a conflict. Receipt deduplication cannot make external side effects exactly-once; after a crash, inspect actual effects before resuming.

Ownership includes generated output paths and shared resources. Validate baselines before edits and current revision before accepting tests. On restart or death, retain claims until old writers and partial work are reconciled. A changed identity does not automatically void old work or authorize takeover.

## Native channels and cross-helper exchange

For available native Codex agents, send the same task envelope using the tool actually exposed in the current session and ask the receiver to return a structured ACK. Retain the actual tool response as provenance, together with any task-owned event/handoff artifact. Native send success without a recipient response is pending. Do not invent a runtime API or require tmux for an agent reachable natively.

For the independently developed Claude `peer-task` helper, read its current `SKILL.md` and protocol reference before adapting. For this iteration use explicit recipient-authored JSON/file handoffs or have both peers invoke the same installed Codex helper/store. Do not parse Claude JSONL using the Codex opaque cursor or convert a `received`/refused/stale ACK into acceptance. An adapter must explicitly map event type, generation, task/message identity, acceptance, timestamps, cursor epochs and artifact revision semantics; no automatic adapter is shipped here.
