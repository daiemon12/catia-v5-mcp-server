# Serialized CATIA execution

MCP requests enqueue work on one persistent STA thread. Connection initialization,
tool execution and connection cleanup use that same thread. The 98 existing tool
schemas and successful text responses are unchanged.

Server-boundary failures return an `ok/code/operation_id/tool/message/data/effects/
diagnostics/warnings/recovery` envelope as both structured content and indented
JSON text, with MCP `isError=true`. Input validation failures do not access COM.
Missing Automation methods retain the guidance about release availability,
pywin32 cache and workbench licences in `message`. Exceptions include their
message and traceback in `catia_mcp.log`.

An ordinary error affects one call. Correct the input or inspect CATIA, then call
again; it does not require restarting the server. A cancelled client request does
not stop an already queued or executing COM operation. The worker completes it
before starting another call. Cancellation does not establish model rollback;
inspect the model before repeating a write.

There is no global unknown-session latch in this runtime change. It does not
introduce CAA tools, binaries, dependencies or native delivery-state handling.
CAA-specific indeterminate writes and recovery belong to the separate adapter.

No modal-dialog detection or COM-call cancellation is implemented. If a CATIA
dialog blocks a call, the worker and shutdown wait for it. Close the dialog. If
CATIA cannot recover, terminate CNEXT and restart MCP. This is a documented
runtime limitation, not a bounded-shutdown guarantee.

Install and run the offline regressions:

```sh
python -m pip install -e ".[dev]"
python -m pytest tests test_server.py -q
```

Windows CI runs this command on Python 3.10 and 3.12. Local tests use COM doubles
for thread ownership, serialization, errors and cancellation; they do not prove
live CATIA method behavior.
