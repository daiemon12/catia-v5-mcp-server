# Deployment Notes — Live CATIA Connection

This documents the actual working deployment against a real CATIA V5 install, and —
more importantly — **the constraints that ruled out the obvious alternatives**, so a
future session doesn't re-spend time rediscovering them. Written to be read without
the conversation that produced it.

## Topology

- **CATIA host:** `192.168.5.42` as of 2026-07-13 (moved from `192.168.5.10`, the
  original address this doc was written against — update any saved `claude mcp`
  HTTP config, firewall rules, and SMB commands below if you're working from an
  older client setup). Reached over a site-to-site VPN (client machine has
  no direct route to the `192.168.5.x` subnet; traffic goes out a specific local
  interface — see "Firewall" below for why that IP matters).
- **CATIA runs interactively** inside a logged-in Windows session on that host
  (observed as `session 8`, user `CORP\sup02`), reached via RDP by whoever operates
  it. It is **not** a service — someone has to be logged in with CATIA open.
- **The MCP server runs inside that same interactive session**, non-elevated, as a
  foreground `python -m catia_mcp --http ...` process. It listens on
  `192.168.5.42:8000`.
- **The client (Claude Code, or any MCP HTTP client) connects over the VPN** to that
  address with a bearer token.
- Server source lives on the box at `C:\Users\sup02\catia-v5-mcp-server\catia_mcp`
  (pushed via SMB admin share, not git — the box has **no internet access**, see
  below). **Corrected 2026-07-13**: earlier revisions of this doc said
  `C:\catia-mcp-setup\catia_mcp` — that path doesn't exist on the `.42` host.
  Confirmed authoritatively by asking the actually-running server process's own
  interpreter where it imports `catia_mcp` from
  (`python.exe -c "import catia_mcp, os; print(os.path.dirname(catia_mcp.__file__))"`);
  don't trust a remembered/documented path over that check if the two ever disagree
  again, e.g. after another host move.
- Python 3.11 is installed at
  `C:\Users\sup02\AppData\Local\Programs\Python\Python311\` on the box (**corrected
  2026-07-13** — earlier revisions said `C:\Python311`, which doesn't exist on
  `.42`; confirmed via `Get-CimInstance Win32_Process` on the listening PID's
  `ExecutablePath`). The box has no other real Python — `python`/`python3` on PATH
  by default resolve to the Microsoft Store alias stub, which prints a bare
  `Python` with no version and does nothing useful; don't waste time debugging
  that, just use the full interpreter path explicitly.

## Why HTTP transport, not the "obvious" alternatives

Three approaches were tried before landing on HTTP. Each failure is a real
architectural constraint, not a configuration bug — don't re-attempt these without
understanding why they failed:

1. **stdio over SSH** (`claude mcp add catia-v5 -- ssh user@host python -m catia_mcp`).
   SSH lands the process in a **new logon session**. CATIA's COM `GetActiveObject`
   only sees instances registered in the Running Object Table of the *same* Windows
   logon session. An SSH-launched process — even authenticating as the exact user
   running CATIA — cannot see that CATIA instance. Confirmed empirically: the same
   Python code that successfully attaches to CATIA from a non-elevated shell *in that
   session* fails with `MK_E_UNAVAILABLE` (`-2147221021`) from any other session,
   **including an elevated PowerShell in the same RDP login** — elevation itself
   creates a separate integrity-level ROT scope. Verified fix: attach only works from
   a plain, non-elevated shell at the same integrity level as CATIA.

2. **DCOM remote activation** (`win32com.client.DispatchEx(progid, machine=host)`).
   This can *launch* a new CATIA instance remotely, but (a) it cannot attach to an
   *already-running* interactive instance — same session-isolation reason as above —
   and (b) DCOM-activated processes run in a non-interactive session with no window
   station, so launching CATIA this way fails outright (`Server execution failed`,
   `0x80080005`) even before the session-isolation problem would bite. Not viable for
   this use case. (`connection.py` still carries `CATIA_HOST`/`CATIA_CLSID`/impersonation
   scaffolding from this attempt — inert unless `CATIA_HOST` is set, harmless to keep
   or remove.)

3. **stdio launched directly by Claude Code, server and client on the same
   machine.** This is the *normal*, simplest way MCP servers run — and would have
   worked, if Claude Code and CATIA were on the same machine. They're not: CATIA is on
   a VPN-reachable Windows workstation, Claude Code runs elsewhere. Hence HTTP.

**HTTP over the VPN sidesteps all of this**: the server process itself runs inside
CATIA's own interactive, non-elevated session (satisfying the ROT constraint), and the
client reaches it over a normal network socket, which isn't session-bound at all.

## Checking connectivity to the current host (192.168.5.42)

Two checks, cheapest first — run from the client machine, over the VPN:

1. **TCP reachability** (confirms the VPN route and that something's listening on
   the port — doesn't confirm it's actually the MCP server or that auth works):
   ```powershell
   Test-NetConnection -ComputerName 192.168.5.42 -Port 8000
   ```
   `TcpTestSucceeded : True` means the route and port are good. `False` means either
   the VPN route is down, the firewall rule (see "Security posture" below) doesn't
   allow this client's IP, or the server process isn't running in the CATIA
   operator's session.

2. **MCP endpoint + auth check** (confirms the actual server is answering and the
   bearer token is correct — a real `initialize` call, not just a port probe):
   ```powershell
   $env:CATIA_MCP_TOKEN = "<the token>"
   $body = @'
   {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"conn-check","version":"0"}}}
   '@
   curl.exe -i http://192.168.5.42:8000/mcp/ `
     -H "Authorization: Bearer $env:CATIA_MCP_TOKEN" `
     -H "Content-Type: application/json" `
     -H "Accept: application/json, text/event-stream" `
     -d $body
   ```
   A `200`/`202` with a JSON-RPC `result` body means the server is up, reachable,
   and the token matches. `401` means the token is wrong or missing on the server
   side; connection refused/timeout means step 1's problem, not this one.

## Running the server

In a **non-elevated** PowerShell inside the CATIA operator's session (this matters —
see above):

```powershell
$env:CATIA_MCP_TOKEN = "<token — ask the user, not stored in this repo>"
cd C:\Users\sup02\catia-v5-mcp-server
C:\Users\sup02\AppData\Local\Programs\Python\Python311\python.exe -m catia_mcp --http --host 192.168.5.42 --port 8000 --allowed-host 192.168.5.42:8000
```

This blocks in the foreground; that's correct, it's the server. Leave the window open.
Logging off that Windows session kills both the server and CATIA.

**To restart after a code update:** prefer the WinRM helper below. Manual fallback is
still `Ctrl+C` in the running window, then re-run the same command.

## Restarting the server remotely with WinRM

WinRM is useful as the remote control channel, but **do not start the MCP server
directly inside the WinRM session**. That process cannot see CATIA's interactive COM
object: this was verified on 2026-07-14 with
`win32com.client.GetActiveObject("CATIA.Application")`, which failed from direct
WinRM Python with `-2147221021 Operation unavailable`.

The working shape is:

1. WinRM connects as `corp\sup02`.
2. The remote script finds the existing MCP `python.exe` in the active CATIA session
   (currently `sup02` session `8`) and stops only that Python process.
3. It duplicates a token from `explorer.exe`/PowerShell in that same interactive
   session and launches a new PowerShell there.
4. That PowerShell reads `CATIA_MCP_TOKEN` from a local untracked token file and
   starts `python.exe -m catia_mcp --http ...` in the CATIA-visible desktop session.

On this host, direct `CreateProcessAsUser`/`CreateProcessWithTokenW` from the WinRM
admin session still fails (`CreateProcessAsUser` reports `1314`, required privilege
not held). The helper therefore falls back to a **temporary LocalSystem launcher
service** only for the start operation, then deletes it. This is not Task Scheduler;
it is a one-shot service shim used because LocalSystem has the required token-launch
privileges.

From this repo on the client machine:

```powershell
.\scripts\restart_remote_catia_mcp.ps1
```

The helper reads `192.168.5.42-creds`, uploads
`scripts\windows\restart_catia_mcp_in_session.ps1` to the CATIA workstation, syncs
the remote token file at
`C:\Users\sup02\catia-v5-mcp-server\.catia-mcp-env`, invokes the restart script over
WinRM, then polls the authenticated `/mcp/` endpoint with an MCP `initialize` request.

Useful variants:

```powershell
# Validate session/process selection without stopping or starting anything.
.\scripts\restart_remote_catia_mcp.ps1 -DryRun

# Reuse the already-uploaded remote script.
.\scripts\restart_remote_catia_mcp.ps1 -SkipUpload

# Reuse the existing remote token file.
.\scripts\restart_remote_catia_mcp.ps1 -SkipTokenSync
```

WinRM prerequisites, already tested from the current client:

```powershell
Test-WSMan 192.168.5.42
Invoke-Command -ComputerName 192.168.5.42 -Credential (Get-Credential) -ScriptBlock {
    whoami
    hostname
}
```

If connecting by IP and authentication fails with `ServerNotTrusted`, set the client
machine's TrustedHosts entry:

```powershell
Set-Item WSMan:\localhost\Client\TrustedHosts -Value "192.168.5.42" -Force
```

The restart helper intentionally does not touch `CNEXT.exe`/CATIA.

## Updating deployed code

The box has no internet and no git — code is pushed via the SMB admin share:

### Local credential source

On the current client workstation, deployment automation must read the credentials
from this Git-ignored file instead of asking for them again or embedding them in a
command/document:

```text
C:\Users\j-avd\Documents\catia-v5-mcp-server-git\catia-v5-mcp-server\192.168.5.42-creds
```

The file contains `local_adm_username`/`local_adm_pass`,
`adm_username`/`adm_pass`, `Deploy_host`, and `MCP_TOKEN`. Use the `adm_*` pair for
the SMB admin share: it was verified against `.42` on 2026-07-14, while the
`local_adm_*` pair returned `Access is denied`. Never print these values in logs or
tool output. The filename is covered by the repository's `*-creds` rule and must
remain untracked.

For a PowerShell deployment, parse the `key=value` file in memory and create a
temporary credentialed drive; this avoids putting the password directly in the
documented command line:

```powershell
$credentialFile = 'C:\Users\j-avd\Documents\catia-v5-mcp-server-git\catia-v5-mcp-server\192.168.5.42-creds'
$deploy = @{}
Get-Content -LiteralPath $credentialFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=:]*?)\s*[:=]\s*(.*)$') {
        $deploy[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$password = ConvertTo-SecureString $deploy.adm_pass -AsPlainText -Force
$credential = [pscredential]::new($deploy.adm_username, $password)
New-PSDrive -Name CATIADeploy -PSProvider FileSystem `
    -Root "\\$($deploy.Deploy_host)\C$" -Credential $credential
```

Remove the temporary drive with `Remove-PSDrive CATIADeploy` in a `finally` block
after copying the files.

The equivalent interactive SMB sequence is:

```powershell
net use \\192.168.5.42\C$ /user:<adm_username from 192.168.5.42-creds> <adm_pass from 192.168.5.42-creds>
Remove-Item '\\192.168.5.42\C$\Users\sup02\catia-v5-mcp-server\catia_mcp' -Recurse -Force
Copy-Item '<local repo path>\catia_mcp' '\\192.168.5.42\C$\Users\sup02\catia-v5-mcp-server\catia_mcp' -Recurse -Force
net use \\192.168.5.42\C$ /delete
```

Then restart the server with `.\scripts\restart_remote_catia_mcp.ps1` — **the running
process does not hot-reload; a stale process will keep reporting the old tool count.**
This was hit directly: the GSD modules existed in the repo and were committed to git
before they were ever pushed to the box, so `tools/list` kept reporting 54 tools
instead of 63 until the redeploy happened.

Python dependencies (`mcp`, `pywin32` — currently `pycatia` is **not** installed and,
per `docs/PLAN.md`, not currently required by any tool module) were installed offline
from pre-downloaded wheels:

```powershell
C:\Users\sup02\AppData\Local\Programs\Python\Python311\python.exe -m pip install --no-index --find-links <wheels-dir> mcp pywin32
```

To refresh/add packages, `pip download <pkg> --dest <dir> --platform win_amd64 --python-version 311 --only-binary=:all:` on a connected machine, then push the wheels dir over SMB the same way as the source.

## Security posture of the HTTP endpoint

This is a real consideration, not boilerplate — the endpoint executes CATIA
automation and file I/O:

- Binds to the specific VPN-facing IP (`192.168.5.42`), never `0.0.0.0`.
- Bearer token required (`CATIA_MCP_TOKEN` env var; server logs a loud warning and
  accepts unauthenticated requests if unset — never run it unset).
- DNS-rebinding Host allow-list is **on** (`--allowed-host`), not disabled.
- Firewall rule scopes port 8000 to the specific client source IP, not the subnet:
  ```powershell
  New-NetFirewallRule -Name catia-mcp-8000 -DisplayName "CATIA MCP (client-only)" `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 8000 `
    -RemoteAddress <client-ip>
  ```
- The actual token value and the SMB/RDP credentials are **not** committed to this
  repo or written in this document. On the current client, use the Git-ignored
  `192.168.5.42-creds` file documented under "Local credential source" above.

## Current verification status

- **Base tools (54, pre-GSD)** — live-verified: `catia_list_documents` and
  `catia_new_product` were both called through the deployed HTTP endpoint and
  confirmed against the actual CATIA window (created a real `Product2.CATProduct`).
- **Current HTTP server** — authenticated `initialize` re-confirmed on
  `192.168.5.42:8000`; **103 published tools** as of 2026-07-15 (95 + 8 drawing tools).
- **Drawing (CATDrawing) tools** — all 8 live-verified 2026-07-15 on the lofted wheel:
  a six-view sheet (front/top/right/iso + section + detail) and a one-call
  `catia_drawing_from_part` drawing were generated, screenshotted, and exported to PDF.
  Key working shapes (see `docs/PLAN.md` item 15): link the 3D via
  `GenerativeBehavior.Document = part_doc` (not `GenerativeLinks.AddLink`), carry that
  link onto derived views or they render empty, and set scale/position explicitly (no
  API auto-layout).
- **Drawing BOM** - `catia_fill_drawing_bom` was live-verified on 2026-07-21 with
  `python scripts/smoke_drawing_bom.py`. It created a three-row DrawingTable in a
  temporary A4 drawing and then found and updated that exact table; the smoke closed the
  drawing without saving.
- **GSD wheel path** — `catia_spline_3d`, `catia_loft`, `catia_fill`, `catia_join`,
  the PartBody-activated `CloseSurface` path, and the resulting circular pattern were
  exercised against live CATIA. A complete ten-spoke wheel was built and saved as
  `C:\Users\sup02\Documents\MCP_Wheel_Lofted_Spokes_20260714_121051.CATPart`.
  The subsequent radial valve-hole stage was also exercised in a complete legacy-call
  build and saved as
  `C:\Users\sup02\Documents\MCP_Wheel_Valve_Hole_20260714_123338.CATPart`.
  Its PartBody ends with `Valve_Hole`; CATIA updated and saved without error, and the
  measured 802.4 mm3 volume reduction matches a diameter 11.3 x 8 mm cylinder.
  This does not imply that every GSD tool is verified: `catia_sew_surface` still requires
  an individual live smoke test. Variable fillet controls and advanced draft were both
  live-verified on 2026-07-19 with `python scripts/smoke_item14.py`; see item 14 in
  `PLAN.md` for the solver-valid PointOnCurve and empty-parting-reference semantics.
- **Wheel construction visibility** - live-verified on 2026-07-19 with
  `python scripts/smoke_wheel_visibility.py`. `catia_design_wheel` now sets the
  `Spoke_Construction` geometrical set to No Show after building the wheel; the live
  report confirmed its `construction_visibility` phase before the temporary CATPart
  was closed without saving.
- **View/screenshot** — `catia_fit_all` and standard view changes work.
  `catia_screenshot` now picks the capture format from the file extension and, because
  CATIA's API has no PNG format, writes a `.png` request as JPEG with a corrected `.jpg`
  path (verified live 2026-07-14 — the returned path reflects the real file). Earlier
  builds' EMF-under-`.png` files predate this fix.
- **Close-up camera zoom** - `catia_zoom_view` is live-verified on 2026-07-19 with
  `python scripts/smoke_zoom_view.py`. The smoke fit a temporary Pad in front view,
  performed three `Viewer.ZoomIn` calls and captured
  `C:\Users\sup02\Documents\CATIA_MCP_Zoom_Smoke.jpg`; the resulting file was a
  168,330-byte JPEG with the `FFD8` signature. The temporary CATPart was closed without
  saving.
- **`catia_open_document` already-open handling** — CATIA's `Documents.Open` raises a
  blocking modal if the target document is already open in the session. `catia_open_document`
  now guards against this: it scans open documents by path and reuses/activates a match
  instead of reopening (verified live — reopening an open part returns in ~2 s). The raw
  modal risk still exists for any code that calls `Documents.Open` directly.

## Repos

- `origin` (GitHub, `daiemon12/catia-v5-mcp-server`) — original project.
- `laduga` (GitLab, `git.laduga.com/root/catia-v5-mcp-server`, private) — storage
  mirror created for this work, includes the GSD extension and HTTP transport.
  Push requires a personal access token; not stored in this repo.
