"""Runtime footer compatibility for NTP Dashboard.

Python loads sitecustomize before importing the application. We patch Flask's
constructor so the footer handler is attached to the actual Flask app even
when a deployment starts app.py directly and bypasses server.py/run.py.
"""
import os
import re
from datetime import datetime, timezone
from html import escape


FOOTER_RE = re.compile(
    r'<footer(?:\s+[^>]*)?class=["\']app-footer["\'][^>]*>.*?</footer>',
    re.DOTALL,
)


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
                    boot = int(line.split()[1])
                    break
        if boot is not None:
            return datetime.fromtimestamp(
                boot + start_ticks / hz, timezone.utc
            ).isoformat(timespec="seconds")
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


def _patch_flask():
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ntp_dashboard_footer_patched", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        @self.after_request
        def _ntp_dashboard_footer(response):
            try:
                if not response.content_type or not response.content_type.startswith("text/html"):
                    return response

                document = response.get_data(as_text=True)
                match = FOOTER_RE.search(document)
                if not match:
                    return response

                footer = (
                    '<footer id="app-footer" class="app-footer">'
                    '<div class="footer-left">'
                    '<span class="footer-name">⏱ NTP Dashboard</span>'
                    '<span class="footer-sep">·</span>'
                    '<span>Started <span id="footer-started" data-runtime-started="1">'
                    + escape(STARTED_AT)
                    + '</span></span>'
                    '</div>'
                    '<span id="footer-image" class="footer-image">'
                    + escape(f"{IMAGE_NAME}:{IMAGE_VERSION}")
                    + '</span>'
                    '</footer>'
                )
                document = document[:match.start()] + footer + document[match.end():]

                css = """
<style>
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
#app-footer .footer-name { color: var(--ui-muted); font-weight: 500; }
#app-footer .footer-sep { color: var(--ui-muted); }
#app-footer .footer-image {
    color: var(--ui-muted);
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    white-space: nowrap;
}
@media(max-width:700px){
    #app-footer.app-footer { align-items:flex-start; flex-direction:column; }
}
</style>
"""
                if "#app-footer.app-footer" not in document:
                    document = document.replace("</style>", css + "</style>", 1)

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
                if "data-runtime-started" in document:
                    document = document.replace("</body>", script + "</body>", 1)

                response.set_data(document)
            except Exception:
                # Metadata must never stop the dashboard from serving.
                pass
            return response

    Flask.__init__ = patched_init
    Flask._ntp_dashboard_footer_patched = True


_patch_flask()
