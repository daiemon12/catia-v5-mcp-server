# Baseline Capability Matrix

This file defines the baseline operating classification for the repository implementation represented by this skill. It is a server-contract classification, not a statement about CATIA V5 product capability.

If the active server provides a newer explicit capability contract, reclassify only with implementation and validation evidence. Do not promote a capability from schema presence alone.

## Status identifiers

- `SUPPORTED_WITH_VERIFICATION`: usable when normal preconditions hold and required postconditions are checked.
- `CONDITIONAL`: usable only within the stated scope or with stronger verification.
- `UNSUPPORTED_EXACT`: the baseline implementation cannot reliably express or verify the advertised exact intent.

## Session and document

| Tool | Status | Contract |
|---|---|---|
| `catia_connect` | `SUPPORTED_WITH_VERIFICATION` | Establish connection state before work when state is unknown. |
| `catia_disconnect` | `CONDITIONAL` | Use only when ending or resetting a session intentionally. |
| `catia_new_part` | `SUPPORTED_WITH_VERIFICATION` | Verify resulting active document type. |
| `catia_new_product` | `SUPPORTED_WITH_VERIFICATION` | Verify resulting active document type. |
| `catia_open_document` | `SUPPORTED_WITH_VERIFICATION` | Use an explicit path and verify active document/type. |
| `catia_save_document` | `CONDITIONAL` | Persistent side effect; use only when required. |
| `catia_close_document` | `CONDITIONAL` | May discard unsaved work; use only when required. |
| `catia_list_documents` | `SUPPORTED_WITH_VERIFICATION` | Context inspection. |
| `catia_get_active_document_info` | `SUPPORTED_WITH_VERIFICATION` | Required context probe for existing-model mutation. |

## Sketcher

| Tool | Status | Contract |
|---|---|---|
| `catia_create_sketch` | `CONDITIONAL` | Baseline support is limited to origin XY/YZ/ZX planes. |
| `catia_close_sketch` | `SUPPORTED_WITH_VERIFICATION` | Close before Part Design consumption. |
| `catia_sketch_line` | `SUPPORTED_WITH_VERIFICATION` | Re-query geometry before index-based constraints. |
| `catia_sketch_rectangle` | `SUPPORTED_WITH_VERIFICATION` | Verify the resulting 3D dimensions rather than relying on sketch creation text. |
| `catia_sketch_centered_rectangle` | `SUPPORTED_WITH_VERIFICATION` | Same requirement as rectangle. |
| `catia_sketch_circle` | `SUPPORTED_WITH_VERIFICATION` | Require positive radius and verify downstream geometry. |
| `catia_sketch_arc` | `CONDITIONAL` | Verify orientation when it matters. |
| `catia_sketch_spline` | `CONDITIONAL` | Verify closure semantics if used for a closed profile. |
| `catia_sketch_point` | `SUPPORTED_WITH_VERIFICATION` | Valid only where the consuming feature supports it. |
| `catia_sketch_constraint` | `CONDITIONAL` | Geometry indices are ephemeral; refresh immediately before use. |
| `catia_sketch_get_geometry` | `SUPPORTED_WITH_VERIFICATION` | Treat returned indices as current-observation data. |

## Part Design

| Tool | Status | Contract |
|---|---|---|
| `catia_pad` | `SUPPORTED_WITH_VERIFICATION` | Verify update, feature, volume increase, and relevant bbox. |
| `catia_pocket` | `CONDITIONAL` | Verify non-zero volume decrease; direction/support can produce a no-effect result. |
| `catia_shaft` | `CONDITIONAL` | Requires valid revolution-axis semantics; verify volume and bbox. |
| `catia_groove` | `CONDITIONAL` | Verify non-zero volume decrease and intended revolution result. |
| `catia_hole` | `CONDITIONAL` for simple holes; `UNSUPPORTED_EXACT` for advertised specialized hole types in baseline | Baseline implementation does not implement all advertised `type` semantics. Never downgrade specialized intent silently. |
| `catia_rect_pattern` | `CONDITIONAL` | Direction/reference semantics are implicit in baseline; verify instance/material effect. |
| `catia_circ_pattern` | `CONDITIONAL` | Axis semantics are implicit in baseline; verify quantitatively. |
| `catia_mirror` | `UNSUPPORTED_EXACT` for feature-specific intent | Baseline implementation does not establish deterministic feature-specific mirroring. |
| `catia_fillet` | `UNSUPPORTED_EXACT` for edge-specific intent | Baseline `edge_name` is not a verified exact BRep target contract. |
| `catia_chamfer` | `UNSUPPORTED_EXACT` for edge-specific intent | Same exact-target limitation as fillet. |
| `catia_shell` | `UNSUPPORTED_EXACT` for requested face removal | Baseline face-name lookup is not a reliable BRep face resolver. |
| `catia_draft` | `UNSUPPORTED_EXACT` for requested face | Baseline advertised face selection is not a verified exact-target contract. |
| `catia_thickness` | `UNSUPPORTED_EXACT` for requested face | Same exact-target limitation. |
| `catia_list_features` | `SUPPORTED_WITH_VERIFICATION` | Structural evidence only; not proof of geometric effect. |
| `catia_list_edges` | `CONDITIONAL` | Returned names/indices are not durable topology identifiers. |

## Measurement and parameters

| Tool | Status | Contract |
|---|---|---|
| `catia_measure_distance` | `CONDITIONAL` | Display-name lookup may be ambiguous or localized. |
| `catia_get_inertia` | `SUPPORTED_WITH_VERIFICATION` | Strong evidence for volume/area/COG where available. |
| `catia_get_bounding_box` | `CONDITIONAL` | Missing/partial ByRef output is a failure, not zero geometry. |
| `catia_get_parameters` | `SUPPORTED_WITH_VERIFICATION` | Filter to reduce ambiguity. |
| `catia_set_parameter` | `CONDITIONAL` | Record the old value externally; baseline server has no verified journal recovery. |
| `catia_update_part` | `SUPPORTED_WITH_VERIFICATION` | Necessary but not sufficient for design correctness. |

## Assembly

| Tool | Status | Contract |
|---|---|---|
| `catia_add_component` | `CONDITIONAL` | Verify component listing after insertion. |
| `catia_add_new_part` | `CONDITIONAL` | Verify component listing. |
| `catia_fix_constraint` | `CONDITIONAL` | Verify constraint listing/status. |
| `catia_coincidence_constraint` | `UNSUPPORTED_EXACT` for geometry-specific mating | Baseline does not establish deterministic `element1`/`element2` geometry resolution. |
| `catia_offset_constraint` | `UNSUPPORTED_EXACT` for geometry-specific mating | Requires exact component-local reference resolution. |
| `catia_angle_constraint` | `UNSUPPORTED_EXACT` for geometry-specific mating | Requires exact component-local reference resolution. |
| `catia_move_component` | `CONDITIONAL` | Use for coarse positioning only; verify position. |
| `catia_list_components` | `SUPPORTED_WITH_VERIFICATION` | Structural/position evidence. |
| `catia_list_constraints` | `CONDITIONAL` | Status evidence does not prove intended geometric references were used. |

## View and export

| Tool | Status | Contract |
|---|---|---|
| `catia_export` | `SUPPORTED_WITH_VERIFICATION` | Verify returned path/format and file existence where available. |
| `catia_screenshot` | `CONDITIONAL` | Baseline width/height inputs are not an enforced pixel-size contract. |
| `catia_set_view` | `CONDITIONAL` | Useful for standard review views; verify only what the tool actually controls. |
| `catia_fit_all` | `SUPPORTED_WITH_VERIFICATION` | Use before final visual evidence. |

## Baseline missing primitives

Do not emulate these in prompt logic when the active server lacks them:

- dedicated serialized STA worker and explicit session-health state;
- structured success/error result envelope;
- stable session object handles;
- topology generation plus stale-token rejection;
- reliable face enumeration and exact BRep face references;
- exact edge references consumed by edge-specific features;
- journal-based recovery for feature/parameter mutations;
- modal-dialog guard;
- native update diagnostics and locale-independent feature typing;
- sketch-on-reference and offset-plane support;
- per-operation `volume_delta_mm3` and `FEATURE_NO_EFFECT` classification.
