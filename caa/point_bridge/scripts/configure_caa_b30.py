"""Write local B30 configuration with LF line endings; never launch CATIA."""
import argparse
from pathlib import Path


def configure(install: Path) -> Path:
    install = install.resolve(strict=True)
    workspace = Path(__file__).resolve().parents[1] / "caa_workspace"
    for path in (install, workspace):
        if any(character in str(path) for character in '\r\n%&|<>^!"'):
            raise ValueError("Path contains unsupported batch characters")
    if not (install / "win_b64/code/bin/CATSTART.exe").is_file():
        raise ValueError("CATIA B30 installation must contain CATSTART.exe")
    config = workspace / "Install_config_win_b64"
    desired = "<Install> compatible\n" + str(install) + "\n"
    if config.exists():
        if config.read_text(encoding="utf-8") != desired:
            raise ValueError("Existing configuration differs; review it before changing")
    else:
        with config.open("x", encoding="utf-8", newline="\n") as output:
            output.write(desired)
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catia-install", required=True, type=Path)
    print(configure(parser.parse_args().catia_install))
