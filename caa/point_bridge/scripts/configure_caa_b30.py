"""Write local B30 configuration with LF line endings; never launch CATIA."""
import argparse
from pathlib import Path

from catia_mcp.caa.runtime_manifest import JSON_HEADER, verify_json_header


def configure(install: Path, json_header: Path) -> Path:
    install = install.resolve(strict=True)
    workspace = Path(__file__).resolve().parents[1] / "caa_workspace"
    for path in (install, workspace):
        if any(character in str(path) for character in '\r\n%&|<>^!"'):
            raise ValueError("Path contains unsupported batch characters")
    if not (install / "win_b64/code/bin/CATSTART.exe").is_file():
        raise ValueError("CATIA B30 installation must contain CATSTART.exe")
    config = workspace / "Install_config_win_b64"
    desired = "<Install> compatible\n" + str(install) + "\n"
    if config.exists() and config.read_text(encoding="utf-8") != desired:
        raise ValueError("Existing configuration differs; review it before changing")
    verify_json_header(json_header)
    local_header = workspace / JSON_HEADER
    if local_header.exists():
        verify_json_header(local_header)
    else:
        with local_header.open("xb") as target:
            target.write(json_header.read_bytes())
    if not config.exists():
        with config.open("x", encoding="utf-8", newline="\n") as output:
            output.write(desired)
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catia-install", required=True, type=Path)
    parser.add_argument("--json-header", required=True, type=Path, help="Official v3.11.3 json.hpp")
    args = parser.parse_args()
    print(configure(args.catia_install, args.json_header))
