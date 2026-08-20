# Production Readiness Checklist

Assess reliability foundations before broadening the modeling surface.

## Execution reliability

- [ ] Structured result envelope with typed codes and lower-layer failure preservation.
- [ ] Dedicated serialized STA worker.
- [ ] Explicit session-health states and safe timeout behavior.
- [ ] Schema/implementation parity for all registered inputs.
- [ ] Operation IDs and structured tracing.
- [ ] Pre/post update and material-effect measurements for material mutations.
- [ ] `FEATURE_NO_EFFECT` and `WRONG_GEOMETRY_EFFECT` classification.
- [ ] Session object-handle registry and deterministic stale-handle failures.
- [ ] Recovery journal for supported reversible mutations.
- [ ] Modal-dialog detection and conservative handling.

## Deterministic geometry intent

- [ ] Reference/offset planes and verified sketch support references.
- [ ] Face enumeration with geometric descriptors.
- [ ] Edge enumeration with geometric descriptors.
- [ ] Opaque topology tokens with generation validation.
- [ ] Exact face/edge resolvers consumed by topology-sensitive features.
- [ ] Explicit pattern direction/axis references.
- [ ] Assembly component-local geometry reference resolver.
- [ ] Constraint status/solve and DOF or equivalent positional verification.

## Diagnostics and native integration

- [ ] Update diagnostics identify failing feature and native reason where available.
- [ ] Locale-independent feature typing where required.
- [ ] CAA bridge protocol preserves lower-layer failure semantics.
- [ ] CAA/BRep exact ResourceSur/ResourceEdge-equivalent reference helpers when advanced topology is supported.

## Evaluation

- [ ] Schema/static tests for all registered tools.
- [ ] Orchestration/session tests.
- [ ] Live CATIA probes for every production-supported capability family.
- [ ] Agent task evaluations with hidden machine assertions.
- [ ] Full tool traces retained for capability regression analysis.
- [ ] Comparative evaluations for claims of incremental backend/CAA value.

## Support classification rule

Do not classify a capability as production-supported solely because a thin COM wrapper exists or a demonstration succeeds once. Support classification requires defined semantics, deterministic failure behavior, recovery boundaries, executable verification, and relevant validation evidence.
