# Failure and Recovery Policy

The baseline server may return ordinary text for both success and failure. The operator must classify failures from all available evidence rather than relying on transport completion.

## Failure conditions

Stop the current mutation chain when any of the following occurs:

- structured `ok=false` or a typed error code;
- COM/tool exception or explicit failure text;
- `catia_update_part` failure;
- expected feature/parameter/component data is missing;
- required material delta is zero or wrong-sign;
- parameter reread differs from requested value;
- bounding box or measurement contradicts the intended model;
- exact face/edge/component reference cannot be verified;
- timeout or modal state makes call completion indeterminate.

## Recovery rules

### Reversible parameter edit

If the prior value is known:

1. restore the old value;
2. update;
3. re-read the parameter;
4. re-measure affected geometry;
5. continue only if the prior verified state is re-established.

### Wrong/no-effect feature

When no verified feature-delete or journal recovery is available:

- do not add further speculative features on top of the suspect state;
- allow a deterministic correction only when it edits the same reversible input and the expected state is clear;
- otherwise stop or rebuild in a clean document only when that preserves the task and does not create an unrequested persistence side effect.

### Ambiguous topology

Re-query topology. If the exact target cannot be represented by the active contract, return `UNSUPPORTED_CAPABILITY`. Do not guess `Edge.N`, `Face.N`, or a selection index.

### COM timeout/session uncertainty

A timeout does not prove the underlying COM call was cancelled. Therefore:

1. stop mutations;
2. mark the session `blocked` or `unknown` conceptually if the server does not already do so;
3. inspect connection/document state after control returns;
4. re-establish the last verified model state;
5. never replay the timed-out mutation blindly.

### Modal dialog

If CATIA is blocked by a modal dialog and the server has no verified dialog guard, stop mutations until session health is restored. Do not repeatedly issue COM calls into a blocked session.

## Retry budget

Default to one targeted mutation retry per failed step when the cause is known and the correction is reversible. A larger retry budget requires a verified rollback/checkpoint mechanism that re-establishes state after every attempt.

## Recovery reporting

When recovery is incomplete, report:

- last verified state;
- failed operation;
- evidence of failure;
- whether partial mutation may remain;
- why safe recovery cannot be established with the active server contract.
