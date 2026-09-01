# DAG schema and checker

`dag.json` is a root-owned plan, not a worker scratchpad. Paths are repo-relative and use `/`; use `dir/**` for directory ownership. Keep semantic dependency edges separate from scheduling locks.

## Complete example

```json
{
  "schema_version": 1,
  "run_id": "adapter-example-001",
  "goal": "Ship two adapter behaviors against one frozen contract",
  "repo": {
    "root": "C:/repo",
    "baseline": "0123456789abcdef"
  },
  "acceptance_criteria": [
    {"id": "AC1", "text": "The adapter contract is explicit and stable"},
    {"id": "AC2", "text": "Both behaviors pass through the real adapter"}
  ],
  "policy": {
    "worker_slots": 2,
    "max_owned_paths_per_node": 6,
    "max_subsystems_per_worker_node": 1,
    "case_sensitive_paths": false
  },
  "shared_hot_paths": [],
  "resource_locks": {},
  "nodes": [
    {
      "id": "F1",
      "title": "Freeze adapter contract",
      "outcome": "Consumers can implement against one versioned adapter contract",
      "kind": "interface_freeze",
      "root_only": false,
      "final_gate": false,
      "gate_roles": [],
      "prerequisites": [],
      "prerequisite_reasons": {},
      "subsystems": ["adapter-contract"],
      "owned_paths": ["src/adapter/contract.ts"],
      "read_only_inputs": ["docs/adapter-contract.md"],
      "forbidden_paths": ["src/adapter/runtime/**"],
      "deliverables": ["Versioned adapter types and invariants"],
      "targeted_verification": ["Run the adapter contract type test"],
      "acceptance_criteria": ["AC1"],
      "interfaces_produced": ["adapter-contract-v1"],
      "interfaces_consumed": [],
      "exclusive_resources": [],
      "heavy_test_groups": [],
      "split_exception": null
    },
    {
      "id": "A1",
      "title": "Implement behavior A",
      "outcome": "A real request executes behavior A through the adapter",
      "kind": "implementation",
      "root_only": false,
      "final_gate": false,
      "gate_roles": [],
      "prerequisites": ["F1"],
      "prerequisite_reasons": {"F1": "Behavior A imports the frozen adapter types and cannot be valid before their shape is fixed"},
      "subsystems": ["behavior-a"],
      "owned_paths": ["src/behavior-a/**", "tests/behavior-a/**"],
      "read_only_inputs": ["src/adapter/contract.ts"],
      "forbidden_paths": ["src/behavior-b/**"],
      "deliverables": ["Behavior A implementation and focused test"],
      "targeted_verification": ["Run behavior A focused tests"],
      "acceptance_criteria": ["AC2"],
      "interfaces_produced": [],
      "interfaces_consumed": ["adapter-contract-v1"],
      "exclusive_resources": [],
      "heavy_test_groups": [],
      "split_exception": null
    },
    {
      "id": "B1",
      "title": "Implement behavior B",
      "outcome": "A real request executes behavior B through the adapter",
      "kind": "implementation",
      "root_only": false,
      "final_gate": false,
      "gate_roles": [],
      "prerequisites": ["F1"],
      "prerequisite_reasons": {"F1": "Behavior B imports the frozen adapter types and cannot be valid before their shape is fixed"},
      "subsystems": ["behavior-b"],
      "owned_paths": ["src/behavior-b/**", "tests/behavior-b/**"],
      "read_only_inputs": ["src/adapter/contract.ts"],
      "forbidden_paths": ["src/behavior-a/**"],
      "deliverables": ["Behavior B implementation and focused test"],
      "targeted_verification": ["Run behavior B focused tests"],
      "acceptance_criteria": ["AC2"],
      "interfaces_produced": [],
      "interfaces_consumed": ["adapter-contract-v1"],
      "exclusive_resources": [],
      "heavy_test_groups": [],
      "split_exception": null
    },
    {
      "id": "G1",
      "title": "Prove the integrated system",
      "outcome": "The integrated adapter survives review, restart, replay, and real E2E use",
      "kind": "final_gate",
      "root_only": true,
      "final_gate": true,
      "gate_roles": ["integration", "cross_review", "restart_replay", "e2e"],
      "prerequisites": ["A1", "B1"],
      "prerequisite_reasons": {
        "A1": "System acceptance must exercise the integrated behavior A implementation",
        "B1": "System acceptance must exercise the integrated behavior B implementation"
      },
      "subsystems": ["integrated-system"],
      "owned_paths": [],
      "read_only_inputs": ["src/**", "tests/**"],
      "forbidden_paths": [],
      "deliverables": ["Cross-review receipt and E2E evidence"],
      "targeted_verification": ["Run restart/replay scenario and the complete integration suite once"],
      "acceptance_criteria": ["AC1", "AC2"],
      "interfaces_produced": [],
      "interfaces_consumed": ["adapter-contract-v1"],
      "exclusive_resources": [],
      "heavy_test_groups": ["full-integration-suite"],
      "split_exception": "The root must evaluate the same integrated state across all final proof roles"
    }
  ]
}
```

## Required meanings

- `prerequisites` contains only semantic edges. `prerequisite_reasons` has one concrete reason for each edge.
- `interfaces_produced` is allowed only on `interface_freeze` nodes. A freeze node may pin an existing committed contract without editing it. Every consumed interface has exactly one producer ancestor.
- `owned_paths` is the exclusive write set. Empty is valid for read-only gates.
- `read_only_inputs` may be inspected but not changed by that node.
- `forbidden_paths` are explicit no-write boundaries for that worker.
- `shared_hot_paths` contains `{ "path": "...", "reason": "..." }` entries for unavoidable unordered write/write overlaps. The scheduler serializes them.
- `resource_locks` maps a named non-file resource to the reason it is exclusive. Nodes claim names through `exclusive_resources`.
- `heavy_test_groups` prevents duplicate expensive suites in one wave.
- `split_exception` is normally `null`. Use a concrete reason only for an intentionally broad root-owned or final gate.
- `gate_roles` uses `integration`, `cross_review`, `restart_replay`, and `e2e`. All four roles must be covered after every non-final node.

## Checker commands

```text
python scripts/check_orchestration.py dag.json
python scripts/check_orchestration.py dag.json --json
python scripts/check_orchestration.py dag.json --events events.jsonl --json
python scripts/check_orchestration.py dag.json --events events.jsonl --require-complete
python scripts/check_orchestration.py --self-test
```

The checker validates required cards, cycles, edge reasons, interface ancestry, acceptance coverage, breadth limits, path safety, final-gate coverage, event transitions, active capacity, and active lock conflicts. It derives deterministic capacity-aware waves. Exit code `0` means no validation errors; warnings and serialization reasons still require root review.
