"""Shared CATIA geometry plumbing for GSD and advanced Part Design tools."""

from __future__ import annotations

import json
import math
from typing import Any

import pythoncom
from win32com.client import VARIANT

from catia_mcp.connection import CATIAConnection


def raw(value: Any) -> Any:
    """Return a pycatia wrapper's COM object, or the value itself."""
    return getattr(value, "com_object", value)


def result(**values: Any) -> str:
    return json.dumps(values, indent=2, ensure_ascii=False)


def byref_doubles(n: int) -> VARIANT:
    """A ByRef SAFEARRAY (VT_BYREF|VT_ARRAY|VT_VARIANT) for CATIA methods
    that fill an array output argument. Read the result back from the
    VARIANT's `.value` after the call.

    Currently unused: the two calls this was built for turned out to be
    wrong for a different reason. GetBoundingBox does not exist anywhere in
    CATIA's Automation API (confirmed against pycatia's source — not a
    marshaling problem at all; three different argument shapes, including
    this VARIANT SAFEARRAY, all failed with the byte-for-byte identical
    "GetMeasurable.GetBoundingBox" error, which is itself the tell that the
    member never resolves regardless of arguments). GetCOG/GetInertia/
    GetPlane are real methods, but GetCOG/GetPlane work fine with plain
    Python lists once given the correct arity (see _choose_subelement), and
    GetInertia's real equivalent lives on a separate Inertia object
    (SPAWorkbench.Inertias.Add), not on Measurable at all.

    Kept in case a genuine CATIA ByRef-array marshaling problem turns up
    later — see docs/PLAN.md for the full investigation.
    """
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, [0.0] * n)


def ref_handle(name: str, kind: str = "feature", brep_name: str | None = None) -> dict[str, Any]:
    handle: dict[str, Any] = {"name": name, "kind": kind}
    if brep_name:
        handle["brep_name"] = brep_name
    return handle


class GeometryContext:
    """Centralizes active geoset, feature lookup, references, and safe updates."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    @property
    def part(self) -> Any:
        return self.conn.get_active_part()

    @property
    def hsf(self) -> Any:
        return self.conn.hybrid_shape_factory

    def find_object(self, name: str) -> Any:
        planes = self.conn.get_origin_elements()
        if name.lower() in planes:
            return planes[name.lower()]
        selection = self.conn.hso
        selection.Clear()
        try:
            selection.Search(f"Name={name},all")
            if selection.Count == 0:
                raise RuntimeError(f"Geometry '{name}' was not found")
            return selection.Item(1).Value
        finally:
            # Value remains a valid COM proxy after selection is cleared.
            selection.Clear()

    def resolve(self, spec: str | dict[str, Any] | Any) -> Any:
        """Resolve a public reference spec into a CATIA Reference."""
        if not isinstance(spec, (str, dict)):
            return self.part.CreateReferenceFromObject(raw(spec))
        if isinstance(spec, str):
            return self.part.CreateReferenceFromObject(self.find_object(spec))
        if spec.get("brep_name"):
            return self.part.CreateReferenceFromName(spec["brep_name"])

        name = spec.get("name") or spec.get("feature")
        if not name:
            raise ValueError("Reference requires 'name'/'feature' or 'brep_name'")
        obj = self.find_object(name)
        kind = spec.get("kind", "feature").lower()
        if kind == "feature":
            return self.part.CreateReferenceFromObject(obj)

        matches = self.list_subelements(name, kind)
        if not matches:
            raise RuntimeError(f"No {kind} sub-elements found on '{name}'")
        chosen = self._choose_subelement(matches, spec)
        if chosen.get("brep_name"):
            return self.part.CreateReferenceFromName(chosen["brep_name"])
        return self.part.CreateReferenceFromObject(chosen["object"])

    def _choose_subelement(
        self, matches: list[dict[str, Any]], spec: dict[str, Any]
    ) -> dict[str, Any]:
        index = spec.get("index")
        if index is not None:
            if index < 1 or index > len(matches):
                raise IndexError(f"Sub-element index {index} is outside 1..{len(matches)}")
            return matches[index - 1]
        point = spec.get("nearest_point")
        normal = spec.get("normal")
        if point or normal:
            spa = self.conn.active_document.GetWorkbench("SPAWorkbench")
            scored: list[tuple[float, dict[str, Any]]] = []
            for match in matches:
                try:
                    measure = spa.GetMeasurable(match["reference"])
                    score = 0.0
                    if point:
                        # A VARIANT-wrapped array made GetCOG raise where a
                        # plain list at least didn't error - reverted pending
                        # a proper fix. See docs/PLAN.md for the ByRef findings.
                        center = [0.0, 0.0, 0.0]
                        measure.GetCOG(center)
                        # GetCOG returns meters (CATIA's base unit); nearest_point
                        # is supplied in mm like every other coordinate in this API.
                        center_mm = [v * 1000 for v in center]
                        score += math.dist(center_mm, point)
                    if normal:
                        # GetPlane(oComponents) takes ONE 9-element array, not
                        # two 3-element ones: origin xyz(0:3), first in-plane
                        # direction xyz(3:6), second in-plane direction
                        # xyz(6:9) - confirmed against CAA V5's VB help via
                        # pycatia's source. The two directions are the plane's
                        # own in-plane basis vectors, not its normal; the true
                        # face normal is their cross product.
                        components = [0.0] * 9
                        measure.GetPlane(components)
                        d1 = components[3:6]
                        d2 = components[6:9]
                        face_normal = (
                            d1[1] * d2[2] - d1[2] * d2[1],
                            d1[2] * d2[0] - d1[0] * d2[2],
                            d1[0] * d2[1] - d1[1] * d2[0],
                        )
                        length = math.sqrt(sum(v * v for v in face_normal)) or 1.0
                        target_len = math.sqrt(sum(v * v for v in normal)) or 1.0
                        dot = sum(a * b for a, b in zip(face_normal, normal)) / (length * target_len)
                        score += 1000.0 * (1.0 - dot)
                    scored.append((score, match))
                except Exception:
                    continue
            if scored:
                return min(scored, key=lambda item: item[0])[1]
        return matches[0]

    def list_subelements(self, feature_name: str, kind: str) -> list[dict[str, Any]]:
        query = {"edge": "Topology.Edge", "face": "Topology.Face", "vertex": "Topology.Vertex"}.get(
            kind.lower()
        )
        if not query:
            raise ValueError("kind must be feature, face, edge, or vertex")
        obj = self.find_object(feature_name)
        selection = self.conn.hso
        selection.Clear()
        selection.Add(obj)
        try:
            selection.Search(f"{query},sel")
            values = []
            for index in range(1, selection.Count + 1):
                item = selection.Item(index).Value
                name = getattr(item, "Name", f"{kind}.{index}")
                ref = self.part.CreateReferenceFromObject(item)
                brep = getattr(ref, "DisplayName", None)
                values.append(
                    {
                        "index": index,
                        "name": name,
                        "brep_name": brep,
                        "object": item,
                        "reference": ref,
                    }
                )
            return values
        finally:
            selection.Clear()

    def geoset(self, name: str | None = None, create: bool = False) -> Any:
        bodies = self.part.HybridBodies
        requested = name or self.conn.active_geoset_name
        if requested:
            try:
                body = bodies.Item(requested)
                self.conn.active_geoset_name = body.Name
                return body
            except Exception:
                if not create:
                    raise RuntimeError(f"Geometrical set '{requested}' was not found")
        if not requested and bodies.Count:
            body = bodies.Item(bodies.Count)
        else:
            body = bodies.Add()
            body.Name = requested or "Construction Geometry"
        self.conn.active_geoset_name = body.Name
        return body

    def append(
        self, shape: Any, name: str | None = None, geoset: str | None = None
    ) -> dict[str, Any]:
        shape = raw(shape)
        if name:
            shape.Name = name
        container = self.geoset(geoset, create=True)
        container.AppendHybridShape(shape)
        self.part.InWorkObject = shape
        self.update(shape)
        return ref_handle(shape.Name)

    def update(self, feature: Any) -> None:
        try:
            self.part.UpdateObject(raw(feature))
        except Exception as exc:
            name = getattr(raw(feature), "Name", type(feature).__name__)
            raise RuntimeError(f"CATIA failed to update feature '{name}': {exc}") from exc
        self.conn.refresh_display()

    # Normals of the three origin planes, used by direction() for the
    # "xy"/"yz"/"zx" shorthand.
    _PLANE_NORMALS = {"xy": (0.0, 0.0, 1.0), "yz": (1.0, 0.0, 0.0), "zx": (0.0, 1.0, 0.0)}

    def direction(self, spec: str | dict[str, Any]) -> Any:
        """Build a CATIA Direction object (not a Reference) for extrude/sweep-line calls.

        AddNewExtrude's direction argument must be a HybridShapeDirection, not a
        Reference — passing a resolved plane/line Reference fails with a COM
        type-mismatch. Accepts "xy"/"yz"/"zx" (mapped to that plane's normal) or
        an explicit {"x":, "y":, "z":} vector.
        """
        if isinstance(spec, dict) and {"x", "y", "z"} <= spec.keys():
            x, y, z = spec["x"], spec["y"], spec["z"]
        elif isinstance(spec, str) and spec.lower() in self._PLANE_NORMALS:
            x, y, z = self._PLANE_NORMALS[spec.lower()]
        else:
            raise ValueError(
                f"direction must be one of 'xy'/'yz'/'zx' or {{'x':, 'y':, 'z':}}; "
                f"got {spec!r}. Arbitrary reference directions are not yet supported."
            )
        return self.hsf.AddNewDirectionByCoord(x, y, z)


def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


REF_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {"type": "string"},
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "feature": {"type": "string"},
                "kind": {"type": "string", "enum": ["feature", "face", "edge", "vertex"]},
                "index": {"type": "integer", "minimum": 1},
                "brep_name": {"type": "string"},
                "nearest_point": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "normal": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
            },
            "additionalProperties": False,
        },
    ]
}
