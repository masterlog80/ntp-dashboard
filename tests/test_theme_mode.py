from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_theme_mode_is_implemented_in_dashboard_js():
    source = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")
    assert "function setThemeMode(mode)" in source
    assert "function initThemeMode()" in source
    assert "root.dataset.colorMode = mode" in source
    assert "localStorage.themeMode" in source
    assert "prefers-color-scheme: dark" in source


def test_theme_mode_palettes_are_in_template():
    source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in source
    assert 'html[data-color-mode="light"]' in source
    assert 'html[data-color-mode="dark"]' in source
    assert 'html[data-color-mode="system"]' in source
    assert 'prefers-color-scheme: light' in source
    assert 'id="btn-light"' in source
    assert 'id="btn-system"' in source
    assert 'id="btn-dark"' in source


def test_theme_injection_module_is_not_used():
    assert not (ROOT / "ntp_dashboard_theme.py").exists()
    assert "ntp_dashboard_theme" not in (ROOT / "ntp_dashboard_runtime.pth").read_text(encoding="utf-8")
