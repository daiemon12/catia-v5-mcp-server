"""The explicit launcher preserves user environment and never selects settings."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "caa_launch",
    Path(__file__).resolve().parents[1] / "caa/point_bridge/scripts/start_catia_bridge_b30.py",
)
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)


@pytest.fixture
def environment(tmp_path):
    install = tmp_path / "B30/win_b64"
    (install / "code/bin").mkdir(parents=True)
    (install / "code/bin/CATSTART.exe").write_bytes(b"not an executable")
    text = (
        "! User CATEnv\n"
        + "\n".join(
            [
                f"CATInstallPath={install}",
                "CATUserSettingPath=CSIDL_APPDATA\\UserSettings",
                "CATReferenceSettingPath=ReferenceSettings",
                "DSLICENSING=DSLS",
                "OTHER=value=with=equals",
                *[
                    f"{key}=original/{key}"
                    for key in (
                        "CATDLLPath",
                        "CATDictionaryPath",
                        "CATICPath",
                        "CATMsgCatalogPath",
                        "PATH",
                    )
                ],
            ]
        )
        + "\n"
    )
    base = tmp_path / "user.txt"
    base.write_text(text, encoding="utf-8")
    return base, tmp_path / "bridge/Runtime", text


def test_derive_preserves_settings_and_licensing_and_original_file(environment):
    base, runtime, original = environment
    catstart, generated = launch.prepare_environment(base, runtime)
    result = generated.read_text(encoding="utf-8")
    assert base.read_text(encoding="utf-8") == original
    for line in original.splitlines():
        key = line.split("=", 1)[0]
        if key in {"CATDLLPath", "CATDictionaryPath", "CATICPath", "CATMsgCatalogPath", "PATH"}:
            assert f"{line};{runtime}" in result
        else:
            assert line in result.splitlines()
    assert f"CATIA_MCP_CAA_BRIDGE_ROOT={runtime / 'jobs'}" in result.splitlines()
    assert catstart.name == "CATSTART.exe"
    assert "CATSettings30" not in result
    assert launch.prepare_environment(base, runtime)[1] == generated


def test_conflicting_generated_environment_is_preserved(environment):
    base, runtime, _ = environment
    _, generated = launch.prepare_environment(base, runtime)
    generated.write_text("user modification", encoding="utf-8")
    with pytest.raises(FileExistsError):
        launch.prepare_environment(base, runtime)
    assert generated.read_text(encoding="utf-8") == "user modification"


@pytest.mark.parametrize("change", ["missing_settings", "missing_install", "duplicate"])
def test_invalid_base_does_not_create_bridge_environment(environment, change):
    base, runtime, text = environment
    if change == "missing_settings":
        text = text.replace("CATUserSettingPath=CSIDL_APPDATA\\UserSettings", "CATUserSettingPath=")
    elif change == "missing_install":
        text = text.replace("CATInstallPath=", "IgnoredInstallPath=")
    else:
        text += "CATUserSettingPath=other\n"
    base.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        launch.prepare_environment(base, runtime)
    assert not runtime.parent.exists()


def test_existing_cnext_refuses_launch_without_closing_it(monkeypatch):
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, '"CNEXT.exe","123","Console","1","12 K"\n')

    monkeypatch.setattr(launch.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="already running"):
        launch.ensure_no_catia()
    assert len(calls) == 1 and calls[0][0] == "tasklist.exe"
