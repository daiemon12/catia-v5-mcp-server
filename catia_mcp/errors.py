"""Typed tool failures that keep a stable machine-readable code.

Tools raise these when they can classify a failure better than the generic
COM_ERROR the server assigns to arbitrary exceptions. `modified` states
whether the model may have changed before the failure: False when the
failure was detected before any CATIA mutation, None when unknown.
"""

from __future__ import annotations

from contextlib import contextmanager


class CATIAToolError(Exception):
    code = "COM_ERROR"

    def __init__(self, message: str, *, code: str | None = None, modified: bool | None = False):
        super().__init__(message)
        if code:
            self.code = code
        self.modified = modified


class InvalidArgument(CATIAToolError):
    code = "INVALID_ARGUMENT"


class UnsupportedCapability(CATIAToolError):
    code = "UNSUPPORTED_CAPABILITY"


class WrongDocumentType(CATIAToolError):
    code = "WRONG_DOCUMENT_TYPE"


class NoActiveDocument(CATIAToolError):
    code = "NO_ACTIVE_DOCUMENT"


class ObjectNotFound(CATIAToolError):
    code = "OBJECT_NOT_FOUND"


class AmbiguousTarget(CATIAToolError):
    code = "AMBIGUOUS_TARGET"


class PermissionDenied(CATIAToolError):
    code = "PERMISSION_DENIED"


@contextmanager
def after_mutation():
    """Wrap code that runs after CATIA was already changed: a typed failure
    raised there must not claim the model is untouched."""
    try:
        yield
    except CATIAToolError as error:
        error.modified = None
        raise
