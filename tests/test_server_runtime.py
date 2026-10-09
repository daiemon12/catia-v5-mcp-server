"""Runtime regressions: serialization, cancellation and per-call failures."""

import asyncio
import json
import logging
import threading
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from mcp.types import CallToolRequest, CallToolRequestParams

from catia_mcp.server import CATIAMCPServer


def test_registered_tools_and_schemas_are_unchanged():
    server = CATIAMCPServer()
    assert len(server._tool_router) == 98
    assert not any(name.startswith("catia_caa") for name in server._tool_router)
    for schema in server._schemas.values():
        Draft202012Validator.check_schema(schema)
    asyncio.run(server.close())


@pytest.mark.parametrize("error", [ValueError("Wrong sketch"), RuntimeError("No active document")])
def test_ordinary_failure_does_not_block_connect_or_next_tool(monkeypatch, error):
    async def run():
        server = CATIAMCPServer()
        monkeypatch.setattr(server.connection, "ensure_connected", lambda: None)
        calls = []

        def execute(name, arguments):
            calls.append(name)
            if name == "catia_new_part":
                raise error
            return "still serving"

        monkeypatch.setattr(server.document_tools, "execute", execute)
        try:
            failure = await server.call_tool("catia_new_part", {})
            assert failure.isError
            assert failure.structuredContent["code"] == "COM_ERROR"
            assert failure.structuredContent["message"] == str(error)
            assert not any(
                "Bridge" in action
                for action in failure.structuredContent["recovery"]["next_actions"]
            )
            for name in ("catia_connect", "catia_list_documents"):
                result = await server.call_tool(name, {})
                assert not result.isError
                assert result.content[0].text == "still serving"
            assert calls == ["catia_new_part", "catia_connect", "catia_list_documents"]
        finally:
            await server.close()

    asyncio.run(run())


def test_failed_connection_can_be_retried_without_restart(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        attempts = 0

        def execute(name, arguments):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("CATIA not running")
            return "Connected"

        monkeypatch.setattr(server.document_tools, "execute", execute)
        try:
            first = await server.call_tool("catia_connect", {})
            assert first.isError and first.structuredContent["effects"]["modified"] is False
            second = await server.call_tool("catia_connect", {})
            assert not second.isError and second.content[0].text == "Connected"
        finally:
            await server.close()

    asyncio.run(run())


def test_all_calls_com_initialization_and_cleanup_share_one_worker(monkeypatch):
    import catia_mcp.connection as connection_module

    threads = []

    def record():
        threads.append(threading.get_ident())

    app = SimpleNamespace(Caption="CATIA stub")
    monkeypatch.setattr(connection_module, "HAS_COM", True)
    monkeypatch.setattr(
        connection_module,
        "pythoncom",
        SimpleNamespace(CoInitialize=record, CoUninitialize=record),
        raising=False,
    )
    monkeypatch.setattr(
        connection_module,
        "win32com",
        SimpleNamespace(client=SimpleNamespace(GetActiveObject=lambda name: app)),
        raising=False,
    )

    async def run():
        server = CATIAMCPServer()

        def execute(name, arguments):
            record()
            server.connection.ensure_connected()
            return "original text"

        monkeypatch.setattr(server.document_tools, "execute", execute)
        try:
            results = await asyncio.gather(
                *(server.call_tool("catia_list_documents", {}) for _ in range(3))
            )
            assert all(result.content[0].text == "original text" for result in results)
        finally:
            await server.close()
        assert len(threads) == 5  # initialize, 3 executions, uninitialize
        assert len(set(threads)) == 1 and threads[0] != threading.get_ident()

    asyncio.run(run())


def test_cancelled_read_only_call_finishes_before_next_call_without_lock(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        started, finish = threading.Event(), threading.Event()
        completed = []
        monkeypatch.setattr(server.connection, "ensure_connected", lambda: None)

        def execute(name, arguments):
            if name == "catia_list_documents":
                started.set()
                assert finish.wait(3)
            completed.append(name)
            return name

        monkeypatch.setattr(server.document_tools, "execute", execute)
        first = asyncio.create_task(server.call_tool("catia_list_documents", {}))
        try:
            assert await asyncio.to_thread(started.wait, 3)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            second = asyncio.create_task(server.call_tool("catia_connect", {}))
            await asyncio.sleep(0.03)
            assert not second.done() and not completed
            finish.set()
            result = await second
            assert not result.isError
            assert completed == ["catia_list_documents", "catia_connect"]
        finally:
            finish.set()
            await server.close()

    asyncio.run(run())


def test_missing_api_keeps_guidance_and_logs_exception(monkeypatch, caplog):
    async def run():
        server = CATIAMCPServer()
        monkeypatch.setattr(server.connection, "ensure_connected", lambda: None)

        def execute(name, arguments):
            raise AttributeError("Missing AddNewPad")

        monkeypatch.setattr(server.document_tools, "execute", execute)
        try:
            with caplog.at_level(logging.INFO, logger="catia_mcp"):
                result = await server.call_tool("catia_new_part", {})
            message = result.structuredContent["message"]
            assert result.isError and result.structuredContent["code"] == "UNSUPPORTED_CAPABILITY"
            assert all(
                text in message for text in ("gen_py", "workbench", "catia_diagnose", "absent")
            )
            assert any(
                record.exc_info and "Missing AddNewPad" in record.getMessage()
                for record in caplog.records
            )
            assert json.loads(result.content[0].text) == result.structuredContent
            assert "\n  " in result.content[0].text
        finally:
            await server.close()

    asyncio.run(run())


def test_invalid_or_unknown_call_does_not_touch_com(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        monkeypatch.setattr(
            server.connection, "ensure_connected", lambda: pytest.fail("COM accessed")
        )
        try:
            unknown = await server.call_tool("catia_missing", {})
            invalid = await server.call_tool("catia_export", {})
            assert unknown.isError and unknown.structuredContent["code"] == "UNKNOWN_TOOL"
            assert invalid.isError and invalid.structuredContent["code"] == "INVALID_ARGUMENT"
            assert invalid.structuredContent["effects"]["modified"] is False
        finally:
            await server.close()

    asyncio.run(run())


def test_sdk_handler_preserves_structured_failure(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        try:
            request = CallToolRequest(
                method="tools/call", params=CallToolRequestParams(name="catia_export", arguments={})
            )
            result = (await server.server.request_handlers[CallToolRequest](request)).root
            assert result.isError and result.structuredContent["code"] == "INVALID_ARGUMENT"
            assert json.loads(result.content[0].text) == result.structuredContent
        finally:
            await server.close()

    asyncio.run(run())
