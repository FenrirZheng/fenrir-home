# Local helper workflow

Use Python 3 on Linux with tmux. No pip packages or sqlite3 executable are required. All commands take one JSON request file; `--request -` reads stdin. JSON results go to stdout, errors to stderr with exit 2; interruption exits 130. `--help` and `--version` are available. These operations do not call a language model.

```bash
python3 -B /home/fenrir/.codex/skills/peer-task-coordination/scripts/peer_tasks.py \
  --store /tmp/authorized-task/mailbox.sqlite get_status --request /tmp/authorized-task/status.json
```

Use the installed skill's actual absolute path if different. Choose one shared, task-owned store inside both peers' allowed write roots. Preserve it through the handoff. Different stores do not share ownership or deduplication. Back up SQLite using its backup API or while every writer is stopped; do not truncate tables or restore an old database while peers are active. The helper never prunes events; restoring a snapshot into an active epoch is unsupported. Event histories may contain sensitive task text, so use an appropriately private parent directory.

Helper 1.1 opens `get_status` and `read_updates` with SQLite `mode=ro` and read transactions. A missing/mistyped store fails without creating directories, schema or an epoch. Initialize deliberately with `init --request` pointing to `{}`; `enroll` also supports first-use initialization. Other mutations require an existing store. Python callers use `Mailbox(path, create=True)` only for bootstrap, `Mailbox(path, readonly=True)` for queries, and `Mailbox(path)` for existing writable stores.

Existing 1.0 SQLite stores require no schema migration. Legacy identity `worktree` is interpreted in memory as both the original pane directory and task directory; renewed enrollment records both fields. The task payload's `worktree` remains a compatibility alias for `task_worktree`. Keep all writers on 1.1 once using updates or rejections: older writers do not enforce the new invariants. A frozen old helper/store may finish an already-running old-protocol coordination separately.

## 1. Receiver self-enrollment

First obtain an explicit receiver handshake by the existing authorized native/file/terminal channel. Inspect the intended UI before terminal submission. The receiver, not the sender, runs `enroll` with:

```json
{
  "worker": "codex-worker",
  "actor_session": "ACTUAL_RUNTIME_SESSION_ID",
  "identity": {
    "socket": "/tmp/tmux-1000/default",
    "pane": "%40",
    "task_worktree": "/absolute/worktree",
    "agent_session_id": "ACTUAL_RUNTIME_SESSION_ID",
    "model": "ACTUAL_OBSERVED_MODEL",
    "identity_evidence": "Receiver reports session/model from current runtime context; coordinator inspected main conversation"
  }
}
```

Replace every illustrative value with observed data. Runtime session/model evidence may come from the agent's current context or a narrowly identified runtime record; do not scrape unrelated sessions or guess from the newest log. If unavailable, retain `unknown` in the manual handshake and do not use automated dispatch until resolved. For tmux discovery, specify the same socket and exact pane:

```bash
tmux -S /tmp/tmux-1000/default list-panes -a -F '#{pane_id} #{session_id} #{pane_pid} #{pane_current_command} #{pane_current_path}'
tmux -S /tmp/tmux-1000/default capture-pane -p -J -t %40 -S -20
```

`enroll` reads tmux server PID/start time, session ID, pane ID/PID, command and `pane_cwd`. The receiver declares an absolute existing `task_worktree`, independently of the terminal directory; legacy `worktree` is an accepted alias, and supplying conflicting aliases fails. Optional `pane_cwd` is checked against observation. Future operations compare the transport tuple (including pane_cwd) and check that task_worktree still exists, without inferring it from the terminal. It returns a fresh random `generation` even if the tuple is unchanged. Self-reported runtime ID/model/worktree are cooperative assertions, not proof of process authorship. Agent runtime changes that preserve tmux metadata require a renewed handshake.

## 2. Queue a task, then notify

Sender runs `send_task`:

```json
{
  "worker": "codex-worker",
  "generation": "RETURNED_GENERATION",
  "task_id": "task-unique-001",
  "message_id": "message-unique-001",
  "message": "Implement the bounded change in the owned path. Report acceptance before work, then running; finish with a versioned handoff.",
  "acceptance": "Describe the requested result and its observable checks here.",
  "base_revision": "full source SHA plus dirty snapshot digest, or explicit unavailable reason and snapshot digest",
  "owned_paths": ["/absolute/worktree/owned-subdirectory"]
}
```

`owned_paths: []` declares read-only work. Parent/child and symlink-resolved path overlaps are rejected across unresolved tasks in this store; build outputs must be included. The helper records the baseline but does not compute/check Git revisions or enforce writes. Compare the actual baseline before editing. Different worktrees may still share Git refs, caches, or external services: coordinate those separately.

One unresolved task is allowed per worker. A repeated identical message ID returns its existing delivery status; changing payload under the same ID fails. `queued` establishes only durable intent. The recipient can read it with `read_updates` without any terminal notification.

For a previously inspected empty main input, run `notify` with `worker`, `generation`, `task_id`, `message_id`, and a nonempty `ui_ready_evidence` describing the fresh inspection. It pastes a literal JSON envelope containing the store/helper paths, then presses Enter. It serializes participating helper calls on the socket/pane. A per-message dedup record prevents repeated sends; the transport attempt is committed before keys so uncertain failures cannot silently resend. The UI can still change after inspection, or another program can type outside this lock. `ui_ready_evidence` is caller evidence, not an automated TUI assertion.

## 3. Receiver acceptance and state

Read `read_updates` using `{"worker":"codex-worker"}`. Inspect the queued task's full payload and scope. The receiver runs `acknowledge`:

```json
{
  "worker": "codex-worker", "generation": "RETURNED_GENERATION",
  "task_id": "task-unique-001", "message_id": "message-unique-001",
  "actor_session": "ACTUAL_RUNTIME_SESSION_ID",
  "accepted": true,
  "evidence": "I read message-unique-001, accept the stated scope and baseline, and will own the listed files."
}
```

Only this explicit acceptance creates an ACK; `acknowledge` with `accepted:false` still errors. To decline, the receiver runs `reject` with worker/generation/task/message/actor fields and a nonempty `reason`. It stores a rejection receipt, returns `delivery: rejected`, and releases the unaccepted task's reserved paths. An identical rejection returns its original receipt; a changed reason conflicts. Rejection after ACK fails: accepted work requires cancellation/reconciliation. The helper does not implement a separate `received` event. Never have the coordinator execute the receiver's ACK/report commands for convenience.

Then run `report` with the same identity/task/message/actor fields, plus `state: "running"` and task-specific `evidence`. Valid work states: `running`, `waiting_approval`, `blocked`, `unknown`, `done`. `idle` comes from enrollment or pre-acceptance task rejection; it cannot release accepted unfinished work. Refresh meaningful evidence within the configured freshness interval; no daemon or automatic heartbeat exists.

### Instructions during execution

Use `send_update` instead of a second `send_task`:

```json
{
  "worker": "codex-worker", "generation": "RETURNED_GENERATION",
  "task_id": "task-unique-001", "message_id": "update-unique-002",
  "update_of": "message-unique-001",
  "message": "The answer to your interface question is option B, within the agreed scope."
}
```

The original task must be accepted and active. `owned_paths`, `base_revision`, `acceptance` and worktree overrides are rejected. New message IDs have independent immutable payloads, notification attempts, ACKs and rejection receipts. Read the `update_queued` event; notify only when the intended UI is ready, or let the receiver poll. Receiver `acknowledge`/`reject` names the update message ID. Those operations resolve that update's delivery without changing original task claims, state, status evidence or timestamp. They do not attest application of the instruction. Continue execution reports on the original message ID.

Current status lists `pending_updates`. `done` fails until each pending update has an ACK or rejection. Review the actual final tree/tests for accepted instructions; include unresolved application explicitly in the handoff. New updates after completion fail; identical retries return historic delivery. Reconciliation closes pending updates with explicit cancellation evidence. An update cannot silently expand scope or authorize new side effects.

## 4. Read current status and incremental events

`get_status` request: `{"worker":"codex-worker","generation":"RETURNED_GENERATION","max_age_seconds":300}`. Generation is optional for discovery but retain it during a task. The result separates `delivery`, `state`, `reported_state`, `evidence[{source,value,observed_at}]`, and `last_update`. No terminal spinner parsing is involved. Socket failures, tuple changes, stale evidence, or a clock moving backwards produce current `unknown`; old ACK/completion records remain historical facts.

`read_updates` request: `{"worker":"codex-worker","cursor":"EXACT_PREVIOUS_NEXT_CURSOR","limit":100}`. Omit cursor on first read; treat it as opaque thereafter. Result: `new_events`, `next_cursor`, `has_more`, `reset`, `truncated`. Limit range is 1–1000; `has_more` means another page, not lost events. A different database epoch, worker generation, malformed cursor, or cursor ahead of retained history causes reset/truncation and restarts at the current generation's first event. A cursor tracks structured events, not complete terminal output. No pruning API is provided. Export relevant events/handoffs before reenrollment: old-generation rows remain in SQLite but this interface only streams the current generation.

## 5. Completion and uncertain delivery

A `report` of `done` also needs:

```json
{
  "handoff": {
    "revision": 1,
    "source_sha": "full code SHA, or null if unavailable",
    "source_note": "Explain unavailable SHA or relevant dirty baseline.",
    "dirty_digest": "sha256 of a documented task-scoped snapshot, including relevant untracked files",
    "tests": [{"command":"actual command", "result":"pass or precise failure", "tested_revision":"the tested SHA plus dirty digest", "updated_at":"2026-09-09T08:00:00Z"}],
    "unresolved": [],
    "artifacts": [{"path":"/absolute/result", "sha256":"actual sha256"}],
    "updated_at": "2026-09-09T08:00:00Z"
  }
}
```

This is the additional `handoff` field, merged into the normal `report` request with identity, actor, task, message, state, and evidence. Use JSON `null` for unavailable SHA; the illustrative string above is not a revision. If no checks/artifacts apply, empty arrays are allowed and the evidence must explain why. Digests and test claims are supplied by the receiver; helper validation checks shape, not actual artifact contents or test success. An unsuccessful result must describe the limitation, not imply the acceptance criteria passed. `done` releases claims; workers must stop writing those paths first. Reviewer verification remains required.

Keep the exact report JSON file for retry. Same revision plus identical canonical report content (including evidence, handoff update time and test times/results) returns the stored report body, without a new event, freshness refresh or state write. This also works for an older revision after a newer handoff or task, within the same verified enrollment. Same revision with any changed content conflicts. A genuinely revised handoff must increase revision and cannot overwrite a newer task's state. Changing enrollment invalidates old receiver operations; read the historical store instead. Current status may expire while historical completion remains available through events.

After a notification timeout/error/interruption, read status/events and inspect the UI. If no ACK and a fresh inspection establishes recovery is appropriate, `notify` may be called once more with the identical task/message, `retry:true`, fresh `ui_ready_evidence`, and `recovery_evidence` describing the ACK/status/input checks. Never use retry just because time elapsed. Do not paste again if the first body is staged or queued. At most two attempts are allowed, including an uncertain attempt; after that reconcile manually.

For a restarted/refusing/stopped worker with unresolved work, first verify that the old worker and its children have stopped touching the owned resources and inspect existing side effects/artifacts. Then the coordinator runs `reconcile` with recorded worker/generation/task/message plus `workers_stopped_evidence` and `artifact_review_evidence`. It resolves claims as a cancellation/recovery event, reports unknown, and requires fresh self-enrollment before another dispatch. It never claims success, kills a worker, discards files, or authorizes those actions. Do not use reconciliation to bypass a still-running owner or revive an unreviewed partial task. A new dispatch needs a new message ID and explicit context about the prior partial work.
