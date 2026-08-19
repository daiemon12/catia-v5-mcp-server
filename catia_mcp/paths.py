"""Filesystem path handling for CATIA file I/O.

CATIA V5's ``Document.SaveAs`` and ``Document.ExportData`` reject POSIX-style
forward-slash paths on Windows, popping a modal *"The above file name is
invalid"* dialog that blocks the (single-threaded) MCP server until an operator
dismisses it. They also do not create missing parent directories. Both were hit
live against the .42 deployment, so normalize every outbound file path here.
"""

from __future__ import annotations

import os


def normalize_catia_path(path: str) -> str:
    """Return a Windows-style absolute path safe to hand to CATIA file I/O.

    Converts forward slashes to backslashes and creates the parent directory so
    an unattended ``SaveAs``/``ExportData`` cannot block on a dialog.
    """
    if not path:
        return path
    norm = os.path.normpath(path)
    parent = os.path.dirname(norm)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return norm
