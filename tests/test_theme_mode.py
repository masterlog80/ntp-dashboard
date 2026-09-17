def test_theme_mode_module_has_expected_modes():
    source = open("ntp_dashboard_theme.py", encoding="utf-8").read()
    assert "['light','system','dark']" in source
    assert "localStorage" in source
    assert "prefers-color-scheme: light" in source
    assert "window.setThemeMode" in source
