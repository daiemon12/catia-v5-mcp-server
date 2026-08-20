---
name: catia-v5-mcp-maintainer
description: Maintain daiemon12/catia-v5-mcp-server against a production reliability contract. Use when changing tool schemas or implementations, COM execution, session health, structured results, object handles, topology references, recovery, diagnostics, CAA bridge integration, or regression evaluation. Requires source-first changes, truthful schemas, deterministic failure behavior, and live CATIA validation for COM/BRep semantics.
compatibility: Python 3.10+; Windows with pywin32 and CATIA V5 for live validation. Source-level tests may run cross-platform when CATIA imports are isolated.
metadata:
  version: "1.1.0"
  locale: "en-US"
  target-repository: "daiemon12/catia-v5-mcp-server"
---

# CATIA V5 MCP Maintainer

Use this skill when changing the target MCP server itself. Production support is a contract between schema, implementation, runtime behavior, diagnostics, recovery, and tests. Tool count alone is not a reliability metric.

## Mandatory engineering rules

1. Inspect repository-local schema and implementation before changing or documenting a tool.
2. Keep public schemas truthful: every advertised input must be consumed with defined semantics or removed/deprecated.
3. Serialize CATIA COM access through a dedicated STA execution boundary; do not let arbitrary MCP request threads use shared COM objects directly.
4. Return structured results with deterministic success/failure classification. Human-readable text is a secondary representation, not the primary protocol.
5. Separate CATIA update success from intended geometry effect.
6. Give material-changing operations measurable postconditions and explicit no-effect/wrong-effect failures.
7. Use server-managed handles for document/model objects rather than relying on display names or long mutable paths.
8. Use generation/version-scoped topology references and reject stale references before mutation.
9. Provide deterministic recovery for supported reversible operations. Do not depend on localized UI command strings for Undo.
10. Treat modal dialogs, timeouts, and indeterminate COM completion as session-health events, not ordinary retryable exceptions.
11. Keep CAA/native access behind typed adapters; do not expose raw native/COM pointers across the MCP boundary.
12. Do not classify a capability as production-supported until schema tests, failure-path tests, and relevant live CATIA validation pass.

## Reference loading

Read `references/repository-contract-gaps.md` before modifying an existing tool or capability group.

Read `references/production-architecture.md` before changing COM/session execution, object lifecycle, recovery, topology, diagnostics, or CAA integration.

Read `references/result-contract.md` before adding or changing tool outputs/errors.

Read `references/test-strategy.md` before accepting a behavior change.

Read `references/production-readiness-checklist.md` when assessing support level across capability groups.

## Source-first change process

For each change:

1. Inspect the exact schema, dispatch path, implementation, and relevant helper functions.
2. Write the intended behavioral contract: inputs, units, target semantics, preconditions, effects, errors, and recovery metadata.
3. Add or adjust an offline contract/failure test that can detect the current defect where possible.
4. Implement the smallest deterministic change that satisfies the contract.
5. Preserve a public tool name only when backward semantics remain compatible; otherwise version, narrow, or deprecate the contract explicitly.
6. Add a live CATIA probe for any behavior that mocks cannot establish, especially COM apartment behavior, CATIA API signatures, BRep references, update diagnostics, and modal UI.
7. Update capability classification only after the implementation and validation evidence agree.

## Runtime execution contract

The target runtime should separate asynchronous MCP transport from CATIA execution:

`MCP request -> typed validation -> operation orchestrator -> serialized STA worker -> CATIA Automation / optional CAA adapter -> result verification`

The worker owns COM initialization and COM object resolution on its own STA thread. Request handlers enqueue logical operations and await structured results.

Do not transfer apartment-bound raw COM objects to request threads. Store logical handles and resolve them on the worker.

## Session-health contract

Use explicit session health such as:

- `healthy`: CATIA state is known and mutations are allowed;
- `blocked`: a known modal/blocked condition prevents safe calls;
- `unknown`: call completion or model state cannot be established;
- `disconnected`: no active CATIA connection.

A timeout does not prove an in-flight COM call was cancelled. If completion is indeterminate, transition to `unknown` or `blocked` and reject further mutations until health and model state are re-established.

## Tool contract

Each engineering-intent tool should define:

- narrow typed inputs;
- units and enum semantics;
- deterministic target references;
- precondition checks;
- mutation/update behavior;
- measurable effects;
- structured data/result fields;
- typed failure codes;
- recovery metadata where applicable;
- tests for success, failure, and no-effect/wrong-effect behavior.

A mutation tool must not return only a phrase such as "created successfully" when design correctness can be measured.

## Schema integrity

A schema field is part of the public contract. If implementation ignores an advertised input, choose one of two actions:

- implement the input semantics and validate them; or
- remove/deprecate the input and narrow the capability description.

Documentation must not be used to compensate for an ignored runtime input.

## Geometry-effect contract

For a tool expected to add/remove material:

1. capture pre-operation update/measurement state;
2. perform the mutation on the STA worker;
3. update CATIA;
4. collect post-operation measurement state;
5. classify effect;
6. return structured effect metadata.

At minimum support typed outcomes for `FEATURE_NO_EFFECT`, `WRONG_GEOMETRY_EFFECT`, and `UPDATE_FAILED` when applicable.

## Object-handle contract

Expose opaque logical handles for session objects such as documents, bodies, sketches, features, and parameters. The handle registry should track owning document/session and object validity.

After document close/reload/session reset, affected handles must fail deterministically, for example with `STALE_HANDLE` or `OBJECT_NOT_FOUND`. Never silently rebind a stale handle by display name.

## Topology-reference contract

Topology references are server-layer abstractions, not durable native CATIA IDs. Treat the external token format as opaque.

A topology record should include:

- token;
- face/edge kind;
- owning document/body;
- topology generation/version;
- geometric descriptors;
- resolver metadata required to reconstruct an exact CATIA/CAA reference.

Every shape-changing mutation increments or invalidates the topology generation. A token from an older generation must return `STALE_TOPOLOGY_TOKEN` before feature creation. Never fall back to the same numeric index in a changed topology.

## Recovery contract

Use an operation journal or equivalent deterministic recovery record. This is a logical recovery mechanism, not an ACID transaction and not a claim of CATIA-native atomicity.

Record, as applicable:

- created feature handle and deletion strategy;
- parameter old/new value;
- document/model generation before and after;
- operation group identity for multi-step intent;
- measurements used to verify rollback.

Rollback must run in reverse order, update CATIA, and verify restoration where measurable.

## Modal-dialog contract

Detect/report blocking CATIA modal dialogs around fragile or long-running calls. Auto-close only an explicit allowlist of non-destructive dialogs. Return dialog metadata and session-health impact. Do not invoke arbitrary buttons based on caption similarity.

## Diagnostics and CAA

Automation exceptions are insufficient for advanced repair. Expose the deepest available diagnostics without inventing native meaning.

When a CAA bridge is present:

- keep the bridge behind a typed JSON/Automation boundary;
- return locale-independent feature types where possible;
- return native CATIA update diagnostics;
- provide exact BRep reference helpers for topology-consuming features;
- preserve lower-layer failure state without re-wrapping it as success.

When a CAA bridge is absent, return the limitation explicitly rather than synthesizing native diagnostic text.

## Validation requirement

Offline tests establish schema/orchestration contracts. Live CATIA probes establish actual COM/API/BRep behavior. Agent task evaluations establish end-to-end capability.

All three levels are required before broad production-support claims for features that depend on CATIA runtime semantics.

## Acceptance criteria

A production-supporting change is complete only when all applicable conditions hold:

- schema and implementation semantics agree;
- structured failure state propagates unchanged across layers;
- no advertised input is silently ignored;
- session/thread rules are preserved;
- stale handles/tokens fail deterministically;
- update success and geometry-effect success are evaluated separately;
- success, failure, and no-effect/wrong-effect paths are tested;
- relevant live CATIA validation passes, or the capability remains explicitly non-production-validated;
- documentation states the supported contract and limitations without overstating them.
