"""Kinematics tools for CATIA V5.

DMU Kinematics: create Revolute joints between assembly components and
drive them through angle commands.

Proven pathway (live-verified against CATIA V5 B30):
- Joint references MUST resolve to standalone wireframe geometry (points /
  lines living directly in a geometrical set). Sketch-embedded sub-elements
  always E_FAIL inside AddJoint.
- References are resolved from the ROOT ReferenceProduct via
  CreateReferenceFromName("{RootName}/{InstanceName}/!{ElementPath}").
  Origin planes are addressed as "!xy plane", "!yz plane", "!zx plane".
- AddJoint argument order for a Revolute joint is
  [Line1, Line2, Plane1, Plane2], where Line1 is constrained normal to
  Plane1 and Line2 normal to Plane2.
- pywin32 sometimes wraps AddJoint / AddCommand results in a 1-tuple;
  results are unwrapped before use.
"""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.connection import CATIAConnection

REVOLUTE_TYPE = "CATKinRevoluteJoint"
PRISMATIC_TYPE = "CATKinPrismaticJoint"
ANGLE_CMD_TYPE = "CATKinAngleCmd"

VALID_PLANES = ("xy plane", "yz plane", "zx plane")


def _unwrap(ret: Any) -> Any:
    """pywin32 packs [out] params into tuples; the object is always element 0.

    AddJoint returns ``(joint, (refs...))``, AddCommand may return
    ``(command,)`` — matching the live-verified recipe, take ``ret[0]``
    of any tuple.
    """
    if isinstance(ret, tuple):
        return ret[0]
    return ret


def _dyn(obj: Any) -> Any:
    """Force late-bound (dynamic) dispatch on a COM object.

    Early-bound gen_py wrappers mangle the DMU Kinematics signatures
    (AddCommand rejects the joint pointer; PutCommandValues can raise
    Catastrophic failure). Every live-verified kinematics automation ran
    through dynamic dispatch, so rewrap anything early-bound we receive.
    """
    try:
        import win32com.client.dynamic

        oleobj = getattr(obj, "_oleobj_", None)
        if oleobj is None:
            return obj
        return win32com.client.dynamic.Dispatch(oleobj)
    except Exception:
        return obj


def _com_desc(e: Exception) -> str:
    """Extract the most specific available description from a COM error."""
    try:
        exc = e.excepinfo  # type: ignore[attr-defined]
        if exc:
            return f"HRESULT {hex(exc[5])}: {exc[2]}"
    except Exception:
        pass
    return str(e)[:200]


class KinematicsTools:
    """Tools for DMU Kinematics (mechanisms, joints, commands) in CATIA V5."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    # ── Tool definitions ──────────────────────────────────────────────

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_kin_create_revolute_joint",
                "description": (
                    "Create a Revolute joint (CATKinRevoluteJoint) between two "
                    "components of the active assembly, using the existing "
                    "Mechanism or creating one. The axis line must be standalone "
                    "wireframe geometry inside a geometrical set of each part "
                    "(e.g. a line named 'Line.1' in geoset 'KinGeo'); "
                    "sketch-embedded elements are rejected by CATIA. The line "
                    "must be normal to the chosen origin plane in each part. "
                    "Idempotent: if a Revolute joint already exists in the "
                    "assembly, its state is reported and nothing is duplicated."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "component_a": {
                            "type": "string",
                            "description": (
                                "Instance name of the first component "
                                "(becomes the mechanism FixedPart unless "
                                "fixed_component overrides it)"
                            ),
                        },
                        "component_b": {
                            "type": "string",
                            "description": "Instance name of the second component",
                        },
                        "line_element": {
                            "type": "string",
                            "description": (
                                "Path of the rotation-axis line inside each part, "
                                "as addressed after '!' (geoset/element). "
                                "Must exist identically in BOTH parts. "
                                "Example: 'KinGeo/Line.1'"
                            ),
                            "default": "KinGeo/Line.1",
                        },
                        "plane_element": {
                            "type": "string",
                            "enum": list(VALID_PLANES),
                            "description": (
                                "Origin plane the axis line is normal to "
                                "(identical in both parts)"
                            ),
                            "default": "xy plane",
                        },
                        "fixed_component": {
                            "type": "string",
                            "description": (
                                "Component to assign as the mechanism FixedPart. "
                                "Defaults to component_a."
                            ),
                        },
                        "command_angle_deg": {
                            "type": "number",
                            "description": (
                                "Optional: also create an Angle command "
                                "(CATKinAngleCmd) on the joint and drive it to "
                                "this angle in degrees."
                            ),
                        },
                    },
                    "required": ["component_a", "component_b"],
                },
            },
            {
                "name": "catia_kin_create_prismatic_joint",
                "description": (
                    "Create a Prismatic joint (CATKinPrismaticJoint) between two "
                    "components of the active assembly, using the existing "
                    "Mechanism or creating one. The translation axis must be "
                    "standalone wireframe geometry inside a geometrical set of "
                    "each part (e.g. a line named 'Line.1' in geoset 'KinGeo'); "
                    "sketch-embedded elements are rejected by CATIA. "
                    "Idempotent: if a Prismatic joint already exists in the "
                    "assembly, its state is reported and nothing is duplicated."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "component_a": {
                            "type": "string",
                            "description": (
                                "Instance name of the first component "
                                "(becomes the mechanism FixedPart unless "
                                "fixed_component overrides it)"
                            ),
                        },
                        "component_b": {
                            "type": "string",
                            "description": "Instance name of the second component",
                        },
                        "line_element": {
                            "type": "string",
                            "description": (
                                "Path of the translation-axis line inside each "
                                "part, as addressed after '!'. Must exist "
                                "identically in BOTH parts. "
                                "Example: 'KinGeo/Line.1'"
                            ),
                            "default": "KinGeo/Line.1",
                        },
                        "plane_element": {
                            "type": "string",
                            "enum": list(VALID_PLANES),
                            "description": (
                                "Origin plane paired with the translation axis "
                                "(identical in both parts)"
                            ),
                            "default": "xy plane",
                        },
                        "fixed_component": {
                            "type": "string",
                            "description": (
                                "Component to assign as the mechanism FixedPart. "
                                "Defaults to component_a."
                            ),
                        },
                    },
                    "required": ["component_a", "component_b"],
                },
            },
            {
                "name": "catia_kin_get_mechanism_info",
                "description": (
                    "List all mechanisms in the active assembly with their "
                    "joints, commands, degrees of freedom and fixed part. "
                    "Read-only."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "catia_kin_drive_mechanism",
                "description": (
                    "Drive the single-command mechanism of the active assembly "
                    "to a given angle (degrees) via PutCommandValues and return "
                    "the command's CurrentValue read-back. Requires exactly one "
                    "command in the mechanism."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "angle_deg": {
                            "type": "number",
                            "description": "Target angle in degrees",
                        },
                    },
                    "required": ["angle_deg"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_kin_create_revolute_joint":
                return self._create_revolute(arguments)
            case "catia_kin_create_prismatic_joint":
                return self._create_prismatic(arguments)
            case "catia_kin_get_mechanism_info":
                return self._mechanism_info()
            case "catia_kin_drive_mechanism":
                return self._drive_mechanism(arguments)
            case _:
                raise ValueError(f"Unknown kinematics tool: {tool_name}")

    # ── Internals ─────────────────────────────────────────────────────

    @staticmethod
    def _clean_element(path: str) -> str:
        """Normalize an element path ('/KinGeo/Line.1' -> 'KinGeo/Line.1')."""
        return path.strip().lstrip("/!")

    def _resolve_component(self, root: Any, name: str) -> Any:
        """Find a component by instance name, part number, or 1-based index."""
        products = root.Products
        try:
            return products.Item(name)
        except Exception:
            pass
        if name.isdigit():
            try:
                return products.Item(int(name))
            except Exception:
                pass
        for i in range(1, products.Count + 1):
            try:
                comp = products.Item(i)
                if comp.Name == name or comp.PartNumber == name:
                    return comp
            except Exception:
                continue
        raise RuntimeError(f"Component '{name}' not found in the active assembly.")

    def _iter_mechanisms(self, root: Any) -> list[Any]:
        """Safely list all mechanisms of the active product."""
        try:
            mechs = root.GetTechnologicalObject("Mechanisms")
        except Exception as e:
            raise RuntimeError(
                f"Cannot access Mechanisms of the active assembly: {_com_desc(e)}"
            ) from e
        try:
            count = mechs.Count
        except Exception:
            return []
        out: list[Any] = []
        for i in range(1, count + 1):
            try:
                out.append(_dyn(mechs.Item(i)))
            except Exception:
                continue
        return out

    def _find_existing_revolute(self, root: Any) -> tuple[Any | None, Any | None]:
        """Return (mechanism, joint) for the first existing Revolute joint."""
        for mech in self._iter_mechanisms(root):
            try:
                joints = mech.Joints
                count = joints.Count
            except Exception:
                continue
            for i in range(1, count + 1):
                try:
                    joint = joints.Item(i)
                    jtype = joint.Type
                except Exception:
                    continue
                if jtype == REVOLUTE_TYPE:
                    return mech, joint
        return None, None

    def _find_existing_prismatic(self, root: Any) -> tuple[Any | None, Any | None]:
        """Return (mechanism, joint) for the first existing Prismatic joint."""
        for mech in self._iter_mechanisms(root):
            try:
                joints = mech.Joints
                count = joints.Count
            except Exception:
                continue
            for i in range(1, count + 1):
                try:
                    joint = joints.Item(i)
                    jtype = joint.Type
                except Exception:
                    continue
                if jtype == PRISMATIC_TYPE:
                    return mech, joint
        return None, None

    def _safe_attr(self, obj: Any, attr: str, default: Any = None) -> Any:
        try:
            return getattr(obj, attr)
        except Exception:
            return default

    def _mech_summary(self, mech: Any) -> dict[str, Any]:
        return {
            "name": self._safe_attr(mech, "Name"),
            "nb_joints": self._safe_attr(mech, "NbJoints"),
            "nb_dof": self._safe_attr(mech, "NbDof"),
            "nb_products": self._safe_attr(mech, "NbProducts"),
            "nb_commands": self._safe_attr(mech, "NbCommands"),
        }

    # ── Tool: create revolute joint ───────────────────────────────────

    def _create_revolute(self, args: dict[str, Any]) -> str:
        root = self.conn.get_active_product()
        rrp = root.ReferenceProduct
        rname = rrp.Name

        comp_a = self._resolve_component(root, args["component_a"])
        comp_b = self._resolve_component(root, args["component_b"])
        in_a, in_b = comp_a.Name, comp_b.Name

        line_el = self._clean_element(args.get("line_element", "KinGeo/Line.1"))
        plane_el = self._clean_element(args.get("plane_element", "xy plane"))
        if plane_el not in VALID_PLANES:
            raise RuntimeError(
                f"plane_element must be one of {VALID_PLANES}, got '{plane_el}'"
            )

        # Idempotency: report an existing Revolute joint instead of duplicating.
        existing_mech, existing_joint = self._find_existing_revolute(root)
        if existing_joint is not None:
            result = {
                "success": True,
                "already_existed": True,
                "mechanism": self._mech_summary(existing_mech),
                "joint": {
                    "name": self._safe_attr(existing_joint, "Name"),
                    "type": REVOLUTE_TYPE,
                },
                "components": {"a": in_a, "b": in_b},
                "message": (
                    "A Revolute joint already exists in this assembly; "
                    "nothing was created."
                ),
            }
            return json.dumps(result, indent=2, ensure_ascii=False)

        # Design mode keeps kinematics solving reliable.
        try:
            root.ApplyWorkMode(0)
        except Exception:
            pass

        # Reuse the first existing mechanism, otherwise create one.
        mechs = self._iter_mechanisms(root)
        if mechs:
            mech = mechs[0]
            mech_created = False
        else:
            mech = _dyn(root.GetTechnologicalObject("Mechanisms").Add())
            mech_created = True

        fixed_name = args.get("fixed_component") or args["component_a"]
        if mech_created or args.get("fixed_component"):
            fixed_comp = self._resolve_component(root, fixed_name)
            mech.FixedPart = fixed_comp

        # Proven reference recipe: standalone wireframe resolved from the
        # ROOT ReferenceProduct. Order: Line1, Line2, Plane1, Plane2.
        ref_paths = {
            "line_a": f"{rname}/{in_a}/!{line_el}",
            "line_b": f"{rname}/{in_b}/!{line_el}",
            "plane_a": f"{rname}/{in_a}/!{plane_el}",
            "plane_b": f"{rname}/{in_b}/!{plane_el}",
        }
        try:
            la = rrp.CreateReferenceFromName(ref_paths["line_a"])
            lb = rrp.CreateReferenceFromName(ref_paths["line_b"])
            pa = rrp.CreateReferenceFromName(ref_paths["plane_a"])
            pb = rrp.CreateReferenceFromName(ref_paths["plane_b"])
        except Exception as e:
            raise RuntimeError(
                f"Failed to resolve joint references. Ensure '{line_el}' is "
                f"standalone wireframe geometry in a geometrical set of both "
                f"parts and the plane is an origin plane. Details: {_com_desc(e)}"
            ) from e

        try:
            ret = mech.AddJoint(REVOLUTE_TYPE, [la, lb, pa, pb])
        except Exception as e:
            raise RuntimeError(
                f"AddJoint({REVOLUTE_TYPE}) failed: {_com_desc(e)}"
            ) from e
        joint = _unwrap(ret)
        # The object returned by AddJoint may not expose .Name immediately;
        # read the canonical name back from the Joints collection instead.
        joint_name = self._safe_attr(joint, "Name")
        if not joint_name:
            try:
                joint_name = mech.Joints.Item(mech.Joints.Count).Name
            except Exception:
                joint_name = None

        # Optional angle command + initial drive.
        command_info: dict[str, Any] | None = None
        angle = args.get("command_angle_deg")
        if angle is not None:
            try:
                cmd = _unwrap(mech.AddCommand(ANGLE_CMD_TYPE, joint))
            except Exception as e:
                raise RuntimeError(
                    f"AddCommand({ANGLE_CMD_TYPE}) failed: {_com_desc(e)}"
                ) from e
            mech.PutCommandValues((float(angle),))
            current = self._safe_attr(cmd, "CurrentValue")
            try:
                current = float(current)
            except (TypeError, ValueError):
                current = None
            command_info = {
                "name": self._safe_attr(cmd, "Name"),
                "type": ANGLE_CMD_TYPE,
                "commanded_deg": float(angle),
                "current_value_deg": current,
            }

        self.conn.refresh_display()

        result = {
            "success": True,
            "already_existed": False,
            "mechanism_created": mech_created,
            "mechanism": self._mech_summary(mech),
            "joint": {
                "name": joint_name,
                "type": REVOLUTE_TYPE,
            },
            "components": {"a": in_a, "b": in_b, "fixed_part": fixed_name},
            "references": ref_paths,
            "command": command_info,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ── Tool: create prismatic joint ──────────────────────────────────

    def _create_prismatic(self, args: dict[str, Any]) -> str:
        """Create a Prismatic joint using the proven standalone-reference path."""
        root = self.conn.get_active_product()
        rrp = root.ReferenceProduct
        rname = rrp.Name

        comp_a = self._resolve_component(root, args["component_a"])
        comp_b = self._resolve_component(root, args["component_b"])
        in_a, in_b = comp_a.Name, comp_b.Name

        line_el = self._clean_element(args.get("line_element", "KinGeo/Line.1"))
        plane_el = self._clean_element(args.get("plane_element", "xy plane"))
        if plane_el not in VALID_PLANES:
            raise RuntimeError(
                f"plane_element must be one of {VALID_PLANES}, got '{plane_el}'"
            )

        existing_mech, existing_joint = self._find_existing_prismatic(root)
        if existing_joint is not None:
            return json.dumps(
                {
                    "success": True,
                    "already_existed": True,
                    "mechanism": self._mech_summary(existing_mech),
                    "joint": {
                        "name": self._safe_attr(existing_joint, "Name"),
                        "type": PRISMATIC_TYPE,
                    },
                    "components": {"a": in_a, "b": in_b},
                    "message": (
                        "A Prismatic joint already exists in this assembly; "
                        "nothing was created."
                    ),
                },
                indent=2,
                ensure_ascii=False,
            )

        try:
            root.ApplyWorkMode(0)
        except Exception:
            pass

        mechs = self._iter_mechanisms(root)
        if mechs:
            mech = mechs[0]
            mech_created = False
        else:
            mech = _dyn(root.GetTechnologicalObject("Mechanisms").Add())
            mech_created = True

        fixed_name = args.get("fixed_component") or args["component_a"]
        if mech_created or args.get("fixed_component"):
            mech.FixedPart = self._resolve_component(root, fixed_name)

        # CATIA Prismatic consumes paired line/plane references:
        # [Line1, Plane1, Line2, Plane2].
        ref_paths = {
            "line_a": f"{rname}/{in_a}/!{line_el}",
            "line_b": f"{rname}/{in_b}/!{line_el}",
            "plane_a": f"{rname}/{in_a}/!{plane_el}",
            "plane_b": f"{rname}/{in_b}/!{plane_el}",
        }
        try:
            la = rrp.CreateReferenceFromName(ref_paths["line_a"])
            lb = rrp.CreateReferenceFromName(ref_paths["line_b"])
            pa = rrp.CreateReferenceFromName(ref_paths["plane_a"])
            pb = rrp.CreateReferenceFromName(ref_paths["plane_b"])
        except Exception as e:
            raise RuntimeError(
                f"Failed to resolve joint references. Ensure '{line_el}' is "
                f"standalone wireframe geometry in a geometrical set of both "
                f"parts and the plane is an origin plane. Details: {_com_desc(e)}"
            ) from e

        try:
            joint = _unwrap(mech.AddJoint(PRISMATIC_TYPE, [la, pa, lb, pb]))
        except Exception as e:
            raise RuntimeError(
                f"AddJoint({PRISMATIC_TYPE}) failed: {_com_desc(e)}"
            ) from e

        joint_name = self._safe_attr(joint, "Name")
        if not joint_name:
            try:
                joint_name = mech.Joints.Item(mech.Joints.Count).Name
            except Exception:
                joint_name = None

        self.conn.refresh_display()
        return json.dumps(
            {
                "success": True,
                "already_existed": False,
                "mechanism_created": mech_created,
                "mechanism": self._mech_summary(mech),
                "joint": {"name": joint_name, "type": PRISMATIC_TYPE},
                "components": {"a": in_a, "b": in_b, "fixed_part": fixed_name},
                "references": ref_paths,
            },
            indent=2,
            ensure_ascii=False,
        )

    # ── Tool: mechanism info ──────────────────────────────────────────

    def _mechanism_info(self) -> str:
        root = self.conn.get_active_product()
        mechs = self._iter_mechanisms(root)
        if not mechs:
            return json.dumps(
                {
                    "success": True,
                    "mechanisms": [],
                    "message": "No mechanisms in the active assembly.",
                },
                indent=2,
                ensure_ascii=False,
            )

        out: list[dict[str, Any]] = []
        for mech in mechs:
            entry = self._mech_summary(mech)
            entry["fixed_part"] = self._safe_attr(
                self._safe_attr(mech, "FixedPart"), "Name"
            )

            joints: list[dict[str, Any]] = []
            try:
                jc = mech.Joints
                for i in range(1, jc.Count + 1):
                    j = jc.Item(i)
                    joints.append(
                        {
                            "index": i,
                            "name": self._safe_attr(j, "Name"),
                            "type": self._safe_attr(j, "Type"),
                        }
                    )
            except Exception:
                pass
            entry["joints"] = joints

            commands: list[dict[str, Any]] = []
            try:
                cc = mech.Commands
                for i in range(1, cc.Count + 1):
                    c = cc.Item(i)
                    commands.append(
                        {
                            "index": i,
                            "name": self._safe_attr(c, "Name"),
                            "type": self._safe_attr(c, "Type"),
                            "current_value": self._safe_attr(c, "CurrentValue"),
                        }
                    )
            except Exception:
                pass
            entry["commands"] = commands
            out.append(entry)

        return json.dumps(
            {"success": True, "mechanisms": out}, indent=2, ensure_ascii=False
        )

    # ── Tool: drive mechanism ─────────────────────────────────────────

    def _drive_mechanism(self, args: dict[str, Any]) -> str:
        root = self.conn.get_active_product()
        mechs = self._iter_mechanisms(root)
        if not mechs:
            raise RuntimeError(
                "No mechanism in the active assembly. Create a joint first "
                "with catia_kin_create_revolute_joint."
            )
        mech = mechs[0]

        nb_cmds = self._safe_attr(mech, "NbCommands")
        if nb_cmds != 1:
            raise RuntimeError(
                f"catia_kin_drive_mechanism expects exactly 1 command in the "
                f"mechanism, found {nb_cmds}. Use command_angle_deg when "
                f"creating the joint to add an Angle command."
            )

        angle = float(args["angle_deg"])
        mech.PutCommandValues((angle,))

        current: Any = None
        try:
            cmd = mech.Commands.Item(1)
            current = self._safe_attr(cmd, "CurrentValue")
            current = float(current)
        except Exception:
            pass

        result = {
            "success": True,
            "mechanism": self._safe_attr(mech, "Name"),
            "commanded_deg": angle,
            "current_value_deg": current,
            "nb_joints": self._safe_attr(mech, "NbJoints"),
            "nb_dof": self._safe_attr(mech, "NbDof"),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
