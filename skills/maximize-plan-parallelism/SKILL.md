---
name: maximize-plan-parallelism
description: Decompose substantial work into dependency-safe parallel tasks and coordinate delivery. Supports separate Codex chats when the user requests them, or native subagents otherwise, with explicit ownership, shared contracts, recovery, and root acceptance. Also supports planning without starting implementation.
---

# Maximize Plan Parallelism

Optimize for the user's finished result, not agent count or planning artifacts. The current task owns scope, interfaces, dispatch, integration and acceptance. Workers own bounded outcomes.

## Match the requested operation

- **Plan:** inspect the baseline, split work and prepare task cards. Do not dispatch implementation or require runtime acceptance to finish a plan. Useful bounded read-only investigation may be delegated within the authorized scope.
- **Prepare tasks:** when requested, create tasks with concrete preparation-only instructions and a stopping point. Creating a task runs its prompt; it is not an inert placeholder. Do not authorize implementation implicitly.
- **Execute:** implement the authorized scope, dispatch ready work, integrate results and verify the assembled outcome. Continue without repeatedly asking the owner to manage routine technical decisions.

Infer the operation from the request and existing authorization. A planning or status request does not authorize deployment, publishing, purchases or a product rewrite. If ambiguity would start unauthorized implementation, finish independent planning and clarify only that boundary.

“Create the chats, but do not develop yet” means prepare tasks, not refuse task creation. “Only show me how to split it” means deliver the plan. Separate task creation still requires the explicit request below.

Choose transport separately:

- Explicit request for separate chats/tasks: use Codex task tools and read [thread-orchestration.md](references/thread-orchestration.md).
- Otherwise use native subagents for suitable bounded work. Do not create sidebar tasks without the user's request; respect live native capacity.
- Honor chosen worker models/effort; otherwise omit overrides. Root and workers need not use the same model. An unavailable requested model blocks that dispatch, not unrelated work. Never silently downgrade or claim to change/verify the current root model without supporting runtime information.

## Split real work

Read current decisions, the supplied plan, relevant code, local instructions and working-tree status. Distinguish decisions, implementation facts, unknowns and history. Preserve accepted interfaces, visuals and approved prompts.

Each worker card needs:

1. One observable outcome and acceptance conditions.
2. Exact baseline and essential context usable without the parent conversation.
3. Prerequisites, with a reason each is necessary.
4. Allowed write paths, read-only inputs and forbidden/shared paths.
5. Input/output interface and artifacts to return.
6. Targeted verification and when to report missing prerequisites or scope conflicts.

Split by independently verifiable results, not arbitrary file counts. Related files may belong to one task. Stabilize a shared interface only when consumers actually need it; pin usable existing types rather than rewriting them. Independent tasks need no dummy foundation gate. A consumer of a changed interface starts after it is accepted in the consumer's baseline. Useful read-only preparation may proceed earlier without inventing that interface.

Separate semantic dependencies from scheduling limits. Two independent tasks may still need serial access to a file, browser, database or test runner. Prefer separate ownership or isolated worktrees; declare genuine shared resources when they cannot be divided.

## Dispatch a rolling ready queue

Use available capacity and the user's cost preferences. Start more workers only for more useful independent outcomes. Reserve root attention for integration.

After a completion, failure, instruction or capacity change:

1. Reconcile the affected task with live status, outputs and changed paths.
2. Accept and integrate it, or return a concrete correction to the same task.
3. Find tasks whose prerequisites are integrated, baseline is available and relevant locks are free.
4. Dispatch those that fit capacity. Do not wait for an unrelated slow branch or unrelated result awaiting review.

Root ownership does not imply global exclusivity. The root may accept one branch or make an independent change while other workers continue. Reserve global pauses for operations that genuinely need them. Results awaiting review hold their own relevant path/resource locks, not all capacity.

Illustrative DAG waves are not synchronization barriers. Contract acceptance, reviews and checks can release dependent tasks as soon as their actual inputs are ready.

## Keep enough state to recover

A short planning request may need only a task table. For execution or many separate chats, keep root-owned state outside worker write sets, normally `~/.codex/orchestrations/<project>/<run-id>/`:

- `plan.md` or `dag.json`: scope, baselines, cards, dependencies and acceptance.
- `threads.json`: node/attempt to real task ID, host, checkout, requested model and wait cursor; equivalent bindings for native agents.
- `events.jsonl`: assignments and state changes.
- `receipts/`: returned work and root acceptance evidence when available.

Do not create empty reports merely to satisfy a template. Read [orchestration-contract.md](references/orchestration-contract.md) for handoff, integration and recovery. Root alone updates orchestration state and the shared integration baseline. Workers may produce local commits if authorized; publishing/merging or expanding ownership is not implicit in assignment.

When machine validation helps, use [dag-schema.md](references/dag-schema.md) and `scripts/check_orchestration.py`. It validates declared structure and ledger consistency, not actual product behavior or permissions. Planning/prepare mode requires no fake execution gates or full suite.

After interruption, match recorded bindings to live tasks and artifacts before retrying, reassigning or creating a duplicate. An unknown outcome is neither success nor failure. Continue unrelated ready work.

## Accept the requested result

Worker completion is a handoff. Inspect actual artifacts/diff, relevant checks and ownership. Integrate into the named baseline before releasing consumers. A receipt identifies node/attempt, baseline, changed paths, outputs, checks, limitations and new dependencies. Accept a compact response for a simple task and normalize it yourself.

Choose final checks from the user's acceptance conditions. Restart/replay matters for persistent state; rendered inspection for UI; end-to-end use for an integrated product. Do not require every gate or a heavy full suite universally. Run shared expensive checks once on the appropriate integrated state, then repeat only what a new change/failure justifies.

For planning, finish with a usable split. For preparation, distinguish created/ready tasks from executed work. For execution, finish when the assembled result meets scope or report the exact unresolved blocker. A launch-only handoff may name running tasks but must not imply continued background supervision without an authorized mechanism. Keep updates brief and do not make the owner operate the orchestration.
