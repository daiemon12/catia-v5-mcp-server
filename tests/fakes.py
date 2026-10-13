"""In-memory doubles of the CATIA automation object model (V5 and 3DEXPERIENCE).

They model only what the orchestration code touches. SystemService.Evaluate
is emulated: the VBScript helpers in catia_mcp.automation are recognised by
function name and dispatched to `_out_<Method>` (object out-parameter),
`_fill_<Method>` (filled array) or `_outs_<Method>` (scalar out-parameters)
on the target object.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any


class Coll:
    """1-based CATIA collection with Item(index or name)."""

    def __init__(self, items: list[Any] | None = None) -> None:
        self.items = list(items or [])

    @property
    def Count(self) -> int:  # noqa: N802 - COM naming
        return len(self.items)

    def Item(self, key: Any) -> Any:  # noqa: N802
        if isinstance(key, int):
            if key < 1 or key > len(self.items):
                raise IndexError(key)
            return self.items[key - 1]
        for item in self.items:
            if getattr(item, "Name", None) == key:
                return item
        raise KeyError(key)

    def append(self, item: Any) -> None:
        self.items.append(item)


class PLMObject:
    """VPMReference / VPMRepReference / PLMEntity with PLM attributes."""

    def __init__(self, **attributes: Any) -> None:
        self.attributes = dict(attributes)
        self.Name = attributes.get("PLM_ExternalID", "obj")

    def GetAttributeValue(self, name: str) -> Any:  # noqa: N802
        if name not in self.attributes:
            raise KeyError(name)
        return self.attributes[name]

    def SetAttributeValue(self, name: str, value: Any) -> None:  # noqa: N802
        self.attributes[name] = value


class SystemService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[Any]]] = []

    def Evaluate(self, code: str, language: int, function: str, params: list[Any]) -> Any:  # noqa: N802
        method = re.search(r"o\.([A-Za-z_]\w*)", code)
        self.calls.append((function, method.group(1) if method else "", list(params)))
        target, *args = params
        if function == "catia_mcp_obj":
            return getattr(target, f"_out_{method.group(1)}")(*args)
        if function == "catia_mcp_fill":
            return getattr(target, f"_fill_{method.group(1)}")(*args)
        if function == "catia_mcp_out":
            return getattr(target, f"_outs_{method.group(1)}")(*args)
        if function == "catia_mcp_inertia":
            return [1.5] + [float(i) for i in range(9)]
        raise AssertionError(f"unexpected script function {function}")


class Selection:
    def __init__(self) -> None:
        self.items: list[Any] = []
        self.clipboard: list[Any] | None = None
        self.on_paste = None

    def Clear(self) -> None:  # noqa: N802
        self.items = []

    def Add(self, obj: Any) -> None:  # noqa: N802
        self.items.append(obj)

    @property
    def Count(self) -> int:  # noqa: N802
        return len(self.items)

    def Copy(self) -> None:  # noqa: N802
        Selection.shared_clipboard = list(self.items)

    def Paste(self) -> None:  # noqa: N802
        if self.on_paste:
            self.on_paste(self.items, Selection.shared_clipboard)


Selection.shared_clipboard = None


class Window:
    def __init__(self, app: Any, editor: Any, caption: str) -> None:
        self.app = app
        self.editor = editor
        self.Caption = caption
        self.closed = False
        self.ActiveViewer = SimpleNamespace(Reframe=lambda: None)

    def Activate(self) -> None:  # noqa: N802
        self.app.ActiveEditor = self.editor
        self.app.ActiveWindow = self

    def Close(self) -> None:  # noqa: N802
        self.closed = True


class Editor:
    def __init__(self, active_object: Any, services: dict[str, Any] | None = None) -> None:
        self.ActiveObject = active_object
        self.Selection = Selection()
        self.services = services or {}

    def GetService(self, name: str) -> Any:  # noqa: N802
        if name not in self.services:
            raise RuntimeError(f"service {name} unavailable")
        return self.services[name]


def make_part(name: str = "Part1", rep: PLMObject | None = None) -> SimpleNamespace:
    main_body = SimpleNamespace(Name="PartBody", Shapes=Coll(), Sketches=Coll())
    part = SimpleNamespace(
        Name=name,
        ShapeFactory=SimpleNamespace(),
        HybridShapeFactory=SimpleNamespace(),
        MainBody=main_body,
        Bodies=Coll([main_body]),
        HybridBodies=Coll(),
        Parent=rep if rep is not None else PLMObject(V_Name=name, PLM_ExternalID=f"rep-{name}"),
        InWorkObject=None,
        Update=lambda: None,
    )
    return part


class App3DX:
    """3DEXPERIENCE Application double."""

    Caption = "3DEXPERIENCE R2024x"

    def __init__(self) -> None:
        self.SystemService = SystemService()
        self.Editors = Coll()
        self.Windows = Coll()
        self.ActiveEditor = None
        self.ActiveWindow = None
        self.session_services: dict[str, Any] = {}

    def GetSessionService(self, name: str) -> Any:  # noqa: N802
        if name not in self.session_services:
            raise RuntimeError(f"no session service {name}")
        return self.session_services[name]

    def open_editor(self, active_object: Any, caption: str, services: dict[str, Any] | None = None) -> Editor:
        editor = Editor(active_object, services)
        window = Window(self, editor, caption)
        self.Editors.append(editor)
        self.Windows.append(window)
        window.Activate()
        return editor


class NewService:
    """PLMNewService double: PLMCreate type, oEditor (out-parameter)."""

    def __init__(self, app: App3DX, refuse: tuple[str, ...] = ()) -> None:
        self.app = app
        self.refuse = refuse
        self.created: list[str] = []

    def _out_PLMCreate(self, plm_type: str) -> Any:  # noqa: N802
        if plm_type in self.refuse:
            raise RuntimeError("Operation not authorized")
        self.created.append(plm_type)
        if plm_type == "3DShape":
            obj = make_part("Shape1")
        elif plm_type == "Drawing":
            obj = SimpleNamespace(
                Name="Drawing1",
                Sheets=SimpleNamespace(ActiveSheet=SimpleNamespace(Name="Sheet.1")),
                Parent=PLMObject(V_Name="Drawing1"),
            )
        else:
            raise AssertionError(plm_type)
        return self.app.open_editor(obj, f"{plm_type} window")


class SearchService:
    def __init__(self, results: list[Any]) -> None:
        self.criteria: list[tuple[str, str]] = []
        self.DatabaseSearch = SimpleNamespace(
            BaseType=None,
            AddEasyCriteria=lambda name, value: self.criteria.append((name, value)),
            Results=Coll(results),
        )
        self.searched = 0

    def Search(self) -> None:  # noqa: N802
        self.searched += 1


class OpenService:
    def __init__(self, app: App3DX, make_object) -> None:
        self.app = app
        self.make_object = make_object
        self.opened: list[Any] = []

    def _out_PLMOpen(self, entity: Any) -> Any:  # noqa: N802
        self.opened.append(entity)
        return self.app.open_editor(self.make_object(entity), f"{entity.attributes['V_Name']} window")
