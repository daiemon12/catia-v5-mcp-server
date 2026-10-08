# Experimental CAA coordinate-point adapter

`catia_caa_demo_create_point` is a source-only contribution for one native
modeling capability: a parameterized coordinate point. It includes the Point
CAA implementation, required loading/communication sources, Python protocol,
MCP adapter, build helpers, tests and text evidence. No DLL, CATPart, official
SDK, or other CAA business implementation is shipped in Git or the source package.

## Layout and licensing

| Path | Contents |
| --- | --- |
| `caa/point_bridge/caa_workspace/CatiaPyBridgeFramework/` | Point sources and loading resources |
| `caa/point_bridge/caa_workspace/CatiaPyBridgeRuntime/code/dictionary/` | Source command registration |
| `caa/point_bridge/scripts/` | Local configuration, build, synchronization and launcher |
| `caa/point_bridge/validation/native-evidence.json` | Original source hashes and native gate summary; machine paths omitted |
| `catia_mcp/caa/` | Bundled Python file-bridge client; no second server/connection |
| `catia_mcp/caa_client.py`, `catia_mcp/tools/caa.py` | Typed MCP preflight and tool facade |
| `examples/caa_point/README.md` | Instructions to create a disposable sample |

The contributor authorized MIT publication of this Point implementation and
its necessary bridge sources. Scoped licenses retain CatiaPyBridge owner
attribution. Other private repository contents and vendor software are excluded.

## Build from source

Use a Git checkout on Windows with Python 3.10+, licensed CATIA V5 B30 CAA/RADE,
B30 mkmk and VS2017/MSVC 14.16. The original accepted build used mkmk
5.30.0.19283 and MSVC 14.16.27023 (win_b64). Install the required VS resource/MFC
headers and configure the matching vendor developer command environment and
RADE licenses. The official SDK supplies its own headers and libraries.

From the repository root, in PowerShell:

```powershell
python -m pip install -e ".[dev]"
# Set these to your actual installation and licensed settings directories:
$env:CATIA_B30_INSTALL = Read-Host 'B30 installation root'
$env:RADECATSettingPath = Read-Host 'RADE settings directory'
$env:CATIA_MCP_PYTHON = (Get-Command python).Source
python caa/point_bridge/scripts/configure_caa_b30.py --catia-install "$env:CATIA_B30_INSTALL"
caa/point_bridge/scripts/build_caa_b30.bat
```

The installer root contains `win_b64/code/bin/CATSTART.exe` and the CAA developer
commands. Configuration writes LF-only `Install_config_win_b64` and refuses to
overwrite a different local configuration. The wrapper runs `mkmk -a`, retains
its log, and only on success synchronizes the isolated runtime and creates
`runtime.json`. Failures have nonzero exit codes. Run the build from a Git
checkout because provenance records its branch, complete HEAD and dirty state.
A source archive carries the source files but is not itself a Git build baseline.

Generated outputs, all Git-ignored:

- `caa_workspace/win_b64/code/bin/`: built Addin and CmdModule DLLs.
- `caa_workspace/CatiaPyBridgeRuntime/`: both DLLs, generated productIC,
  resource copies and runtime manifest.
- `%TEMP%/CatiaPyBridge_mkmk_*.log`: build log; retain it with your validation record.

`runtime.json` records actual source directory, branch/HEAD/dirty, build command,
source hashes and six runtime hashes. Native source hashes must match the MCP
package's `native-source.json`. Update and validate both if the native source
changes. Rebuilt DLL hashes may differ; no fixed developer-build hash is required.
The instructions define a reproducible build procedure; bit-identical output
across different toolchains is not claimed. The relocated wrappers have not been
executed against B30 in this contribution preparation. This preparation did not
recompile CAA; the previous native acceptance is separate evidence.

## Start and configure

After a successful local build:

```powershell
caa/point_bridge/scripts/start_catia_bridge_b30.bat --prepare-only
caa/point_bridge/scripts/start_catia_bridge_b30.bat
$env:CATIA_MCP_CAA_RUNTIME = (Resolve-Path 'caa/point_bridge/caa_workspace/CatiaPyBridgeRuntime').Path
python -m catia_mcp
```

Use one CNEXT instance. The launcher verifies the locally generated manifest
before writing CATEnv or starting CATIA; it does not build or silently switch
runtimes. For a desktop MCP client, pass the same absolute runtime directory in
its `env.CATIA_MCP_CAA_RUNTIME` and use your installed Python executable with
`args: ["-m", "catia_mcp"]`. No private external Python SDK is needed.

Before a call, the adapter verifies source identity, runtime file hashes and
actual loaded DLL paths. The command DLL may load during the first read-only
preview; writes require both DLLs already verified. Hashes check agreement with
a trusted local build and are not a digital signature.

## Call and result contract

Create a disposable model using [the sample instructions](../examples/caa_point/README.md).
Provide exact `catia_process_id`, active saved local `part_document_path`,
unique ordinary public root `geometrical_set_name`, unique `point_name`, and
finite `x_mm/y_mm/z_mm` in Part absolute millimeters.

First call with `dry_run=true` (default). Review the returned plan, then submit
the same plan with `dry_run=false`, `confirm_action=true`, `plan_hash`,
`state_fingerprint`, and `confirmed_preview_token`. Tokens expire after 300
seconds and may be used once. Creation adds three coordinate length parameters
and one point, performs Update and native coordinate/name/membership readback.
The tool never opens, saves, overwrites, deletes or closes a document.

The CAA result uses `ok`, `code`, `operation_id`, `tool`, `message`, `data`,
`effects`, `diagnostics`, `warnings`, and `recovery`. `ok` controls MCP `isError`;
JSON text and `structuredContent` are identical. The operation ID is the native
file request/response ID. Native error code, stage and partial modification
remain in diagnostics/data. `effects.modified=null` means unknown, not false.
Recovery states explicitly that automatic rollback/retry is unsupported.
No aliases for the former outer `success/error_code` envelope are provided.
Existing upstream COM tools retain their text success results in this draft;
server-boundary errors use the structured envelope.

All COM calls and cleanup use one STA worker. CAA receives the shared attached
COM object and never auto-launches CATIA. Timeout, unreadable response or
cancellation causes `SESSION_STATE_UNKNOWN` and blocks subsequent operations.
Do not retry a write. Inspect CATIA and `%TEMP%/CatiaPyBridge` before restarting
MCP. Restarting does not discard a pending request or authorize replay. A blocked
COM call must finish before worker shutdown can complete.

## Draft status against the maintainer contract

| Contract | Current state |
| --- | --- |
| Current v0.2.2 tool surface, typed JSON adapter, shared serialized STA | Implemented; offline checks cover dispatch/thread behavior |
| Structured CAA outcome, operation ID, native failure preservation | Implemented; offline checks cover protocol and partial/unknown mutation |
| Native Point algorithm | Original B30 build and 23 live gates passed; source hashes preserved |
| New MCP/connection path and relocated build scripts | Relevant live B30 validation pending |
| Object-handle identity / model generation | Not implemented; explicit PID/path/unique name and native plan fingerprint are used |
| Journal / automatic rollback / modal-dialog guard | Not implemented; manual inspection/recovery boundary is explicit |
| Other COM tools' full production result contract | Outside this Point draft |

This is an experimental integration for early review, not a production-support
claim. The original native/package-MCP evidence is summarized in
`native-evidence.json`; original machine-specific reports/binaries remain in the
private Clean reference package and are not build dependencies.

Limits: B30, one CNEXT, 128 root bodies, 256 direct members, +/-1,000,000 mm.
Name/type state fingerprints cannot detect same-name/same-type member replacement.
Native Update fault injection was not performed. No other CAA business is added.

```powershell
python test_server.py
python -m pytest tests -q
```
