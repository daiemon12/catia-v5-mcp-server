"""Derive a local bridge CATEnv from an explicitly selected user environment."""

import argparse
import csv
import subprocess
from pathlib import Path

from catia_mcp.caa.paths import BRIDGE_ROOT_ENV, BRIDGE_ROOT_NAME
from catia_mcp.caa.runtime_manifest import verify_files


def prepare_environment(base_env: Path, runtime: Path) -> tuple[Path, Path]:
    base_env = base_env.resolve(strict=True)
    text = base_env.read_text(encoding="utf-8-sig")
    entries = {}
    for line in text.splitlines():
        if not line or line.startswith("!") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in entries:
            raise ValueError(f"Duplicate CATEnv variable: {key}")
        entries[key] = value
    install_value = entries.get("CATInstallPath", "")
    install = Path(install_value)
    if not install_value or not install.is_absolute():
        raise ValueError("CATInstallPath must identify an absolute win_b64 directory")
    catstart = install / "code/bin/CATSTART.exe"
    if not catstart.is_file():
        raise ValueError("The selected CATEnv does not identify an installed CATSTART.exe")
    if not entries.get("CATUserSettingPath"):
        raise ValueError("The selected CATEnv must specify the user's CATUserSettingPath")
    if BRIDGE_ROOT_ENV in entries:
        raise ValueError(f"Select the original CATEnv without {BRIDGE_ROOT_ENV}")
    additions = {
        "CATDLLPath": runtime / "code/bin",
        "CATDictionaryPath": runtime / "code/dictionary",
        "CATICPath": runtime / "code/productIC",
        "CATMsgCatalogPath": runtime / "resources/msgcatalog",
        "PATH": runtime / "code/bin",
    }
    if any(not entries.get(key) for key in additions):
        raise ValueError("The selected CATEnv must provide all bridge resource search paths")
    rewritten = []
    for line in text.splitlines():
        key = line.split("=", 1)[0]
        if key in additions:
            line = f"{key}={entries[key]};{additions[key]}"
        rewritten.append(line)
    rewritten.append(f"{BRIDGE_ROOT_ENV}={runtime / BRIDGE_ROOT_NAME}")
    desired = "\n".join(rewritten) + "\n"
    destination = runtime.parent / "CATEnv/CatiaPyBridge_B30.txt"
    if destination.resolve() == base_env:
        raise ValueError("Select the original user CATEnv, not the generated bridge environment")
    if destination.exists():
        if destination.read_text(encoding="utf-8-sig") != desired:
            raise FileExistsError("Generated CATEnv differs; review it before replacing it")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="\n") as output:
            output.write(desired)
    return catstart, destination


def ensure_no_catia() -> None:
    processes = subprocess.run(
        ["tasklist.exe", "/fi", "imagename eq CNEXT.exe", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
    )
    if any(
        row and row[0].lower() == "cnext.exe" for row in csv.reader(processes.stdout.splitlines())
    ):
        raise RuntimeError(
            "CATIA is already running; attach to it or close it yourself before an explicit launch"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-env", required=True, type=Path, help="Original user CATEnv file, UTF-8 text"
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    runtime = Path(__file__).resolve().parents[1] / "caa_workspace/CatiaPyBridgeRuntime"
    verify_files(runtime)
    if not args.prepare_only:
        ensure_no_catia()
    catstart, environment = prepare_environment(args.base_env, runtime)
    print(f"Base CATEnv: {args.base_env.resolve()}")
    print(f"Bridge CATEnv: {environment}")
    if not args.prepare_only:
        subprocess.run(
            [
                str(catstart),
                "-direnv",
                str(environment.parent),
                "-env",
                environment.stem,
                "-run",
                "CNEXT.exe",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
