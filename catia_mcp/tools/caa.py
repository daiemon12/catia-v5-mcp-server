"""MCP facade for the bundled Point-only CAA implementation."""
from copy import deepcopy

from catia_mcp.caa_client import METHOD, SCHEMA, create_point


class CaaTools:
    def __init__(self, connection):
        self.conn = connection

    def get_tool_definitions(self):
        return [{"name": METHOD, "description": (
            "Create one parameterized coordinate point in an already saved CATPart's unique, "
            "public ordinary root Geometrical Set. Millimeters, Part absolute coordinates. "
            "Requires one existing CNEXT with the requested PID and the verified Point-only B30 runtime. "
            "Read-only preview defaults true; execution requires explicit confirmation and the "
            "matching five-minute, one-time plan/state token. Adds three length parameters and one "
            "point; Update and native coordinate/name/membership readback. Never saves, deletes, "
            "opens or closes documents. Never retry an uncertain write. Limits: 128 root bodies, "
            "256 direct members, +/-1000000 mm. State fingerprint compares member names/types "
            "and cannot detect same-name/same-type replacement."
        ), "inputSchema": deepcopy(SCHEMA)}]

    def execute(self, name, arguments):
        if name != METHOD:
            raise ValueError("Unknown CAA tool")
        return create_point(self.conn, arguments)
