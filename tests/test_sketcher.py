from __future__ import annotations

from catia_mcp.tools.sketcher import SketcherTools


class FakeDimension:
    Value = None


class FakeConstraint:
    def __init__(self) -> None:
        self.Dimension = FakeDimension()


class FakeConstraints:
    def __init__(self) -> None:
        self.calls: list[tuple[int, object]] = []

    def AddMonoEltCst(self, constraint_type: int, reference: object) -> FakeConstraint:
        self.calls.append((constraint_type, reference))
        return FakeConstraint()


class FakeGeometry:
    def Item(self, index: int) -> str:
        assert index == 2
        return "Circle.1"


class FakeSketch:
    Constraints = FakeConstraints()
    GeometricElements = FakeGeometry()


class FakePart:
    def CreateReferenceFromObject(self, geometry: object) -> tuple[str, object]:
        return ("reference", geometry)


class FakeConnection:
    def get_active_part(self) -> FakePart:
        return FakePart()


def test_radius_constraint_uses_a_part_reference() -> None:
    tools = SketcherTools(FakeConnection())
    sketch = FakeSketch()
    tools._active_sketch = sketch

    result = tools._add_constraint(
        {"type": "radius", "geometry_index_1": 2, "value": 20.0}
    )

    assert result == "Radius constraint added: 20.0 mm"
    assert sketch.Constraints.calls == [(14, ("reference", "Circle.1"))]
