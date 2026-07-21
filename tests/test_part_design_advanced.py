"""Pure-Python tests for advanced Part Design COM call semantics."""

from __future__ import annotations

import json

import pytest

from catia_mcp.tools.part_design_advanced import AdvancedPartDesignTools


class FakeDomain:
    def __init__(self) -> None:
        self.direction = None
        self.faces = []

    def SetPullingDirection(self, x: float, y: float, z: float) -> None:
        self.direction = (x, y, z)

    def AddFaceToDraft(self, face: object) -> None:
        self.faces.append(face)


class FakeDomains:
    def __init__(self, domain: FakeDomain) -> None:
        self.domain = domain

    def Item(self, index: int) -> FakeDomain:
        assert index == 1
        return self.domain


class FakeFeature:
    def __init__(self, name: str, domain: FakeDomain | None = None) -> None:
        self.Name = name
        self.imposed = []
        if domain is not None:
            self.DraftDomains = FakeDomains(domain)

    def AddImposedVertex(self, vertex: object, radius: float) -> None:
        self.imposed.append((vertex, radius))


class FakeShapeFactory:
    def __init__(self) -> None:
        self.calls = []
        self.domain = FakeDomain()
        self.feature = None

    def AddNewSolidEdgeFilletWithVaryingRadius(self, *args: object) -> FakeFeature:
        self.calls.append(("fillet", args))
        self.feature = FakeFeature("VariableFillet.1")
        return self.feature

    def AddNewDraft(self, *args: object) -> FakeFeature:
        self.calls.append(("draft", args))
        self.feature = FakeFeature("Draft.1", self.domain)
        return self.feature


class FakePart:
    def __init__(self) -> None:
        self.InWorkObject = None
        self.empty_reference = object()

    def CreateReferenceFromName(self, name: str) -> object:
        assert name == ""
        return self.empty_reference


class FakePoint:
    Name = ""


class FakeHsf:
    def __init__(self) -> None:
        self.calls = []
        self.point = FakePoint()

    def AddNewPointOnCurveFromPercent(
        self, edge: object, position: float, reverse: bool
    ) -> FakePoint:
        self.calls.append((edge, position, reverse))
        return self.point


class FakeGeoset:
    def __init__(self) -> None:
        self.items = []

    def AppendHybridShape(self, item: object) -> None:
        self.items.append(item)


class FakeGeometry:
    def __init__(self, part: FakePart) -> None:
        self.part = part
        self.updated = []
        self.references = {}
        self.hsf = FakeHsf()
        self.control_geoset = FakeGeoset()

    def resolve(self, spec: object) -> object:
        return self.references.get(str(spec), spec)

    def update(self, feature: object) -> None:
        self.updated.append(feature)

    def geoset(self, name: str, create: bool = False) -> FakeGeoset:
        assert name == "Variable_Fillet_Controls"
        assert create is True
        return self.control_geoset


class FakeConnection:
    def __init__(self) -> None:
        self.shape_factory = FakeShapeFactory()
        self.body = object()

    def get_active_part_body(self) -> object:
        return self.body


class FakeMeasurable:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def GetPointsOnCurve(self, holder: list[float]) -> None:
        holder[:] = self.values

    def GetPoint(self, holder: list[float]) -> None:
        holder[:] = self.values


class FakeSpa:
    def __init__(self, measurements: dict[object, list[float]]) -> None:
        self.measurements = measurements

    def GetMeasurable(self, reference: object) -> FakeMeasurable:
        return FakeMeasurable(self.measurements[reference])


class FakeDocument:
    def __init__(self, spa: FakeSpa) -> None:
        self.spa = spa

    def GetWorkbench(self, name: str) -> FakeSpa:
        assert name == "SPAWorkbench"
        return self.spa


class FakeSlinkyFeature:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.Name = ""
        self.closing = None
        self.points = []

    def SetClosing(self, closing: bool) -> None:
        self.closing = closing

    def AddPoint(self, point: object) -> None:
        self.points.append(point)


class FakeSlinkyHsf:
    def __init__(self) -> None:
        self.calls = []

    def AddNewSpline(self) -> FakeSlinkyFeature:
        feature = FakeSlinkyFeature("spline")
        self.calls.append(("spline", feature))
        return feature

    def AddNewPointCoord(self, x: float, y: float, z: float) -> FakeSlinkyFeature:
        feature = FakeSlinkyFeature("point")
        self.calls.append(("point", (x, y, z), feature))
        return feature

    def AddNewPlane3Points(self, *points: object) -> FakeSlinkyFeature:
        feature = FakeSlinkyFeature("plane")
        self.calls.append(("plane", points, feature))
        return feature

    def AddNewCircleCtrRad(
        self, center: object, plane: object, geodesic: bool, radius: float
    ) -> FakeSlinkyFeature:
        feature = FakeSlinkyFeature("circle")
        self.calls.append(("circle", (center, plane, geodesic, radius), feature))
        return feature

    def AddNewSweepExplicit(self, profile: object, guide: object) -> FakeSlinkyFeature:
        feature = FakeSlinkyFeature("sweep")
        self.calls.append(("sweep", (profile, guide), feature))
        return feature


class FakeSlinkyPart:
    def __init__(self) -> None:
        self.InWorkObject = None
        self.updated = []

    @staticmethod
    def CreateReferenceFromObject(feature: object) -> tuple[str, object]:
        return ("ref", feature)

    def UpdateObject(self, feature: object) -> None:
        self.updated.append(feature)


class FakeSlinkyShapeFactory:
    def __init__(self) -> None:
        self.close_surface_reference = None
        self.solid = FakeSlinkyFeature("solid")

    def AddNewCloseSurface(self, reference: object) -> FakeSlinkyFeature:
        self.close_surface_reference = reference
        return self.solid


class FakeSlinkyConnection:
    def __init__(self) -> None:
        self.shape_factory = FakeSlinkyShapeFactory()
        self.body = object()
        self.refreshed = False

    def get_active_part_body(self) -> object:
        return self.body

    def refresh_display(self) -> None:
        self.refreshed = True


class FakeSlinkyGeometry:
    def __init__(self) -> None:
        self.part = FakeSlinkyPart()
        self.hsf = FakeSlinkyHsf()
        self.container = FakeGeoset()

    def geoset(self, name: str, create: bool = False) -> FakeGeoset:
        assert name == "Smoke_Slinky_Construction"
        assert create is True
        return self.container

    @staticmethod
    def resolve(spec: object) -> object:
        return spec


def make_tools() -> tuple[AdvancedPartDesignTools, FakeConnection, FakeGeometry]:
    connection = FakeConnection()
    tools = AdvancedPartDesignTools(connection)  # type: ignore[arg-type]
    geometry = FakeGeometry(FakePart())
    tools.geo = geometry  # type: ignore[assignment]
    return tools, connection, geometry


def test_variable_fillet_adds_resolved_position_variation(monkeypatch: pytest.MonkeyPatch) -> None:
    tools, connection, geometry = make_tools()
    edge_ref = object()
    endpoint_ref = object()
    edge_spec = {"feature": "Pad.1", "kind": "edge", "index": 1}
    geometry.references[str(edge_spec)] = edge_ref
    monkeypatch.setattr(tools, "_variation_control", lambda *args: endpoint_ref)

    response = json.loads(
        tools.execute(
            "catia_variable_fillet",
            {
                "edge": edge_spec,
                "radius": 4.0,
                "variations": [{"position": 0.25, "radius": 2.0}],
            },
        )
    )

    assert connection.shape_factory.calls == [("fillet", (edge_ref, 1, 1, 4.0))]
    assert connection.shape_factory.feature.imposed == [(endpoint_ref, 2.0)]
    assert response["tool"] == "catia_variable_fillet"


def test_position_variation_builds_point_on_fillet_edge() -> None:
    tools, _connection, geometry = make_tools()
    edge_ref = object()
    point_ref = object()
    geometry.part.CreateReferenceFromObject = lambda point: point_ref  # type: ignore[attr-defined]
    geometry.part.UpdateObject = lambda point: geometry.updated.append(point)  # type: ignore[attr-defined]

    chosen = tools._variation_control(
        edge_ref, {"position": 0.75, "radius": 4.0}, 2, "Variable_Fillet_Controls"
    )

    assert chosen is point_ref
    assert geometry.hsf.calls == [(edge_ref, 0.75, False)]
    assert geometry.hsf.point.Name == "VariableFillet_Control_02"
    assert geometry.control_geoset.items == [geometry.hsf.point]
    assert geometry.updated == [geometry.hsf.point]


def test_advanced_draft_uses_empty_parting_and_adds_extra_faces() -> None:
    tools, connection, geometry = make_tools()
    geometry.references.update(
        {
            "side-1": "side-ref-1",
            "side-2": "side-ref-2",
            "bottom": "bottom-ref",
        }
    )

    tools.execute(
        "catia_advanced_draft",
        {
            "faces": ["side-1", "side-2"],
            "neutral": "bottom",
            "pull_direction": {"x": 0, "y": 0, "z": 10},
            "angle": 5.0,
        },
    )

    call = connection.shape_factory.calls[0]
    assert call[0] == "draft"
    assert call[1] == (
        "side-ref-1",
        "bottom-ref",
        0,
        geometry.part.empty_reference,
        0.0,
        0.0,
        1.0,
        0,
        5.0,
        0,
    )
    assert connection.shape_factory.domain.direction == (0.0, 0.0, 1.0)
    assert connection.shape_factory.domain.faces == ["side-ref-2"]


def test_advanced_draft_preserves_explicit_parting() -> None:
    tools, connection, geometry = make_tools()
    geometry.references.update({"side": "side-ref", "neutral": "neutral-ref", "split": "split-ref"})

    tools.execute(
        "catia_advanced_draft",
        {
            "faces": ["side"],
            "neutral": "neutral",
            "parting": "split",
            "pull_direction": "xy",
            "angle": 3.0,
        },
    )

    assert connection.shape_factory.calls[0][1][3] == "split-ref"


def test_zero_draft_pull_direction_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-zero"):
        AdvancedPartDesignTools._pull_vector({"x": 0, "y": 0, "z": 0})


def test_build_slinky_creates_explicit_sweep_and_closed_surface() -> None:
    connection = FakeSlinkyConnection()
    tools = AdvancedPartDesignTools(connection)  # type: ignore[arg-type]
    geometry = FakeSlinkyGeometry()
    tools.geo = geometry  # type: ignore[assignment]

    response = json.loads(
        tools.execute(
            "catia_build_slinky_from_points",
            {
                "points": [[20, 0, 0], [0, 20, 2], [-20, 0, 4], [0, -20, 6]],
                "wire_radius": 2.0,
                "geoset": "Smoke_Slinky_Construction",
                "guide_name": "Smoke_Slinky_Guide",
                "profile_name": "Smoke_Slinky_Profile",
                "surface_name": "Smoke_Slinky_Surface",
                "solid_name": "Smoke_Slinky_Solid",
            },
        )
    )

    guide = next(call[1] for call in geometry.hsf.calls if call[0] == "spline")
    sweep = next(call[2] for call in geometry.hsf.calls if call[0] == "sweep")
    assert guide.closing is False
    assert len(guide.points) == 4
    assert [call[0] for call in geometry.hsf.calls] == [
        "spline",
        "point",
        "point",
        "point",
        "point",
        "point",
        "point",
        "point",
        "plane",
        "circle",
        "sweep",
    ]
    circle_call = next(call for call in geometry.hsf.calls if call[0] == "circle")
    assert circle_call[1][2:] == (False, 2.0)
    assert connection.shape_factory.close_surface_reference == ("ref", sweep)
    assert connection.shape_factory.solid.Name == "Smoke_Slinky_Solid"
    assert geometry.part.InWorkObject is connection.body
    assert connection.refreshed is True
    assert response == {
        "feature": {"name": "Smoke_Slinky_Solid", "kind": "feature"},
        "guide": {"name": "Smoke_Slinky_Guide", "kind": "feature"},
        "surface": {"name": "Smoke_Slinky_Surface", "kind": "feature"},
        "points": 4,
        "wire_radius": 2.0,
        "tool": "catia_build_slinky_from_points",
    }
