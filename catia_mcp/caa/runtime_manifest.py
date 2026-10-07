"""Record build provenance and verify the configured Point runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from .protocol import atomic_write_json, utc_now_iso
from .runonce import METHOD

DLL_NAMES = ("CatiaPyBridgeAddin.dll", "CatiaPyBridgeCmdModule.dll")
RUNTIME_FILES = tuple("code/bin/" + name for name in DLL_NAMES) + (
    "code/dictionary/CatiaPyBridge.dico",
    "code/productIC/CatiaPyBridgeFrameworkIC.xml",
    "resources/msgcatalog/CatiaPyBridgeAddin.CATNls",
    "resources/msgcatalog/CatiaPyBridgeCommandHeader.CATNls",
)
SOURCE = json.loads(Path(__file__).with_name("native-source.json").read_text(encoding="utf-8"))


class RuntimeManifestError(RuntimeError):
    code = "CAA_BRIDGE_MISMATCH"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(workspace: Path) -> None:
    """Run after a successful mkmk build and synchronization, never before."""
    actual = {name: file_hash(workspace / name) for name in SOURCE["files"]}
    if actual != SOURCE["files"]:
        raise RuntimeManifestError("Native sources differ from the MCP package; update and validate both together")
    runtime = workspace / "CatiaPyBridgeRuntime"
    def git(*args):
        return subprocess.check_output(["git", "-C", str(workspace), *args], text=True).strip()
    manifest = {
        "method": METHOD,
        "created_at": utc_now_iso(),
        "build": {"source_directory": str(workspace.resolve()), "branch": git("branch", "--show-current"),
                  "head": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
                  "command": "scripts/build_caa_b30.bat (mkmk -a)", "platform": "B30 win_b64"},
        "native_source_files": actual,
        "runtime_files": {name: file_hash(runtime / name) for name in RUNTIME_FILES},
    }
    atomic_write_json(runtime / "runtime.json", manifest)


def verify_files(runtime: Path) -> None:
    """The manifest records a trusted local build; hashes are not a signature."""
    try:
        manifest = json.loads((runtime / "runtime.json").read_text(encoding="utf-8"))
        if manifest["method"] != METHOD or manifest["native_source_files"] != SOURCE["files"]:
            raise RuntimeManifestError("Point runtime source/contract mismatch")
        records = manifest["runtime_files"]
        if set(records) != set(RUNTIME_FILES):
            raise RuntimeManifestError("Point runtime file set mismatch")
        for name in RUNTIME_FILES:
            path = runtime / name
            if not path.resolve().is_relative_to(runtime.resolve()) or file_hash(path) != records[name]:
                raise RuntimeManifestError("Point runtime hash mismatch: " + name)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeManifestError("Missing or invalid Point runtime manifest/files") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--workspace", type=Path)
    mode.add_argument("--verify-runtime", type=Path)
    args = parser.parse_args()
    if args.workspace:
        write_manifest(args.workspace.resolve())
    else:
        verify_files(args.verify_runtime.resolve())


if __name__ == "__main__":
    main()
