# Point-only CAA source contribution

This directory contributes only `catia_caa_demo_create_point` and the native
loading/RunOnce communication required to run it. `CatiaPyBridgeCore.cpp` routes
only that method; no other CAA business implementation is included.

| Directory | Contents |
| --- | --- |
| `caa_workspace/CatiaPyBridgeFramework/` | Point algorithm, coordinate parameters, command and file-bridge sources |
| `caa_workspace/CatiaPyBridgeRuntime/code/dictionary/` | Source command registration |
| `scripts/` | Explicit local configuration, build, runtime synchronization and launch |
| `validation/native-evidence.json` | Contributor-reported historical validation and source hashes |

No DLL, CATPart, vendor SDK, vendor `CATIAV5Level.lvl`, local CATEnv or licence
configuration is committed. Generate proprietary workspace files locally using
the installed matching RADE tools. The bundled Python protocol is under
`catia_mcp/caa/`; a disposable sample can be created using `examples/caa_point/`.

Contributor rancy777 authorized MIT publication of this Point implementation
and its necessary bridge sources; see [LICENSE](LICENSE). These sources were
extracted from the contributor's private Clean package. Its historical build
record identifies commit `214c4d90b2b3dad91317090aede42e9f8a09aa3d` with dirty
changes, not a reproducible clean commit or this contribution branch. No rights
to vendor software or other private CAA business code are conveyed.

See [adapter instructions and draft limitations](../../docs/caa-point.md).
The historical B30 checks reused the original DLLs. The current source uses
wide Windows file paths, a shared job directory and structural JSON parsing.
The exact-branch B30 build and live checks are pending.
