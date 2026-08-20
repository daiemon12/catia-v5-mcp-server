# Topology and Assembly Safety

## Topology lifecycle

A production topology token is an MCP/server-layer reference abstraction, not a persistent native CATIA identifier. Treat the token itself as opaque.

A valid topology contract should return, at minimum:

- token;
- entity kind (`face` or `edge`);
- geometric descriptors needed for selection;
- document/session identity;
- topology generation or equivalent version metadata.

After a shape-changing operation, previously issued topology references are stale unless the server explicitly proves otherwise. Shape-changing operations include pad, pocket, hole, pattern, mirror, shell, fillet, chamfer, draft, thickness, boolean operations, and parameter updates that alter the body.

The server must reject stale references before mutation. A stale token must not be rebound by index to another face/edge.

## Baseline edge limitation

The baseline repository can enumerate edge-like names/indices, but the exact edge target is not reliably consumed by baseline fillet/chamfer execution.

Therefore:

- do not treat `catia_list_edges` output as a durable edge token;
- do not claim a named edge was filleted/chamfered unless the active server exposes an exact resolver and the feature tool consumes it;
- classify exact-edge intent as `UNSUPPORTED_CAPABILITY` under the baseline contract.

## Baseline face limitation

The baseline contract does not provide a production-safe `list_faces` plus exact BRep face resolver. Face-name lookup in shell/draft/thickness paths is not sufficient evidence of exact target selection.

Therefore, exact face-removal/draft/thickness intent is unsupported under the baseline contract.

## Required exact-topology contract

For exact topology operations, require:

1. face/edge enumeration with geometric descriptors;
2. opaque tokens with generation metadata;
3. deterministic resolver on the CATIA/CAA side;
4. stale-token rejection before feature creation;
5. exact ResourceSur/ResourceEdge-equivalent reference consumption;
6. update plus geometry-effect verification.

## Assembly geometry references

Precision assembly mating requires component-local geometry references. A production constraint contract should include:

- component identity/handle;
- component-local face/plane/axis reference;
- exact constraint type and value/units;
- solve/update result;
- constraint status;
- remaining DOF or equivalent positional validation when available.

The baseline coincidence/offset/angle paths do not establish that the advertised element references are resolved to exact geometry. Do not claim exact face-to-face/plane-to-plane/axis mating under that baseline.

Safe baseline assembly actions are limited to actions whose results can be verified independently, such as component listing, component insertion, constraint listing, coarse move/rotation, and fix constraint when sufficient for the task.
