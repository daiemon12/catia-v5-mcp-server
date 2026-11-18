"""Verify contribution scope, runtime integrity, and the actual file protocol."""

import json
from pathlib import Path

import pytest

from catia_mcp.caa import runtime_manifest as manifest
from catia_mcp.caa.client import CatiaCaaBridgeClient
from catia_mcp.caa.errors import (
    CatiaBridgePreDeliveryError,
    CatiaBridgeResponseError,
)
from catia_mcp.caa.paths import BridgePaths
from catia_mcp.caa.protocol import atomic_write_json, read_json
from catia_mcp.caa.runonce import METHOD, RunOnceFileBridgeTransport

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "caa/point_bridge/caa_workspace"
RUNTIME = WORKSPACE / "CatiaPyBridgeRuntime"


def test_contributed_sources_match_current_source_manifest():
    for name, expected in manifest.SOURCE["files"].items():
        assert manifest.file_hash(WORKSPACE / name) == expected


@pytest.fixture
def built_runtime(tmp_path):
    # Synthetic files exercise integrity checks without committing/running DLLs.
    runtime = tmp_path / "runtime"
    for name in manifest.RUNTIME_FILES:
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("fixture:" + name).encode())
    data = {
        "method": METHOD,
        "native_source_files": manifest.SOURCE["files"],
        "runtime_files": {
            name: manifest.file_hash(runtime / name) for name in manifest.RUNTIME_FILES
        },
    }
    (runtime / "runtime.json").write_text(json.dumps(data), encoding="utf-8")
    return runtime


def test_valid_local_runtime_is_accepted(built_runtime):
    manifest.verify_files(built_runtime)


@pytest.mark.parametrize("change", ["dll", "source", "method", "missing"])
def test_runtime_tampering_is_rejected(built_runtime, change):
    runtime = built_runtime
    path = runtime / "runtime.json"
    data = json.loads(path.read_text())
    if change == "dll":
        (runtime / "code/bin/CatiaPyBridgeCmdModule.dll").write_bytes(b"foreign DLL")
    elif change == "source":
        data["native_source_files"] = {}
    elif change == "method":
        data["method"] = "another_caa_business"
    else:
        (runtime / "code/dictionary/CatiaPyBridge.dico").unlink()
    path.write_text(json.dumps(data))
    with pytest.raises(manifest.RuntimeManifestError):
        manifest.verify_files(runtime)


@pytest.mark.parametrize("response", ["success", "native_error", "wrong_id", "bad_result"])
def test_runonce_correlates_response_and_preserves_native_failure(tmp_path, response):
    pytest.importorskip("win32event")
    paths = BridgePaths.from_root(tmp_path)
    calls = []

    class Catia:
        def StartCommand(self, command):
            calls.append(command)
            job = read_json(paths.current_job_path)
            assert set(job) == {"job_id"}
            request = read_json(paths.request_path(job["job_id"]))
            assert request["method"] == METHOD
            assert request["id"] == "11111111111111111111111111111111"
            payload = {"id": request["id"], "ok": True, "result": {"modified": False}}
            if response == "native_error":
                payload.update(
                    ok=False,
                    error={
                        "code": "CAA_POINT_CREATE_FAILED",
                        "message": "Update failed",
                        "detail": '{"modified":true,"failure_stage":"update"}',
                    },
                )
            elif response == "wrong_id":
                payload["id"] = "different-request"
            elif response == "bad_result":
                payload["result"] = []
            atomic_write_json(paths.response_path(job["job_id"]), payload)

    transport = RunOnceFileBridgeTransport(Catia(), tmp_path, operation_id="11111111111111111111111111111111")
    if response == "success":
        assert transport.call(METHOD, {}, timeout=1) == {"modified": False}
    elif response == "native_error":
        with pytest.raises(CatiaBridgeResponseError) as error:
            transport.call(METHOD, {}, timeout=1)
        assert error.value.code == "CAA_POINT_CREATE_FAILED"
        assert json.loads(error.value.detail)["modified"] is True
    else:
        with pytest.raises(RuntimeError, match="Invalid response for delivered Point request"):
            transport.call(METHOD, {}, timeout=1)
    assert calls == ["CatiaPyBridge_RunOnce"]
    job_id = "11111111111111111111111111111111"
    if response in {"wrong_id", "bad_result"}:
        assert paths.current_job_path.exists()
        assert paths.request_path(job_id).exists()
    else:
        assert not paths.current_job_path.exists()
        assert (paths.done / paths.request_path(job_id).name).exists()
        assert (paths.done / paths.response_path(job_id).name).exists()


def test_unresolved_previous_request_never_reaches_startcommand(tmp_path):
    class Catia:
        def StartCommand(self, command):
            pytest.fail("Unresolved request was replayed")

    pytest.importorskip("win32event")
    transport = RunOnceFileBridgeTransport(Catia(), tmp_path)
    atomic_write_json(transport.paths.current_job_path, {"job_id": "pending"})
    with pytest.raises(CatiaBridgePreDeliveryError):
        transport.call(METHOD, {})


def test_bundled_sdk_refuses_other_business_methods():
    class Transport:
        def call(self, *args, **kwargs):
            pytest.fail("Other business method reached transport")

    with pytest.raises(ValueError, match="Only"):
        CatiaCaaBridgeClient(transport=Transport()).call("catia_caa_other", {})


@pytest.mark.parametrize("failure", ["mutex", "write"])
def test_transport_setup_failure_is_known_predelivery(tmp_path, monkeypatch, failure):
    win32event = pytest.importorskip("win32event")
    from catia_mcp.caa import runonce

    def fail(*args, **kwargs):
        raise OSError("Setup unavailable")

    if failure == "mutex":
        monkeypatch.setattr(win32event, "CreateMutex", fail)
    else:
        monkeypatch.setattr(runonce, "atomic_write_json", fail)
    transport = RunOnceFileBridgeTransport(
        type("Catia", (), {"StartCommand": lambda *args: pytest.fail("Delivered")})(),
        tmp_path,
    )
    with pytest.raises(CatiaBridgePreDeliveryError) as error:
        transport.call(METHOD, {})
    assert error.value.code == "CAA_PREDELIVERY_FAILED"
    assert error.value.modified is False


@pytest.mark.parametrize(
    "request_method,request_id", [(METHOD, "a" * 32), ("other_caa", "b" * 32), (METHOD, "b" * 32)]
)
def test_completed_previous_job_only_archives_correlated_point_request(
    tmp_path, request_method, request_id
):
    pytest.importorskip("win32event")
    paths = BridgePaths.from_root(tmp_path)
    old_id = "a" * 32
    atomic_write_json(paths.current_job_path, {"job_id": old_id})
    atomic_write_json(paths.request_path(old_id), {"id": request_id, "method": request_method})
    atomic_write_json(paths.response_path(old_id), {"id": old_id, "ok": True, "result": {}})
    calls = []

    class Catia:
        def StartCommand(self, command):
            calls.append(command)
            job = read_json(paths.current_job_path)
            atomic_write_json(
                paths.response_path(job["job_id"]),
                {"id": job["job_id"], "ok": True, "result": {"modified": False}},
            )

    transport = RunOnceFileBridgeTransport(Catia(), tmp_path)
    if request_method == METHOD and request_id == old_id:
        assert transport.call(METHOD, {}) == {"modified": False}
        assert not paths.current_job_path.exists()
        assert (paths.done / paths.request_path(old_id).name).is_file()
        assert calls == ["CatiaPyBridge_RunOnce"]
    else:
        with pytest.raises(CatiaBridgePreDeliveryError) as error:
            transport.call(METHOD, {})
        assert error.value.code == "CAA_PENDING_JOB" and error.value.modified is False
        assert paths.current_job_path.exists() and paths.request_path(old_id).exists()
        assert calls == []


@pytest.mark.parametrize("native_error", [False, True])
def test_cleanup_failure_preserves_correlated_native_outcome(tmp_path, monkeypatch, native_error):
    pytest.importorskip("win32event")
    paths = BridgePaths.from_root(tmp_path)

    class Catia:
        def StartCommand(self, command):
            job = read_json(paths.current_job_path)
            response = {"id": job["job_id"], "ok": True, "result": {"modified": True}}
            if native_error:
                response.update(
                    ok=False,
                    error={
                        "code": "UPDATE_FAILED",
                        "message": "Update failed",
                        "detail": "raw native detail",
                    },
                )
            atomic_write_json(paths.response_path(job["job_id"]), response)

    transport = RunOnceFileBridgeTransport(Catia(), tmp_path)

    def fail(job_id):
        raise PermissionError("Archive unavailable")

    monkeypatch.setattr(transport, "_archive", fail)
    if native_error:
        with pytest.raises(CatiaBridgeResponseError) as error:
            transport.call(METHOD, {})
        assert error.value.code == "UPDATE_FAILED"
        detail = json.loads(error.value.detail)
        assert detail["detail"] == "raw native detail"
        assert "Archive unavailable" in detail["warnings"][0]
    else:
        result = transport.call(METHOD, {})
        assert result["modified"] is True and "Archive unavailable" in result["warnings"][0]
    assert paths.current_job_path.exists()


def test_completed_job_recovers_after_interrupted_archive(tmp_path):
    pytest.importorskip("win32event")
    paths = BridgePaths.from_root(tmp_path)
    old_id = "a" * 32
    atomic_write_json(paths.current_job_path, {"job_id": old_id})
    atomic_write_json(paths.done / paths.request_path(old_id).name, {"id": old_id, "method": METHOD})
    atomic_write_json(
        paths.done / paths.response_path(old_id).name,
        {"id": old_id, "ok": True, "result": {"modified": True}},
    )

    class Catia:
        def StartCommand(self, command):
            job = read_json(paths.current_job_path)
            assert job["job_id"] != old_id
            atomic_write_json(
                paths.response_path(job["job_id"]),
                {"id": job["job_id"], "ok": True, "result": {"modified": False}},
            )

    transport = RunOnceFileBridgeTransport(Catia(), tmp_path)
    assert transport.call(METHOD, {}, timeout=1) == {"modified": False}
    assert not paths.current_job_path.exists()
