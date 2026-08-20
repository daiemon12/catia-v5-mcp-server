# Test Strategy

Production support requires multiple validation layers because mocks cannot establish CATIA runtime semantics.

## Layer 1 — schema and static contract

No CATIA required.

Validate:

- unique registered tool names;
- valid schemas;
- required inputs match execution signatures;
- no advertised input is silently ignored;
- enums map to implemented branches;
- result envelope and error propagation;
- string/control-character serialization;
- pagination/collector behavior;
- handle/token parsing and stale-generation rules.

These tests should be platform-independent when CATIA-specific imports are isolated.

## Layer 2 — orchestration tests with doubles/mocks

Validate server behavior without claiming CATIA API correctness:

- STA queue serialization;
- request handlers do not use raw shared COM objects;
- session-health transitions;
- timeout classification;
- journal entries and reverse recovery order;
- parameter revert logic;
- effect-classification logic;
- stale topology rejection before adapter mutation;
- lower-layer failure preservation.

## Layer 3 — live CATIA probes

Use small deterministic tests against supported CATIA environments.

Minimum probes for a broad Part Design claim:

- connect/new part/save/close;
- rectangle -> pad -> expected bbox/volume;
- circle -> pad;
- pocket with expected non-zero volume decrease;
- parameter change and propagation;
- deliberate invalid parameter -> update failure/diagnostics;
- recovery restores parameter and measurable geometry;
- exact edge enumeration + fillet when that capability is supported;
- exact face enumeration + shell opening when supported;
- modal dialog/session-health behavior;
- assembly exact-reference constraint when assembly mating is supported;
- export and screenshot existence.

Record CATIA release/build and locale with probe results.

## Layer 4 — agent task evaluations

Each task should contain:

- initial model/state;
- natural-language instruction visible to the agent;
- hidden machine assertions;
- required capability class;
- expected error code for intentionally unsupported scenarios where applicable.

Measure more than final pass/fail:

- update-clean state;
- numeric geometry assertions;
- tool calls;
- failed calls;
- recovery count;
- elapsed time;
- token/cost metrics when available;
- screenshot existence, and visual correctness only when an explicit vision grader is used.

## Comparative evaluation

When adding a CAA bridge or alternative backend, compare on tasks that exercise the added capability. Use repeated paired runs when nondeterminism matters and preserve full tool traces. Easy tasks that both variants already solve do not establish incremental value.

## Production-support gate

A capability may be classified as production-supported only when:

- schema/static contract tests pass;
- failure and no-effect paths pass;
- relevant live CATIA probe passes on the supported environment;
- known limits are stated accurately;
- no known input is silently ignored.
