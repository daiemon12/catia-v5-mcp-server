"""Late-bound COM helpers shared by the CATIA V5 and 3DEXPERIENCE code paths.

Out-parameters do not marshal through late-bound IDispatch: pywin32 passes
Python values by value, so an array or scalar that CATIA is supposed to fill
comes back untouched. The field-proven route (V5R20, also used by pycatia) is
SystemService.Evaluate running a small VBScript function that declares the
out variables locally and returns them. The same detour serves 3DEXPERIENCE
calls whose result is an out-parameter, such as PLMNewService.PLMCreate and
PLMOpenService.PLMOpen.

Every generated script takes the target object and the input values as
Evaluate parameters, so no caller data is ever spliced into script text.
Method names are spliced, and are therefore restricted to identifiers.
"""

from __future__ import annotations

import inspect
import re
from typing import Any

# CATScriptLanguage.CATVBScriptLanguage
VBSCRIPT = 0

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_identifier(name: str) -> str:
    if not _IDENTIFIER.match(name or ""):
        raise ValueError(f"Not a valid automation member name: {name!r}")
    return name


def evaluate(app: Any, code: str, function: str, params: list[Any] | tuple = ()) -> Any:
    """Run a VBScript function inside CATIA and return its result."""
    return app.SystemService.Evaluate(code, VBSCRIPT, function, list(params))


def _signature(count: int) -> tuple[str, str]:
    names = [f"p{i}" for i in range(count)]
    return ", ".join(["o", *names]), ", ".join(names)


def call_fill_array(app: Any, obj: Any, method: str, count: int, *in_args: Any) -> list[float]:
    """Call `obj.method(in_args..., a)` where CATIA fills the array `a`.

    Used for GetCOG, GetPoint, GetPlane, GetInertiaMatrix and
    Position.GetComponents.
    """
    _check_identifier(method)
    signature, args = _signature(len(in_args))
    call_args = f"{args}, a" if args else "a"
    code = (
        f"Public Function catia_mcp_fill({signature})\n"
        f"    Dim a({count - 1})\n"
        f"    o.{method} {call_args}\n"
        "    catia_mcp_fill = a\n"
        "End Function\n"
    )
    result = evaluate(app, code, "catia_mcp_fill", [obj, *in_args])
    values = [float(v) for v in result]
    if len(values) != count:
        raise RuntimeError(f"{method} returned {len(values)} values, expected {count}")
    return values


def call_out_values(app: Any, obj: Any, method: str, n_out: int, *in_args: Any) -> list[Any]:
    """Call `obj.method(in_args..., r0, r1, ...)` for scalar out-parameters
    (for example 3DEXPERIENCE MeasurableInContext.GetPoint x, y, z)."""
    _check_identifier(method)
    signature, args = _signature(len(in_args))
    outs = ", ".join(f"r{i}" for i in range(n_out))
    call_args = ", ".join(a for a in (args, outs) if a)
    code = (
        f"Public Function catia_mcp_out({signature})\n"
        f"    Dim {outs}\n"
        f"    o.{method} {call_args}\n"
        f"    catia_mcp_out = Array({outs})\n"
        "End Function\n"
    )
    return list(evaluate(app, code, "catia_mcp_out", [obj, *in_args]))


def call_out_object(app: Any, obj: Any, method: str, *in_args: Any) -> Any:
    """Call `obj.method(in_args..., result)` where the last parameter is an
    out-parameter (an object in practice) and return it."""
    _check_identifier(method)
    signature, args = _signature(len(in_args))
    call_args = f"{args}, r" if args else "r"
    code = (
        f"Public Function catia_mcp_obj({signature})\n"
        "    Dim r\n"
        f"    o.{method} {call_args}\n"
        "    If IsObject(r) Then\n"
        "        Set catia_mcp_obj = r\n"
        "    Else\n"
        "        catia_mcp_obj = r\n"
        "    End If\n"
        "End Function\n"
    )
    return evaluate(app, code, "catia_mcp_obj", [obj, *in_args])


def get_member(obj: Any, name: str) -> Any:
    """Read a property, or call a zero-argument method exposed as one.

    Several 3DEXPERIENCE navigation members (ReferenceRootOccurrenceOf,
    ReferenceInstanceOf, InstanceOccurrenceOf) are documented as methods
    but used as properties in VBA; pywin32 hands back a bound method when
    type information says "method", so call it.
    """
    value = getattr(obj, name)
    if inspect.ismethod(value) or inspect.isfunction(value):
        value = value()
    return value


def safe_get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return get_member(obj, name)
    except Exception:
        return default


def resolves(obj: Any, name: str) -> bool:
    """True when `obj.name` resolves AND reads without error."""
    try:
        getattr(obj, name)
        return True
    except Exception:
        return False


def name_exists(obj: Any, name: str) -> bool:
    """True when the object knows the member name, even if reading it fails
    (pywin32 raises AttributeError only when GetIDsOfNames rejects it)."""
    try:
        getattr(obj, name)
        return True
    except AttributeError:
        return False
    except Exception:
        return True


def iter_items(collection: Any):
    """Yield the items of a 1-based CATIA collection."""
    for i in range(1, int(collection.Count) + 1):
        yield collection.Item(i)


def com_name(obj: Any, default: str = "<unnamed>") -> str:
    try:
        return str(obj.Name)
    except Exception:
        return default
