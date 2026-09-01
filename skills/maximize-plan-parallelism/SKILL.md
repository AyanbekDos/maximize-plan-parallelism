---
name: maximize-plan-parallelism
description: Convert a large repo-grounded implementation plan into a dependency-safe DAG and execute it with native subagents inside one active Codex Sol Ultra task. Use when work needs durable root-owned orchestration, interface freezes, exclusive path ownership, capacity-aware waves, recovery after context compaction, and final integration evidence. Do not use for small changes or to create sidebar tasks.
---

# Maximize Plan Parallelism

Act as the sole root orchestrator for one active Codex task. Keep the plan, dispatch, reconciliation, integration, and final proof in this task. Use native subagents as workers; never create, fork, or coordinate separate sidebar tasks for DAG nodes.

## Establish the execution boundary

1. Inspect the real repository, its local instructions, current status, the supplied plan, and the authoritative acceptance criteria before decomposing anything.
2. Separate current implementation facts, accepted decisions, hypotheses, history, and unknowns. Do not turn an old plan into current authority silently.
3. Preserve the user's requested model. Before execution dispatch, verify that the active root is Sol Ultra and that native subagents inherit that model and reasoning unless the user explicitly requests another choice. If either condition is false or unverifiable, stop after the validated DAG and report the mismatch; never downgrade silently.
4. If native subagent tools are unavailable, produce and validate the DAG but stop before claiming parallel execution.
5. Respect the request's mutation boundary. A planning or forward-test request is read-only even though the graph describes implementation.

## Persist the control plane outside the repo

Before spawning a worker, create a run directory under the personal Codex state directory, normally `~/.codex/orchestrations/<repo-slug>/<run-id>/`. A read-only forward test may instead use an explicitly supplied isolated output directory. Never place orchestration state in the repo or a worker worktree.

Only the root writes these files:

- `brief.md` - frozen goal, authority sources, baseline revision, acceptance criteria, constraints, and unknowns.
- `dag.json` - frozen semantic DAG and task cards.
- `events.jsonl` - append-only state transitions and agent assignments.
- `receipts/<node-id>.json` - normalized worker handoffs copied by the root.
- `final-report.md` - acceptance matrix and final evidence.

Read [the orchestration contract](references/orchestration-contract.md) before dispatch or recovery. Read [the DAG schema](references/dag-schema.md) when creating `dag.json` or running the checker.

## Build the semantic DAG

Decompose by independently observable outcomes, not by activities or arbitrary file counts. A worker node should normally have:

- one outcome a reviewer can observe;
- one primary subsystem and an exclusive write boundary;
- explicit read-only inputs and forbidden paths;
- concrete deliverables and targeted verification;
- acceptance-criterion IDs;
- prerequisites with a specific reason for every edge.

Create an `interface_freeze` node before parallel consumers when signatures, schemas, event shapes, migrations, fixtures, or other shared contracts are not stable. When the contract already exists, the node may be a read-only gate that pins its exact baseline and proves that no consumer may redefine it; do not invent interface churn merely to satisfy the graph. A consumer may start only after its producer is `integrated`.

Keep these concepts separate:

- DAG edges are semantic prerequisites. Removing one would make the dependent result invalid or unknowable.
- Shared hot paths, exclusive resources, heavy-test groups, and worker capacity are scheduling constraints. They serialize starts without inventing false dependency edges.

Detect every write/write overlap. First try to split ownership. If the shared file is genuinely indivisible, declare it in `shared_hot_paths` with a concrete reason and never run the affected nodes together. Treat an unordered write/read overlap as a planning error: add the real dependency or redesign the boundary.

Re-split a card before implementation when it combines several observable outcomes, crosses independent subsystems, owns too many unrelated paths, asks a worker to run the full suite, or cannot be verified without another unfinished card. A broad root-only gate is allowed only with an explicit `split_exception` explaining why it cannot safely be divided.

## Validate before dispatch

Run:

```text
python <skill-dir>/scripts/check_orchestration.py <run-dir>/dag.json --json
```

Do not dispatch while the checker reports an error. Review its derived waves and serialization reasons; the graph is not frozen merely because it is acyclic.

After first dispatch, treat `brief.md` and `dag.json` as frozen. If repo evidence forces a change, stop affected nodes, record the reason, write a new DAG revision, rerun the checker, and then resume. Workers never edit the DAG or ledger.

## Run capacity-aware waves

For each wave:

1. Replay `events.jsonl`, inspect repo status/diffs, and reconcile the ledger with the live native-subagent registry.
2. Compute the ready frontier: only nodes whose prerequisites are `integrated` qualify. `worker_done` and `verified` are not dependency completion.
3. Determine live worker capacity after reserving the root for orchestration and integration. Spawn only the non-conflicting ready nodes that fit it; do not target a large agent count.
4. Give each worker exactly one task card, the frozen baseline/current integration state, owned paths, forbidden paths, commands allowed for targeted verification, and the receipt contract.
5. Use native subagent operations attached to this task for spawn, follow-up, waiting, and status inspection. Do not use task/thread management operations such as `create_thread`, `fork_thread`, `send_message_to_thread`, or `wait_threads` for DAG workers.
6. While workers run, the root may inspect and prepare integration, but must not edit an active worker's owned paths.

Workers return evidence; they do not declare themselves integrated. For each completion, the root inspects the actual diff/artifact, checks path ownership, runs or validates targeted verification once, records a receipt, and advances:

```text
planned -> claimed -> running -> worker_done -> verified -> integrated
```

Use `blocked`, `failed`, or `orphaned` with evidence when necessary. A dependent remains blocked until the prerequisite reaches `integrated`.

Avoid duplicated heavy tests. Workers run narrow checks. Assign each heavy-test group at most once per wave, run shared subsystem gates after the relevant wave, and reserve the complete integration suite for the final stage.

## Recover instead of forgetting

At the start of every wave and after any context compaction or interruption:

1. Reload `brief.md` and `dag.json`.
2. Validate and replay the ledger:

```text
python <skill-dir>/scripts/check_orchestration.py <run-dir>/dag.json --events <run-dir>/events.jsonl --json
```

3. List live subagents and reconcile each one to exactly one claimed/running node.
4. Compare receipts with actual files, diffs, commits when used, and test output.
5. Mark vanished unproven work `orphaned`; do not guess that it completed.

Do not start a new wave while an active agent or changed path is unaccounted for. Do not give a final answer while any worker is still active.

## Finish with a final gate stage

After every non-final node is integrated, run the final-gate nodes for:

- system-wide integration;
- independent cross-review;
- restart/replay or resume-path verification;
- end-to-end acceptance evidence.

Run the full heavy suite once from the integrated state. Verify observable product behavior, not only schemas or green unit mocks.

The final report must include the acceptance matrix, node receipts, final repo state, targeted and full-test evidence, unresolved risks, and a short explanation of every remaining sequential constraint. Distinguish semantic dependencies from capacity, hot-path, resource-lock, and heavy-test serialization. Explain why each semantic edge could not be removed safely.
