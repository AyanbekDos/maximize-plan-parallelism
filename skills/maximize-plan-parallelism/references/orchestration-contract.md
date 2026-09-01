# Orchestration contract

Use this contract for an executing run or when recovering one after interruption. The root task is the control plane; native subagents are disposable workers.

## Frozen run artifacts

Resolve one external run directory before dispatch. Record its absolute path in the active task.

`brief.md` must contain:

- the user-visible goal and mutation authority;
- repo root and exact baseline revision or immutable snapshot identity;
- authoritative plan and acceptance-criteria paths;
- accepted decisions, implementation facts, unknowns, and non-goals;
- live worker capacity and why it is safe;
- the final proof required.

`dag.json` follows [dag-schema.md](dag-schema.md). Freeze it only after the checker passes and the root has reviewed derived waves.

`events.jsonl` contains one JSON object per line:

```json
{"seq":1,"node_id":"N1","from":"planned","to":"claimed","agent_ref":"native-agent-id","evidence":"Assigned the frozen N1 card"}
```

Sequence numbers are contiguous. Only the root appends. Include concrete evidence for `worker_done`, `verified`, `integrated`, `blocked`, `failed`, `orphaned`, and `superseded` transitions.

## State ownership

The root alone may:

- revise the DAG;
- assign or reassign nodes;
- change node status;
- accept a receipt;
- decide whether verification passed;
- incorporate work into the integration state;
- declare final completion.

A worker owns only the paths and observable outcome on its card. It may inspect read-only inputs, must not touch forbidden paths, and must stop when an undisclosed shared edit becomes necessary.

`worker_done` means only that a worker returned. `verified` means the root inspected the actual artifact/diff and the targeted evidence. `integrated` means the verified result is present in the controlled integration state and is safe for dependents to consume.

## Worker dispatch card

Send the worker the exact card plus:

- current integration baseline;
- whether the task is implementation or read-only forward testing;
- explicit instruction not to broaden scope or edit the ledger;
- the targeted command budget;
- instruction to report newly discovered dependency or path overlap instead of working around it.

Require this receipt shape in the response:

```json
{
  "node_id": "N1",
  "status": "worker_done",
  "summary": "Observable result produced",
  "changed_paths": ["repo/relative/path"],
  "deliverables": ["artifact or behavior"],
  "verification": [
    {"command": "targeted command", "result": "pass", "evidence": "concise output"}
  ],
  "assumptions": [],
  "risks": [],
  "new_dependencies": []
}
```

Reject or rework a receipt when changed paths exceed ownership, evidence is only asserted, a prerequisite was guessed, or a deliverable is not observable.

## Reconciliation loop

Run this loop before every dispatch and after context compaction:

1. Read the frozen brief and DAG from disk.
2. Replay the ledger with the checker.
3. Inspect the live native-subagent registry.
4. Map every live agent to exactly one `claimed` or `running` node.
5. Inspect repo status/diff and map every changed path to one active or received card.
6. Match every `worker_done` node to a returned receipt and actual artifact.
7. Mark missing unproven work `orphaned`; never infer completion from silence.
8. Resolve discrepancies before spawning anything else.

If a worker requests a forbidden or shared path, pause it. The root either narrows the card, adds a genuine semantic edge in a new DAG revision, or schedules the hot path serially. Do not let workers negotiate ownership among themselves.

## Integration and verification

For each returned node, the root:

1. checks changed paths against `owned_paths` and `forbidden_paths`;
2. inspects the diff or produced artifact;
3. reruns or independently validates narrow verification;
4. checks all mapped acceptance criteria;
5. records the receipt and `verified` event;
6. incorporates it into the current integration state;
7. records `integrated` only after incorporation is proven.

Do not duplicate a heavy suite across workers. A heavy group has one owner in a wave. Run a shared subsystem gate once after its contributing nodes integrate, and run the complete suite once in the final gate stage.

## Completion contract

Completion requires:

- every non-superseded node is `integrated`;
- no native subagent remains active or unaccounted for;
- every changed path maps to an accepted receipt;
- every acceptance criterion maps to inspectable evidence;
- system integration, cross-review, restart/replay, and E2E roles all ran after non-final work integrated;
- the final repo state and test outputs are identified precisely;
- remaining risks and sequential constraints are explained without calling capacity limits semantic dependencies.

Use `--require-complete` with the checker before the final response.
