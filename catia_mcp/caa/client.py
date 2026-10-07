"""One public modeling capability: a parameterized coordinate point."""
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

from .runonce import METHOD, RunOnceFileBridgeTransport

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "caa_point.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class CatiaCaaBridgeClient:
    def __init__(self, catia=None, transport=None, timeout=60, operation_id=None):
        if transport is None and catia is None:
            raise ValueError("An explicitly attached CATIA instance is required")
        self.transport = transport or RunOnceFileBridgeTransport(catia, operation_id=operation_id)
        self.timeout = timeout

    def call(self, method, params, timeout=None):
        if method != METHOD:
            raise ValueError("Only " + METHOD + " is implemented")
        return self.transport.call(method, params, timeout=timeout or self.timeout)

    def demo_create_point(self, **params):
        Draft202012Validator(SCHEMA).validate(params)
        for key in ("x_mm", "y_mm", "z_mm"):
            if not math.isfinite(params[key]):
                raise ValueError("Coordinates must be finite")
        return self.call(METHOD, params)
