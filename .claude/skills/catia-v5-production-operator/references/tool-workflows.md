# Tool Workflows

These are execution templates. The capability matrix and verification policy remain authoritative.

## New rectangular block

1. `catia_connect` when needed.
2. `catia_new_part`.
3. Verify active CATPart.
4. `catia_create_sketch(plane="xy")`.
5. Create the requested rectangle.
6. `catia_close_sketch`.
7. `catia_pad(height=...)`.
8. `catia_update_part`.
9. Verify feature structure.
10. Measure volume and bounding box.
11. Compare with requested dimensions and `width * height * pad_length` when assumptions are exact.

## New cylinder

1. Create and verify CATPart.
2. XY sketch.
3. Circle with requested radius.
4. Close sketch.
5. Pad requested length.
6. Update.
7. Verify feature, volume, and bbox.
8. Cross-check `pi * r^2 * length` for a pure cylinder.

## Simple pocket

Use only when sketch support and direction can be expressed by the active contract.

1. Capture pre-cut volume.
2. Create and close the supported sketch/profile.
3. `catia_pocket`.
4. Update.
5. Verify Pocket structure.
6. Measure post-cut volume.
7. Require a non-zero volume decrease consistent with the intended cut.

If the support/direction cannot be expressed deterministically, classify the requested cut as unsupported rather than creating a speculative Pocket.

## Parameter modification

1. Verify active CATPart.
2. Discover exact parameter.
3. Record old value and relevant measurements.
4. Set new value once.
5. Update.
6. Re-read parameter.
7. Re-measure propagated geometry.
8. Revert deterministically if the change fails and prior value is known.

## Read-only model audit

1. Establish document context.
2. List features/components as applicable.
3. Read relevant parameters.
4. Measure inertia/volume and bbox where available.
5. Use standard views/screenshots only as supporting evidence.
6. Report discrepancies without mutation or save calls.

## Save/export

Perform persistence only after model verification:

1. final update;
2. final numeric/structural checks;
3. optional fit/view/screenshot;
4. save only if required;
5. export only if required;
6. report only actual produced paths.

## Exact topology request

For requests such as exact four-edge fillet, exact top-face shell opening, or exact assembly face mating:

1. check the active topology/reference contract;
2. require deterministic reference resolution and stale-reference behavior;
3. if absent, return `UNSUPPORTED_CAPABILITY`;
4. if present, enumerate/select using fresh tokens, perform one mutation, update, and verify exact-target effect.
