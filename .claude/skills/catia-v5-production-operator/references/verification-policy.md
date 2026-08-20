# Verification Policy

Production CAD automation requires executable postconditions. Prefer evidence in this order:

1. CATIA update/rebuild state.
2. Structural evidence: expected feature, parameter, component, or constraint exists.
3. Numeric evidence: volume, bounding box, distance, parameter value, mass/COG where relevant.
4. Analytic cross-check when the geometry is simple enough and assumptions are valid.
5. View/screenshot evidence as a final visual check.

A screenshot must not replace measurable geometry assertions.

## Baseline snapshot

Before modifying an existing CATPart, capture applicable evidence:

- active document identity/type;
- feature list;
- volume/inertia;
- bounding box;
- parameters that may change.

Before precision work on a CATProduct, capture:

- active document identity/type;
- component list;
- constraint list;
- positional/DOF evidence when available.

The baseline is evidence. It is not a rollback guarantee.

## Material-effect checks

Record volume before and after each operation that is expected to add or remove solid material.

Classify:

- `PASS`: expected sign and magnitude within tolerance.
- `NO_EFFECT`: required material change is effectively zero.
- `WRONG_EFFECT`: wrong sign or implausible magnitude.
- `UPDATE_FAILED`: rebuild/update fails.
- `INCONCLUSIVE`: the active contract cannot establish the effect.

Do not map an inconclusive result to success.

## Tolerance selection

Use an explicit tolerance appropriate to the task. Do not use one fixed tolerance for all models.

Priority:

1. User or drawing tolerance, when provided.
2. Exact/simple analytic geometry: use a relative tolerance appropriate to CATIA/model precision plus a small absolute epsilon.
3. Complex geometry: verify sign, critical dimensions, and a defensible plausibility band; state when only partial numeric verification is possible.

For bounding boxes, compare each intended dimension independently in the tool's reported units.

## Analytic checks

Use formulas only when their assumptions are satisfied.

- Rectangular prism: `width * height * length`.
- Cylinder: `pi * r^2 * length`.
- Blind cylindrical hole: `pi * r^2 * depth` only when the full cylindrical cut lies in solid material.
- Through hole: use actual intersected material thickness, not arbitrary tool overtravel.
- Pattern: multiply seed effect by instance count only when instances do not overlap and pattern semantics are known.

Do not force an analytic formula onto unsupported geometry assumptions.

## Parameter propagation

After `catia_set_parameter`:

1. re-read the exact parameter;
2. verify requested value within parameter precision;
3. update;
4. re-measure affected geometry;
5. verify dependent features still have intended effect.

A parameter value alone does not prove dependency propagation.

## Structural checks

Use `catia_list_features` and assembly listings to confirm structure. Structural presence is necessary evidence, but it is not proof of correct geometry or exact target selection.

## Visual checks

When useful:

1. `catia_fit_all`;
2. set an informative standard view such as isometric;
3. capture a screenshot if requested or if visual evidence materially helps.

Do not claim exact screenshot pixel dimensions unless the active implementation enforces and verifies them.

## Completion evidence

Strong evidence combines update state, structure, and numeric assertions, for example:

- expected Pad exists; update succeeded; volume and bbox match the requested block within tolerance;
- parameter reread matches the new value; update succeeded; downstream geometry changed consistently.

Insufficient evidence includes only:

- a success string;
- feature-tree presence;
- a plausible screenshot.
