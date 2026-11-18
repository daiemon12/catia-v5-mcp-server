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

The contributed Point and bridge sources are licensed under MIT by rancy777.
The native parser uses the separately supplied MIT-licensed nlohmann/json header.

## Build from source

Use a Git checkout on Windows with Python 3.10+, licensed CATIA V5 B30 CAA/RADE,
B30 mkmk and VS2017/MSVC 14.16. The contributor-reported historical build used mkmk
5.30.0.19283 and MSVC 14.16.27023 (win_b64). Install the required VS resource/MFC
headers and configure the matching vendor developer command environment and
RADE licenses. The official SDK supplies its own headers and libraries.

Download the official [v3.11.3 single header](https://github.com/nlohmann/json/releases/tag/v3.11.3)
as `json.hpp`. The release SHA-256 is checked during configuration and runtime
manifest generation. From the repository root in the VS2017 x64 developer
environment, run the following in PowerShell:

```powershell
python -m pip install -e ".[dev]"
# Set these to your actual installation and licensed settings directories:
$env:CATIA_B30_INSTALL = Read-Host 'B30 installation root'
$env:RADECATSettingPath = Read-Host 'RADE settings directory'
$env:CATIA_MCP_PYTHON = (Get-Command python).Source
$jsonHeader = Read-Host 'Absolute path to the v3.11.3 json.hpp'
python caa/point_bridge/scripts/configure_caa_b30.py --catia-install "$env:CATIA_B30_INSTALL" --json-header "$jsonHeader"
caa/point_bridge/scripts/build_caa_b30.bat
```

The installer root contains `win_b64/code/bin/CATSTART.exe` and the CAA developer
commands. Configuration writes LF-only `Install_config_win_b64`, installs the
header locally in the command module and refuses to overwrite differing files. The wrapper runs `mkmk -a`, retains
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
source hashes, build wrapper and JSON dependency hashes, and six runtime hashes. Native source hashes must match the MCP
package's `native-source.json`. Update and validate both if the native source
changes. Rebuilt DLL hashes may differ; no fixed developer-build hash is required.
Regenerate the proprietary `CATIAV5Level.lvl` locally using your matching RADE
workspace setup; it is deliberately absent from this source contribution.
The configure/build/sync/start workflow still needs an exact-branch B30 run.

## Start and configure

After a local build of the current sources, identify your normal CATEnv (UTF-8 text).
The earlier Point DLL used a different bridge protocol. Keep its runtime manifest
with the historical validation record.

```powershell
$baseEnv = Read-Host 'Absolute path to your normal CATEnv file'
caa/point_bridge/scripts/start_catia_bridge_b30.bat --base-env "$baseEnv" --prepare-only
# Launch only after you have preserved and closed any existing CATIA yourself:
caa/point_bridge/scripts/start_catia_bridge_b30.bat --base-env "$baseEnv"
$env:CATIA_MCP_CAA_RUNTIME = (Resolve-Path 'caa/point_bridge/caa_workspace/CatiaPyBridgeRuntime').Path
python -m catia_mcp
```

Use one CNEXT instance. The launcher verifies the local manifest and requires
an explicit base CATEnv; it preserves the original settings/licensing entries
and appends the bridge resource paths and `CATIA_MCP_CAA_BRIDGE_ROOT` to a
generated local copy. The server checks that CNEXT's value points to the
configured runtime's `jobs` directory before sending a request. It refuses to
launch while CNEXT is running or to overwrite a different generated CATEnv. It
does not build, choose a default settings directory or modify the original file. For a desktop MCP client, pass the same absolute runtime directory in
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
seconds and may be used once. This two-step gate can be completed by the same
agent. In server `--read-only` mode the Point tool is unavailable, including preview.
Creation adds three coordinate length parameters
and one point, performs Update and native coordinate/name/membership readback.
The tool never opens, saves, overwrites, deletes or closes a document.

The CAA result uses `ok`, `code`, `operation_id`, `tool`, `message`, `data`,
`effects`, `diagnostics`, `warnings`, and `recovery`. `ok` controls MCP `isError`;
JSON text and `structuredContent` are identical. The operation ID is the native
file request/response ID. Native error code, stage and partial modification
remain in diagnostics/data. `effects.modified=null` means unknown, not false.
Recovery states explicitly that automatic rollback/retry is unsupported.
Existing upstream COM tools retain their text success results in this draft;
server-boundary errors use the structured envelope.

All COM calls and cleanup use one STA worker. CAA receives the shared attached
COM object and never auto-launches CATIA. Ordinary errors and client cancellation
do not lock the other tools. Cancellation does not stop a running COM call;
later calls remain serialized behind it. A blocked COM call must finish before
worker shutdown can complete.

A Point job without a correlated response blocks only the Point bridge's next
request. Inspect CATIA and `<runtime>/jobs/pending/current_job.json`, then use its
job ID to find the request, response and bridge logs under `jobs`. A correlated
response allows the next call to finish archiving. If the response is absent
or invalid, inspect the model for partial changes. Stop the MCP server and exit
the affected CATIA instance after handling the document, then move the descriptor
out of `pending` for investigation. Restart with the derived CATEnv and use a
fresh preview only after resolving the previous operation. Pre-delivery refusals
and failed previews report `effects.modified=false`. A delivered write with
unknown effects reports `null`.

## Local launch environment

Prefer attaching to the user's existing instance. When a test requires an
explicit launch, identify the user's normal CATSTART shortcut or script, its
`-env` and `-direnv`, CATEnv, settings paths and licensing configuration first.
Derive a local bridge environment from that configuration and add the
required resource paths and shared bridge root. Do not silently substitute a demo settings directory,
overwrite the user's environment or settings, or commit local licensing files.
If the normal environment cannot be identified, ask for its launch entry point.
A window caption alone does not establish the active licence configuration.

## Draft status against the maintainer contract

| Contract | Current state |
| --- | --- |
| Upstream tool surface, typed JSON adapter, shared serialized STA and read-only mode | Offline checks cover dispatch, threading and Point refusal in read-only mode |
| Structured CAA outcome, operation ID, native failure preservation | Implemented; offline checks cover protocol and partial/unknown mutation |
| Native Point algorithm | Contributor-reported historical B30 build/23 gates; source hashes retained, not automated acceptance of this branch |
| Earlier MCP/connection and launch checks | Seven historical live integration checks reused the earlier DLLs and verified the user's CATSettings and loaded module paths |
| Current configure/build/sync/start | Exact proposed commit and live B30 build log pending |
| Native Unicode paths, structural JSON parsing, shared bridge root | Implemented in the source revision; live B30 validation pending |
| Object-handle identity / model generation | Not implemented; explicit PID/path/unique name and native plan fingerprint are used |
| Journal / automatic rollback / modal-dialog guard | Not implemented; manual inspection/recovery boundary is explicit |
| Other COM tools' full production result contract | Outside this Point draft |

This is an experimental integration for early review, not a production-support
claim. The contributor-reported historical native/package-MCP evidence is summarized in
`native-evidence.json`; original machine-specific reports/binaries remain in the
private Clean reference package and are not build dependencies.

Limits: B30, one CNEXT, 128 root bodies, 256 direct members, +/-1,000,000 mm.
Name/type state fingerprints cannot detect same-name/same-type member replacement.
Live B30 validation should cover an ordinary public Geometrical Set, rejection of
private and ordered sets, a Unicode bridge directory, and names matching JSON keys.
The exact B30 return contract for `CATIGSMTool::IsPrivate` and native Update
fault injection still need verification.

```powershell
python -m pytest tests test_server.py -q
```
