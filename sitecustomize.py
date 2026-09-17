"""Early runtime compatibility layer for NTP Dashboard.

Python imports ``sitecustomize`` automatically during normal startup. This
means the dashboard keeps its runtime footer even when an external launcher
(Kubernetes, Docker Compose, etc.) overrides the image CMD and starts
``app.py`` directly instead of ``run.py``.

The normal ``run.py`` path still provides richer Docker/Kubernetes metadata;
this module is the safe fallback path.
"""
import re
import time
from datetime import datetime, timezone


def _process_start_time():
    try:
        hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        with open("/proc/self/stat", encoding="utf-8") as f:
            stat = f.read()
        start_ticks = int(stat.rsplit(") ", 1)[1].split()[19])
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("btime "):
                    boot = float(line.split()[1])
                    return datetime.fromtimestamp(
                        boot + start_ticks / hz, tz=timezone.utc
                    ).isoformat(timespec="seconds")
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Imported lazily below so Python startup remains cheap when this module is
# loaded by tools other than the dashboard.
import os

STARTED_AT = _process_start_time()
IMAGE_NAME = os.environ.get("IMAGE_NAME", "ntp-dashboard") or "ntp-dashboard"
IMAGE_VERSION = (
    os.environ.get("IMAGE_VERSION")
    or os.environ.get("APP_VERSION")
    or "dev"
)


try:
    import flask
    from markupsafe import Markup

    _original_render_template = flask.render_template

    def _render_template_with_runtime(template_name, **context):
        context.setdefault("app_started_at", STARTED_AT)
        context.setdefault("image_name", IMAGE_NAME)
        context.setdefault("image_version", IMAGE_VERSION)

        rendered = _original_render_template(template_name, **context)

        # Only touch the dashboard footer. The operation is deliberately
        # idempotent so run.py can add its richer footer without duplication.
        if "id=\"app-footer\"" in rendered:
            return rendered

        footer_re = re.compile(
            r'<footer class="app-footer">.*?</footer>', re.DOTALL
        )
        footer = footer_re.search(rendered)
        if not footer:
            return rendered

        replacement = (
            '<footer id="app-footer" class="app-footer">'
            '<div class="footer-left">'
            '<span class="footer-name">⏱ NTP Dashboard</span>'
            '<span class="footer-sep">·</span>'
            '<span>Started <span id="footer-started" '
            'class="mono" data-runtime-started="1">'
            f'{STARTED_AT}</span></span>'
            '</div>'
            f'<span class="footer-image mono">{IMAGE_NAME}:{IMAGE_VERSION}</span>'
            '</footer>'
        )

        rendered = rendered[:footer.start()] + replacement + rendered[footer.end():]

        css = """
<style>
/* Runtime footer: intentionally mirrors the HLS Proxy footer layout. */
#app-footer.app-footer {
    width: 100vw;
    margin-left: calc(50% - 50vw);
    border-top: 1px solid var(--ui-border);
    padding: 1rem max(1.5rem, calc((100vw - 1400px) / 2 + 1.5rem));
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: .75rem;
    color: var(--ui-muted);
    font-size: 11px;
}
#app-footer .footer-left {
    display: flex;
    align-items: center;
    gap: .75rem;
    flex-wrap: wrap;
    min-width: 0;
}
#app-footer .footer-name {
    color: var(--ui-text);
    font-weight: 600;
}
#app-footer .footer-sep { color: var(--ui-muted); }
#app-footer .footer-image {
    color: var(--ui-text);
    white-space: nowrap;
}
@media (max-width: 700px) {
    #app-footer.app-footer {
        align-items: flex-start;
        flex-direction: column;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
}
</style>
"""
        rendered = rendered.replace("</head>", css + "</head>", 1)

        script = """
<script>
(function () {
    const el = document.querySelector('[data-runtime-started="1"]');
    if (!el) return;
    const date = new Date(el.textContent.trim());
    if (!Number.isNaN(date.getTime())) {
        el.textContent = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    }
})();
</script>
"""
        rendered = rendered.replace("</body>", script + "</body>", 1)
        return Markup(rendered)

    flask.render_template = _render_template_with_runtime
except Exception:
    # Never prevent the dashboard from starting because the compatibility
    # footer is unavailable.
    pass
