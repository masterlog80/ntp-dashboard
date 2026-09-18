"""Runtime footer hook loaded before the Flask application."""
import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import escape

FOOTER_RE = re.compile(r'<footer(?:\s+[^>]*)?class=["\']app-footer["\'][^>]*>.*?</footer>', re.DOTALL)
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"


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


def docker_request(path):
    """Read a Docker Engine API endpoint through the optional local Unix socket."""
    socket_path = "/var/run/docker.sock"
    if not os.path.exists(socket_path):
        return None
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect(socket_path)
        sock.sendall(
            f"GET {path} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode()
        )
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        header, _, body = raw.partition(b"\r\n\r\n")
        status = header.split(b"\r\n", 1)[0] if header else b""
        if not status.startswith(b"HTTP/") or b" 200 " not in status:
            return None
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None
    finally:
        sock.close()


def container_id():
    """Find the Docker container ID from HOSTNAME or cgroup metadata."""
    hostname = os.environ.get("HOSTNAME", "").strip()
    if len(hostname) >= 12 and all(c in "0123456789abcdef" for c in hostname.lower()):
        return hostname
    try:
        with open("/proc/self/cgroup", encoding="utf-8") as f:
            for line in f:
                for part in line.strip().split("/"):
                    if len(part) >= 12 and all(c in "0123456789abcdef" for c in part.lower()):
                        return part[:64]
    except Exception:
        pass
    return None


def kubernetes_pod():
    """Return the current Pod object when the Kubernetes API is available."""
    token_file = os.path.join(SA_DIR, "token")
    namespace_file = os.path.join(SA_DIR, "namespace")
    ca_file = os.path.join(SA_DIR, "ca.crt")
    pod_name = os.environ.get("HOSTNAME", "").strip()
    if not pod_name or not all(os.path.exists(p) for p in (token_file, namespace_file, ca_file)):
        return None

    try:
        with open(token_file, encoding="utf-8") as f:
            token = f.read().strip()
        with open(namespace_file, encoding="utf-8") as f:
            namespace = f.read().strip()
        with open(ca_file, "rb") as f:
            ca_data = f.read()

        host = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        url = (
            f"https://{host}:{port}/api/v1/namespaces/"
            f"{urllib.parse.quote(namespace, safe='')}/pods/"
            f"{urllib.parse.quote(pod_name, safe='')}"
        )
        request = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        context = ssl.create_default_context(cadata=ca_data.decode("utf-8"))
        with urllib.request.urlopen(request, timeout=3, context=context) as response:
            return json.load(response)
    except Exception:
        return None


def detect_image_ref():
    """Return the exact image reference, preferring Docker then Kubernetes."""
    cid = container_id()
    if cid:
        container = docker_request(f"/containers/{cid}/json")
        if container:
            raw = (container.get("Config") or {}).get("Image")
            if raw:
                return raw.strip()

    pod = kubernetes_pod()
    if pod:
        containers = pod.get("spec", {}).get("containers") or []
        for container in containers:
            if container.get("name") == "ntp-dashboard" and container.get("image"):
                return container["image"].strip()
        if containers and containers[0].get("image"):
            return containers[0]["image"].strip()

    return None


STARTED_AT = process_started_at()
IMAGE_REF = detect_image_ref() or os.environ.get("IMAGE_REF") or "ntp-dashboard:unknown"


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
                    + escape(IMAGE_REF)
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
