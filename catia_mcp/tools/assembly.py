"""Assembly tools for CATIA V5.

Product/Assembly management: add components, constraints (Fix, Coincidence,
Contact, Offset, Angle), move components, and manage the product tree.
"""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.connection import CATIAConnection


class AssemblyTools:
    """Tools for assembly (Product) operations in CATIA V5."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_add_component",
                "description": (
                    "Add an existing CATPart or CATProduct file as a component in the active assembly. "
                    "The component is inserted at the origin."
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
                    "Returns the name of the created component."
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
                "name": "catia_fix_constraint",
                "description": (
                    "Fix a component in place (remove all degrees of freedom). "
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
                    "Create a Coincidence constraint between two components. "
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
                    "Create an Offset constraint between two faces/planes of two components. "
                    "Maintains a constant distance between the reference elements."
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
                "description": "Create an Angle constraint between two components.",
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
                    "Translation in mm, rotation in degrees."
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
                "description": "List all components in the active assembly/product with their names and positions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_list_constraints",
                "description": "List all assembly constraints in the active product.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_reorder_components",
                "description": (
                    "Reorder a set of existing components within the active assembly's "
                    "specification tree. CATIA's Products collection has no native reorder "
                    "method (only AddComponent/Remove), so this removes exactly the named "
                    "components and re-adds them from their source files in the given order, "
                    "appended after whatever components are left in the tree. Components not "
                    "named in component_order are left completely untouched (position and "
                    "constraints preserved). Position/PartNumber of the reordered components "
                    "are restored from before removal; any constraint attached directly to a "
                    "reordered component will be lost and must be recreated."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "component_order": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "description": (
                                "Names of existing components (as returned by "
                                "catia_list_components), in the desired final order."
                            ),
                        },
                    },
                    "required": ["component_order"],
                },
            },
            {
                "name": "catia_replace_component",
                "description": (
                    "Replace a component in a CATProduct with another CATPart/CATProduct file. "
                    "Can replace all instances that share the selected component's reference."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "new_file_path": {
                            "type": "string",
                            "description": "Full path to the replacement .CATPart or .CATProduct file",
                        },
                        "product_path": {
                            "type": "string",
                            "description": (
                                "Optional full path to the CATProduct to edit. If omitted, "
                                "the active product is used."
                            ),
                        },
                        "old_component_name": {
                            "type": "string",
                            "description": "Optional component instance name to replace",
                        },
                        "old_file_path": {
                            "type": "string",
                            "description": (
                                "Optional source .CATPart/.CATProduct path of the component "
                                "to replace. The first matching instance is used."
                            ),
                        },
                        "all_instances": {
                            "type": "boolean",
                            "description": (
                                "Whether to replace all instances of the selected reference "
                                "(default true)."
                            ),
                            "default": True,
                        },
                        "save": {
                            "type": "boolean",
                            "description": "Save the CATProduct after replacement (default true).",
                            "default": True,
                        },
                    },
                    "required": ["new_file_path"],
                },
            },
            {
                "name": "catia_show_all_components",
                "description": (
                    "Force top-level product components and their referenced part bodies/features "
                    "into Show mode, then update and optionally save the product."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_path": {
                            "type": "string",
                            "description": "Optional full path to the CATProduct to edit.",
                        },
                        "save": {
                            "type": "boolean",
                            "description": "Save the CATProduct after changing visibility (default true).",
                            "default": True,
                        },
                    },
                },
            },
            {
                "name": "catia_component_geometry_report",
                "description": (
                    "Report each top-level component's source file and referenced CATPart body/"
                    "feature counts. Use this to verify that components contain 3D geometry."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_path": {
                            "type": "string",
                            "description": "Optional full path to the CATProduct to inspect.",
                        },
                    },
                },
            },
            {
                "name": "catia_rebuild_task02_product",
                "description": (
                    "Rebuild task 02 CATProduct from numbers.CATPart and Void*.CATPart files "
                    "in a source folder, ordered as Numbers, Void3, Void1, Void4, Void5, Void2. "
                    "This is a contest-specific repair tool."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_path": {
                            "type": "string",
                            "description": "Full path to the CATProduct to rebuild/save.",
                        },
                        "source_folder": {
                            "type": "string",
                            "description": "Folder containing numbers.CATPart and Void*.CATPart.",
                        },
                        "save": {
                            "type": "boolean",
                            "description": "Save the CATProduct after rebuilding (default true).",
                            "default": True,
                        },
                    },
                    "required": ["product_path", "source_folder"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_add_component":
                return self._add_component(arguments["file_path"])
            case "catia_add_new_part":
                return self._add_new_part(arguments.get("name"))
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
            case "catia_reorder_components":
                return self._reorder_components(arguments["component_order"])
            case "catia_replace_component":
                return self._replace_component(arguments)
            case "catia_show_all_components":
                return self._show_all_components(arguments)
            case "catia_component_geometry_report":
                return self._component_geometry_report(arguments)
            case "catia_rebuild_task02_product":
                return self._rebuild_task02_product(arguments)
            case _:
                raise ValueError(f"Unknown assembly tool: {tool_name}")

    def _add_component(self, file_path: str) -> str:
        product = self.conn.get_active_product()
        products = product.Products
        component = products.AddComponentsFromFiles(
            [file_path], "All"
        )
        self.conn.refresh_display()
        return f"Component added from: {file_path}"

    def _add_new_part(self, name: str | None = None) -> str:
        product = self.conn.get_active_product()
        products = product.Products
        new_product = products.AddNewProduct("Part")
        if name:
            new_product.Name = name
        self.conn.refresh_display()
        return f"New Part component created in assembly: '{new_product.Name}'"

    def _fix_constraint(self, component_name: str) -> str:
        product = self.conn.get_active_product()
        constraints = product.Connections("CATIAConstraints")

        component = product.Products.Item(component_name)
        cst = constraints.AddMonoEltCst(0, component)  # Fix constraint
        cst.Name = f"Fix.{component_name}"

        self.conn.refresh_display()
        return f"Fix constraint applied to '{component_name}'"

    def _coincidence_constraint(self, args: dict[str, Any]) -> str:
        product = self.conn.get_active_product()
        constraints = product.Connections("CATIAConstraints")

        comp1 = product.Products.Item(args["component1"])
        comp2 = product.Products.Item(args["component2"])

        cst = constraints.AddBiEltCst(0, comp1, comp2)  # Coincidence
        self.conn.refresh_display()
        return (
            f"Coincidence constraint created between "
            f"'{args['component1']}' and '{args['component2']}'"
        )

    def _offset_constraint(self, args: dict[str, Any]) -> str:
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

    def _move_component(self, args: dict[str, Any]) -> str:
        import math
        product = self.conn.get_active_product()
        component = product.Products.Item(args["component_name"])

        # CATIA Product.Move.Apply expects a 3x4 transform flattened as
        # rotation basis followed by translation. It applies an incremental move.
        matrix = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]

        # Apply translation (values 9, 10, 11 are tx, ty, tz)
        matrix[9] = args.get("tx", 0)
        matrix[10] = args.get("ty", 0)
        matrix[11] = args.get("tz", 0)

        # Apply rotations if specified (simplified: sequential Euler rotations)
        rx = math.radians(args.get("rx", 0))
        ry = math.radians(args.get("ry", 0))
        rz = math.radians(args.get("rz", 0))

        if rx != 0 or ry != 0 or rz != 0:
            # Build rotation matrix (Rz * Ry * Rx convention)
            cx, sx = math.cos(rx), math.sin(rx)
            cy, sy = math.cos(ry), math.sin(ry)
            cz, sz = math.cos(rz), math.sin(rz)

            # Rotation matrix components
            r00 = cy * cz
            r01 = cz * sx * sy - cx * sz
            r02 = sx * sz + cx * cz * sy
            r10 = cy * sz
            r11 = cx * cz + sx * sy * sz
            r12 = cx * sy * sz - cz * sx
            r20 = -sy
            r21 = cy * sx
            r22 = cx * cy

            matrix[0] = r00
            matrix[1] = r01
            matrix[2] = r02
            matrix[3] = r10
            matrix[4] = r11
            matrix[5] = r12
            matrix[6] = r20
            matrix[7] = r21
            matrix[8] = r22

        component.Move.Apply(matrix)
        self.conn.refresh_display()

        return (
            f"Component '{args['component_name']}' moved: "
            f"T=({args.get('tx', 0)}, {args.get('ty', 0)}, {args.get('tz', 0)}) mm, "
            f"R=({args.get('rx', 0)}, {args.get('ry', 0)}, {args.get('rz', 0)})°"
        )

    def _list_components(self) -> str:
        product = self.conn.get_active_product()
        products = product.Products

        components = []
        for i in range(1, products.Count + 1):
            comp = products.Item(i)
            pos = comp.Position
            matrix = [0.0] * 12
            try:
                pos.GetComponents(matrix)
            except Exception:
                pass
            components.append({
                "index": i,
                "name": comp.Name,
                "part_number": comp.PartNumber,
                "position": {
                    "x": round(matrix[9], 3),
                    "y": round(matrix[10], 3),
                    "z": round(matrix[11], 3),
                },
            })

        if not components:
            return "No components in the active assembly"
        return json.dumps(components, indent=2, ensure_ascii=False)

    def _component_file_path(self, component: Any) -> str:
        # A component instance's own document path isn't exposed directly;
        # it must be read off the prototype (ReferenceProduct) it points at.
        try:
            return component.ReferenceProduct.Parent.FullName
        except Exception as exc:
            raise RuntimeError(
                f"Could not resolve source file for component '{component.Name}': {exc}"
            ) from exc

    def _product_document_from_path(self, product_path: str | None) -> Any:
        self.conn.ensure_connected()
        if not product_path:
            return self.conn.active_document

        import os

        from catia_mcp.paths import normalize_catia_path

        docs = self.conn.documents
        product_path = normalize_catia_path(product_path)
        target = os.path.normcase(os.path.abspath(product_path))
        for index in range(1, docs.Count + 1):
            doc = docs.Item(index)
            full_name = getattr(doc, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                try:
                    doc.Activate()
                except Exception:
                    pass
                return doc

        doc = docs.Open(product_path)
        try:
            doc.Activate()
        except Exception:
            pass
        return doc

    def _find_component_to_replace(
        self,
        products: Any,
        old_component_name: str | None,
        old_file_path: str | None,
    ) -> Any:
        import os

        from catia_mcp.paths import normalize_catia_path

        target_path = None
        if old_file_path:
            target_path = os.path.normcase(os.path.abspath(normalize_catia_path(old_file_path)))

        seen_names = []
        seen_paths = []
        for index in range(1, products.Count + 1):
            component = products.Item(index)
            seen_names.append(component.Name)
            if old_component_name and component.Name == old_component_name:
                return component

            try:
                source_path = self._component_file_path(component)
                seen_paths.append(source_path)
            except Exception:
                source_path = ""

            if target_path and source_path:
                source_norm = os.path.normcase(os.path.abspath(source_path))
                if source_norm == target_path:
                    return component

        raise ValueError(
            "Could not find component to replace. "
            f"Requested name={old_component_name!r}, old_file_path={old_file_path!r}. "
            f"Top-level component names={seen_names}, source paths={seen_paths}"
        )

    def _source_counts(self, products: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for index in range(1, products.Count + 1):
            component = products.Item(index)
            try:
                source_path = self._component_file_path(component)
            except Exception:
                source_path = f"<unresolved:{component.Name}>"
            counts[source_path] = counts.get(source_path, 0) + 1
        return counts

    def _replace_component(self, args: dict[str, Any]) -> str:
        from catia_mcp.paths import normalize_catia_path

        doc = self._product_document_from_path(args.get("product_path"))
        try:
            product = doc.Product
        except Exception as exc:
            raise RuntimeError(
                f"Document '{getattr(doc, 'Name', '<unknown>')}' is not a CATProduct."
            ) from exc

        products = product.Products
        old_component = self._find_component_to_replace(
            products,
            args.get("old_component_name"),
            args.get("old_file_path"),
        )
        old_name = old_component.Name
        try:
            old_source = self._component_file_path(old_component)
        except Exception:
            old_source = "<unresolved>"

        before_counts = self._source_counts(products)
        new_file_path = normalize_catia_path(args["new_file_path"])
        all_instances = bool(args.get("all_instances", True))
        new_component = products.ReplaceComponent(old_component, new_file_path, all_instances)

        try:
            product.Update()
        except Exception:
            doc.Product.Update()

        if args.get("save", True):
            doc.Save()

        after_counts = self._source_counts(products)
        self.conn.refresh_display()

        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "selected_component": old_name,
                "selected_source": old_source,
                "replacement_file": new_file_path,
                "all_instances": all_instances,
                "new_component_name": getattr(new_component, "Name", ""),
                "before_source_counts": before_counts,
                "after_source_counts": after_counts,
                "saved": bool(args.get("save", True)),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _set_show(self, obj: Any) -> bool:
        selection = self.conn.hso
        try:
            selection.Clear()
            selection.Add(obj)
            selection.VisProperties.SetShow(0)  # catVisPropertyShowAttr
            return True
        except Exception:
            return False
        finally:
            try:
                selection.Clear()
            except Exception:
                pass

    def _show_part_geometry(self, part_doc: Any) -> dict[str, Any]:
        result: dict[str, Any] = {
            "document": getattr(part_doc, "FullName", getattr(part_doc, "Name", "")),
            "shown_objects": 0,
            "failed_objects": 0,
        }
        try:
            part = part_doc.Part
        except Exception:
            return result

        def show_collection(collection: Any) -> None:
            try:
                count = collection.Count
            except Exception:
                return
            for index in range(1, count + 1):
                try:
                    item = collection.Item(index)
                except Exception:
                    continue
                if self._set_show(item):
                    result["shown_objects"] += 1
                else:
                    result["failed_objects"] += 1

        try:
            bodies = part.Bodies
            for body_index in range(1, bodies.Count + 1):
                body = bodies.Item(body_index)
                if self._set_show(body):
                    result["shown_objects"] += 1
                else:
                    result["failed_objects"] += 1
                show_collection(getattr(body, "Shapes", None))
                show_collection(getattr(body, "Sketches", None))
        except Exception:
            pass

        try:
            hbs = part.HybridBodies
            for hb_index in range(1, hbs.Count + 1):
                hb = hbs.Item(hb_index)
                if self._set_show(hb):
                    result["shown_objects"] += 1
                else:
                    result["failed_objects"] += 1
        except Exception:
            pass

        try:
            part.Update()
        except Exception:
            pass
        return result

    def _show_all_components(self, args: dict[str, Any]) -> str:
        doc = self._product_document_from_path(args.get("product_path"))
        try:
            product = doc.Product
        except Exception as exc:
            raise RuntimeError(
                f"Document '{getattr(doc, 'Name', '<unknown>')}' is not a CATProduct."
            ) from exc

        products = product.Products
        report: list[dict[str, Any]] = []
        for index in range(1, products.Count + 1):
            component = products.Item(index)
            item: dict[str, Any] = {
                "index": index,
                "name": component.Name,
                "part_number": component.PartNumber,
                "component_show_set": self._set_show(component),
            }
            try:
                part_doc = component.ReferenceProduct.Parent
                item["source_path"] = getattr(part_doc, "FullName", getattr(part_doc, "Name", ""))
                item["part_visibility"] = self._show_part_geometry(part_doc)
            except Exception as exc:
                item["part_visibility_error"] = str(exc)
            report.append(item)

        try:
            product.Update()
        except Exception:
            pass
        if args.get("save", True):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(report, indent=2, ensure_ascii=False)

    def _part_geometry_summary(self, part_doc: Any) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "document": getattr(part_doc, "FullName", getattr(part_doc, "Name", "")),
            "type": "unknown",
            "bodies": [],
            "total_bodies": 0,
            "total_shapes": 0,
            "total_hybrid_bodies": 0,
        }
        try:
            part = part_doc.Part
        except Exception as exc:
            summary["error"] = str(exc)
            return summary

        summary["type"] = "CATPart"
        try:
            bodies = part.Bodies
            summary["total_bodies"] = bodies.Count
            for body_index in range(1, bodies.Count + 1):
                body = bodies.Item(body_index)
                body_info = {
                    "name": body.Name,
                    "shape_count": 0,
                    "shapes": [],
                }
                try:
                    shapes = body.Shapes
                    body_info["shape_count"] = shapes.Count
                    summary["total_shapes"] += shapes.Count
                    for shape_index in range(1, shapes.Count + 1):
                        body_info["shapes"].append(shapes.Item(shape_index).Name)
                except Exception:
                    pass
                summary["bodies"].append(body_info)
        except Exception as exc:
            summary["bodies_error"] = str(exc)

        try:
            summary["total_hybrid_bodies"] = part.HybridBodies.Count
        except Exception:
            pass
        return summary

    def _component_geometry_report(self, args: dict[str, Any]) -> str:
        doc = self._product_document_from_path(args.get("product_path"))
        try:
            product = doc.Product
        except Exception as exc:
            raise RuntimeError(
                f"Document '{getattr(doc, 'Name', '<unknown>')}' is not a CATProduct."
            ) from exc

        report = []
        products = product.Products
        for index in range(1, products.Count + 1):
            component = products.Item(index)
            item: dict[str, Any] = {
                "index": index,
                "name": component.Name,
                "part_number": component.PartNumber,
            }
            try:
                item["source_path"] = self._component_file_path(component)
            except Exception as exc:
                item["source_path_error"] = str(exc)
            try:
                item["geometry"] = self._part_geometry_summary(component.ReferenceProduct.Parent)
            except Exception as exc:
                item["geometry_error"] = str(exc)
            report.append(item)
        return json.dumps(report, indent=2, ensure_ascii=False)

    def _rebuild_task02_product(self, args: dict[str, Any]) -> str:
        import os

        from catia_mcp.paths import normalize_catia_path

        product_path = normalize_catia_path(args["product_path"])
        source_folder = normalize_catia_path(args["source_folder"])
        doc = self._product_document_from_path(product_path)
        try:
            product = doc.Product
        except Exception as exc:
            raise RuntimeError(
                f"Document '{getattr(doc, 'Name', '<unknown>')}' is not a CATProduct."
            ) from exc

        products = product.Products
        removed = []
        while products.Count:
            name = products.Item(1).Name
            products.Remove(name)
            removed.append(name)

        desired = [
            ("Numbers", "numbers.CATPart"),
            ("Void3", "Void3.CATPart"),
            ("Void1", "Void1.CATPart"),
            ("Void4", "Void4.CATPart"),
            ("Void5", "Void5.CATPart"),
            ("Void2", "Void2.CATPart"),
        ]

        added = []
        identity = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        for part_number, file_name in desired:
            file_path = os.path.join(source_folder, file_name)
            if not os.path.exists(file_path):
                raise FileNotFoundError(file_path)
            products.AddComponentsFromFiles([file_path], "All")
            component = products.Item(products.Count)
            try:
                component.PartNumber = part_number
            except Exception:
                pass
            try:
                component.Name = f"{part_number}.1"
            except Exception:
                pass
            try:
                component.Position.SetComponents(identity)
            except Exception:
                pass
            self._set_show(component)
            try:
                self._show_part_geometry(component.ReferenceProduct.Parent)
            except Exception:
                pass
            added.append({
                "name": component.Name,
                "part_number": component.PartNumber,
                "source_path": file_path,
            })

        try:
            product.Update()
        except Exception:
            pass
        if args.get("save", True):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "removed": removed,
                "added": added,
                "saved": bool(args.get("save", True)),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _reorder_components(self, order: list[str]) -> str:
        self.conn.ensure_connected()
        product = self.conn.get_active_product()
        products = product.Products

        current_names = [products.Item(i).Name for i in range(1, products.Count + 1)]
        missing = [name for name in order if name not in current_names]
        if missing:
            raise ValueError(
                f"component_order references components not present in the assembly: {missing}. "
                f"Current components: {current_names}"
            )
        if len(set(order)) != len(order):
            raise ValueError(f"component_order contains duplicate names: {order}")

        # Snapshot file path / part number / position matrix before removal -
        # Remove() invalidates the component objects, so this must happen first.
        saved: dict[str, dict[str, Any]] = {}
        for name in order:
            comp = products.Item(name)
            matrix = [0.0] * 12
            try:
                comp.Position.GetComponents(matrix)
            except Exception:
                pass
            saved[name] = {
                "file_path": self._component_file_path(comp),
                "part_number": comp.PartNumber,
                "matrix": matrix,
            }

        # Remove only the named components. Everything else (and any
        # constraints attached to it) is left untouched.
        for name in order:
            products.Remove(name)

        # Re-add one at a time, in the requested order, so each lands at the
        # end of the tree in sequence; then restore identity.
        for name in order:
            info = saved[name]
            products.AddComponentsFromFiles([info["file_path"]], "All")
            new_comp = products.Item(products.Count)
            new_comp.Name = name
            try:
                new_comp.PartNumber = info["part_number"]
            except Exception:
                pass
            try:
                new_comp.Position.SetComponents(info["matrix"])
            except Exception:
                pass

        self.conn.active_document.Save()
        self.conn.refresh_display()

        final_order = [products.Item(i).Name for i in range(1, products.Count + 1)]
        return "Reordered components. New tree order: " + " -> ".join(final_order)

    def _list_constraints(self) -> str:
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
