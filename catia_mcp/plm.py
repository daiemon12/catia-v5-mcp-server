"""3DEXPERIENCE PLM session helpers: create, open, save, search, attributes.

Recipes (field-documented for 3DEXPERIENCE automation):

- Create:  CATIA.GetSessionService("PLMNewService").PLMCreate type, oEditor
  with type "3DShape", "3DPart", "Drawing" or "VPMReference" (Physical
  Product). "3DPart" and "VPMReference" need an extra licence/role on many
  sites (macro reports: "Operation not authorized"); "3DShape" and
  "Drawing" are always available. The new content opens in a new editor
  that becomes CATIA.ActiveEditor.
- Open:    CATIA.GetSessionService("Search").DatabaseSearch (BaseType,
  AddEasyCriteria "V_Name", title), Search, .Results (PLMEntities), then
  GetSessionService("PLMOpenService").PLMOpen entity, oEditor.
- Save:    GetSessionService("PLMPropagateService").PLMPropagate saves the
  content of the ACTIVE editor to the 3DSpace database.
- Rename:  rep or reference .SetAttributeValue "V_Name", title.

PLMCreate and PLMOpen return the editor through an out-parameter, so they
run through the SystemService.Evaluate detour (automation.call_out_object).
"""

from __future__ import annotations

from typing import Any

from catia_mcp.automation import (
    call_out_object,
    get_member,
    iter_items,
    name_exists,
    resolves,
    safe_get,
)
from catia_mcp.connection import CATIAConnection
from catia_mcp.errors import AmbiguousTarget, ObjectNotFound, UnsupportedCapability

# Attributes read for search results and attribute reports. Not every type
# carries every attribute; missing ones are skipped.
STANDARD_ATTRIBUTES = (
    "V_Name",
    "PLM_ExternalID",
    "revision",
    "V_description",
    "current",
    "owner",
    "project",
    "organization",
    "originated",
    "modified",
    "V_discipline",
    "V_usage",
)

CREATE_TYPES = {
    "3dpart": "3DPart",
    "3dshape": "3DShape",
    "drawing": "Drawing",
    "vpmreference": "VPMReference",
    "product": "VPMReference",
    "physical_product": "VPMReference",
}


def _not_authorized(error: Exception) -> bool:
    text = str(error).lower()
    return "not authorized" in text or "not allowed" in text or "licen" in text


class PLMSession:
    """3DEXPERIENCE PLM operations bound to one CATIA connection."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    # ── Editors ──

    def editors(self) -> list[Any]:
        app = self.conn.app
        try:
            return list(iter_items(app.Editors))
        except Exception:
            return []

    def editor_count(self) -> int | None:
        try:
            return int(self.conn.app.Editors.Count)
        except Exception:
            try:
                return int(self.conn.app.Windows.Count)
            except Exception:
                return None

    # ── Create / open / save ──

    def create(self, plm_type: str) -> Any:
        """PLMCreate one object and return its (now active) editor."""
        service = self.conn.session_service("PLMNewService")
        before = self.editor_count()
        try:
            editor = call_out_object(self.conn.app, service, "PLMCreate", plm_type)
        except Exception as script_error:
            after = self.editor_count()
            if before is not None and after is not None and after > before:
                # The object was created but the out-parameter could not be
                # read back: the new editor is the active one.
                return self.conn.active_editor
            if _not_authorized(script_error):
                raise
            try:
                # pywin32 with type information returns out-parameters.
                editor = service.PLMCreate(plm_type)
            except Exception:
                raise script_error
        if editor is None or not resolves(editor, "ActiveObject"):
            editor = self.conn.active_editor
        return editor

    def open_entity(self, entity: Any) -> Any:
        service = self.conn.session_service("PLMOpenService")
        before = self.editor_count()
        try:
            editor = call_out_object(self.conn.app, service, "PLMOpen", entity)
        except Exception as script_error:
            after = self.editor_count()
            if before is not None and after is not None and after > before:
                return self.conn.active_editor
            try:
                editor = service.PLMOpen(entity)
            except Exception:
                raise script_error
        if editor is None or not resolves(editor, "ActiveObject"):
            editor = self.conn.active_editor
        return editor

    def propagate(self) -> None:
        """Save the active editor's content to the 3DSpace database."""
        self.conn.session_service("PLMPropagateService").PLMPropagate()

    # ── Search ──

    def search(
        self,
        value: str,
        base_type: str = "VPMReference",
        attribute: str = "V_Name",
        extra_criteria: dict[str, str] | None = None,
    ) -> list[Any]:
        service = self.conn.session_service("Search")
        db_search = service.DatabaseSearch
        # The DatabaseSearch object may persist across searches in a session;
        # clear earlier criteria where the release exposes a way to.
        for clear in ("ClearCriteria", "RemoveAllCriteria", "ResetCriteria"):
            if name_exists(db_search, clear):
                try:
                    getattr(db_search, clear)()
                except Exception:
                    pass
                break
        db_search.BaseType = base_type
        db_search.AddEasyCriteria(attribute, value)
        for name, criterion in (extra_criteria or {}).items():
            db_search.AddEasyCriteria(name, criterion)
        service.Search()
        return list(iter_items(db_search.Results))

    def pick_one(self, entities: list[Any], description: str, index: int | None) -> Any:
        if not entities:
            raise ObjectNotFound(
                f"No {description} found in the 3DEXPERIENCE database. Check the "
                "title (V_Name), the type, and your collaborative space access; '*' "
                "works as a wildcard."
            )
        if index is not None:
            if index < 1 or index > len(entities):
                raise ObjectNotFound(
                    f"index {index} is out of range: the search returned {len(entities)} result(s)."
                )
            return entities[index - 1]
        if len(entities) > 1:
            rows = [self.describe(e, i) for i, e in enumerate(entities[:25], start=1)]
            raise AmbiguousTarget(
                f"{len(entities)} objects match {description}. Nothing was opened; "
                "pass 'index' (1-based) or a 'revision' to pick one: "
                + "; ".join(
                    ", ".join(f"{k}={v}" for k, v in row.items()) for row in rows
                )
            )
        return entities[0]

    # ── Attributes ──

    @staticmethod
    def attribute(obj: Any, name: str) -> Any:
        try:
            value = obj.GetAttributeValue(name)
        except Exception:
            return None
        if value is None or value == "":
            return None
        return value if isinstance(value, (int, float, bool)) else str(value)

    def attributes(self, obj: Any, names: tuple[str, ...] | list[str] = STANDARD_ATTRIBUTES) -> dict[str, Any]:
        result = {}
        for name in names:
            value = self.attribute(obj, name)
            if value is not None:
                result[name] = value
        return result

    def describe(self, entity: Any, index: int | None = None) -> dict[str, Any]:
        row: dict[str, Any] = {}
        if index is not None:
            row["index"] = index
        row.update(self.attributes(entity, ("V_Name", "PLM_ExternalID", "revision", "current", "owner", "modified")))
        if len(row) <= (1 if index is not None else 0):
            row["name"] = str(safe_get(entity, "Name", "<unnamed>"))
        return row

    def set_title(self, obj: Any, title: str) -> bool:
        try:
            obj.SetAttributeValue("V_Name", title)
            return True
        except Exception:
            return False

    # ── Product structure ──

    def reference_of(self, obj: Any) -> Any | None:
        """VPMReference behind an occurrence / instance / reference."""
        if resolves(obj, "ReferenceRootOccurrenceOf"):
            return get_member(obj, "ReferenceRootOccurrenceOf")
        if resolves(obj, "InstanceOccurrenceOf"):
            instance = get_member(obj, "InstanceOccurrenceOf")
            return safe_get(instance, "ReferenceInstanceOf")
        if resolves(obj, "ReferenceInstanceOf"):
            return get_member(obj, "ReferenceInstanceOf")
        if resolves(obj, "Instances") or resolves(obj, "RepInstances"):
            return obj
        return None

    def plm_object_of(self, obj: Any) -> Any | None:
        """The PLM object carrying the attributes of an editor object: the
        VPMReference for products and 3D Parts, the VPMRepReference (the
        Part's / DrawingRoot's Parent) for a 3D Shape or Drawing."""
        reference = self.reference_of(obj)
        if reference is not None:
            return reference
        parent = safe_get(obj, "Parent")
        if parent is not None and resolves(parent, "GetAttributeValue"):
            return parent
        if resolves(obj, "GetAttributeValue"):
            return obj
        return None

    def plm_object_of_active(self) -> Any:
        plm_object = self.plm_object_of(self.conn.active_object())
        if plm_object is None:
            raise UnsupportedCapability(
                "Could not reach the PLM object (VPMReference / VPMRepReference) behind "
                "the active editor's object."
            )
        return plm_object

    def title_of(self, obj: Any) -> str:
        """Display title of an editor object (V_Name, else its Name)."""
        plm_object = self.plm_object_of(obj)
        if plm_object is not None:
            title = self.attribute(plm_object, "V_Name") or self.attribute(plm_object, "PLM_ExternalID")
            if title:
                return str(title)
        return str(safe_get(obj, "Name", "<unnamed>"))

    def occurrence_name(self, occurrence: Any) -> str:
        instance = safe_get(occurrence, "InstanceOccurrenceOf")
        for obj in (instance, occurrence):
            if obj is None:
                continue
            for attr in ("PLM_ExternalID", "V_Name"):
                value = self.attribute(obj, attr)
                if value:
                    return str(value)
            name = safe_get(obj, "Name")
            if name:
                return str(name)
        return "<unnamed>"

    def child_occurrences(self, occurrence: Any) -> list[Any]:
        try:
            return list(iter_items(occurrence.Occurrences))
        except Exception:
            return []

    def find_occurrence(self, root: Any, name: str) -> Any:
        """Depth-first search by instance name (PLM_ExternalID), then title."""
        matches: list[Any] = []

        def visit(occurrence: Any) -> None:
            for child in self.child_occurrences(occurrence):
                instance = safe_get(child, "InstanceOccurrenceOf")
                reference = safe_get(instance, "ReferenceInstanceOf") if instance else None
                names = {self.occurrence_name(child)}
                if reference is not None:
                    title = self.attribute(reference, "V_Name")
                    if title:
                        names.add(str(title))
                if name in names:
                    matches.append(child)
                visit(child)

        visit(root)
        if not matches:
            children = [self.occurrence_name(c) for c in self.child_occurrences(root)]
            raise ObjectNotFound(
                f"No component named '{name}' in the product structure. Top-level "
                f"components: {', '.join(children) or 'none'}. Use catia_list_components."
            )
        if len(matches) > 1:
            raise AmbiguousTarget(
                f"{len(matches)} components are named '{name}'. Use the instance name "
                "(PLM_ExternalID) shown by catia_get_product_tree."
            )
        return matches[0]
