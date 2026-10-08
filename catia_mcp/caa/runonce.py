"""Existing RunOnce JSON protocol, with one method and no automatic retry."""
import json
import time

from .errors import CatiaBridgeResponseError, CatiaBridgeTimeoutError
from .paths import BridgePaths
from .protocol import BridgeRequest, CurrentJob, atomic_write_json, read_json, utc_now_iso

METHOD = "catia_caa_demo_create_point"


class RunOnceFileBridgeTransport:
    def __init__(self, catia, operation_id=None):
        self.catia = catia
        self.operation_id = operation_id
        self.paths = BridgePaths.from_root()

    def call(self, method, params, timeout=60):
        if method != METHOD:
            raise ValueError("The Point-only bridge accepts only " + METHOD)
        import win32event
        import win32api

        mutex = win32event.CreateMutex(None, False, "Local\\CatiaPyBridgePointRequest")
        acquired = False
        try:
            status = win32event.WaitForSingleObject(mutex, 0)
            if status not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
                raise ValueError("Another Point request is still running")
            acquired = True
            self.paths.ensure()
            if self.paths.current_job_path.exists():
                try:
                    previous = read_json(self.paths.current_job_path)
                except (ValueError, OSError) as error:
                    raise CatiaBridgeTimeoutError("Previous job state is unreadable; resolve it before another request") from error
                previous_response = self.paths.response_path(previous["job_id"])
                if not previous_response.is_file():
                    raise CatiaBridgeTimeoutError("An earlier request has no response; resolve its state before another call")
            request = BridgeRequest.create(method, params, job_id=self.operation_id)
            request_path = self.paths.request_path(request.id)
            response_path = self.paths.response_path(request.id)
            job = CurrentJob(request.id, request_path.resolve().as_posix(), response_path.resolve().as_posix(), utc_now_iso())
            atomic_write_json(request_path, request.to_dict())
            atomic_write_json(self.paths.current_job_path, job.to_dict())
            # A StartCommand exception does not prove non-delivery. Leave the
            # descriptor intact, never retry and report modified=null upstream.
            self.catia.StartCommand("CatiaPyBridge_RunOnce")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if response_path.is_file():
                    try:
                        response = read_json(response_path)
                    except (ValueError, OSError) as error:
                        raise RuntimeError("Delivered request has an unreadable response; mutation state is unknown") from error
                    if response.get("id") != request.id:
                        raise RuntimeError("Bridge response ID differs from this request")
                    if response.get("ok") is not True:
                        error = response.get("error") or {}
                        raise CatiaBridgeResponseError(error.get("code", "CAA_ERROR"), error.get("message", "CAA failure"), error.get("detail"))
                    result = response.get("result")
                    if not isinstance(result, dict):
                        raise RuntimeError("Bridge success response has no object result")
                    return result
                time.sleep(0.1)
            raise CatiaBridgeTimeoutError("Point response not received; no automatic retry")
        finally:
            if acquired:
                win32event.ReleaseMutex(mutex)
            win32api.CloseHandle(mutex)
