"""Offline failures and dispatch contracts; no real CATIA is called."""
import asyncio
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from catia_mcp import caa_client as caa
from catia_mcp.server import CATIAMCPServer

PARAMS = {"catia_process_id": 123, "part_document_path": "D:/Parts/test.CATPart",
          "geometrical_set_name": "Geometry", "point_name": "Point1",
          "x_mm": 10, "y_mm": 20, "z_mm": 30}


@pytest.mark.parametrize("change", [{"extra": 1}, {"x_mm": True}, {"x_mm": float("nan")},
                                     {"x_mm": float("inf")}, {"x_mm": 1000001},
                                     {"catia_process_id": 0}, {"dry_run": False},
                                     {"dry_run": False, "confirm_action": False}])
def test_invalid_params_never_attach(change):
    class Connection:
        def attach_caa(self, pid):
            pytest.fail("Invalid input reached CATIA")
    result = caa.create_point(Connection(), dict(PARAMS, **change))
    assert result["ok"] is False and result["effects"]["modified"] is False
    assert result["data"]["failure_stage"] == "validate"


def test_missing_dependency_never_attach(monkeypatch):
    monkeypatch.delenv("CATIA_MCP_CAA_RUNTIME", raising=False)
    result = caa.create_point(None, PARAMS)
    assert result["code"] == "CAA_BRIDGE_UNAVAILABLE"
    assert result["effects"]["modified"] is False


@pytest.fixture
def adapter(monkeypatch):
    app = object()
    connection = SimpleNamespace(attach_caa=lambda pid: app)
    monkeypatch.setattr(caa, "configured_runtime", lambda: Path("D:/host"))
    monkeypatch.setattr(caa, "verify_runtime", lambda *args, **kwargs: None)
    return connection, app


def test_shared_app_and_params_are_injected(adapter, monkeypatch):
    connection, app = adapter
    calls = []
    ids = []
    class Client:
        def __init__(self, catia, operation_id):
            assert catia is app
            ids.append(operation_id)
        def demo_create_point(self, **params):
            calls.append(params)
            return {"created": False, "modified": False, "dry_run": True}
    monkeypatch.setattr(caa, "CatiaCaaBridgeClient", Client)
    result = caa.create_point(connection, PARAMS)
    assert result["ok"] is True and calls == [PARAMS]
    assert ids == [result["operation_id"]]
    assert set(result) == {"ok", "code", "operation_id", "tool", "message", "data",
                           "effects", "diagnostics", "warnings", "recovery"}
    assert result["code"] == "OK" and result["tool"] == caa.METHOD


@pytest.mark.parametrize("error,modified,stage", [
    (TimeoutError("No response"), None, "transport"),
    (RuntimeError("Invalid response"), None, "transport"),
])
def test_uncertain_delivery_stays_unknown(adapter, monkeypatch, error, modified, stage):
    class Client:
        def __init__(self, catia, operation_id):
            pass
        def demo_create_point(self, **params):
            raise error
    monkeypatch.setattr(caa, "CatiaCaaBridgeClient", Client)
    result = caa.create_point(adapter[0], PARAMS)
    assert result["ok"] is False and result["effects"]["modified"] is modified
    assert result["data"]["failure_stage"] == stage and result["recovery"]["automatic_retry_allowed"] is False


def test_native_partial_write_evidence_survives(adapter, monkeypatch):
    class NativeError(Exception):
        code = "CAA_POINT_CREATE_FAILED"
        detail = '{"failure_stage":"update","modified":true,"saved":false}'
    class Client:
        def __init__(self, catia, operation_id):
            pass
        def demo_create_point(self, **params):
            raise NativeError("Update failed")
    monkeypatch.setattr(caa, "CatiaCaaBridgeClient", Client)
    result = caa.create_point(adapter[0], PARAMS)
    assert result["code"] == "CAA_POINT_CREATE_FAILED"
    assert result["data"]["failure_stage"] == "update" and result["effects"]["modified"] is True
    assert result["data"]["saved"] is False
    assert result["diagnostics"][0]["code"] == "CAA_POINT_CREATE_FAILED"
    assert result["recovery"]["rollback_supported"] is False
    assert result["recovery"]["next_actions"]


def test_runtime_mismatch_never_delivers(adapter, monkeypatch):
    monkeypatch.setattr(caa, "CatiaCaaBridgeClient", lambda **kw: pytest.fail("Delivered"))
    def mismatch(*args, **kwargs):
        raise caa.CaaPreflightError("CAA_BRIDGE_MISMATCH", "Wrong DLL")
    monkeypatch.setattr(caa, "verify_runtime", mismatch)
    result = caa.create_point(adapter[0], PARAMS)
    assert result["code"] == "CAA_BRIDGE_MISMATCH" and result["effects"]["modified"] is False


def test_caa_protocol_result_and_no_automatic_connect(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        monkeypatch.setattr(server.connection, "connect", lambda: pytest.fail("Launched CATIA"))
        monkeypatch.setattr(server.caa_tools, "execute", lambda *args: {
            "ok": False, "message": "Native failure", "effects": {"modified": True},
            "code": "CAA_POINT_CREATE_FAILED", "operation_id": "test-id", "data": {"failure_stage": "update"}})
        try:
            result = await server.call_tool(caa.METHOD, PARAMS)
            assert result.isError is True
            assert result.structuredContent["code"] == "CAA_POINT_CREATE_FAILED"
            assert json.loads(result.content[0].text) == result.structuredContent
        finally:
            await server.close()
    asyncio.run(run())


def test_unknown_delivery_blocks_the_next_operation(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        calls = []
        def execute(*args):
            calls.append(args)
            return {"ok": False, "data": None, "message": "Timed out", "effects": {"modified": None}, "operation_id": "test-id", "code": "COM_TIMEOUT"}
        monkeypatch.setattr(server.caa_tools, "execute", execute)
        try:
            await server.call_tool(caa.METHOD, PARAMS)
            result = await server.call_tool(caa.METHOD, PARAMS)
            assert result.structuredContent["code"] == "SESSION_STATE_UNKNOWN"
            assert len(calls) == 1
        finally:
            await server.close()
    asyncio.run(run())


def test_all_calls_and_cleanup_share_one_worker(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        threads = []
        active = 0
        def execute(*args):
            nonlocal active
            assert active == 0
            active += 1
            threads.append(threading.get_ident())
            time.sleep(0.01)
            active -= 1
            return {"ok": True, "data": {}, "message": "Preview", "operation_id": "test-id", "code": "OK"}
        monkeypatch.setattr(server.caa_tools, "execute", execute)
        monkeypatch.setattr(server.connection, "disconnect", lambda: threads.append(threading.get_ident()))
        try:
            await asyncio.gather(*(server.call_tool(caa.METHOD, PARAMS) for _ in range(3)))
        finally:
            await server.close()
        assert len(set(threads)) == 1 and threads[0] != threading.get_ident()
    asyncio.run(run())


def test_existing_com_dispatch_uses_same_worker_and_keeps_text_success(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        threads = []
        def record():
            threads.append(threading.get_ident())
        def execute(name, arguments):
            assert name == "catia_new_part" and arguments == {}
            record()
            return "upstream tool success"
        monkeypatch.setattr(server.connection, "ensure_connected", record)
        monkeypatch.setattr(server.document_tools, "execute", execute)
        monkeypatch.setattr(server.connection, "disconnect", record)
        try:
            result = await server.call_tool("catia_new_part", {})
            assert result.content[0].text == "upstream tool success"
            assert result.isError is False
        finally:
            await server.close()
        assert len(threads) == 3 and len(set(threads)) == 1
        assert threads[0] != threading.get_ident()
    asyncio.run(run())


def test_cancellation_does_not_cancel_com_or_allow_another_write(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        started, finish = threading.Event(), threading.Event()
        completed = []
        def execute(*args):
            started.set()
            assert finish.wait(3)
            completed.append(True)
            return {"ok": True, "data": {}, "message": "Done", "operation_id": "test-id", "code": "OK"}
        monkeypatch.setattr(server.caa_tools, "execute", execute)
        task = asyncio.create_task(server.call_tool(caa.METHOD, PARAMS))
        try:
            assert await asyncio.to_thread(started.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            result = await server.call_tool(caa.METHOD, PARAMS)
            assert result.structuredContent["code"] == "SESSION_STATE_UNKNOWN"
        finally:
            finish.set()
            await server.close()
        assert completed == [True]
    asyncio.run(run())


def test_unknown_and_invalid_tools_never_touch_com(monkeypatch):
    async def run():
        server = CATIAMCPServer()
        monkeypatch.setattr(server.connection, "connect", lambda: pytest.fail("COM accessed"))
        try:
            unknown = await server.call_tool("catia_missing", {})
            invalid = await server.call_tool(caa.METHOD, {})
            assert unknown.structuredContent["code"] == "UNKNOWN_TOOL"
            assert invalid.structuredContent["code"] == "INVALID_ARGUMENT"
        finally:
            await server.close()
    asyncio.run(run())


@pytest.mark.parametrize("pids", [[0, 123], [0, 123, 124], [0]])
def test_attach_caa_reuses_app_and_never_launches(monkeypatch, pids):
    import pywintypes
    import win32api
    import win32process
    import catia_mcp.connection as connection_module
    connection = connection_module.CATIAConnection()
    app = SimpleNamespace(Documents=SimpleNamespace(Count=1))
    connection.app = app
    monkeypatch.setattr(win32process, "EnumProcesses", lambda: pids)
    def open_process(access, inherit, pid):
        if pid == 0:
            raise pywintypes.error(5, "OpenProcess", "Access denied")
        return pid
    monkeypatch.setattr(win32api, "OpenProcess", open_process)
    monkeypatch.setattr(win32api, "CloseHandle", lambda handle: None)
    monkeypatch.setattr(win32process, "GetModuleFileNameEx", lambda handle, module: "D:/CATIA/CNEXT.exe")
    monkeypatch.setattr(connection_module.pythoncom, "CoInitialize", lambda: None)
    monkeypatch.setattr(connection_module.win32com.client, "Dispatch", lambda *args: pytest.fail("Launched CATIA"))
    monkeypatch.setattr(connection_module.win32com.client, "GetActiveObject", lambda *args: pytest.fail("Rebound shared app"))
    if pids == [0, 123]:
        assert connection.attach_caa(123) is app
    else:
        with pytest.raises(ValueError):
            connection.attach_caa(123)


def test_stdio_discovery_and_failure_without_catia(monkeypatch):
    async def run():
        import os
        import sys
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("CATIA_MCP_CAA_RUNTIME", None)
        parameters = StdioServerParameters(command=sys.executable, args=["-B", "-m", "catia_mcp.server"],
                                          cwd=str(Path(__file__).resolve().parents[1]), env=env)
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert sum(tool.name == caa.METHOD for tool in tools) == 1
                result = await session.call_tool(caa.METHOD, PARAMS)
                assert result.isError is True
                assert result.structuredContent["code"] == "CAA_BRIDGE_UNAVAILABLE"
                assert result.structuredContent["effects"]["modified"] is False
                assert set(result.structuredContent) == {"ok", "code", "operation_id", "tool", "message",
                                                        "data", "effects", "diagnostics", "warnings", "recovery"}
    asyncio.run(run())


@pytest.mark.parametrize("preview,command_loaded,wrong_path", [
    (True, False, False), (False, False, False), (False, True, False), (False, True, True)
])
def test_runtime_requires_exact_loaded_dlls(tmp_path, monkeypatch, preview, command_loaded, wrong_path):
    import win32api
    import win32process
    runtime = tmp_path / "code/bin"
    runtime.mkdir(parents=True)
    for name in caa.DLL_NAMES:
        path = runtime / name
        path.write_bytes(name.encode())
    loaded = [runtime / "CatiaPyBridgeAddin.dll"]
    if command_loaded:
        loaded.append((tmp_path / "foreign" if wrong_path else runtime) / "CatiaPyBridgeCmdModule.dll")
    closed = []
    monkeypatch.setattr(caa, "verify_files", lambda path: None)
    monkeypatch.setattr(win32api, "OpenProcess", lambda *args: 123)
    monkeypatch.setattr(win32api, "CloseHandle", lambda handle: closed.append(handle))
    monkeypatch.setattr(win32process, "EnumProcessModules", lambda handle: range(len(loaded)))
    monkeypatch.setattr(win32process, "GetModuleFileNameEx", lambda handle, module: str(loaded[module]))
    if wrong_path or (not preview and not command_loaded):
        with pytest.raises(caa.CaaPreflightError):
            caa.verify_runtime(123, tmp_path, preview=preview)
    else:
        caa.verify_runtime(123, tmp_path, preview=preview)
    assert closed == [123]
