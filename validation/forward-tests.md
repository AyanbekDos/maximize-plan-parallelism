# Initial forward tests

The initial skill and checker were exercised against two large implementation plans before public packaging. Both runs were planning-only: no workers were dispatched and no source repository or worktree was changed.

Private repository names, local paths, and proprietary plan text are omitted here. The scheduling topology and checker results are preserved.

## Test A - independent review frontier

The plan contained eight nodes:

1. Freeze an already committed interface contract read-only.
2. Preserve implementation artifact A.
3. Preserve implementation artifact B.
4. Review A.
5. Review B.
6. Integrate both reviewed artifacts.
7. Run combined E2E verification.
8. Run the final acceptance gate.

The checker returned `ok: true`, with no errors or warnings. It derived seven waves:

```text
F0
P-A
P-B
R-A + R-B
INTEGRATION
E2E
ACCEPTANCE
```

The useful parallel frontier was the review wave. Both inputs had already been preserved, the reviews were read-only, and their heavy-test groups were distinct. Integration and acceptance remained sequential semantic gates.

## Test B - honest serialization

The second plan contained a clean-worktree gate, an interface freeze, seven proposed implementation verticals, and a final generated integration gate.

Every vertical wrote the same central API client mount and fallback path. Additional pairs also shared model-settings UI, carrier authority, or client runtime paths.

The checker returned `ok: true`, with no errors or warnings, and kept all seven implementation verticals in separate waves. It reported the exact shared hot paths responsible for each scheduling lock instead of inventing DAG edges between otherwise independent outcomes.

## What these tests established

- The scheduler exposes parallel work when outcomes and verification are genuinely independent.
- Shared hot paths serialize dispatch without being mislabeled as semantic prerequisites.
- A read-only interface-freeze gate can pin an existing committed contract without creating interface churn.
- A graph with no safe implementation parallelism is a valid result.
