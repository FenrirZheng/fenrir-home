# Real UI acceptance evidence — matrix revision 1

Observed 2026-09-09. This matrix describes specific exercised cases, not general product compatibility. Claude Code 2.1.266, self-reported model claude-fable-5-1, pane %42. Codex receiver version not measured because no receiver case was exercised.

| Case | Claude Code receiver | Codex receiver |
| --- | --- | --- |
| Inspected empty main input, short bootstrap via paste/Enter | Tested: Codex loaded bootstrap.txt into a tmux buffer, used bracketed paste then Enter; Claude produced claude-handshake.json and self-enrolled | Untested |
| Durable task read and receiver-authored ACK/running | Tested via shared SQLite read_updates, without another terminal notification; events 2–4 in the task mailbox | Untested |
| Helper notify into empty main input | Untested with a real model | Untested with a real model |
| Busy model / queued input | Untested; do not infer safe submission from an empty visible prompt while busy | Untested |
| Long multiline or Unicode payload near UI limits | Untested; fixture literal round-trip is separate evidence | Untested |
| Permission dialog or selector owns Enter | Untested; defer notification and retain unknown delivery | Untested |
| Uncertain notification recovery and bounded retry | Untested with a real model; inspect ACK, events and pending input before retry | Untested with a real model |

Evidence provenance: /tmp/peer-skill-20260909/bootstrap.txt, claude-handshake.json, mailbox.sqlite; task peer-skill-improvements-20260909, message claude-discuss-implement-001. The helper's private tmux/Python fixture suite verifies transport mechanics only. A model's ACK is separate evidence, and only exercised cases qualify. Do not interrupt drafts, synthesize permission approvals, reset conversations or force failures to fill the matrix. On changed versions or routes, retain prior results as historical and recheck the intended case when naturally available.
