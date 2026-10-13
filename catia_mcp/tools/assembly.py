"""Assembly tools for CATIA V5 and CATIA 3DEXPERIENCE.

V5: Product/Assembly management: add components, constraints (Fix,
Coincidence, Offset, Angle), move components, and list the product tree.

3DEXPERIENCE: the product structure is VPMReference / VPMInstance /
VPMOccurrence. Listing and moving work through occurrences and instance
Positions. The automation API lost its add/remove structure methods after
2013x, so components are inserted by copy/paste through the editor
selections (catia_insert_existing_component, catia_add_new_part); this route
is verified by counting child occurrences before and after. Assembly
constraints became engineering connections, which the documented automation
API does not create; those tools report UNSUPPORTED_CAPABILITY there.

Positions: Position.GetComponents fills an in/out array, which does not
marshal through late-bound COM, so it is read through the
SystemService.Evaluate detour. The 12 components are the X, Y and Z axis
vectors followed by the origin, in mm.
"""

from __future__ import annotations

import json
import math
from typing import Any

from catia_mcp.automation import call_fill_array, safe_get
from catia_mcp.connection import PLATFORM_3DX, CATIAConnection
from catia_mcp.errors import UnsupportedCapability, after_mutation
from catia_mcp.plm import PLMSession


def compose_position(
    matrix: list[float],
    translation: tuple[float, float, float],
    rotation_deg: tuple[float, float, float],
) -> list[float]:
    """Rotate a component about its own origin, then translate it.

    `matrix` is CATIA's 12-value position: X axis (0-2), Y axis (3-5),
    Z axis (6-8), origin (9-11). The rotation applies about the global X,
    then Y, then Z directions (Q = Rz * Ry * Rx) to each axis vector; the
    origin only moves by the translation.
    """
    rx, ry, rz = (math.radians(a) for a in rotation_deg)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    q = (
        (cy * cz, cz * sx * sy - cx * sz, sx * sz + cx * cz * sy),
        (cy * sz, cx * cz + sx * sy * sz, cx * sy * sz - cz * sx),
        (-sy, cy * sx, cx * cy),
    )
    result = list(matrix)
    for axis in range(3):
        v = matrix[3 * axis: 3 * axis + 3]
        for row in range(3):
            result[3 * axis + row] = q[row][0] * v[0] + q[row][1] * v[1] + q[row][2] * v[2]
    result[9] = matrix[9] + translation[0]
    result[10] = matrix[10] + translation[1]
    result[11] = matrix[11] + translation[2]
    return result


class AssemblyTools:
    """Tools for assembly (Product) operations in CATIA V5 and 3DEXPERIENCE."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.plm = PLMSession(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_add_component",
                "description": (
                    "V5: add an existing CATPart or CATProduct file as a component in the "
                    "active assembly, inserted at the origin. On 3DEXPERIENCE use "
                    "catia_insert_existing_component (database content)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path to the .CATPart or .CATProduct file to add",
                        },
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "catia_add_new_part",
                "description": (
                    "Create a new empty Part directly inside the active assembly. "
                    "3DEXPERIENCE: creates a 3D Part (licence/role permitting) and pastes "
                    "it under the active product, verified by the child count; the new "
                    "part's own editor stays open for modeling."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the new part component",
                        },
                    },
                },
            },
            {
                "name": "catia_insert_existing_component",
                "description": (
                    "3DEXPERIENCE only: insert an existing Physical Product / 3D Part from "
                    "the database under the root of the active product (open it, copy, "
                    "paste; verified by the child count). Refuses to guess between "
                    "several matches: pass revision or index."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title (V_Name) of the object to insert"},
                        "revision": {"type": "string", "description": "Optional revision"},
                        "index": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "1-based result index when several objects match",
                        },
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "catia_fix_constraint",
                "description": (
                    "V5: fix a component in place (remove all degrees of freedom). "
                    "Typically applied to the base/reference component."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "component_name": {
                            "type": "string",
                            "description": "Name of the component to fix",
                        },
                    },
                    "required": ["component_name"],
                },
            },
            {
                "name": "catia_coincidence_constraint",
                "description": (
                    "V5: create a Coincidence constraint between two components. "
                    "Aligns axes, planes, or points of two components."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "component1": {
                            "type": "string",
                            "description": "Name of first component",
                        },
                        "component2": {
                            "type": "string",
                            "description": "Name of second component",
                        },
                        "element1": {
                            "type": "string",
                            "description": "Geometry element on component1 (e.g., 'xy plane', 'Face.1')",
                        },
                        "element2": {
                            "type": "string",
                            "description": "Geometry element on component2",
                        },
                    },
                    "required": ["component1", "component2"],
                },
            },
            {
                "name": "catia_offset_constraint",
                "description": (
                    "V5: create an Offset constraint between two faces/planes of two "
                    "components. Maintains a constant distance between the reference elements."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "component1": {
                            "type": "string",
                            "description": "Name of first component",
                        },
                        "component2": {
                            "type": "string",
                            "description": "Name of second component",
                        },
                        "offset": {
                            "type": "number",
                            "description": "Offset distance in mm",
                        },
                    },
                    "required": ["component1", "component2", "offset"],
                },
            },
            {
                "name": "catia_angle_constraint",
                "description": "V5: create an Angle constraint between two components.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "component1": {
                            "type": "string",
                            "description": "Name of first component",
                        },
                        "component2": {
                            "type": "string",
                            "description": "Name of second component",
                        },
                        "angle": {
                            "type": "number",
                            "description": "Angle in degrees",
                        },
                    },
                    "required": ["component1", "component2", "angle"],
                },
            },
            {
                "name": "catia_move_component",
                "description": (
                    "Move a component by translation and/or rotation. "
                    "Translation in mm, rotation in degrees about the global X, then Y, "
                    "then Z directions, applied around the component's own origin. "
                    "3DEXPERIENCE: name is the instance name (PLM_ExternalID) or title."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "component_name": {
                            "type": "string",
                            "description": "Name of the component to move",
                        },
                        "tx": {"type": "number", "description": "Translation X (mm)", "default": 0},
                        "ty": {"type": "number", "description": "Translation Y (mm)", "default": 0},
                        "tz": {"type": "number", "description": "Translation Z (mm)", "default": 0},
                        "rx": {"type": "number", "description": "Rotation around X (degrees)", "default": 0},
                        "ry": {"type": "number", "description": "Rotation around Y (degrees)", "default": 0},
                        "rz": {"type": "number", "description": "Rotation around Z (degrees)", "default": 0},
                    },
                    "required": ["component_name"],
                },
            },
            {
                "name": "catia_list_components",
                "description": "List the components of the active assembly/product with their names and positions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_list_constraints",
                "description": (
                    "List assembly constraints (V5) or engineering connections "
                    "(3DEXPERIENCE) of the active product."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_add_component":
                return self._add_component(arguments["file_path"])
            case "catia_add_new_part":
                return self._add_new_part(arguments.get("name"))
            case "catia_insert_existing_component":
                return self._insert_existing(arguments)
            case "catia_fix_constraint":
                return self._fix_constraint(arguments["component_name"])
            case "catia_coincidence_constraint":
                return self._coincidence_constraint(arguments)
            case "catia_offset_constraint":
                return self._offset_constraint(arguments)
            case "catia_angle_constraint":
                return self._angle_constraint(arguments)
            case "catia_move_component":
                return self._move_component(arguments)
            case "catia_list_components":
                return self._list_components()
            case "catia_list_constraints":
                return self._list_constraints()
            case _:
                raise ValueError(f"Unknown assembly tool: {tool_name}")

    # ── Shared helpers ──

    def _read_position(self, position: Any) -> list[float]:
        return call_fill_array(self.conn.app, position, "GetComponents", 12)

    def _constraints_unsupported(self, tool: str) -> None:
        if self.conn.is_3dx:
            raise UnsupportedCapability(
                f"{tool}: 3DEXPERIENCE replaced V5 assembly constraints with engineering "
                "connections, which the documented automation API does not create. Add "
                "the constraint in the UI (Assembly Design / Mechanical Systems), or use "
                "catia_move_component to position components."
            )

    # ── Add components ──

    def _add_component(self, file_path: str) -> str:
        if self.conn.is_3dx:
            raise UnsupportedCapability(
                "3DEXPERIENCE components come from the database, not files: use "
                "catia_insert_existing_component (title from catia_search_database)."
            )
        product = self.conn.get_active_product()
        products = product.Products
        products.AddComponentsFromFiles([file_path], "All")
        self.conn.refresh_display()
        return f"Component added from: {file_path}"

    def _add_new_part(self, name: str | None = None) -> str:
        if self.conn.is_3dx:
            return self._paste_under_root(
                lambda: self.plm.create("3DPart"), name, "new 3D Part", close_source=False
            )
        product = self.conn.get_active_product()
        products = product.Products
        new_product = products.AddNewProduct("Part")
        if name:
            new_product.Name = name
        self.conn.refresh_display()
        return f"New Part component created in assembly: '{new_product.Name}'"

    def _insert_existing(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        self.conn.require_platform(PLATFORM_3DX, "catia_insert_existing_component")
        extra = {"revision": args["revision"]} if args.get("revision") else None
        entities = self.plm.search(args["title"], "VPMReference", "V_Name", extra)
        entity = self.plm.pick_one(entities, f"product/part titled '{args['title']}'", args.get("index"))
        return self._paste_under_root(
            lambda: self.plm.open_entity(entity), None, f"'{args['title']}'", close_source=True
        )

    def _paste_under_root(self, open_source: Any, name: str | None, label: str, close_source: bool) -> str:
        """Open/create the source in its own editor, copy its root occurrence
        and paste it under the target's root occurrence; verify by count."""
        app = self.conn.app
        target_window = app.ActiveWindow
        target_editor = self.conn.active_editor
        target_root = self.conn.root_occurrence(target_editor)
        before = len(self.plm.child_occurrences(target_root))

        open_source()
        with after_mutation():
            return self._copy_paste(app, target_window, target_editor, before, name, label, close_source)

    def _copy_paste(
        self,
        app: Any,
        target_window: Any,
        target_editor: Any,
        before: int,
        name: str | None,
        label: str,
        close_source: bool,
    ) -> str:
        source_window = app.ActiveWindow
        source_editor = self.conn.active_editor
        source_root = self.conn.root_occurrence(source_editor)
        if name:
            reference = self.plm.reference_of(source_root)
            if reference is not None:
                self.plm.set_title(reference, name)
        source_sel = source_editor.Selection
        source_sel.Clear()
        source_sel.Add(source_root)
        source_sel.Copy()
        source_sel.Clear()

        target_window.Activate()
        target_root = self.conn.root_occurrence(target_editor)
        target_sel = target_editor.Selection
        target_sel.Clear()
        target_sel.Add(target_root)
        target_sel.Paste()
        target_sel.Clear()

        target_root = self.conn.root_occurrence(target_editor)
        children = self.plm.child_occurrences(target_root)
        source_note = ""
        if close_source:
            try:
                source_window.Close()
            except Exception:
                source_note = " The source editor could not be closed and stays open."
        else:
            source_note = " The new part's own editor stays open (activate it to model)."
        if len(children) != before + 1:
            raise RuntimeError(
                f"Paste of {label} under the product did not add exactly one component "
                f"({before} -> {len(children)} children). Inspect the product tree; "
                "nothing was rolled back." + source_note
            )
        new_name = self.plm.occurrence_name(children[-1])
        self.conn.refresh_display()
        return (
            f"Inserted {label} as component '{new_name}' under the active product "
            f"({before} -> {len(children)} children). Not yet saved to the database."
            + source_note
        )

    # ── V5 constraints ──

    def _fix_constraint(self, component_name: str) -> str:
        self._constraints_unsupported("catia_fix_constraint")
        product = self.conn.get_active_product()
        constraints = product.Connections("CATIAConstraints")

        component = product.Products.Item(component_name)
        cst = constraints.AddMonoEltCst(0, component)  # Fix constraint
        cst.Name = f"Fix.{component_name}"

        self.conn.refresh_display()
        return f"Fix constraint applied to '{component_name}'"

    def _coincidence_constraint(self, args: dict[str, Any]) -> str:
        self._constraints_unsupported("catia_coincidence_constraint")
        product = self.conn.get_active_product()
        constraints = product.Connections("CATIAConstraints")

        comp1 = product.Products.Item(args["component1"])
        comp2 = product.Products.Item(args["component2"])

        constraints.AddBiEltCst(0, comp1, comp2)  # Coincidence
        self.conn.refresh_display()
        return (
            f"Coincidence constraint created between "
            f"'{args['component1']}' and '{args['component2']}'"
        )

    def _offset_constraint(self, args: dict[str, Any]) -> str:
        self._constraints_unsupported("catia_offset_constraint")
        product = self.conn.get_active_product()
        constraints = product.Connections("CATIAConstraints")

        comp1 = product.Products.Item(args["component1"])
        comp2 = product.Products.Item(args["component2"])

        cst = constraints.AddBiEltCst(1, comp1, comp2)  # Offset
        cst.Dimension.Value = args["offset"]

        self.conn.refresh_display()
        return (
            f"Offset constraint: {args['offset']} mm between "
            f"'{args['component1']}' and '{args['component2']}'"
        )

    def _angle_constraint(self, args: dict[str, Any]) -> str:
        self._constraints_unsupported("catia_angle_constraint")
        product = self.conn.get_active_product()
        constraints = product.Connections("CATIAConstraints")

        comp1 = product.Products.Item(args["component1"])
        comp2 = product.Products.Item(args["component2"])

        cst = constraints.AddBiEltCst(2, comp1, comp2)  # Angle
        cst.Dimension.Value = args["angle"]

        self.conn.refresh_display()
        return (
            f"Angle constraint: {args['angle']}° between "
            f"'{args['component1']}' and '{args['component2']}'"
        )

    # ── Positions ──

    def _component_position(self, component_name: str) -> Any:
        if self.conn.is_3dx:
            root = self.conn.root_occurrence()
            occurrence = self.plm.find_occurrence(root, component_name)
            instance = safe_get(occurrence, "InstanceOccurrenceOf")
            holder = instance if instance is not None else occurrence
            return holder.Position
        product = self.conn.get_active_product()
        return product.Products.Item(component_name).Position

    def _move_component(self, args: dict[str, Any]) -> str:
        position = self._component_position(args["component_name"])
        matrix = self._read_position(position)
        translation = (args.get("tx", 0), args.get("ty", 0), args.get("tz", 0))
        rotation = (args.get("rx", 0), args.get("ry", 0), args.get("rz", 0))
        new_matrix = compose_position(matrix, translation, rotation)
        position.SetComponents(new_matrix)
        self.conn.refresh_display()

        return (
            f"Component '{args['component_name']}' moved: "
            f"T=({args.get('tx', 0)}, {args.get('ty', 0)}, {args.get('tz', 0)}) mm, "
            f"R=({args.get('rx', 0)}, {args.get('ry', 0)}, {args.get('rz', 0)})°. "
            f"Origin now ({new_matrix[9]:.3f}, {new_matrix[10]:.3f}, {new_matrix[11]:.3f}) mm."
        )

    def _position_row(self, holder: Any) -> dict[str, Any]:
        try:
            matrix = self._read_position(holder.Position)
        except Exception as e:
            return {"position": f"unavailable: {e}"}
        return {
            "position": {
                "x": round(matrix[9], 3),
                "y": round(matrix[10], 3),
                "z": round(matrix[11], 3),
            }
        }

    def _list_components(self) -> str:
        if self.conn.is_3dx:
            return self._list_components_3dx()
        product = self.conn.get_active_product()
        products = product.Products

        components = []
        for i in range(1, products.Count + 1):
            comp = products.Item(i)
            row = {
                "index": i,
                "name": comp.Name,
                "part_number": comp.PartNumber,
            }
            row.update(self._position_row(comp))
            components.append(row)

        if not components:
            return "No components in the active assembly"
        return json.dumps(components, indent=2, ensure_ascii=False)

    def _list_components_3dx(self) -> str:
        root = self.conn.root_occurrence()
        components = []
        for i, occurrence in enumerate(self.plm.child_occurrences(root), start=1):
            instance = safe_get(occurrence, "InstanceOccurrenceOf")
            reference = safe_get(instance, "ReferenceInstanceOf") if instance is not None else None
            row: dict[str, Any] = {"index": i, "name": self.plm.occurrence_name(occurrence)}
            if reference is not None:
                row.update(self.plm.attributes(reference, ("V_Name", "revision")))
            row.update(self._position_row(instance if instance is not None else occurrence))
            components.append(row)
        if not components:
            return "No components in the active product"
        return json.dumps(components, indent=2, ensure_ascii=False)

    def _list_constraints(self) -> str:
        if self.conn.is_3dx:
            return self._list_connections_3dx()
        product = self.conn.get_active_product()
        constraints = product.Connections("CATIAConstraints")

        cst_list = []
        for i in range(1, constraints.Count + 1):
            cst = constraints.Item(i)
            info = {
                "index": i,
                "name": cst.Name,
                "type": cst.Type if hasattr(cst, "Type") else "unknown",
            }
            try:
                info["status"] = "resolved" if cst.Status == 0 else "broken"
            except Exception:
                pass
            cst_list.append(info)

        if not cst_list:
            return "No constraints in the active assembly"
        return json.dumps(cst_list, indent=2, ensure_ascii=False)

    def _list_connections_3dx(self) -> str:
        root = self.conn.root_occurrence()
        reference = self.plm.reference_of(root)
        if reference is None:
            raise UnsupportedCapability("Could not reach the root VPMReference of the product.")
        try:
            connections = reference.GetItem("CATEngConnections")
        except Exception as e:
            raise UnsupportedCapability(
                f"Engineering connections are not reachable here (GetItem('CATEngConnections') "
                f"failed: {e})."
            )
        rows = []
        for i in range(1, int(connections.Count) + 1):
            connection = connections.Item(i)
            rows.append({"index": i, "name": str(safe_get(connection, "Name", "<unnamed>"))})
        if not rows:
            return "No engineering connections in the active product"
        return json.dumps(rows, indent=2, ensure_ascii=False)
