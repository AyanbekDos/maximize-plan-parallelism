# Handoff, integration and recovery

Use for execution or interrupted-run recovery. This protocol does not authorize starting implementation.

## One integration baseline

Identify repo root, branch/commit and dirty tracked/untracked inputs. A SHA alone does not identify an uncommitted feature. Preserve necessary dirty inputs as a snapshot with file identities before workers depend on them. For non-repo work, use an immutable directory snapshot.

Separate tasks do not inherit the parent's files or conversation automatically. Verify their inputs. Prefer isolated worktrees for overlapping repo work; assign disjoint exact paths in a shared checkout. Account for symlinks and alternate paths to the same file: the checker is lexical, not a permission guard.

Distinguish live shared inputs from pinned inputs in separate checkouts. A worker reading an unchanged accepted snapshot does not depend on an unrelated worker editing another copy of that file. Record the snapshot identity in the card; use `read_only_inputs` for live shared reads in the JSON conflict model. Root must verify that the supposedly pinned input really stays fixed. Shared interface changes still require acceptance before consumers use the new version, and overlapping output paths still need integration ownership.

Each worker receives accepted prerequisite artifacts. Root incorporates its returned patch/commit, preserves unrelated changes, resolves conflicts and runs affected checks. Publishing remains separately authorized.

## States and attempts

```text
planned -> claimed -> running -> worker_done -> verified -> integrated
```

- `claimed`: a ready node reserves capacity and a unique attempt; setup may be pending.
- `running`: the intended task has started that attempt.
- `worker_done`: result returned; relevant write/resource locks remain until review.
- `verified`: root checked the result; consumers still wait for integration.
- `integrated`: root incorporated the result into the recorded baseline.
- `blocked`, `failed`, `orphaned`: concrete conditions, not mere slowness. Reassignment increments the attempt; an old reply cannot complete the new attempt.

Before releasing failed/blocked task locks, confirm the task stopped writing and account for partial changes. A ledger transition does not stop a process. Superseding a node does not satisfy its consumers; update their real dependency explicitly.

Root records transitions. A stable `agent_ref` identifies an assignment; `threads.json` maps it to real thread/host/cursor. Pending setup can resolve without changing attempt identity. Acceptance transitions carry `actor: "root"`. These labels prevent accidental stale bookkeeping, not malicious forgery.

## Dispatch and handoff

Send the mutation boundary, baseline, allowed paths, prerequisites, acceptance, outputs and narrow verification. Include run/node/attempt identity for reconciliation. A worker reports a new shared-path need before editing it.

Example receipt; scale detail to the task:

```json
{
  "node_id": "UI",
  "attempt": 1,
  "agent_ref": "ui-attempt-1",
  "baseline": "accepted commit plus snapshot",
  "summary": "Practice panel handles the agreed run states",
  "changed_paths": ["app/components/PracticePanel.tsx"],
  "deliverables": ["local commit or patch location"],
  "verification": [{"check": "targeted UI path", "result": "pass", "evidence": "artifact location"}],
  "limitations": [],
  "new_dependencies": []
}
```

Inspect the actual diff: a worker's path list may be incomplete. Check acceptance against evidence. Return corrections to the same task unless its context/checkout is unusable. Never copy secrets into cards, logs or reports.

No global review barrier: while UI awaits review, an independent reader adapter can start. A task reading UI's changing unaccepted files waits. Root may accept UI while another worker edits unrelated paths.

## Resume

1. Read the plan revision and bindings; validate the ledger if using JSON.
2. Query real task IDs with recorded hosts/cursors. Do not use pending client IDs where real thread IDs are required.
3. Match active attempts, completed results and changes to cards. Inspect unknown outcomes before retrying.
4. Recover partial work. A task still running elsewhere is not orphaned.
5. Recompute readiness from integrated prerequisites and actual free resources; continue independent work.

Preserve preceding plan revisions. Pause only tasks affected by a contract/ownership change. Do not replay an old ledger against an incompatible graph. For a material split, start a named successor run referencing accepted artifacts instead of inventing an automatic ledger migration.

## Completion

An executing plan has root acceptance with checks appropriate to the result. Independent review workers return evidence; they do not self-accept the product. Review may start once its actual inputs are integrated; final root acceptance covers required contributions.

The checker does not inspect receipts or the working tree. `--require-complete` checks the ledger's completion claims; root separately verifies artifacts and behavior. Report these as different proofs.

A launch-only handoff names running tasks and how to resume. An execution handoff names the accepted baseline, evidence and limitations. A completed task, valid DAG, build or running server alone is not a finished product.
