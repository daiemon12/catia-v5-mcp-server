---
name: catia-v5-production-operator
description: Operate CATIA V5 through daiemon12/catia-v5-mcp-server under a conservative production execution contract. Use for CATPart or CATProduct creation and modification, sketching, Part Design, parameter edits, measurement, assembly operations, screenshots, saving, or export. Requires serialized CATIA calls, explicit document context, per-step verification, topology-reference safety, bounded recovery, and explicit unsupported-capability reporting.
compatibility: Windows with CATIA V5 R2016+ and daiemon12/catia-v5-mcp-server configured as an MCP server.
metadata:
  version: "1.1.0"
  locale: "en-US"
  target-repository: "daiemon12/catia-v5-mcp-server"
---

# CATIA V5 Production Operator

Use this skill as the runtime operating contract for CATIA V5 work through the target MCP server. This skill constrains how available tools are used; it does not substitute for server capabilities that are absent or unverified.

## Mandatory execution rules

1. Execute CATIA MCP calls serially. Do not issue overlapping CATIA mutations against the shared active session unless the active server explicitly guarantees serialized STA execution.
2. Establish the active document and document type before modifying an existing model. For a new-document task, create the document first and then verify the resulting active document.
3. Separate command completion from design correctness. A normal tool response or clean CATIA update is not sufficient evidence that the intended geometry exists.
4. Decompose modeling into the smallest steps that have executable postconditions: `inspect -> mutate -> update -> measure -> decide`.
5. Discover references before use. Do not invent feature names, parameter paths, component names, sketch geometry indices, faces, or edges.
6. Treat names and indices as short-lived observations after model mutation. Re-query them before reuse.
7. Use exact face/edge operations only when the active server resolves and consumes deterministic BRep references and can reject stale references.
8. Keep recovery bounded. Do not continue trial-and-error mutations in a model whose integrity has not been re-established.
9. Persist changes only when required by the task. Saving, overwriting, closing, and exporting are separate side effects and must not be performed implicitly.
10. Use screenshots as supporting evidence only. Prefer structural and numeric verification whenever the result is measurable.

## Capability-profile rule

Use `references/capability-matrix.md` as the baseline contract for the repository implementation represented by this skill.

If the active server exposes a stronger capability/status contract, a capability may be promoted only when all of the following are explicit and verifiable:

- the input is consumed by the implementation;
- target-reference semantics are defined;
- failure behavior is typed or otherwise deterministic;
- a relevant postcondition can be evaluated;
- the capability has a live CATIA validation path where COM/BRep behavior is involved.

Do not infer stronger support from a tool name, schema field, successful transport call, or feature-tree entry alone.

## Reference loading

Read `references/capability-matrix.md` before holes, patterns, mirror, fillet, chamfer, shell, draft, thickness, exact face/edge selection, or assembly constraints.

Read `references/verification-policy.md` for all multi-step modeling, parameter propagation, or dimensional/material assertions.

Read `references/failure-recovery.md` after any exception, update failure, no-effect result, wrong-effect result, timeout, modal-block condition, or ambiguous state.

Read `references/topology-and-assembly.md` before topology-sensitive Part Design or precision assembly mating.

Read `references/tool-workflows.md` for common verified execution sequences.

## Preflight

For a mutation task:

1. Establish connection state with `catia_connect` when needed.
2. Determine whether the task creates a new document or modifies an existing document.
3. For a new CATPart/CATProduct, create it first, then call `catia_get_active_document_info` and verify the document type.
4. For an existing model, call `catia_get_active_document_info` before mutation and require the expected type.
5. For an existing CATPart, capture an applicable baseline:
   - `catia_list_features`;
   - `catia_get_inertia` when a measurable solid exists;
   - `catia_get_bounding_box` when geometry exists;
   - `catia_get_parameters` for parameters that may be changed.
6. For an existing CATProduct, capture component and constraint listings before precision assembly work.
7. Define the expected postconditions internally: expected feature, material-effect direction, key dimensions, parameter values, and any required persistence side effect.

If a required geometric reference cannot be discovered through the active tool contract, classify the operation as unsupported rather than guessing the reference.

## Modeling cycle

For each material-changing feature:

1. Capture the pre-step evidence needed for the assertion, typically volume and relevant dimensions.
2. Execute one feature operation.
3. Call `catia_update_part`.
4. Verify expected structural state with `catia_list_features` when applicable.
5. Re-measure volume and relevant bounding-box dimensions.
6. Re-read changed parameters when applicable.
7. Continue only if the evidence is consistent with the intended effect.

A later successful update must not be used to retroactively validate an earlier unverified feature.

## Geometry-effect classification

Classify a material mutation as one of:

- `PASS`: update succeeds and structural/numeric evidence matches the intended effect within an explicit tolerance.
- `NO_EFFECT`: update succeeds but a required material change is effectively zero.
- `WRONG_EFFECT`: update succeeds but the material change has the wrong sign or an implausible magnitude.
- `UPDATE_FAILED`: CATIA rebuild/update fails.
- `INCONCLUSIVE`: the active contract cannot produce enough evidence to verify the requested effect.

Do not report `NO_EFFECT`, `WRONG_EFFECT`, or `INCONCLUSIVE` as successful design completion.

## Parameter edits

For an existing-model parameter change:

1. Discover the exact parameter with `catia_get_parameters`.
2. Record the original value and relevant baseline measurements.
3. Call `catia_set_parameter` once.
4. Call `catia_update_part`.
5. Re-read the parameter and verify the requested value.
6. Re-measure geometry that should propagate from the parameter change.
7. If the change fails and the original value is known, perform one deterministic revert and re-verify the restored state.

A successful parameter assignment does not prove dependent pockets, holes, or patterns still intersect the intended solid.

## Sketch operations

1. Use only support geometry explicitly supported by the active server contract.
2. Add sketch geometry.
3. Immediately before an index-based constraint, call `catia_sketch_get_geometry` and use only freshly observed indices.
4. Close the sketch before a Part Design feature consumes it.
5. Verify the resulting 3D feature; do not treat a visually closed sketch as proof of a valid solid operation.

Do not represent an origin-plane sketch as attached to a model face when the server does not provide a verified sketch-support reference.

## Topology-sensitive operations

Exact fillet/chamfer/shell/draft/thickness requests require deterministic topology references. If the active server lacks a verified face/edge enumeration and reference-resolution contract, return `UNSUPPORTED_CAPABILITY` for exact-target intent.

If topology tokens are available:

- treat the token as opaque;
- use the generation/version metadata returned with it;
- invalidate tokens after any shape-changing mutation unless the server explicitly states otherwise;
- reject or re-query after `STALE_TOPOLOGY_TOKEN`.

See `references/topology-and-assembly.md`.

## Hole operations

Support `counterbored`, `countersunk`, `tapered`, threaded, or other specialized hole semantics only when the active implementation consumes the corresponding inputs and the result can be verified.

Never silently convert a requested specialized hole into a simple cylindrical hole.

## Assembly operations

Exact face/plane/axis mating is production-verifiable only when component-local geometry references are resolved deterministically and the resulting constraint/DOF state can be inspected.

Component listing, constraint listing, component insertion, and coarse positioning may still be used when their own postconditions are verifiable.

## Failure and recovery

Treat structured failure, exceptions, update errors, missing required result fields, contradictory measurements, and unverified target selection as failures.

On failure:

1. stop the current mutation chain;
2. inspect the current document and measurements;
3. determine the last verified state;
4. apply a bounded deterministic correction only when the cause and recovery path are known;
5. re-verify from a known state before further mutation.

If a COM timeout or blocked modal state leaves call completion indeterminate, treat the session as `blocked` or `unknown`. Do not replay the mutation until session health and model state are re-established.

Use `references/failure-recovery.md` for the recovery decision rules.

## Completion criteria

Before reporting a CATPart task complete, require all applicable evidence:

- requested features exist;
- update completes cleanly;
- key dimensions and numeric geometry match the design within stated tolerance;
- parameter values match requested values;
- required additive/subtractive steps have the expected non-zero material effect;
- topology-specific intent is verified when such intent was requested;
- save/export side effects occurred only when required and their produced paths are known.

Before reporting a CATProduct task complete, require component/constraint evidence plus any available positional or DOF/solve evidence. Disclose any exact-reference limitation that remains.

## User-facing result

Report only:

- what was created or changed;
- the strongest verification evidence;
- any unresolved capability or verification limitation;
- save/export paths that were actually produced.

Do not translate an unverified tool call into a verified CAD claim.
