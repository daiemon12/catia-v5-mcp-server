"""Offline contract tests for the 3DEXPERIENCE port and the platform layer.

These use in-memory doubles (tests/fakes.py). They establish orchestration
contracts (which service is called, in which order, what is refused before
touching CATIA); they do not prove live 3DEXPERIENCE API behavior.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from catia_mcp.connection import PLATFORM_3DX, PLATFORM_V5, CATIAConnection, normalize_platform
from catia_mcp.errors import ObjectNotFound, UnsupportedCapability, WrongDocumentType
from catia_mcp.server import CATIAMCPServer, parse_args
from catia_mcp.tools.assembly import compose_position
from tests.fakes import (
    App3DX,
    Coll,
    Editor,
    NewService,
    OpenService,
    PLMObject,
    SearchService,
    SystemService,
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


def _connected(app) -> CATIAConnection:
    conn = CATIAConnection(platform="3dx")
    conn.app = app
    conn.platform = PLATFORM_3DX
    return conn


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


# ── Drawing factory binding ──


def test_drawing_factory_binds_arguments_by_kind(monkeypatch):
    import catia_mcp.tools.drawing as drawing_module

    calls = []
    factory = SimpleNamespace(DefineFrontView=lambda *a: calls.append(a) or "VIEW")
    monkeypatch.setattr(
        drawing_module,
        "method_params",
        lambda obj, method: [
            {"name": "i3DObject", "type": "object", "out": False, "optional": False},
            *({"name": n, "type": "double", "out": False, "optional": False}
              for n in ("iX1", "iY1", "iZ1", "iX2", "iY2", "iZ2")),
        ],
    )
    tools = drawing_module.DraftingTools(_connected(App3DX()))
    source = object()
    assert tools._bind_factory_call(factory, "DefineFrontView",
                                    {"object": [source], "double": [1, 0, 0, 0, 1, 0]}) == "VIEW"
    assert calls == [(source, 1, 0, 0, 0, 1, 0)]

    with pytest.raises(UnsupportedCapability, match="i3DObject"):
        tools._bind_factory_call(factory, "DefineFrontView", {"double": [1, 0, 0, 0, 1, 0]})


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
