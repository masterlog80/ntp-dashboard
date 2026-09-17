import os
import subprocess
import sys
from pathlib import Path


def test_runtime_hook_can_patch_flask_before_app_import(tmp_path):
    # Exercise the same mechanism used by the Docker image: a module imported
    # from site-packages before the application imports Flask/render_template.
    hook = Path(__file__).resolve().parents[1] / "ntp_dashboard_runtime.py"
    pth = tmp_path / "runtime.pth"
    pth.write_text("import ntp_dashboard_runtime\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(hook.parent)
    code = "import flask; import ntp_dashboard_runtime; from flask import Flask, render_template; app=Flask(__name__); print(getattr(Flask, '_ntp_dashboard_runtime_footer', False))"
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "True"
