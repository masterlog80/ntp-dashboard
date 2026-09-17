"""Runtime footer hook loaded before the Flask application."""
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import escape

FOOTER_RE = re.compile(r'<footer(?:\s+[^>]*)?class=["\']app-footer["\'][^>]*>.*?</footer>', re.DOTALL)


def process_started_at():
    try:
        hz = os.sysconf("SC_CLK_TCK")
        with open("/proc/self/stat", encoding="utf-8") as f:
            stat = f.read()
        ticks = int(stat.rsplit(") ", 1)[1].split()[19])
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("btime "):
                    boot = int(line.split()[1])
                    return datetime.fromtimestamp(boot + ticks / hz, timezone.utc).isoformat(timespec="seconds")
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()


def kubernetes_pod_image():
    """Return the image reference from the current Kubernetes Pod, if available."""
    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    namespace_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    try:
        with open(token_path, encoding="utf-8") as f:
            token = f.read().strip()
        with open(namespace_path, encoding="utf-8") as f:
            namespace = f.read().strip()

        pod_name = os.environ.get("HOSTNAME", "").strip()
        host = os.environ.get("KUBERNETES_SERVICE_HOST", "").strip()
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443").strip()
        if not token or not namespace or not pod_name or not host:
            return None

        url = (
            f"https://{host}:{port}/api/v1/namespaces/"
            f"{urllib.parse.quote(namespace, safe='')}/pods/"
            f"{urllib.parse.quote(pod_name, safe='')}"
        )
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

        context = ssl.create_default_context(cafile=ca_path) if os.path.exists(ca_path) else ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=2, context=context) as response:
            pod = json.load(response)

        containers = pod.get("spec", {}).get("containers", [])
        if not containers:
            return None

        preferred = next(
            (c for c in containers if c.get("name") == "ntp-dashboard"),
            containers[0],
        )
        return (preferred.get("image") or "").strip() or None
    except (OSError, ValueError, KeyError, urllib.error.URLError, ssl.SSLError):
        return None


def version_file_image():
    """Return the build-time image version written into /app/.version."""
    try:
        with open("/app/.version", encoding="utf-8") as f:
            version = f.read().strip()
        if version:
            return version
    except OSError:
        pass
    return None


STARTED_AT = process_started_at()

# Follow the same reliable strategy used by hls-proxy:
#   1. build-time /app/.version (works in ordinary Docker without privileges)
#   2. Kubernetes Pod image (when running under Kubernetes)
#   3. environment fallback
#
# The version file is deliberately checked first because a normal Docker
# container cannot see the tag it was started from unless the Docker socket is
# mounted. The Dockerfile creates the file from APP_VERSION and defaults it to
# "latest", which matches the normal ntp-dashboard:latest image.
FILE_VERSION = version_file_image()
K8S_IMAGE = kubernetes_pod_image()

if FILE_VERSION:
    IMAGE_NAME = (os.environ.get("IMAGE_NAME") or "ntp-dashboard").strip() or "ntp-dashboard"
    IMAGE_VERSION = FILE_VERSION
elif K8S_IMAGE:
    def image_parts(image_ref):
        image_ref = (image_ref or "").strip()
        if not image_ref:
            return "ntp-dashboard", "latest"
        if "@" in image_ref:
            name, digest = image_ref.rsplit("@", 1)
            return name, digest
        last = image_ref.rsplit("/", 1)[-1]
        if ":" in last:
            name, version = image_ref.rsplit(":", 1)
            return name, version
        return image_ref, "latest"

    IMAGE_NAME, IMAGE_VERSION = image_parts(K8S_IMAGE)
else:
    IMAGE_NAME = (os.environ.get("IMAGE_NAME") or "ntp-dashboard").strip() or "ntp-dashboard"
    IMAGE_VERSION = (
        os.environ.get("IMAGE_VERSION")
        or os.environ.get("APP_VERSION")
        or "latest"
    ).strip() or "latest"


def install():
    try:
        from flask import Flask
    except Exception:
        return
    if getattr(Flask, "_ntp_dashboard_runtime_footer", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        @self.after_request
        def runtime_footer(response):
            try:
                if not (response.content_type and response.content_type.startswith("text/html")):
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
                    + '</span></span></div>'
                    '<span class="footer-image">'
                    + escape(f"{IMAGE_NAME}:{IMAGE_VERSION}")
                    + '</span></footer>'
                )
                document = document[:match.start()] + footer + document[match.end():]

                css = """
<style>
#app-footer.app-footer{width:100%;display:flex;justify-content:space-between;align-items:center;gap:12px;border-top:1px solid var(--ui-border);margin-top:24px;padding:14px 2px;color:var(--ui-muted);font-size:11px}
#app-footer .footer-left{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
#app-footer .footer-name{color:var(--ui-muted);font-weight:500}
#app-footer .footer-sep{color:var(--ui-muted)}
#app-footer .footer-image{color:var(--ui-muted);font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace;white-space:nowrap}
@media(max-width:700px){#app-footer.app-footer{align-items:flex-start;flex-direction:column}}
</style>
"""
                document = document.replace("</style>", css + "</style>", 1)

                script = """
<script>
(function(){const e=document.getElementById('footer-started');if(!e)return;const d=new Date(e.textContent.trim());if(!Number.isNaN(d.getTime()))e.textContent=d.toLocaleDateString()+' '+d.toLocaleTimeString();})();
</script>
"""
                document = document.replace("</body>", script + "</body>", 1)
                response.set_data(document)
            except Exception:
                pass
            return response

    Flask.__init__ = patched_init
    Flask._ntp_dashboard_runtime_footer = True


install()
