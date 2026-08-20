# Production Architecture Contract

## Runtime layers

```text
MCP transport / asynchronous request handling
        |
        v
Typed tool facade + schema validation
        |
        v
Operation orchestrator + recovery journal
        |
        v
Dedicated CATIA STA worker queue
        |
        +--> Automation adapter (COM)
        |
        +--> optional CAA bridge adapter
        |
        v
CATIA V5 session
```

Cross-cutting services:

- session-health manager;
- object-handle registry;
- topology generation/token registry;
- update/diagnostic collector;
- measurement/effect verifier;
- modal-dialog guard;
- structured operation tracing.

## STA worker ownership

Use one owned STA worker per CATIA session unless a different model is explicitly validated.

The worker:

- initializes/uninitializes COM on its own thread;
- owns and resolves apartment-bound COM references;
- executes queued CATIA operations serially;
- updates session health after COM exceptions/timeouts;
- rejects unsafe mutations when session health is not `healthy`.

MCP request handlers must not keep or call raw shared COM objects directly.

## Session health state machine

Recommended states:

- `disconnected`: no active CATIA connection;
- `healthy`: state known, mutations allowed;
- `blocked`: known modal/blocked condition;
- `unknown`: completion/model state cannot be established.

Transitions must be explicit. A timeout with indeterminate COM completion moves the session away from `healthy`. Mutation resumes only after a health probe and model-context verification establish a known state.

## Operation identity

Every mutation/query should carry an `operation_id`. Multi-step logical intent may also carry an `operation_group_id`.

Use operation identity for:

- structured logs;
- correlation across worker/adapter layers;
- recovery journal entries;
- diagnostics and test traces.

## Object handles

Expose opaque handles rather than leaking COM objects or relying on display paths.

Registry entries should include:

- handle;
- object class/kind;
- owning document/session;
- resolver data;
- creation/validity generation where needed.

Document close/reload/session reset invalidates affected handles deterministically.

## Topology registry

Topology tokens are opaque server references. Store separately:

- token;
- entity kind;
- owning document/body;
- topology generation;
- geometric descriptors;
- exact resolver data.

Any shape change invalidates prior generation. Token resolution validates document/body/generation before any CATIA feature call.

## Mutation verification pipeline

A material mutation should follow:

1. validate arguments and target references;
2. capture baseline update/measurement state;
3. execute mutation on STA worker;
4. update CATIA;
5. collect diagnostics;
6. measure post-state;
7. classify material/geometric effect;
8. update handle/topology generations;
9. write journal/recovery metadata;
10. return structured result.

## Recovery journal

The journal records reversible server-supported operations. It is not a database transaction layer and must not claim CATIA-native atomic behavior.

Recommended entries:

- operation identity;
- owning document;
- mutation kind;
- created object handles;
- old/new parameter values;
- generation before/after;
- recovery action;
- baseline measurements used to verify restoration.

## Dialog guard

The dialog guard should:

- detect CATIA modal windows relevant to an operation;
- collect title/text/button metadata safely;
- classify session impact;
- auto-close only explicitly allowlisted non-destructive dialogs;
- return diagnostics to the caller.

## CAA bridge boundary

Keep CAA behind a stable Automation/JSON adapter. Do not pass native CAA objects through Python/MCP.

The bridge should provide only deterministic domain functions such as:

- feature report and locale-independent feature type;
- native update diagnostics;
- face/edge enumeration with descriptors;
- exact topology reference resolution;
- advanced Part Design operations that Automation cannot express reliably.

Bridge failures must preserve failure semantics across the adapter boundary.
