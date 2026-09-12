# maximize-plan-parallelism

A Codex skill for decomposing substantial work into dependency-safe, bounded tasks and coordinating the result through root-owned integration and acceptance.

It supports three operations:

- **Plan**: inspect the baseline and prepare a usable split without dispatching implementation.
- **Prepare tasks**: create concrete preparation-only tasks when requested, with a clear stopping point.
- **Execute**: dispatch authorized ready work, integrate accepted results, and verify the assembled outcome.

## Coordination model

The skill separates semantic prerequisites from scheduling constraints. A task begins when its accepted inputs are available and its relevant path or resource locks are free; illustrative DAG waves are not global synchronization barriers. After a handoff, the root reconciles the result, integrates or corrects it, and then dispatches the next useful work from a rolling ready queue.

Every task card defines one observable outcome, baseline, prerequisites, exclusive write paths, read-only inputs, forbidden/shared paths, deliverables, targeted checks, and return format. Workers hand work back; the root owns the orchestration state, shared integration baseline, and acceptance decision.

## Separate Codex tasks and native subagents

When the user explicitly requests separate Codex chats/tasks, the skill uses the supported task tools and records their bindings for recovery. Otherwise it uses native subagents for suitable bounded work. Separate tasks are never created implicitly.

User-selected model and reasoning settings are passed through when supported and recorded as requested values. The skill does not promise that a selected model is available, applied, or matches the root task.

## Declared-plan validation

For substantial coordination, the included checker validates the declared DAG and optional event ledger. It checks structure, dependencies, ownership conflicts, scheduling locks, and completion claims recorded in the ledger. It does not verify actual task configuration, permissions, changed files, receipts, or product behavior.

Run the deterministic regression scenarios:

```bash
python skills/maximize-plan-parallelism/scripts/check_orchestration.py --self-test
```

Validate a declared plan:

```bash
python skills/maximize-plan-parallelism/scripts/check_orchestration.py path/to/dag.json --json
```

Replay an event ledger, optionally requiring every node to be recorded as integrated:

```bash
python skills/maximize-plan-parallelism/scripts/check_orchestration.py path/to/dag.json --events path/to/events.jsonl --require-complete --json
```

The checker uses Python's standard library. See the [historical initial forward-test report](validation/forward-tests.md) for planning-only examples from the first release.

## Install

Ask Codex:

```text
Use $skill-installer to install https://github.com/AyanbekDos/maximize-plan-parallelism/tree/main/skills/maximize-plan-parallelism
```

## Use

```text
Use $maximize-plan-parallelism for this repository and implementation plan.
Build a dependency-safe split, then execute only authorized ready work.
```

## Package layout

```text
skills/maximize-plan-parallelism/
  SKILL.md
  agents/openai.yaml
  references/dag-schema.md
  references/orchestration-contract.md
  references/thread-orchestration.md
  scripts/check_orchestration.py
  scripts/test_orchestration.py
```

## License

MIT - see [LICENSE](LICENSE).
