# Deployment Notes — Live CATIA Connection

This documents the actual working deployment against a real CATIA V5 install, and —
more importantly — **the constraints that ruled out the obvious alternatives**, so a
future session doesn't re-spend time rediscovering them. Written to be read without
the conversation that produced it.

## Topology

- **CATIA host:** `192.168.5.10`, reached over a site-to-site VPN (client machine has
  no direct route to the `192.168.5.x` subnet; traffic goes out a specific local
  interface — see "Firewall" below for why that IP matters).
- **CATIA runs interactively** inside a logged-in Windows session on that host
  (observed as `session 8`, user `CORP\sup02`), reached via RDP by whoever operates
  it. It is **not** a service — someone has to be logged in with CATIA open.
- **The MCP server runs inside that same interactive session**, non-elevated, as a
  foreground `python -m catia_mcp --http ...` process. It listens on
  `192.168.5.10:8000`.
- **The client (Claude Code, or any MCP HTTP client) connects over the VPN** to that
  address with a bearer token.
- Server source lives on the box at `C:\catia-mcp-setup\catia_mcp` (pushed via SMB
  admin share, not git — the box has **no internet access**, see below).
- Python 3.11 is installed at `C:\Python311` on the box (the box has no other real
  Python — `python`/`python3` on PATH by default resolve to the Microsoft Store alias
  stub, which prints a bare `Python` with no version and does nothing useful; don't
  waste time debugging that, just use `C:\Python311\python.exe` explicitly).

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

## Running the server

In a **non-elevated** PowerShell inside the CATIA operator's session (this matters —
see above):

```powershell
$env:CATIA_MCP_TOKEN = "<token — ask the user, not stored in this repo>"
cd C:\catia-mcp-setup
C:\Python311\python.exe -m catia_mcp --http --host 192.168.5.10 --port 8000 --allowed-host 192.168.5.10:8000
```

This blocks in the foreground; that's correct, it's the server. Leave the window open.
Logging off that Windows session kills both the server and CATIA.

**To restart after a code update:** `Ctrl+C` the running window, then re-run the same
command. There is currently no supervisor/service wrapper — a real gap if this needs
to survive unattended.

## Updating deployed code

The box has no internet and no git — code is pushed via the SMB admin share:

```powershell
net use \\192.168.5.10\C$ /user:CORP\sup02 <password — ask the user>
Remove-Item '\\192.168.5.10\C$\catia-mcp-setup\catia_mcp' -Recurse -Force
Copy-Item '<local repo path>\catia_mcp' '\\192.168.5.10\C$\catia-mcp-setup\catia_mcp' -Recurse -Force
net use \\192.168.5.10\C$ /delete
```

Then restart the server (previous section) — **the running process does not hot-reload;
a stale process will keep reporting the old tool count.** This was hit directly: the
GSD modules existed in the repo and were committed to git before they were ever pushed
to the box, so `tools/list` kept reporting 54 tools instead of 63 until the redeploy
happened.

Python dependencies (`mcp`, `pywin32` — currently `pycatia` is **not** installed and,
per `docs/PLAN.md`, not currently required by any tool module) were installed offline
from pre-downloaded wheels:

```powershell
C:\Python311\python.exe -m pip install --no-index --find-links <wheels-dir> mcp pywin32
```

To refresh/add packages, `pip download <pkg> --dest <dir> --platform win_amd64 --python-version 311 --only-binary=:all:` on a connected machine, then push the wheels dir over SMB the same way as the source.

## Security posture of the HTTP endpoint

This is a real consideration, not boilerplate — the endpoint executes CATIA
automation and file I/O:

- Binds to the specific VPN-facing IP (`192.168.5.10`), never `0.0.0.0`.
- Bearer token required (`CATIA_MCP_TOKEN` env var; server logs a loud warning and
  accepts unauthenticated requests if unset — never run it unset).
- DNS-rebinding Host allow-list is **on** (`--allowed-host`), not disabled.
- Firewall rule scopes port 8000 to the specific client source IP, not the subnet:
  ```powershell
  New-NetFirewallRule -Name catia-mcp-8000 -DisplayName "CATIA MCP (client-only)" `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 8000 `
    -RemoteAddress <client-ip>
  ```
- The actual token value and the SMB/RDP credentials are **not** in this repo or this
  document — ask whoever ran the deployment, or check the Claude Code MCP config
  (`claude mcp list`) on the client machine.

## Current verification status

- **Base tools (54, pre-GSD)** — live-verified: `catia_list_documents` and
  `catia_new_product` were both called through the deployed HTTP endpoint and
  confirmed against the actual CATIA window (created a real `Product2.CATProduct`).
- **GSD tools (the +9 new modules, 63 total)** — code exists and is committed, **not
  yet run against live CATIA** as of this writing. See `docs/PLAN.md` → "Open Work" for
  the smoke-test plan. If you're picking this up fresh: that's the very next step,
  before trusting any of the surfacing code.

## Repos

- `origin` (GitHub, `daiemon12/catia-v5-mcp-server`) — original project.
- `laduga` (GitLab, `git.laduga.com/root/catia-v5-mcp-server`, private) — storage
  mirror created for this work, includes the GSD extension and HTTP transport.
  Push requires a personal access token; not stored in this repo.
