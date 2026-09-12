# Optional JSON plan and ledger

Use the checker for substantial coordination where declared ownership, dependencies and recovery benefit from deterministic checks. A short planning table need not be converted to JSON.

## Version 2

Required top-level fields: `schema_version: 2`, `run_id`, `goal`, `repo` with absolute `root` and exact `baseline` identity, a nonempty `acceptance_criteria` list and nonempty `nodes`. The baseline may identify an immutable directory snapshot when this is not repo work.

- `mode`: `plan` (default), `prepare`, or `execute`. This declares scope, not permission to mutate anything.
- `transport`: `native` (default) or `threads`. Tool availability and authorization are checked by the orchestrator, not this script.
- `policy.worker_slots`: positive integer, default 2. Root has one additional execution slot. Use actual capacity/cost constraints.
- `policy.case_sensitive_paths`: default true; use false for Windows working paths.
- `policy.required_final_roles`: default empty. Choose only relevant roles from `integration`, `cross_review`, `restart_replay`, `e2e`, `plan_review`.
- `policy.max_owned_paths_per_node` and `max_subsystems_per_worker_node`: optional explicit hard limits. Without them breadth thresholds only warn.
- `shared_hot_paths`: optional list of `{path, reason}` for genuine unordered shared writes. They serialize that resource, not all work.
- `resource_locks`: optional mapping from resource name to nonempty reason.
- Optional model metadata is descriptive. The checker neither selects models nor proves their live configuration.

Node requirements: `id`, `title`, `outcome`, `owned_paths` (possibly empty), `deliverables`, `targeted_verification`, `acceptance_criteria`. The last three lists must be nonempty. Each criterion ID must exist at the top level; every criterion must be covered.

Optional node fields:

| Field | Meaning / default |
|---|---|
| `kind` | `implementation` by default; descriptive except the special producer/final cases below. |
| `root_only` | false. Owner restriction, not a global execution lock. |
| `exclusive_run` | false. Explicitly excludes all other locked work while this operation runs or awaits acceptance. |
| `prerequisites`, `prerequisite_reasons` | Empty list/map. One concrete reason per prerequisite; no filler length requirement. |
| `read_only_inputs`, `forbidden_paths` | Empty lists. `read_only_inputs` are live shared read paths for conflict detection. Pinned inputs in separate checkouts are identified in the baseline/card instead; root verifies their immutability. |
| `interfaces_produced`, `interfaces_consumed` | Empty lists. A consumed interface needs exactly one producer ancestor with `kind: interface_freeze`. No consumed interface means no mandatory freeze node. |
| `exclusive_resources`, `heavy_test_groups` | Empty lists of scheduling locks; named resources must be declared. |
| `subsystems` | Optional description for breadth review. |
| `final_gate`, `gate_roles` | false / empty. A final gate must have `kind: final_gate` and `root_only: true`. |
| `split_exception` | Optional explanation for intentionally broad root work under explicit breadth limits. |

`execute` requires a root final acceptance stage after all nonfinal contributions. Independent review workers are ordinary review nodes feeding that stage. Required final roles come from policy, not a universal full-suite mandate. `plan` and `prepare` need no execution final gate. If a final gate is explicitly supplied, its declared dependencies and root ownership are still checked.

## Minimal execution example with independent work

```json
{
  "schema_version": 2,
  "mode": "execute",
  "transport": "threads",
  "run_id": "docs-update",
  "goal": "Update two independent guides and accept the combined result",
  "repo": {"root": "C:/project", "baseline": "commit plus immutable dirty snapshot identity"},
  "acceptance_criteria": [{"id": "AC1", "text": "Both guides match the implemented behavior"}],
  "policy": {"worker_slots": 2, "case_sensitive_paths": false, "required_final_roles": ["integration"]},
  "nodes": [
    {
      "id": "A", "title": "Guide A", "outcome": "Guide A matches its feature",
      "owned_paths": ["docs/a.md"], "read_only_inputs": ["src/a/**"],
      "deliverables": ["Updated guide A"], "targeted_verification": ["Compare examples with feature A"],
      "acceptance_criteria": ["AC1"]
    },
    {
      "id": "B", "title": "Guide B", "outcome": "Guide B matches its feature",
      "owned_paths": ["docs/b.md"], "read_only_inputs": ["src/b/**"],
      "deliverables": ["Updated guide B"], "targeted_verification": ["Compare examples with feature B"],
      "acceptance_criteria": ["AC1"]
    },
    {
      "id": "G", "title": "Accept guides", "outcome": "Both accepted guides are integrated",
      "kind": "final_gate", "final_gate": true, "root_only": true,
      "gate_roles": ["integration"], "prerequisites": ["A", "B"],
      "prerequisite_reasons": {"A": "Read the completed guide A", "B": "Read the completed guide B"},
      "owned_paths": [], "read_only_inputs": ["docs/a.md", "docs/b.md"],
      "deliverables": ["Acceptance evidence on the combined baseline"],
      "targeted_verification": ["Inspect the combined diff and affected links"],
      "acceptance_criteria": ["AC1"]
    }
  ]
}
```

For a plan-only version, use `mode: plan`, keep A/B and omit G and `required_final_roles`. No fictitious interface or runtime tests are needed.

## Paths and queue semantics

Paths are workspace-relative with `/`. Supported patterns are exact paths, `dir/**` and `**`. Other globs are explicitly rejected, not treated as proven conflicts. Absolute paths, parent traversal, overlapping owned/forbidden paths and unsafe unordered write/read overlaps are rejected. External inputs should be delivered as a named baseline snapshot under the chosen workspace root or tracked separately in human-readable context; do not invent `../` ownership escapes.

Active `claimed`/`running` tasks use execution slots. `worker_done`/`verified` release their slot but retain relevant file/resource locks until accepted/integrated. Root can run with disjoint workers; only `exclusive_run` or actual conflicts serialize them globally.

`waves` are illustrative. After ledger replay, `ready_nodes` and `blocked_nodes` describe readiness against current declared state. Several ready nodes may compete for the remaining slots or each other; choose a fitting subset and recheck after each claim. Do not dispatch the entire list blindly. Blocked/failed/orphaned retries require root reconciliation before a fresh claim; they are not automatically relaunched by the checker.

## Ledger version 2

One JSON object per line, contiguous integer `seq` starting at 1. Root writes the ledger. `agent_ref` is a stable assignment key mapped to actual task/host IDs in `threads.json`.

```json
{"seq":1,"node_id":"A","from":"planned","to":"claimed","attempt":1,"agent_ref":"a-attempt-1","evidence":"Task creation reserved"}
{"seq":2,"node_id":"A","from":"claimed","to":"running","attempt":1,"agent_ref":"a-attempt-1","evidence":"Real task ID resolved and work started"}
{"seq":3,"node_id":"A","from":"running","to":"worker_done","attempt":1,"agent_ref":"a-attempt-1","evidence":"Receipt and patch returned"}
{"seq":4,"node_id":"A","from":"worker_done","to":"verified","attempt":1,"actor":"root","evidence":"Root inspected the diff and checks"}
{"seq":5,"node_id":"A","from":"verified","to":"integrated","attempt":1,"actor":"root","evidence":"Patch present in named integration baseline"}
```

Every claim requires a positive attempt, incremented on retry, and `agent_ref`; root-owned claims use `agent_ref: root`. Every later transition for that attempt includes the matching attempt. `running` and `worker_done` also match the assigned `agent_ref`. `verified` and `integrated` require `actor: root`. Evidence must be nonempty for completion, blocking, failure and supersession transitions. An initially blocked/superseded node has no execution attempt yet.

See [orchestration-contract.md](orchestration-contract.md) for state meanings. Validate that a live process stopped before releasing its locks; the checker cannot observe it. Acceptance labels are bookkeeping, not proof of authorship or behavior.

## Commands and limits

```text
python scripts/check_orchestration.py dag.json --json
python scripts/check_orchestration.py dag.json --events events.jsonl --json
python scripts/check_orchestration.py dag.json --events events.jsonl --require-complete
python scripts/check_orchestration.py --example
python scripts/check_orchestration.py --self-test
```

`--self-test` runs stdlib regression scenarios from `scripts/test_orchestration.py`. `--example` prints a larger v2 example without creating tasks. Exit 0 means the declared structure/ledger passed; it does not verify receipts, changed files, actual task settings or working software. Root checks those independently.

Legacy v1 plans and ledgers remain readable with a warning. They retain legacy final-role requirements and have reduced attempt/actor checks. The supported path language is now exact/directory patterns; an old complex-glob plan must be reviewed explicitly. No file or ledger is migrated automatically.
