"""Verify contribution scope, runtime integrity, and the actual file protocol."""
import json
from pathlib import Path

import pytest

from catia_mcp.caa import runtime_manifest as manifest
from catia_mcp.caa.client import CatiaCaaBridgeClient
from catia_mcp.caa.errors import CatiaBridgeResponseError, CatiaBridgeTimeoutError
from catia_mcp.caa.paths import BridgePaths
from catia_mcp.caa.protocol import atomic_write_json, read_json
from catia_mcp.caa.runonce import METHOD, RunOnceFileBridgeTransport

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "caa/point_bridge/caa_workspace"
RUNTIME = WORKSPACE / "CatiaPyBridgeRuntime"


def test_contributed_sources_match_accepted_point_build():
    recorded = json.loads((ROOT / "caa/point_bridge/validation/native-evidence.json").read_text(encoding="utf-8"))
    assert recorded["business_methods"] == [METHOD]
    for name, expected in recorded["native_source_files"].items():
        assert manifest.file_hash(WORKSPACE / name) == expected
    assert len(recorded["original_native_live_gates"]) == 23
    assert all(gate["passed"] for gate in recorded["original_native_live_gates"])


@pytest.fixture
def built_runtime(tmp_path):
    # Synthetic files exercise integrity checks without committing/running DLLs.
    runtime = tmp_path / "runtime"
    for name in manifest.RUNTIME_FILES:
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("fixture:" + name).encode())
    data = {"method": METHOD, "native_source_files": manifest.SOURCE["files"],
            "runtime_files": {name: manifest.file_hash(runtime / name) for name in manifest.RUNTIME_FILES}}
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


@pytest.mark.parametrize("response", ["success", "native_error", "wrong_id"])
def test_runonce_correlates_response_and_preserves_native_failure(tmp_path, response):
    paths = BridgePaths.from_root(tmp_path)
    calls = []
    class Catia:
        def StartCommand(self, command):
            calls.append(command)
            job = read_json(paths.current_job_path)
            request = read_json(Path(job["request_path"]))
            assert request["method"] == METHOD
            assert request["id"] == "test-operation-id"
            payload = {"id": request["id"], "ok": True, "result": {"modified": False}}
            if response == "native_error":
                payload.update(ok=False, error={"code": "CAA_POINT_CREATE_FAILED", "message": "Update failed",
                                               "detail": '{"modified":true,"failure_stage":"update"}'})
            elif response == "wrong_id":
                payload["id"] = "different-request"
            atomic_write_json(Path(job["response_path"]), payload)
    transport = RunOnceFileBridgeTransport(Catia(), operation_id="test-operation-id")
    transport.paths = paths
    if response == "success":
        assert transport.call(METHOD, {}, timeout=1) == {"modified": False}
    elif response == "native_error":
        with pytest.raises(CatiaBridgeResponseError) as error:
            transport.call(METHOD, {}, timeout=1)
        assert error.value.code == "CAA_POINT_CREATE_FAILED"
        assert json.loads(error.value.detail)["modified"] is True
    else:
        with pytest.raises(RuntimeError, match="ID differs"):
            transport.call(METHOD, {}, timeout=1)
    assert calls == ["CatiaPyBridge_RunOnce"]


def test_unresolved_previous_request_never_reaches_startcommand(tmp_path):
    class Catia:
        def StartCommand(self, command):
            pytest.fail("Unresolved request was replayed")
    transport = RunOnceFileBridgeTransport(Catia())
    transport.paths = BridgePaths.from_root(tmp_path)
    atomic_write_json(transport.paths.current_job_path, {"job_id": "pending"})
    with pytest.raises(CatiaBridgeTimeoutError):
        transport.call(METHOD, {})


def test_bundled_sdk_refuses_other_business_methods():
    class Transport:
        def call(self, *args, **kwargs):
            pytest.fail("Other business method reached transport")
    with pytest.raises(ValueError, match="Only"):
        CatiaCaaBridgeClient(transport=Transport()).call("catia_caa_other", {})
