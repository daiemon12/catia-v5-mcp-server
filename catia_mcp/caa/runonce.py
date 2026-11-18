"""Existing RunOnce JSON protocol, with one method and no automatic retry."""

import json
import re
import time

from .errors import CatiaBridgePreDeliveryError, CatiaBridgeResponseError, CatiaBridgeTimeoutError
from .paths import BridgePaths
from .protocol import BridgeRequest, CurrentJob, atomic_write_json, read_json

METHOD = "catia_caa_demo_create_point"


class RunOnceFileBridgeTransport:
    def __init__(self, catia, root, operation_id=None):
        self.catia = catia
        self.operation_id = operation_id
        self.paths = BridgePaths.from_root(root)

    def call(self, method, params, timeout=60):
        if method != METHOD:
            raise ValueError("The Point-only bridge accepts only " + METHOD)
        try:
            import win32api
            import win32event

            mutex = win32event.CreateMutex(None, False, "Local\\CatiaPyBridgePointRequest")
        except Exception as error:
            raise CatiaBridgePreDeliveryError("CAA_PREDELIVERY_FAILED", str(error)) from error
        acquired = False
        delivered = False
        try:
            status = win32event.WaitForSingleObject(mutex, 0)
            if status not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
                raise CatiaBridgePreDeliveryError(
                    "CAA_REQUEST_BUSY", "Another Point request is still running"
                )
            acquired = True
            self.paths.ensure()
            if self.paths.current_job_path.exists():
                try:
                    previous = read_json(self.paths.current_job_path)
                except (ValueError, OSError) as error:
                    raise CatiaBridgePreDeliveryError(
                        "CAA_PENDING_JOB",
                        f"Inspect unresolved descriptor {self.paths.current_job_path}",
                    ) from error
                previous_id = previous.get("job_id")
                if not isinstance(previous_id, str) or not re.fullmatch(
                    r"[0-9a-f]{32}", previous_id
                ):
                    raise CatiaBridgePreDeliveryError(
                        "CAA_PENDING_JOB",
                        f"Invalid previous job ID; inspect {self.paths.current_job_path}",
                    )
                previous_response = self._job_file(self.paths.response_path(previous_id))
                if not previous_response.is_file():
                    raise CatiaBridgePreDeliveryError(
                        "CAA_PENDING_JOB",
                        f"Earlier request has no response; inspect {self.paths.current_job_path}",
                    )
                try:
                    self._read_response(previous_response, previous_id)
                except (OSError, ValueError) as error:
                    raise CatiaBridgePreDeliveryError(
                        "CAA_PENDING_JOB", f"Invalid previous response: {previous_response}"
                    ) from error
                previous_request = self._job_file(self.paths.request_path(previous_id))
                previous_request_data = (
                    read_json(previous_request) if previous_request.is_file() else {}
                )
                if (
                    previous_request_data.get("method") != METHOD
                    or previous_request_data.get("id") != previous_id
                ):
                    raise CatiaBridgePreDeliveryError(
                        "CAA_PENDING_JOB",
                        "Previous request is not an owned Point job; inspect it manually",
                    )
                self._archive(previous_id)
            request = BridgeRequest.create(method, params, job_id=self.operation_id)
            if not re.fullmatch(r"[0-9a-f]{32}", request.id):
                raise CatiaBridgePreDeliveryError(
                    "INVALID_ARGUMENT", "job_id must be 32 lowercase hex characters"
                )
            request_path = self.paths.request_path(request.id)
            response_path = self.paths.response_path(request.id)
            job = CurrentJob(request.id)
            atomic_write_json(request_path, request.to_dict())
            atomic_write_json(self.paths.current_job_path, job.to_dict())
            # A StartCommand exception does not prove non-delivery. Leave the
            # descriptor intact, never retry and report modified=null upstream.
            delivered = True
            self.catia.StartCommand("CatiaPyBridge_RunOnce")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if response_path.is_file():
                    try:
                        response = self._read_response(response_path, request.id)
                    except (ValueError, OSError) as error:
                        raise RuntimeError(
                            f"Invalid response for delivered Point request: {error}"
                        ) from error
                    cleanup_warning = None
                    try:
                        self._archive(request.id)
                    except OSError as cleanup_error:
                        cleanup_warning = f"Job cleanup failed: {cleanup_error}; inspect {self.paths.current_job_path}"
                    if not response["ok"]:
                        error = response["error"]
                        detail = error.get("detail")
                        if cleanup_warning:
                            try:
                                evidence = json.loads(detail) if detail else {}
                            except (TypeError, ValueError):
                                evidence = {"detail": detail}
                            if not isinstance(evidence, dict):
                                evidence = {"detail": detail}
                            evidence.setdefault("warnings", []).append(cleanup_warning)
                            detail = json.dumps(evidence)
                        raise CatiaBridgeResponseError(
                            error.get("code", "CAA_ERROR"),
                            error.get("message", "CAA failure"),
                            detail,
                        )
                    result = response["result"]
                    if cleanup_warning:
                        result.setdefault("warnings", []).append(cleanup_warning)
                    return result
                time.sleep(0.1)
            raise CatiaBridgeTimeoutError(
                f"Point response not received; inspect {self.paths.current_job_path}; bridge root={self.paths.root}; no automatic retry"
            )
        except Exception as error:
            if not delivered and not isinstance(error, CatiaBridgePreDeliveryError):
                raise CatiaBridgePreDeliveryError("CAA_PREDELIVERY_FAILED", str(error)) from error
            raise
        finally:
            if acquired:
                win32event.ReleaseMutex(mutex)
            win32api.CloseHandle(mutex)

    @staticmethod
    def _read_response(path, job_id):
        response = read_json(path)
        if response.get("id") != job_id:
            raise ValueError("Bridge response ID differs from the request")
        ok = response.get("ok")
        if not isinstance(ok, bool) or not isinstance(response.get("result" if ok else "error"), dict):
            raise ValueError("Bridge response must contain a boolean status and a result or error object")
        return response

    def _job_file(self, active_path):
        if active_path.exists():
            return active_path
        return self.paths.done / active_path.name

    def _archive(self, job_id):
        # Called only after a correlated response. An unresolved descriptor is
        # retained for operator inspection, never silently replayed or discarded.
        for source in (self.paths.request_path(job_id), self.paths.response_path(job_id)):
            if source.is_file():
                destination = self.paths.done / source.name
                if destination.exists():
                    raise FileExistsError(f"Archive already exists: {destination}")
                source.rename(destination)
        self.paths.current_job_path.unlink()
