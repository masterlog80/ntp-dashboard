"""Runtime footer compatibility for NTP Dashboard.

This module is imported automatically by Python before the application starts.
The dashboard historically imports ``render_template`` directly in app.py,
so replacing ``flask.render_template`` is not sufficient. Instead we attach an
``after_request`` handler to the actual Flask app once it exists. This works
whether the process is started as ``app.py``, ``server.py`` or another WSGI
launcher.
"""
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from html import escape


FOOTER_RE = re.compile(r'<footer(?:\s+[^>]*)?class="app-footer"[^>]*>.*?</footer>', re.DOTALL)


def _started_at():
    try:
        hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        with open("/proc/self/stat", encoding="utf-8") as f:
            stat = f.read()
        start_ticks = int(stat.rsplit(") ", 1)[1].split()[19])
        boot = None
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("btime "):
                    boot = float(line.split()[1])
                    break
        if boot is not None:
            return datetime.fromtimestamp(boot + start_ticks / hz, timezone.utc).isoformat(timespec="seconds")
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


STARTED_AT = _started_at()
IMAGE_NAME = (os.environ.get("IMAGE_NAME") or "ntp-dashboard").strip() or "ntp-dashboard"
IMAGE_VERSION = (
    os.environ.get("IMAGE_VERSION")
    or os.environ.get("APP_VERSION")
    or "dev"
).strip() or "dev"


FOOTER_CSS = """
/* NTP Dashboard footer — same structure as HLS Proxy Copilot */
#app-footer.app-footer {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    border-top: 1px solid var(--ui-border);
    margin-top: 24px;
    padding: 14px 2px;
    color: var(--ui-muted);
    font-size: 11px;
}
#app-footer .footer-left {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    min-width: 0;
}
#app-footer .footer-name {
    color: var(--ui-muted);
    font-weight: 500;
}
#app-footer .footer-sep { color: var(--ui-muted); }
#app-footer .footer-image {
    color: var(--ui-muted);
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    white-space: nowrap;
}
@media(max-width:700px){
    #app-footer.app-footer { align-items:flex-start; flex-direction:column; }
}
"""


def _footer_response(response):
    try:
        if not response.content_type or not response.content_type.startswith("text/html"):
            return response
        document = response.get_data(as_text=True)
        match = FOOTER_RE.search(document)
        if not match:
            return response

        # Never trust the Jinja values here: this handler is specifically the
        # fallback for deployments where app.py is launched directly and no
        # server.py context processor is active.
        footer = (
            '<footer id="app-footer" class="app-footer">'
            '<div class="footer-left">'
            '<span class="footer-name">⏱ NTP Dashboard</span>'
            '<span class="footer-sep">·</span>'
            '<span>Started <span id="footer-started" data-started="1">'
            + escape(STARTED_AT)
            + '</span></span>'
            '</div>'
            '<span id="footer-image" class="footer-image">'
            + escape(IMAGE_NAME + ":" + IMAGE_VERSION)
            + '</span>'
            '</footer>'
        )
        document = document[:match.start()] + footer + document[match.end():]

        if "/* NTP Dashboard footer — same structure as HLS Proxy Copilot */" not in document:
            document = document.replace("</style>", FOOTER_CSS + "</style>", 1)

        script = """
<script>
(function () {
    const el = document.getElementById('footer-started');
    if (!el) return;
    const d = new Date(el.textContent.trim());
    if (!Number.isNaN(d.getTime())) {
        el.textContent = d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
    }
})();
</script>
"""
        document = document.replace("</body>", script + "</body>", 1)
        response.set_data(document)
    except Exception:
        # Footer metadata must never prevent the dashboard from serving.
        pass
    return response


def _install():
    for _ in range(100):
        for module in (sys.modules.get("app"), sys.modules.get("__main__")):
            flask_app = getattr(module, "app", None) if module else None
            if flask_app is not None and hasattr(flask_app, "after_request"):
                # Avoid installing twice when a launcher imports app and then
                # server.py imports it again.
                if not getattr(flask_app, "_ntp_footer_installed", False):
                    flask_app.after_request(_footer_response)
                    flask_app._ntp_footer_installed = True
                return
        time.sleep(0.05)


threading.Thread(target=_install, name="ntp-footer-install", daemon=True).start()
