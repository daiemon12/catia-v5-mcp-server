"""Read COM type information from live CATIA objects.

The 3DEXPERIENCE automation API is documented only in the DSYAutomation.chm
shipped with each installation, and signatures and enum values drift across
releases. Instead of hard-coding guesses, the server reads the type library
of the running installation: member lists and parameter names
(ITypeInfo.GetFuncDesc / GetNames) and enum values (TKIND_ENUM VarDescs).
Everything here is read-only: it never invokes the members it describes.
"""

from __future__ import annotations

from typing import Any

from catia_mcp.errors import UnsupportedCapability

# oaidl.h constants (hard-coded so this module imports without pywin32).
INVOKE_FUNC = 1
INVOKE_PROPERTYGET = 2
INVOKE_PROPERTYPUT = 4
INVOKE_PROPERTYPUTREF = 8
TKIND_ENUM = 0
PARAMFLAG_FOUT = 2
PARAMFLAG_FRETVAL = 8
PARAMFLAG_FOPT = 16
FUNCFLAG_FRESTRICTED = 1

_INFRASTRUCTURE = {
    "QueryInterface", "AddRef", "Release",
    "GetTypeInfoCount", "GetTypeInfo", "GetIDsOfNames", "Invoke",
}


def type_info(obj: Any) -> Any:
    ole = getattr(obj, "_oleobj_", None)
    if ole is None:
        raise UnsupportedCapability(
            "This object exposes no COM type information (not a late-bound CATIA object)."
        )
    try:
        return ole.GetTypeInfo()
    except Exception as e:
        raise UnsupportedCapability(f"CATIA returned no type information for this object: {e}")


def type_name(obj: Any) -> str | None:
    try:
        return str(type_info(obj).GetDocumentation(-1)[0])
    except Exception:
        return None


# VARTYPE codes (wtypes.h)
_VT_KINDS = {
    2: "int", 3: "int", 16: "int", 17: "int", 18: "int", 19: "int", 20: "int",
    21: "int", 22: "int", 23: "int",
    4: "double", 5: "double", 6: "double",
    8: "string", 11: "bool", 9: "object", 13: "object", 12: "variant",
}
VT_PTR = 26
VT_SAFEARRAY = 27
VT_CARRAY = 28
VT_USERDEFINED = 29
TKIND_INTERFACE = 3
TKIND_DISPATCH = 4
TKIND_ALIAS = 6


def vt_kind(ti: Any, typedesc: Any) -> str:
    """Coarse kind of a parameter type: double, int, string, bool, object,
    variant, array or other. Enums count as int."""
    if isinstance(typedesc, int):
        return _VT_KINDS.get(typedesc, "other")
    try:
        vt, sub = typedesc
    except Exception:
        return "other"
    if vt == VT_PTR:
        return vt_kind(ti, sub)
    if vt in (VT_SAFEARRAY, VT_CARRAY):
        return "array"
    if vt == VT_USERDEFINED:
        try:
            ref = ti.GetRefTypeInfo(sub)
            kind = int(ref.GetTypeAttr()[5])
        except Exception:
            return "other"
        if kind == TKIND_ENUM:
            return "int"
        if kind in (TKIND_INTERFACE, TKIND_DISPATCH):
            return "object"
        if kind == TKIND_ALIAS:
            try:
                return vt_kind(ref, ref.GetTypeAttr()[14])
            except Exception:
                return "other"
    return "other"


def _param_flags(fd: Any) -> list[int]:
    flags = []
    for arg in getattr(fd, "args", ()) or ():
        try:
            flags.append(int(arg[1]))
        except Exception:
            flags.append(0)
    return flags


def describe_members(obj: Any) -> list[dict[str, Any]]:
    """List methods and properties with parameter names and directions."""
    ti = type_info(obj)
    attr = ti.GetTypeAttr()
    methods: dict[str, dict[str, Any]] = {}
    properties: dict[str, dict[str, Any]] = {}
    for j in range(int(attr[6])):  # cFuncs
        fd = ti.GetFuncDesc(j)
        if int(getattr(fd, "wFuncFlags", 0) or 0) & FUNCFLAG_FRESTRICTED:
            continue
        try:
            names = list(ti.GetNames(fd.memid))
        except Exception:
            continue
        if not names or names[0] in _INFRASTRUCTURE:
            continue
        name = str(names[0])
        invkind = int(fd.invkind)
        flags = _param_flags(fd)
        if invkind == INVOKE_FUNC:
            params = []
            args = getattr(fd, "args", ()) or ()
            for k, flag in enumerate(flags):
                if flag & PARAMFLAG_FRETVAL:
                    continue
                pname = str(names[k + 1]) if k + 1 < len(names) else f"arg{k + 1}"
                try:
                    kind = vt_kind(ti, args[k][0])
                except Exception:
                    kind = "other"
                params.append({
                    "name": pname,
                    "type": kind,
                    "out": bool(flag & PARAMFLAG_FOUT),
                    "optional": bool(flag & PARAMFLAG_FOPT),
                })
            methods[name] = {"name": name, "kind": "method", "params": params}
        else:
            entry = properties.setdefault(
                name, {"name": name, "kind": "property", "readable": False, "writable": False}
            )
            if invkind == INVOKE_PROPERTYGET:
                entry["readable"] = True
                indexed = [f for f in flags if not f & PARAMFLAG_FRETVAL]
                if indexed:
                    entry["indexed"] = True
            elif invkind in (INVOKE_PROPERTYPUT, INVOKE_PROPERTYPUTREF):
                entry["writable"] = True
    return sorted(properties.values(), key=lambda m: m["name"]) + sorted(
        methods.values(), key=lambda m: m["name"]
    )


def method_params(obj: Any, method: str) -> list[dict[str, Any]] | None:
    """Parameters of one method, or None when type info is unavailable or
    the method is unknown."""
    try:
        members = describe_members(obj)
    except Exception:
        return None
    for member in members:
        if member["kind"] == "method" and member["name"].lower() == method.lower():
            return member["params"]
    return None


def _type_libraries(objs: list[Any]) -> list[Any]:
    libs = []
    for obj in objs:
        try:
            lib = type_info(obj).GetContainingTypeLib()[0]
        except Exception:
            continue
        if all(lib is not seen for seen in libs):
            libs.append(lib)
    return libs


def list_enums(objs: list[Any]) -> list[str]:
    names: list[str] = []
    for lib in _type_libraries(objs):
        for i in range(int(lib.GetTypeInfoCount())):
            try:
                if int(lib.GetTypeInfoType(i)) == TKIND_ENUM:
                    names.append(str(lib.GetDocumentation(i)[0]))
            except Exception:
                continue
    return sorted(set(names))


def find_enum(objs: list[Any], enum_name: str) -> dict[str, int] | None:
    """Values of an enum declared in the type library of any given object
    (exact name first, then case-insensitive)."""
    wanted = enum_name.lower()
    for lib in _type_libraries(objs):
        for i in range(int(lib.GetTypeInfoCount())):
            try:
                if int(lib.GetTypeInfoType(i)) != TKIND_ENUM:
                    continue
                if str(lib.GetDocumentation(i)[0]).lower() != wanted:
                    continue
                eti = lib.GetTypeInfo(i)
                eattr = eti.GetTypeAttr()
                values = {}
                for j in range(int(eattr[7])):  # cVars
                    vd = eti.GetVarDesc(j)
                    values[str(eti.GetNames(vd.memid)[0])] = int(vd.value)
                return values
            except Exception:
                continue
    return None
