# Repository Contract Gaps

This file records baseline schema/implementation gaps that materially affect the production contract. Revalidate the relevant entry against source and tests before changing the associated tool. These entries describe this MCP implementation baseline, not CATIA V5 as a product.

## Session execution

### Shared synchronous COM path

Baseline request handling executes module operations synchronously against a shared CATIA connection and does not establish a dedicated serialized STA worker queue for all CATIA calls.

Required production contract:

- one owned STA execution boundary per CATIA session;
- queued serialized operations;
- explicit session health;
- timeout handling that blocks further mutation when completion is indeterminate.

### Text-oriented result surface

Baseline tools commonly return human-readable strings, and server-boundary exceptions can become ordinary text content.

Required production contract: structured result/error envelope with typed codes; text summary is secondary.

## Part Design schema/implementation gaps

### `catia_hole`

Schema advertises specialized hole `type` values beyond a simple hole. Baseline implementation does not establish distinct execution semantics for all advertised types.

Required action: implement and validate every advertised hole type or narrow/deprecate unsupported schema options.

### `catia_fillet` / `catia_chamfer`

Baseline schema includes an edge selector, but exact edge targeting is not established as a consumed BRep reference contract.

Required action: enumerate edges with descriptors, issue generation-scoped tokens, resolve exact BRep/ResourceEdge-equivalent references, and test stale-token failure.

### `catia_shell`

Baseline face-removal selection does not provide a production-safe BRep face resolver and target-resolution failures may not establish a deterministic failure.

Required action: face enumeration + exact token resolver + target-resolution error + geometric postcondition.

### `catia_draft` / `catia_thickness`

Advertised face selection is not established as a consumed exact-target contract.

### `catia_mirror`

Feature-specific mirroring semantics are not established by the baseline implementation.

### Patterns

Direction/axis intent relies on implicit references in baseline paths. Production semantics require explicit reference handles/tokens and verifiable instance effects.

## Topology query surface

### `catia_list_edges`

Returned names/indices are observations of current topology, not durable IDs, and baseline downstream edge-consuming features do not establish exact token consumption.

### Face enumeration

No baseline production-safe face enumeration + exact resolver contract is established.

## Sketch support

Baseline sketch creation is limited to origin planes. Production multi-step Part Design needs deterministic support references for offset planes and sketch-on-reference/face workflows.

## Assembly constraint references

Baseline coincidence/offset/angle schemas describe element references, but exact component-local geometry resolution is not established in the execution contract.

Required production contract:

- component-local geometry handles/tokens;
- exact reference construction;
- constraint solve/status result;
- DOF or positional verification where available.

## View/screenshot

Baseline screenshot width/height inputs do not establish an enforced output-resolution contract.

Required action: enforce and verify capture dimensions or remove/narrow those inputs.

## Missing reliability primitives

The baseline does not establish all of the following production primitives:

- structured result envelope and typed errors;
- operation IDs and structured tracing;
- dedicated serialized STA worker;
- session-health state machine;
- object-handle registry;
- topology generation and stale-token rejection;
- journal-based recovery;
- modal-dialog guard;
- per-mutation material-effect classification;
- native update diagnostics and locale-independent feature typing;
- exact CAA/BRep topology helpers.
