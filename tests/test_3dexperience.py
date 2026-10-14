"""Offline contract tests for the 3DEXPERIENCE port and the platform layer.

These use in-memory doubles (tests/fakes.py). They establish orchestration
contracts (which service is called, in which order, what is refused before
touching CATIA); they do not prove live 3DEXPERIENCE API behavior.
"""

from __future__ import annotations

import asyncio
import json
import math
from types import SimpleNamespace

import pytest

from catia_mcp.connection import PLATFORM_3DX, PLATFORM_V5, CATIAConnection, normalize_platform
from catia_mcp.errors import ObjectNotFound, UnsupportedCapability, WrongDocumentType
from catia_mcp.references import topology_reference
from catia_mcp.server import CATIAMCPServer, parse_args
from catia_mcp.tools.assembly import compose_position
from tests.fakes import (
    App3DX,
    Coll,
    Editor,
    Hole,
    NewService,
    OpenService,
    PLMObject,
    SearchService,
    Selection,
    SystemService,
    VolumeService,
    make_part,
)


def run(coro):
    return asyncio.run(coro)


def server_on(app, platform=PLATFORM_3DX, **kwargs) -> CATIAMCPServer:
    server = CATIAMCPServer(**kwargs)
    server.connection.app = app
    server.connection.platform = platform
    return server


async def call(server: CATIAMCPServer, name: str, arguments: dict | None = None):
    try:
        return await server.call_tool(name, arguments or {})
    finally:
        await server.close()


def text(result) -> str:
    return result.content[0].text


# ── Platform detection ──


def test_platform_detection_and_override():
    conn = CATIAConnection(platform="auto")
    conn.app = SimpleNamespace(Caption="CATIA V5")
    assert conn._detect_platform() == PLATFORM_V5

    conn.app = App3DX()
    assert conn._detect_platform() == PLATFORM_3DX

    forced = CATIAConnection(platform="v5")
    forced.app = App3DX()
    assert forced._detect_platform() == PLATFORM_V5

    assert normalize_platform("3DEXPERIENCE") == PLATFORM_3DX
    assert normalize_platform(None) is None
    with pytest.raises(ValueError):
        normalize_platform("v4")


def test_platform_environment_variable(monkeypatch):
    monkeypatch.setenv("CATIA_MCP_PLATFORM", "3dx")
    conn = CATIAConnection()
    conn.app = SimpleNamespace(Caption="CATIA V5")
    assert conn._detect_platform() == PLATFORM_3DX


def test_cli_platform_and_scripts_flags():
    args = parse_args(["--platform", "3dx", "--allow-scripts"])
    assert args.platform == "3dx" and args.allow_scripts is True
    assert parse_args([]).allow_scripts is False
    with pytest.raises(SystemExit):
        parse_args(["--platform", "nope"])


# ── Part resolution ──


def _connected(app, platform=PLATFORM_3DX) -> CATIAConnection:
    conn = CATIAConnection(platform=platform)
    conn.app = app
    conn.platform = platform
    return conn


def _v5_app(part, workbench=None):
    """CATIA V5 Application double with one active Part document."""
    document = SimpleNamespace(Part=part, Selection=Selection(), GetWorkbench=lambda name: workbench)
    return SimpleNamespace(
        Caption="CATIA V5",
        ActiveDocument=document,
        ActiveWindow=SimpleNamespace(ActiveViewer=SimpleNamespace(Reframe=lambda: None)),
    )


def _app_with_part(part, platform, services=None):
    if platform == PLATFORM_V5:
        return _v5_app(part)
    app = App3DX()
    app.open_editor(part, "Shape", services)
    return app


def test_3d_shape_level_active_object_is_the_part():
    app = App3DX()
    part = make_part()
    app.open_editor(part, "Shape")
    assert _connected(app).get_active_part() is part


def test_3d_part_level_walks_reference_to_shape_representation():
    app = App3DX()
    part = make_part()
    rep_ref = SimpleNamespace(GetItem=lambda kind: part if kind == "Part" else None)
    drawing_rep = SimpleNamespace(GetItem=lambda kind: (_ for _ in ()).throw(RuntimeError("no")))
    reference = SimpleNamespace(
        RepInstances=Coll([
            SimpleNamespace(ReferenceInstanceOf=lambda: drawing_rep),
            SimpleNamespace(ReferenceInstanceOf=lambda: rep_ref),
        ])
    )
    root = SimpleNamespace(ReferenceRootOccurrenceOf=lambda: reference)
    app.open_editor(root, "3D Part")
    assert _connected(app).get_active_part() is part


def test_product_without_shape_and_drawing_are_wrong_document_type():
    app = App3DX()
    reference = SimpleNamespace(RepInstances=Coll())
    app.open_editor(SimpleNamespace(ReferenceRootOccurrenceOf=lambda: reference), "Product")
    with pytest.raises(WrongDocumentType, match="Physical Product"):
        _connected(app).get_active_part()

    app.open_editor(SimpleNamespace(Sheets=Coll()), "Drawing")
    with pytest.raises(WrongDocumentType, match="Drawing"):
        _connected(app).get_active_part()


def test_selection_comes_from_the_active_editor():
    app = App3DX()
    editor = app.open_editor(make_part(), "Shape")
    assert _connected(app).hso is editor.Selection


def test_stale_active_body_fails_instead_of_switching_body():
    app = App3DX()
    part = make_part()
    second = SimpleNamespace(Name="Body.2", Shapes=Coll(), Sketches=Coll())
    part.Bodies.append(second)
    app.open_editor(part, "Shape")
    conn = _connected(app)
    assert conn.set_active_body("Body.2") is second
    assert conn.get_active_part_body() is second
    part.Bodies.items.remove(second)
    with pytest.raises(ObjectNotFound, match="no longer exists"):
        conn.get_active_part_body()
    assert conn.get_active_part_body() is part.MainBody


# ── Document tools ──


def test_new_part_falls_back_to_3d_shape_and_sets_title():
    app = App3DX()
    service = NewService(app, refuse=("3DPart",))
    app.session_services["PLMNewService"] = service
    server = server_on(app)
    result = run(call(server, "catia_new_part", {"name": "Bracket"}))
    assert not result.isError, text(result)
    assert service.created == ["3DShape"]
    assert "3DShape 'Bracket'" in text(result) and "not authorized" in text(result)
    assert app.ActiveEditor.ActiveObject.Parent.attributes["V_Name"] == "Bracket"


def test_new_part_with_explicit_type_does_not_fall_back():
    app = App3DX()
    app.session_services["PLMNewService"] = NewService(app, refuse=("3DPart",))
    result = run(call(server_on(app), "catia_new_part", {"plm_type": "3DPart"}))
    assert result.isError and "refused" in result.structuredContent["message"]


def test_plm_type_is_rejected_on_v5():
    app = SimpleNamespace(Caption="CATIA V5", Documents=SimpleNamespace(Add=lambda kind: pytest.fail("created")))
    result = run(call(server_on(app, PLATFORM_V5), "catia_new_part", {"plm_type": "3DShape"}))
    assert result.structuredContent["code"] == "INVALID_ARGUMENT"
    assert result.structuredContent["effects"]["modified"] is False


def test_save_propagates_and_refuses_file_path_before_touching_catia():
    app = App3DX()
    propagated = []
    app.session_services["PLMPropagateService"] = SimpleNamespace(PLMPropagate=lambda: propagated.append(1))
    app.open_editor(make_part("Bracket"), "Shape")

    refused = run(call(server_on(app), "catia_save_document", {"file_path": "C:/x.CATPart"}))
    assert refused.structuredContent["code"] == "INVALID_ARGUMENT" and propagated == []

    saved = run(call(server_on(app), "catia_save_document"))
    assert not saved.isError and propagated == [1]
    assert "database" in text(saved)


def test_list_documents_reports_editors():
    app = App3DX()
    app.open_editor(make_part("Bracket"), "Bracket A.1")
    app.open_editor(SimpleNamespace(Sheets=Coll(), Parent=PLMObject(V_Name="DWG-1")), "DWG-1")
    result = run(call(server_on(app), "catia_list_documents"))
    assert '"type": "part"' in text(result) and '"type": "drawing"' in text(result)
    assert "DWG-1" in text(result)


def test_activate_document_by_caption_and_ambiguity():
    app = App3DX()
    first = app.open_editor(make_part("Bracket"), "Bracket A.1 - Part Design")
    app.open_editor(make_part("Base"), "Base A.1 - Part Design")
    ok = run(call(server_on(app), "catia_activate_document", {"name": "Bracket"}))
    assert not ok.isError and app.ActiveEditor is first
    ambiguous = run(call(server_on(app), "catia_activate_document", {"name": "Part Design"}))
    assert ambiguous.structuredContent["code"] == "AMBIGUOUS_TARGET"


# ── Database search / open ──


def _entities():
    return [
        PLMObject(V_Name="Bracket", PLM_ExternalID="prd-1", revision="A.1"),
        PLMObject(V_Name="Bracket", PLM_ExternalID="prd-1", revision="B.1"),
    ]


def test_open_from_database_refuses_to_guess_then_opens_the_chosen_index():
    app = App3DX()
    entities = _entities()
    app.session_services["Search"] = SearchService(entities)
    opener = OpenService(app, lambda entity: make_part(entity.attributes["V_Name"]))
    app.session_services["PLMOpenService"] = opener

    ambiguous = run(call(server_on(app), "catia_open_from_database", {"title": "Bracket"}))
    assert ambiguous.structuredContent["code"] == "AMBIGUOUS_TARGET"
    assert opener.opened == [] and "B.1" in ambiguous.structuredContent["message"]

    opened = run(call(server_on(app), "catia_open_from_database", {"title": "Bracket", "index": 2}))
    assert not opened.isError, text(opened)
    assert opener.opened == [entities[1]]
    assert app.SystemService.calls[-1][:2] == ("catia_mcp_obj", "PLMOpen")


def test_search_database_returns_attributes_and_criteria():
    app = App3DX()
    search = SearchService(_entities())
    app.session_services["Search"] = search
    result = run(call(server_on(app), "catia_search_database", {"query": "Brack*", "max_results": 1}))
    assert '"total": 2' in text(result) and '"returned": 1' in text(result)
    assert search.criteria == [("V_Name", "Brack*")] and search.DatabaseSearch.BaseType == "VPMReference"


def test_database_tools_refuse_on_v5():
    app = SimpleNamespace(Caption="CATIA V5")
    result = run(call(server_on(app, PLATFORM_V5), "catia_search_database", {"query": "x"}))
    assert result.structuredContent["code"] == "INVALID_ARGUMENT"


def test_set_plm_attributes_reports_applied_and_failed():
    app = App3DX()
    part = make_part("Bracket")
    app.open_editor(part, "Shape")
    original = part.Parent.SetAttributeValue

    def guarded(name, value):
        if name == "owner":
            raise RuntimeError("read-only")
        original(name, value)

    part.Parent.SetAttributeValue = guarded
    result = run(call(server_on(app), "catia_set_plm_attributes",
                      {"attributes": {"V_description": "Rev B", "owner": "me"}}))
    assert not result.isError
    assert '"V_description": "Rev B"' in text(result) and "read-only" in text(result)


# ── Assembly ──


def test_compose_position_rotates_axes_about_own_origin():
    identity = [1, 0, 0, 0, 1, 0, 0, 0, 1, 10, 20, 30]
    moved = compose_position(identity, (1, 2, 3), (0, 0, 90))
    assert [round(v, 9) for v in moved[0:3]] == [0, 1, 0]  # X axis -> +Y
    assert [round(v, 9) for v in moved[3:6]] == [-1, 0, 0]  # Y axis -> -X
    assert moved[6:9] == [0, 0, 1]
    assert moved[9:] == [11, 22, 33]
    assert compose_position(identity, (0, 0, 0), (0, 0, 0)) == identity


def test_v5_list_and_move_components_read_positions_through_evaluate():
    position_values = [1, 0, 0, 0, 1, 0, 0, 0, 1, 5, 6, 7]
    written = []
    position = SimpleNamespace(
        _fill_GetComponents=lambda: list(position_values),
        SetComponents=lambda m: written.append(list(m)),
    )
    component = SimpleNamespace(Name="Bolt.1", PartNumber="Bolt", Position=position)
    product = SimpleNamespace(Products=Coll([component]))
    app = SimpleNamespace(
        Caption="CATIA V5",
        SystemService=SystemService(),
        ActiveDocument=SimpleNamespace(Product=product),
        ActiveWindow=SimpleNamespace(ActiveViewer=SimpleNamespace(Reframe=lambda: None)),
    )
    listed = run(call(server_on(app, PLATFORM_V5), "catia_list_components"))
    assert '"x": 5' in text(listed) and '"z": 7' in text(listed)

    moved = run(call(server_on(app, PLATFORM_V5), "catia_move_component",
                     {"component_name": "Bolt.1", "tx": 1, "rz": 90}))
    assert not moved.isError, text(moved)
    assert [round(v, 9) for v in written[0][:3]] == [0, 1, 0]  # rotation kept orthonormal
    assert written[0][9:] == [6, 6, 7]


def test_3dx_constraints_report_unsupported_without_touching_the_model():
    app = App3DX()
    result = run(call(server_on(app), "catia_fix_constraint", {"component_name": "x"}))
    assert result.structuredContent["code"] == "UNSUPPORTED_CAPABILITY"
    assert result.structuredContent["effects"]["modified"] is False


def test_insert_existing_component_pastes_under_root_and_verifies_count():
    app = App3DX()
    children: list = []
    target_root = SimpleNamespace(
        ReferenceRootOccurrenceOf=lambda: SimpleNamespace(RepInstances=Coll()),
        Occurrences=Coll(children),
    )
    product_service = SimpleNamespace(RootOccurrence=target_root)
    target = app.open_editor(target_root, "Assembly", {"PLMProductService": product_service})
    target.Selection.on_paste = lambda selected, clipboard: target_root.Occurrences.append(
        SimpleNamespace(Name="Bracket.1", InstanceOccurrenceOf=None)
    )
    entity = PLMObject(V_Name="Bracket", PLM_ExternalID="prd-1", revision="A.1")
    app.session_services["Search"] = SearchService([entity])

    def make_source(_entity):
        return SimpleNamespace(ReferenceRootOccurrenceOf=lambda: SimpleNamespace(RepInstances=Coll()))

    app.session_services["PLMOpenService"] = OpenService(app, make_source)
    result = run(call(server_on(app), "catia_insert_existing_component", {"title": "Bracket"}))
    assert not result.isError, text(result)
    assert "0 -> 1 children" in text(result)
    assert app.ActiveEditor is target
    assert app.Windows.Item(2).closed is True


# ── Measurement backend ──


def test_3dx_volume_uses_type_library_enum_code(monkeypatch):
    import catia_mcp.measure as measure_module

    monkeypatch.setattr(
        measure_module,
        "find_enum",
        lambda objs, name: {"CATMeasurableUnknown": 0, "CATMeasurableVolume": 7, "CATMeasurablePoint": 8},
    )
    requested = []

    def get_measurable(target, code):
        requested.append(code)
        if code != 7:
            raise RuntimeError("wrong type")
        return SimpleNamespace(GetVolume=lambda: 2.4e-4, GetArea=lambda: 0.0272)

    app = App3DX()
    part = make_part()
    part.CreateReferenceFromObject = lambda obj: obj
    app.open_editor(part, "Shape", {"MeasurableService": SimpleNamespace(GetMeasurable=get_measurable)})
    measurer = measure_module.Measurer(_connected(app))
    assert measurer.volume_mm3(part, part.MainBody) == pytest.approx(240000.0)
    assert requested == [7]
    assert measurer.area_mm2(part, part.MainBody) == pytest.approx(27200.0)
    assert requested == [7, 7]  # cached code tried first


def test_3dx_point_reads_scalar_out_parameters():
    from catia_mcp.measure import Measurer

    app = App3DX()
    measurable = SimpleNamespace(GetPoint=lambda *a: None, _outs_GetPoint=lambda: [1.0, 2.0, 3.0])
    service = SimpleNamespace(GetMeasurable=lambda target, code: measurable)
    app.open_editor(make_part(), "Shape", {"MeasurableService": service})
    measurer = Measurer(_connected(app))
    measurer._enum_read, measurer._enum = True, None
    assert measurer.point_mm(object()) == [1.0, 2.0, 3.0]


# CATMeasurableType as read live from R428 SP6.
_R428_MEASURABLE_TYPES = {
    "CAAMeasurableAxisSystem": 0, "CAAMeasurableBetween": 1, "CAAMeasurableCircle": 2,
    "CAAMeasurableCone": 3, "CAAMeasurableCurve": 4, "CAAMeasurableCylinder": 5,
    "CAAMeasurableLine": 6, "CAAMeasurablePlane": 7, "CAAMeasurablePoint": 8,
    "CAAMeasurableSphere": 9, "CAAMeasurableSurface": 10, "CAAMeasurableVolume": 11,
}


def test_3dx_center_of_gravity_uses_get_cofg(monkeypatch):
    """R428 MeasurableVolume has GetCOfG(oX, oY, oZ), not V5's GetCOG."""
    import catia_mcp.measure as measure_module

    monkeypatch.setattr(measure_module, "find_enum", lambda objs, name: dict(_R428_MEASURABLE_TYPES))
    measurable = SimpleNamespace(GetVolume=lambda: 2.36e-4, GetCOfG=None,
                                 _outs_GetCOfG=lambda: [0.0, 0.0, 20.17])
    service = SimpleNamespace(GetMeasurable=lambda target, code: measurable)
    app = App3DX()
    part = make_part()
    part.CreateReferenceFromObject = lambda obj: obj
    app.open_editor(part, "Shape", {"MeasurableService": service})
    cog = measure_module.Measurer(_connected(app)).cog_mm(part, part.MainBody)
    assert cog == [0.0, 0.0, 20.17]
    assert app.SystemService.calls[-1][:2] == ("catia_mcp_out", "GetCOfG")


def _between_service(axis, requested):
    """MeasurableService whose CAAMeasurableBetween measures 50 mm (live R428
    values for P1 (0,0,60) -> P2 (50,0,60))."""
    distance_calls = []

    def get_measurable(target, code):
        requested.append(code)
        return SimpleNamespace(
            DistanceMinTo=None,
            _fill_GetAxisSystemFromMeasurable=lambda: list(axis),
            _outs_DistanceMinTo=lambda other, other_axis: (
                distance_calls.append((target, other, list(other_axis)))
                or [50.0, 0.0, 0.0, 60.0, 50.0, 0.0, 60.0]
            ),
        )

    return SimpleNamespace(GetMeasurable=get_measurable), distance_calls


def test_3dx_min_distance_uses_measurable_between_in_mm(monkeypatch):
    import catia_mcp.measure as measure_module

    monkeypatch.setattr(measure_module, "find_enum", lambda objs, name: dict(_R428_MEASURABLE_TYPES))
    axis = [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]
    requested: list = []
    service, distance_calls = _between_service(axis, requested)
    app = App3DX()
    app.open_editor(make_part(), "Shape", {"MeasurableService": service})
    ref1, ref2 = object(), object()

    measured = measure_module.Measurer(_connected(app)).min_distance(ref1, ref2)
    assert measured == {
        "distance_mm": 50.0, "point1_mm": [0.0, 0.0, 60.0], "point2_mm": [50.0, 0.0, 60.0],
    }
    assert set(requested) == {1}  # chosen by enum name, no trial of other types
    assert distance_calls == [(ref1, ref2, axis)]  # other element's own axis system


def test_measure_distance_tool_resolves_faces_and_reports_points(monkeypatch):
    import catia_mcp.measure as measure_module

    monkeypatch.setattr(measure_module, "find_enum", lambda objs, name: dict(_R428_MEASURABLE_TYPES))
    service, distance_calls = _between_service([0] * 12, [])
    app = App3DX()
    part = make_part()
    part.MainBody.topology = {"Face": [SimpleNamespace(Reference=f"face-ref-{i}") for i in range(1, 7)]}
    part.MainBody.Shapes.append(SimpleNamespace(Name="Pad.1"))
    app.open_editor(part, "Shape", {"MeasurableService": service})

    result = run(call(server_on(app), "catia_measure_distance",
                      {"element1": "Face.1", "element2": "Face.2"}))
    assert not result.isError, text(result)
    assert ": 50.0000 mm; closest points (0, 0, 60) and (50, 0, 60) mm" in text(result)
    assert distance_calls[0][:2] == ("face-ref-1", "face-ref-2")


def _boolean_last_part(last_faces):
    """A body whose last shape is a boolean: R428 exposes no cells on Add.1
    but 15 faces on the body."""
    part = make_part()
    body = part.MainBody
    body.topology = {"Face": [SimpleNamespace(Reference=f"body-{i}") for i in range(1, 16)]}
    body.Shapes.append(SimpleNamespace(Name="Pad.1", topology={"Face": ["pad"] * 6}))
    body.Shapes.append(SimpleNamespace(Name="Add.1", topology={"Face": last_faces}))
    return part


@pytest.mark.parametrize("platform", [PLATFORM_V5, PLATFORM_3DX])
def test_topology_after_a_boolean_comes_from_the_body(platform):
    """V5 falls back to the body when the last shape exposes no cells;
    3DEXPERIENCE always searches the body."""
    app = _app_with_part(_boolean_last_part([]), platform)
    listed = run(call(server_on(app, platform), "catia_list_faces"))
    assert not listed.isError and len(json.loads(text(listed))) == 15
    assert topology_reference(_connected(app, platform), "Face", 15) == "body-15"


def test_v5_topology_keeps_the_last_shape_enumeration_when_it_has_cells():
    last = [SimpleNamespace(Reference=f"last-{i}") for i in range(1, 4)]
    app = _v5_app(_boolean_last_part(last))
    listed = run(call(server_on(app, PLATFORM_V5), "catia_list_faces"))
    assert len(json.loads(text(listed))) == 3
    assert topology_reference(_connected(app, PLATFORM_V5), "Face", 2) == "last-2"


def _cells(kind, refs):
    return {kind: [SimpleNamespace(Reference=ref) for ref in refs]}


def test_3dx_topology_comes_from_the_body_when_the_last_feature_is_a_hole():
    """Live R428: with a Hole last, the last-shape search returns only the
    hole's own cells (2 faces); the body search returns the final solid
    (14 faces for a block with 4 holes)."""
    part = make_part()
    body = part.MainBody
    corners = [(x, y, z) for x in (0.0, 100.0) for y in (0.0, 60.0) for z in (0.0, 40.0)]
    body.topology = {
        **_cells("Face", [f"body-face-{i}" for i in range(1, 15)]),
        **_cells("Edge", [f"body-edge-{i}" for i in range(1, 21)]),
        **_cells("Vertex", corners),
    }
    body.Shapes.append(SimpleNamespace(Name="Pad.1"))
    body.Shapes.append(SimpleNamespace(Name="Hole.4", topology={
        **_cells("Face", ["hole-face-1", "hole-face-2"]),
        **_cells("Edge", ["hole-edge-1", "hole-edge-2", "hole-edge-3"]),
        **_cells("Vertex", [(80.0, 30.0, 40.0), (80.0, 30.0, 20.0)]),
    }))
    points = SimpleNamespace(GetMeasurable=lambda ref, code: SimpleNamespace(
        GetPoint=None, _outs_GetPoint=lambda: list(ref)))
    app = _app_with_part(part, PLATFORM_3DX, {"MeasurableService": points})

    faces = run(call(server_on(app), "catia_list_faces"))
    assert len(json.loads(text(faces))) == 14
    edges = run(call(server_on(app), "catia_list_edges"))
    assert len(json.loads(text(edges))) == 20
    box = run(call(server_on(app), "catia_get_bounding_box"))
    assert json.loads(text(box))["dimensions"] == {"length_x": 100.0, "length_y": 60.0, "length_z": 40.0}
    assert topology_reference(_connected(app), "Face", 14) == "body-face-14"


# ── Part Design: hole effect, user pattern seeds ──

_BLOCK_MM3 = 240000.0  # 100 x 60 x 40 mm smoke block
_D8_DEPTH20_MM3 = math.pi / 4 * 8**2 * 20  # 1005.3 mm3


def _drilled_block(drills_material_when_reversed):
    """Part holding the block. Updating a hole removes its cylinder when its
    direction (reversed or not) is in `drills_material_when_reversed`, and
    nothing otherwise (drilled into air)."""
    volume = VolumeService(_BLOCK_MM3)
    part = make_part()
    part.MainBody.Shapes.append(SimpleNamespace(Name="Pad.1"))
    part.MainBody.Sketches.append(SimpleNamespace(Name="Sketch.2"))
    holes: list = []

    def add_hole(sketch, depth):
        hole = Hole(f"Hole.{len(holes) + 1}")
        holes.append(hole)
        part.MainBody.Shapes.append(hole)
        return hole

    def update(obj):
        volume.volume_mm3 = _BLOCK_MM3 - sum(
            math.pi / 4 * h.Diameter.Value**2 * h.BottomLimit.Dimension.Value
            for h in holes
            if h.reversed in drills_material_when_reversed
        )

    part.ShapeFactory = SimpleNamespace(AddNewHoleFromSketch=add_hole)
    part.UpdateObject = update
    return part, holes, volume


def _hole_server(drills_material_when_reversed):
    part, holes, volume = _drilled_block(drills_material_when_reversed)
    app = _app_with_part(part, PLATFORM_3DX, {"MeasurableService": volume})
    return server_on(app), part, holes


def test_hole_sets_the_depth_explicitly_and_reports_the_removed_volume():
    server, _, holes = _hole_server({False})
    result = run(call(server, "catia_hole", {"diameter": 8, "depth": 20}))
    assert not result.isError, text(result)
    assert holes[0].BottomLimit.Dimension.Value == 20  # R428 kept 10 from the factory
    assert holes[0].reverse_calls == 0
    assert "depth 20 mm" in text(result)
    assert f"Removed {_D8_DEPTH20_MM3:.1f} mm3 (240000.0 -> {_BLOCK_MM3 - _D8_DEPTH20_MM3:.1f})" in text(result)


def test_hole_drilled_into_air_is_reversed_once_and_verified():
    server, _, holes = _hole_server({True})
    result = run(call(server, "catia_hole", {"diameter": 8, "depth": 20}))
    assert not result.isError, text(result)
    assert holes[0].reverse_calls == 1
    assert "direction reversed" in text(result)
    assert f"Removed {_D8_DEPTH20_MM3:.1f} mm3" in text(result)


def test_hole_removing_nothing_either_way_is_feature_no_effect():
    server, _, holes = _hole_server(set())
    result = run(call(server, "catia_hole", {"diameter": 8, "depth": 20}))
    assert result.isError
    assert result.structuredContent["code"] == "FEATURE_NO_EFFECT"
    assert result.structuredContent["effects"]["modified"] is None
    assert holes[0].reverse_calls == 1  # one reversal tried, no more
    assert "Hole.1" in result.structuredContent["message"]


class _IgnoredLength:
    """Length parameter whose writes CATIA ignores."""

    Value = property(lambda self: 10.0, lambda self, value: None)


def test_hole_depth_that_does_not_take_is_wrong_geometry_effect():
    server, part, _ = _hole_server({False})
    create = part.ShapeFactory.AddNewHoleFromSketch

    def stuck(sketch, depth):
        hole = create(sketch, depth)
        hole.BottomLimit.Dimension = _IgnoredLength()
        return hole

    part.ShapeFactory.AddNewHoleFromSketch = stuck
    result = run(call(server, "catia_hole", {"diameter": 8, "depth": 20}))
    assert result.structuredContent["code"] == "WRONG_GEOMETRY_EFFECT"
    assert result.structuredContent["effects"]["modified"] is None


def test_hole_with_a_non_positive_depth_is_refused_untouched():
    server, _, holes = _hole_server({False})
    result = run(call(server, "catia_hole", {"diameter": 8, "depth": 0}))
    assert result.structuredContent["code"] == "INVALID_ARGUMENT"
    assert result.structuredContent["effects"]["modified"] is False
    assert holes == []


def test_v5_hole_sets_the_depth_and_measures_through_the_spa_workbench():
    part, holes, volume = _drilled_block({False})
    part.CreateReferenceFromObject = lambda obj: obj
    spa = SimpleNamespace(GetMeasurable=lambda ref: SimpleNamespace(Volume=volume.volume_mm3 / 1e9))
    result = run(call(server_on(_v5_app(part, spa), PLATFORM_V5), "catia_hole",
                      {"diameter": 8, "depth": 20}))
    assert not result.isError, text(result)
    assert holes[0].BottomLimit.Dimension.Value == 20 and holes[0].reverse_calls == 0
    assert f"Removed {_D8_DEPTH20_MM3:.1f} mm3" in text(result)


def _pattern_part(seed):
    part = make_part()
    part.MainBody.Shapes.append(seed)
    part.MainBody.Sketches.append(SimpleNamespace(Name="Sketch.3"))
    created = []

    def add_pattern(feature, count):
        pattern = SimpleNamespace(Name="UserPattern.1", located=[])
        pattern.AddFeatureToLocatePositions = pattern.located.append
        created.append((feature, count, pattern))
        return pattern

    part.ShapeFactory = SimpleNamespace(AddNewUserPattern=add_pattern)
    part.UpdateObject = lambda obj: None
    return part, created


def test_3dx_user_pattern_of_a_hole_is_unsupported_and_untouched():
    part, created = _pattern_part(Hole("Hole.1"))
    app = _app_with_part(part, PLATFORM_3DX)
    result = run(call(server_on(app), "catia_user_pattern", {"count": 3, "sketch_name": "Sketch.3"}))
    assert result.structuredContent["code"] == "UNSUPPORTED_CAPABILITY"
    assert result.structuredContent["effects"]["modified"] is False
    assert created == []
    message = result.structuredContent["message"]
    assert "Hole.1" in message and "catia_pocket" in message


@pytest.mark.parametrize(
    ("platform", "seed"),
    [(PLATFORM_3DX, SimpleNamespace(Name="Pocket.1")), (PLATFORM_V5, Hole("Hole.1"))],
)
def test_user_pattern_still_runs_for_other_seeds_and_on_v5(platform, seed):
    part, created = _pattern_part(seed)
    app = _app_with_part(part, platform)
    result = run(call(server_on(app, platform), "catia_user_pattern",
                      {"count": 3, "sketch_name": "Sketch.3"}))
    assert not result.isError, text(result)
    (feature, count, pattern), = created
    assert feature is seed and count == 3
    assert [s.Name for s in pattern.located] == ["Sketch.3"]


# ── Part Design: pocket, slot and rib effect ──

_PLATFORMS = [PLATFORM_V5, PLATFORM_3DX]


def _measured_server(part, volume, platform):
    """Server on `platform` whose body volume measurement reads `volume`."""
    if platform == PLATFORM_V5:
        part.CreateReferenceFromObject = lambda obj: obj
        spa = SimpleNamespace(GetMeasurable=lambda ref: SimpleNamespace(Volume=volume.volume_mm3 / 1e9))
        return server_on(_v5_app(part, spa), PLATFORM_V5)
    return server_on(_app_with_part(part, PLATFORM_3DX, {"MeasurableService": volume}))


def _pocketed_block(cuts_when_oriented):
    """Part holding the block. Updating a pocket cuts a D8 x 20 mm cylinder
    when its DirectionOrientation is in `cuts_when_oriented`, and nothing
    otherwise (cut on the side away from the solid). Each pocket records its
    orientation at every update."""
    volume = VolumeService(_BLOCK_MM3)
    part = make_part()
    part.MainBody.Shapes.append(SimpleNamespace(Name="Pad.1"))
    part.MainBody.Sketches.append(SimpleNamespace(Name="Sketch.2"))
    pockets: list = []

    def add_pocket(sketch, depth):
        pocket = SimpleNamespace(Name=f"Pocket.{len(pockets) + 1}", DirectionOrientation=None, updates=[])
        pockets.append(pocket)
        part.MainBody.Shapes.append(pocket)
        return pocket

    def update(obj):
        obj.updates.append(obj.DirectionOrientation)
        volume.volume_mm3 = _BLOCK_MM3 - sum(
            _D8_DEPTH20_MM3 for p in pockets if p.DirectionOrientation in cuts_when_oriented
        )

    part.ShapeFactory = SimpleNamespace(AddNewPocket=add_pocket)
    part.UpdateObject = update
    return part, pockets, volume


@pytest.mark.parametrize("platform", _PLATFORMS)
def test_pocket_removing_material_reports_the_removed_volume(platform):
    part, pockets, volume = _pocketed_block({0})
    result = run(call(_measured_server(part, volume, platform), "catia_pocket", {"depth": 20}))
    assert not result.isError, text(result)
    assert pockets[0].updates == [0]
    assert (
        f"Pocket 'Pocket.1' created: 20 mm deep. Removed {_D8_DEPTH20_MM3:.1f} mm3 "
        f"(240000.0 -> {_BLOCK_MM3 - _D8_DEPTH20_MM3:.1f})."
    ) == text(result)


@pytest.mark.parametrize("platform", _PLATFORMS)
def test_pocket_cutting_into_air_is_flipped_once_and_verified(platform):
    part, pockets, volume = _pocketed_block({1})
    result = run(call(_measured_server(part, volume, platform), "catia_pocket", {"depth": 20}))
    assert not result.isError, text(result)
    assert pockets[0].updates == [0, 1]
    assert "direction auto-flipped" in text(result)
    assert f"Removed {_D8_DEPTH20_MM3:.1f} mm3" in text(result)


@pytest.mark.parametrize("platform", _PLATFORMS)
def test_pocket_removing_nothing_in_an_explicit_direction_is_feature_no_effect(platform):
    # The other side would cut, but an explicit direction is never flipped.
    part, pockets, volume = _pocketed_block({0})
    result = run(call(_measured_server(part, volume, platform), "catia_pocket",
                      {"depth": 20, "direction": "reverse"}))
    assert result.isError
    assert result.structuredContent["code"] == "FEATURE_NO_EFFECT"
    assert result.structuredContent["effects"]["modified"] is None
    assert pockets[0].updates == [1]
    message = result.structuredContent["message"]
    assert "Pocket.1" in message and "in the requested direction" in message
    assert "240000.0 mm3" in message and "profile intersects the solid" in message


@pytest.mark.parametrize("platform", _PLATFORMS)
def test_pocket_removing_nothing_either_way_is_feature_no_effect(platform):
    part, pockets, volume = _pocketed_block(set())
    result = run(call(_measured_server(part, volume, platform), "catia_pocket", {"depth": 20}))
    assert result.isError
    assert result.structuredContent["code"] == "FEATURE_NO_EFFECT"
    assert result.structuredContent["effects"]["modified"] is None
    assert pockets[0].updates == [0, 1, 0]  # one flip tried, then the requested side restored
    message = result.structuredContent["message"]
    assert "Pocket.1" in message and "in either direction" in message
    assert "240000.0 mm3" in message and "profile intersects the solid" in message


def _swept_block(delta_mm3):
    """Part holding the block, a profile sketch and a center-curve sketch.
    Updating a rib or slot changes the block volume by `delta_mm3`."""
    volume = VolumeService(_BLOCK_MM3)
    part = make_part()
    part.MainBody.Shapes.append(SimpleNamespace(Name="Pad.1"))
    for name in ("Profile", "Spine"):
        part.MainBody.Sketches.append(SimpleNamespace(Name=name))
    created: list = []

    def factory(kind):
        def add(profile, center):
            feature = SimpleNamespace(Name=f"{kind}.1")
            created.append((feature.Name, profile.Name, center.Name))
            part.MainBody.Shapes.append(feature)
            return feature

        return add

    def update(obj):
        volume.volume_mm3 = _BLOCK_MM3 + delta_mm3

    part.ShapeFactory = SimpleNamespace(AddNewRib=factory("Rib"), AddNewSlot=factory("Slot"))
    part.UpdateObject = update
    return part, created, volume


_SWEEP_ARGS = {"profile": "Profile", "center_curve": "Spine"}


@pytest.mark.parametrize("platform", _PLATFORMS)
@pytest.mark.parametrize(
    ("tool", "feature", "delta"),
    [("catia_slot", "Slot.1", -1000.0), ("catia_rib", "Rib.1", 1000.0)],
)
def test_sweep_with_the_required_material_change_reports_the_volumes(platform, tool, feature, delta):
    part, created, volume = _swept_block(delta)
    result = run(call(_measured_server(part, volume, platform), tool, _SWEEP_ARGS))
    assert not result.isError, text(result)
    assert created == [(feature, "Profile", "Spine")]
    assert text(result) == (
        f"{feature.split('.')[0]} '{feature}' created along 'Spine'. "
        f"Volume 240000.0 -> {_BLOCK_MM3 + delta:.1f} mm3."
    )


@pytest.mark.parametrize("platform", _PLATFORMS)
@pytest.mark.parametrize(
    ("tool", "feature", "effect"),
    [("catia_slot", "Slot.1", "removed no material"), ("catia_rib", "Rib.1", "added no material")],
)
def test_sweep_changing_no_material_is_feature_no_effect(platform, tool, feature, effect):
    part, created, volume = _swept_block(0.0)
    result = run(call(_measured_server(part, volume, platform), tool, _SWEEP_ARGS))
    assert result.isError
    assert result.structuredContent["code"] == "FEATURE_NO_EFFECT"
    assert result.structuredContent["effects"]["modified"] is None
    assert created == [(feature, "Profile", "Spine")]
    message = result.structuredContent["message"]
    assert f"'{feature}'" in message and effect in message and "240000.0" in message


# ── Drawing factory binding ──


def _params(*names_and_types):
    return [{"name": n, "type": t, "out": False, "optional": False} for n, t in names_and_types]


# R428 SP6 type information (live) and DSYAutomation.chm R428.
_FRONT_VIEW = _params(
    ("iXPos", "double"), ("iYpos", "double"), ("iListofPrdInst", "array"), ("iPlane", "array"),
    ("iViewStyle", "string"), ("iComputeUpdate", "bool"), ("iViewProp", "object"),
)
_PROJECTION_VIEW = _params(
    ("iXPos", "double"), ("iYpos", "double"), ("iParentView", "object"), ("iType", "int"),
    ("iViewStyle", "string"), ("iComputeUpdate", "bool"), ("iViewProp", "object"),
)


def test_drawing_factory_binds_arguments_by_name(monkeypatch):
    import catia_mcp.tools.drawing as drawing_module

    calls = []
    factory = SimpleNamespace(DefineFrontView=lambda *a: calls.append(a) or "VIEW")
    monkeypatch.setattr(drawing_module, "method_params", lambda obj, method: _FRONT_VIEW)
    tools = drawing_module.DraftingTools(_connected(App3DX()))
    source, prop = object(), object()
    resolved = []
    values = {
        "ixpos": 10.0, "IYPOS": 20.0,  # names match case-insensitively
        "iPlane": [1, 0, 0, 0, 1, 0], "iListofPrdInst": [source],
        "iViewStyle": "", "iComputeUpdate": True,
        "iViewProp": drawing_module._Lazy(lambda: resolved.append(1) or prop),
    }
    assert tools._bind_factory_call(factory, "DefineFrontView", values) == "VIEW"
    assert calls == [(10.0, 20.0, [source], [1, 0, 0, 0, 1, 0], "", True, prop)]
    assert resolved == [1]

    # A parameter this tool cannot name refuses before calling, and lazy
    # values a refused signature never asks for are never resolved.
    del values["iListofPrdInst"]
    resolved.clear()
    with pytest.raises(UnsupportedCapability, match="iListofPrdInst"):
        tools._bind_factory_call(factory, "DefineFrontView", values)
    assert len(calls) == 1 and resolved == []


def test_3dx_projection_view_passes_anchor_parent_type_and_view_properties(monkeypatch):
    import catia_mcp.tools.drawing as drawing_module

    monkeypatch.setattr(drawing_module, "method_params", lambda obj, method: _PROJECTION_VIEW)
    app = App3DX()
    prop = object()
    app.session_services["CATDrawingGenService"] = SimpleNamespace(DrawingGenViewProp=prop)
    parent = SimpleNamespace(Name="Front View", x=100.0, y=80.0, Scale=1.0, IsGenerative=lambda: True)
    views = Coll([SimpleNamespace(Name="Main"), SimpleNamespace(Name="Background"), parent])
    calls = []

    def define_projection(*args):
        calls.append(args)
        view = SimpleNamespace(Name="View", x=0.0, y=0.0, Scale=1.0, Update=lambda: None)
        views.append(view)
        return view

    views.DrawingDefineGenView = SimpleNamespace(DefineProjectionView=define_projection)
    sheet = SimpleNamespace(Name="Sheet.1", Views=views, ProjectionMethod=1)
    app.open_editor(SimpleNamespace(Sheets=SimpleNamespace(ActiveSheet=sheet)), "Drawing")

    result = run(call(server_on(app), "catia_drawing_projection_view", {"direction": "right"}))
    assert not result.isError, text(result)
    assert calls == [(200.0, 80.0, parent, 0, "", True, prop)]  # third angle: right of parent
    assert views.Item(4).Name == "right view" and views.Item(4).x == 200.0


def _factory_drawing(app, define_front_view):
    views = Coll([SimpleNamespace(Name="Main"), SimpleNamespace(Name="Background")])
    views.DrawingDefineGenView = SimpleNamespace(DefineFrontView=define_front_view)
    sheet = SimpleNamespace(Name="Sheet.1", Views=views)
    app.open_editor(SimpleNamespace(Sheets=SimpleNamespace(ActiveSheet=sheet)), "Drawing")
    return views


def _product_root(title="Bracket Assy"):
    reference = PLMObject(V_Name=title, PLM_ExternalID="prd-9")
    reference.RepInstances = Coll()
    return SimpleNamespace(Name="root", ReferenceRootOccurrenceOf=lambda: reference)


def test_3dx_front_view_projects_the_product_root_occurrence(monkeypatch):
    import catia_mcp.tools.drawing as drawing_module

    monkeypatch.setattr(drawing_module, "method_params", lambda obj, method: _FRONT_VIEW)
    app = App3DX()
    prop = object()
    app.session_services["CATDrawingGenService"] = SimpleNamespace(DrawingGenViewProp=prop)
    root = _product_root()
    app.open_editor(root, "Bracket Assy")
    calls = []

    def define_front_view(*args):
        calls.append(args)
        view = SimpleNamespace(Name="FRONT", x=0.0, y=0.0, Scale=1.0, Update=lambda: None)
        views.append(view)
        return view

    views = _factory_drawing(app, define_front_view)
    result = run(call(server_on(app), "catia_drawing_add_view", {"plane": "yz"}))
    assert not result.isError, text(result)
    assert calls == [(300.0, 150.0, [root], [0.0, 1.0, 0.0, 0.0, 0.0, 1.0], "", True, prop)]
    assert views.Item(3).Name == "Front View" and "Bracket Assy" in text(result)


def test_3dx_front_view_finds_a_3d_part_by_its_title_from_a_shape_level_editor(monkeypatch):
    """Live R428: a 3D Part edited at shape level shows its 3D Shape in the
    editor, so the user's title is the enclosing product's."""
    import catia_mcp.tools.drawing as drawing_module

    monkeypatch.setattr(drawing_module, "method_params", lambda obj, method: _FRONT_VIEW)
    app = App3DX()
    app.session_services["CATDrawingGenService"] = SimpleNamespace(DrawingGenViewProp=object())
    root = _product_root("TEST PART, CLAUDE")
    shape = make_part("3D Shape00565980")
    app.open_editor(shape, "TEST PART, CLAUDE A",
                    {"PLMProductService": SimpleNamespace(RootOccurrence=root)})
    calls = []

    def define_front_view(*args):
        calls.append(args)
        view = SimpleNamespace(Name="FRONT", x=0.0, y=0.0, Scale=1.0, Update=lambda: None)
        views.append(view)
        return view

    views = _factory_drawing(app, define_front_view)
    result = run(call(server_on(app), "catia_drawing_add_view", {"part_name": "TEST PART, CLAUDE"}))
    assert not result.isError, text(result)
    assert calls[0][2] == [root]
    assert "of 'TEST PART, CLAUDE'" in text(result)


def test_3dx_front_view_refuses_a_standalone_3d_shape_untouched(monkeypatch):
    import catia_mcp.tools.drawing as drawing_module

    monkeypatch.setattr(drawing_module, "method_params", lambda obj, method: _FRONT_VIEW)
    app = App3DX()
    app.open_editor(make_part("Bracket"), "Bracket")  # no product service: standalone
    views = _factory_drawing(app, lambda *a: pytest.fail("factory called"))
    result = run(call(server_on(app), "catia_drawing_add_view", {"part_name": "Bracket"}))
    assert result.structuredContent["code"] == "UNSUPPORTED_CAPABILITY"
    assert result.structuredContent["effects"]["modified"] is False
    assert "standalone 3D Shape" in result.structuredContent["message"]
    assert views.Count == 2


def test_3dx_front_view_silently_rejected_is_no_effect_and_untouched(monkeypatch):
    import catia_mcp.tools.drawing as drawing_module

    monkeypatch.setattr(drawing_module, "method_params", lambda obj, method: _FRONT_VIEW)
    app = App3DX()
    app.session_services["CATDrawingGenService"] = SimpleNamespace(DrawingGenViewProp=object())
    app.open_editor(_product_root(), "Bracket Assy")
    _factory_drawing(app, lambda *a: None)  # live R428: no error, no view
    result = run(call(server_on(app), "catia_drawing_add_view", {}))
    assert result.structuredContent["code"] == "FEATURE_NO_EFFECT"
    assert result.structuredContent["effects"]["modified"] is False


def test_projection_without_a_user_view_is_object_not_found_and_untouched():
    app = App3DX()
    views = Coll([SimpleNamespace(Name="Main"), SimpleNamespace(Name="Background")])
    views.DrawingDefineGenView = SimpleNamespace()
    sheet = SimpleNamespace(Name="Sheet.1", Views=views)
    app.open_editor(SimpleNamespace(Sheets=SimpleNamespace(ActiveSheet=sheet)), "Drawing")
    result = run(call(server_on(app), "catia_drawing_projection_view", {"direction": "right"}))
    assert result.structuredContent["code"] == "OBJECT_NOT_FOUND"
    assert result.structuredContent["effects"]["modified"] is False


# ── Export ──


def test_3dx_refused_export_data_is_unsupported_and_untouched(tmp_path):
    app = App3DX()
    app.open_editor(make_part(), "Shape")

    def refuse(path, fmt):
        raise RuntimeError("The method ExportData failed")  # live R428 SP6 message

    app.ActiveDocument = SimpleNamespace(ExportData=refuse)
    result = run(call(server_on(app), "catia_export", {"file_path": str(tmp_path / "a.stp")}))
    assert result.structuredContent["code"] == "UNSUPPORTED_CAPABILITY"
    assert result.structuredContent["effects"]["modified"] is False
    assert "Export command" in result.structuredContent["message"]


def test_export_without_a_written_file_fails_on_both_platforms(tmp_path):
    silent = SimpleNamespace(ExportData=lambda path, fmt: None)
    app_3dx = App3DX()
    app_3dx.open_editor(make_part(), "Shape")
    app_3dx.ActiveDocument = silent
    app_v5 = SimpleNamespace(Caption="CATIA V5", ActiveDocument=silent)
    for app, platform in ((app_3dx, PLATFORM_3DX), (app_v5, PLATFORM_V5)):
        result = run(call(server_on(app, platform), "catia_export",
                          {"file_path": str(tmp_path / "missing.stp")}))
        assert result.isError and "wrote no file" in result.structuredContent["message"]


def test_export_does_not_count_a_stale_file_as_written(tmp_path):
    stale = tmp_path / "old.stp"
    stale.write_text("previous export")
    app = SimpleNamespace(Caption="CATIA V5", ActiveDocument=SimpleNamespace(ExportData=lambda p, f: None))
    result = run(call(server_on(app, PLATFORM_V5), "catia_export", {"file_path": str(stale)}))
    assert result.isError and "wrote no file" in result.structuredContent["message"]


def test_export_reports_the_written_file(tmp_path):
    def write(path, fmt):
        with open(path, "w") as fh:
            fh.write("ISO-10303-21;")

    app = SimpleNamespace(Caption="CATIA V5", ActiveDocument=SimpleNamespace(ExportData=write))
    result = run(call(server_on(app, PLATFORM_V5), "catia_export", {"file_path": str(tmp_path / "b.stp")}))
    assert not result.isError, text(result)
    assert "(13 bytes) (format: STP)" in text(result)


# ── Introspection ──


class _FakeTypeInfo:
    """ITypeInfo double: one method with an out parameter and one property."""

    def __init__(self):
        self.funcs = [
            SimpleNamespace(memid=1, invkind=1, wFuncFlags=0, args=((5, 1, None), (9, 2, None))),
            SimpleNamespace(memid=2, invkind=2, wFuncFlags=0, args=()),
            SimpleNamespace(memid=3, invkind=4, wFuncFlags=0, args=((8, 1, None),)),
        ]
        self.names = {1: ("GetThing", "iValue", "oResult"), 2: ("Title",), 3: ("Title", "value")}

    def GetTypeAttr(self):  # noqa: N802
        return (None, 0, 0, 0, 0, 4, len(self.funcs), 0, 0)

    def GetFuncDesc(self, j):  # noqa: N802
        return self.funcs[j]

    def GetNames(self, memid):  # noqa: N802
        return self.names[memid]

    def GetDocumentation(self, index):  # noqa: N802
        return ("ThingService", "", 0, "")


class _FakeEnumInfo:
    def GetTypeAttr(self):  # noqa: N802
        return (None, 0, 0, 0, 0, 0, 0, 2, 0)

    def GetVarDesc(self, j):  # noqa: N802
        return SimpleNamespace(memid=j, value=[0, 8][j])

    def GetNames(self, memid):  # noqa: N802
        return (["CATMeasurableUnknown", "CATMeasurablePoint"][memid],)


class _FakeTypeLib:
    def GetTypeInfoCount(self):  # noqa: N802
        return 2

    def GetTypeInfoType(self, i):  # noqa: N802
        return [4, 0][i]

    def GetDocumentation(self, i):  # noqa: N802
        return (["ThingService", "CATMeasurableType"][i], "", 0, "")

    def GetTypeInfo(self, i):  # noqa: N802
        return _FakeEnumInfo()


def _com_double():
    info = _FakeTypeInfo()
    info.GetContainingTypeLib = lambda: (_FakeTypeLib(), 0)
    return SimpleNamespace(_oleobj_=SimpleNamespace(GetTypeInfo=lambda: info))


def test_introspection_reads_members_and_enums():
    from catia_mcp.introspect import describe_members, find_enum, list_enums

    obj = _com_double()
    members = {m["name"]: m for m in describe_members(obj)}
    assert members["Title"] == {"name": "Title", "kind": "property", "readable": True, "writable": True}
    assert members["GetThing"]["params"] == [
        {"name": "iValue", "type": "double", "out": False, "optional": False},
        {"name": "oResult", "type": "object", "out": True, "optional": False},
    ]
    assert find_enum([obj], "catmeasurabletype") == {"CATMeasurableUnknown": 0, "CATMeasurablePoint": 8}
    assert list_enums([obj]) == ["CATMeasurableType"]


def test_inspect_api_tool_allows_getters_only():
    app = App3DX()
    app.open_editor(make_part(), "Shape")
    app.Thing = _com_double()
    ok = run(call(server_on(app), "catia_inspect_api", {"path": "app.Thing", "filter": "get"}))
    assert not ok.isError and "GetThing" in text(ok) and "Title" not in text(ok)
    refused = run(call(server_on(app), "catia_inspect_api", {"path": "app.Quit()"}))
    assert refused.structuredContent["code"] == "INVALID_ARGUMENT"


def test_run_script_is_disabled_unless_allowed():
    app = App3DX()
    denied = run(call(server_on(app), "catia_run_script", {"code": "Function CATMain()\nEnd Function"}))
    assert denied.structuredContent["code"] == "PERMISSION_DENIED"
    assert app.SystemService.calls == []

    app.SystemService.Evaluate = lambda code, lang, fn, params: [fn, *params]
    allowed = run(call(server_on(app, allow_scripts=True), "catia_run_script",
                       {"code": "x", "function": "Go", "args": [1, "a"]}))
    assert not allowed.isError and '"Go"' in text(allowed)


# ── Error contract ──


def test_unsupported_message_mentions_3dexperience_resources(monkeypatch):
    app = App3DX()
    server = server_on(app)

    def boom(name, arguments):
        raise AttributeError("AddNewPad")

    monkeypatch.setattr(server.part_design_tools, "execute", boom)
    result = run(call(server, "catia_pad", {"height": 10}))
    message = result.structuredContent["message"]
    assert result.structuredContent["code"] == "UNSUPPORTED_CAPABILITY"
    assert "catia_inspect_api" in message and "DSYAutomation.chm" in message


def test_v5_editor_free_tools_unchanged_on_v5():
    """V5 sessions never touch 3DEXPERIENCE services."""
    docs = SimpleNamespace(Count=0)
    app = SimpleNamespace(Caption="CATIA V5", Documents=docs)
    result = run(call(server_on(app, PLATFORM_V5), "catia_list_documents"))
    assert text(result) == "No documents open in CATIA"


def test_editor_double_is_not_mistaken_for_a_part():
    assert CATIAConnection.classify(Editor(None)) == "other"
    assert CATIAConnection.classify(make_part()) == "part"


# ── Effects truthfulness ──


def test_lookup_failure_after_point_creation_reports_unknown_modification():
    app = App3DX()
    part = make_part()
    created = []
    geoset = SimpleNamespace(
        Name="GSD_Set",
        HybridShapes=Coll(),
        HybridSketches=Coll(),
        HybridBodies=Coll(),
        AppendHybridShape=lambda shape: created.append(shape),
    )
    part.HybridBodies = Coll([geoset])
    part.HybridShapeFactory = SimpleNamespace(AddNewPointCoord=lambda x, y, z: SimpleNamespace(Name="Point.1"))
    part.UpdateObject = lambda obj: None
    part.CreateReferenceFromObject = lambda obj: obj
    part.OriginElements = SimpleNamespace()
    app.open_editor(part, "Shape")

    result = run(call(server_on(app), "catia_gsd_line", {"point1": [0, 0, 0], "point2": "Missing"}))
    assert result.structuredContent["code"] == "OBJECT_NOT_FOUND"
    assert created and result.structuredContent["effects"]["modified"] is None

    untouched = run(call(server_on(app), "catia_gsd_line", {"point1": "Missing", "point2": "Other"}))
    assert untouched.structuredContent["effects"]["modified"] is False


def test_failure_after_plm_create_does_not_claim_untouched(monkeypatch):
    app = App3DX()
    app.session_services["PLMNewService"] = NewService(app)
    server = server_on(app)

    def broken_part():
        raise WrongDocumentType("no part")

    monkeypatch.setattr(server.connection, "get_active_part", broken_part)
    result = run(call(server, "catia_new_part", {"plm_type": "3DShape"}))
    assert result.structuredContent["code"] == "WRONG_DOCUMENT_TYPE"
    assert result.structuredContent["effects"]["modified"] is None
