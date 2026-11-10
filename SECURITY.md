# Security

This document describes what the server does and does not do, so that a
security team can evaluate it before use. Everything stated here can be
checked in the source code, which is fully open.

## What the server is

A local Python process that receives tool calls from an MCP client (an AI
assistant) and translates them into CATIA V5 COM Automation calls, the same
interface used by VBA macros. It runs with the rights of the logged-in
Windows user and drives the CATIA session that user has open.

## Network behaviour

- **Default mode (stdio): no network at all.** The server talks to the MCP
  client through standard input and output, and to CATIA through local COM.
  It opens no socket, makes no outbound request, and contains no telemetry,
  analytics or update check.
- **Optional HTTP mode (`--http`)**: off unless explicitly started. It binds
  to `127.0.0.1` by default and refuses to listen on any other address
  without a bearer token of at least 16 characters, compared in constant
  time. It provides no TLS; see [docs/remote-access.md](docs/remote-access.md).

## Where model data goes

The server sends nothing anywhere. The **AI assistant** does: whatever the
tools return (feature names, parameter values, dimensions, measurements,
file paths) becomes part of the conversation and is sent to the model
provider configured in the MCP client. Confidentiality therefore depends on
the model hosting you choose: an enterprise tenant, or a model hosted
locally, keeps this data inside your perimeter. Evaluate on non-sensitive
parts first.

## Read-only mode

Start the server with `--read-only` (or `CATIA_MCP_READ_ONLY=1`) to expose
only inspection and measurement tools. In this mode nothing can be created,
modified, saved or exported; every other tool is hidden from the assistant
and refused with `READ_ONLY_MODE` if called anyway. The exact allowlist is
`READ_ONLY_TOOLS` in `catia_mcp/server.py`, enforced by
`tests/test_read_only.py`.

## Files and processes

- The server itself writes one file: `catia_mcp.log`, next to the package.
  It records each tool call with its arguments and a preview of the result.
  Treat it as containing model metadata.
- Outside read-only mode, CATIA writes files only where a tool is asked to:
  `catia_save_document`, `catia_export`, `catia_screenshot`,
  `catia_create_design_table` (reads a sheet).
- The server starts no subprocess and executes no shell command. There is
  no tool that runs arbitrary scripts.
- A few measurements run short, fixed VBScript functions inside CATIA
  through `SystemService.Evaluate`, because some array-returning methods do
  not marshal through Python. The script text is built from constants in
  the source, not from tool arguments.

## Input handling

Tool arguments are validated against each tool's JSON Schema before any COM
call. Calls are executed one at a time on a single worker thread. Failures
are returned as structured errors and do not affect later calls.

## Dependencies and supply chain

Three direct runtime dependencies: `mcp` (official MCP SDK), `pywin32` and
`jsonschema`. `requirements-lock.txt` pins the full resolved set for Windows
with SHA-256 hashes:

```
pip install --require-hashes -r requirements-lock.txt
pip install --no-deps .
```

No binaries are committed to the repository. Every change goes through CI
on Windows, and contributions are reviewed before merge.

## Known limits

- An AI assistant can make modelling mistakes; outside read-only mode it
  can modify the open session. Work on copies and review results.
- There is no per-user authentication or role model beyond the HTTP token.
- A CATIA modal dialog can block a call until it is dismissed.
- The project is community-maintained and provided without warranty (MIT).

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's
private vulnerability reporting on this repository (Security tab, "Report a
vulnerability"), or contact the maintainer through the LinkedIn profile
linked in the README. You will get an answer within a few days.
