import importlib.util
import os
from pathlib import Path


def load_runtime(monkeypatch, tmp_path):
    module_path = Path(__file__).parents[1] / "ntp_dashboard_runtime.py"
    spec = importlib.util.spec_from_file_location("ntp_dashboard_runtime_test", module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(module.os.path, "exists", lambda path: False)
    spec.loader.exec_module(module)
    return module


def test_version_file_is_preferred(monkeypatch, tmp_path):
    version = tmp_path / ".version"
    version.write_text("latest\n", encoding="utf-8")

    original_open = open

    def fake_open(path, *args, **kwargs):
        if path == "/app/.version":
            return original_open(version, *args, **kwargs)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setenv("IMAGE_NAME", "ntp-dashboard")
    monkeypatch.setenv("IMAGE_VERSION", "dev")
    monkeypatch.delenv("APP_VERSION", raising=False)

    module = load_runtime(monkeypatch, tmp_path)
    assert module.IMAGE_NAME == "ntp-dashboard"
    assert module.IMAGE_VERSION == "latest"
