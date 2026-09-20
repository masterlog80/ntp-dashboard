from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_theme_mode_is_implemented_in_dashboard_js():
    source = (ROOT / "static" / "dashboard.js").read_text(encoding="utf-8")
    assert "function setThemeMode(mode)" in source
    assert "function initThemeMode()" in source
    assert "root.dataset.colorMode = theme" in source
    assert "ntp-dashboard-theme" in source
    assert "btnTheme" in source


def test_theme_toggle_is_in_template():
    source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in source
    assert 'html[data-color-mode="light"]' in source
    assert 'html[data-color-mode="dark"]' in source
    assert 'id="btnTheme"' in source
    assert 'id="btn-light"' not in source
    assert 'id="btn-system"' not in source
    assert 'id="btn-dark"' not in source
    assert '>Theme ▾<' not in source


def test_theme_injection_module_is_not_used():
    assert not (ROOT / "ntp_dashboard_theme.py").exists()
    assert "ntp_dashboard_theme" not in (ROOT / "ntp_dashboard_runtime.pth").read_text(encoding="utf-8")



def test_ntp_sources_has_collapsible_chrony_explanation():
    source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert '<details class="source-help">' in source
    assert 'How to read the Chrony output' in source
    assert 'chronyc sources' in source
    assert 'Reach:</strong>' in source
    assert 'Last Sample:</strong>' in source
