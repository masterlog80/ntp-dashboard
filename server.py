"""Runtime wrapper that adds container metadata to the dashboard UI.

The application itself remains in app.py. This wrapper captures the actual
container/process start time and exposes the exact image reference to Jinja.
Detection prefers the Docker Engine API when available, then the Kubernetes
Pod API, then an explicit IMAGE_REF fallback.
"""
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from app import app

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"


def _process_start_time():
    """Return the current process start time as ISO-8601 UTC."""
    try:
        hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        with open("/proc/self/stat", encoding="utf-8") as f:
            stat = f.read()
        start_ticks = int(stat.rsplit(") ", 1)[1].split()[19])
        boot_time = None
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("btime "):
                    boot_time = float(line.split()[1])
                    break
        if boot_time is not None:
            return datetime.fromtimestamp(boot_time + start_ticks / hz, tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()


def _docker_request(path):
    socket_path = "/var/run/docker.sock"
    if not os.path.exists(socket_path):
        return None
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect(socket_path)
        sock.sendall(f"GET {path} HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
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


def _container_id():
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


def _k8s_pod():
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
        url = f"https://{host}:{port}/api/v1/namespaces/{urllib.parse.quote(namespace, safe='')}/pods/{urllib.parse.quote(pod_name, safe='')}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        context = ssl.create_default_context(cadata=ca_data.decode("utf-8"))
        with urllib.request.urlopen(req, context=context, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _parse_image_reference(raw):
    """Return the exact reference split into name and version for templates."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    if "@" in raw:
        return raw, None
    last = raw.rsplit("/", 1)[-1]
    if ":" in last:
        return raw.rsplit(":", 1)[0], raw.rsplit(":", 1)[1]
    return raw, "latest"


def _image_info():
    fallback_ref = os.environ.get("IMAGE_REF", "").strip()
    fallback_name = os.environ.get("IMAGE_NAME", "ntp-dashboard").strip() or "ntp-dashboard"
    fallback_version = os.environ.get("IMAGE_VERSION", "unknown").strip() or "unknown"
    fallback_started = _process_start_time()

    cid = _container_id()
    container = _docker_request(f"/containers/{cid}/json") if cid else None
    if container:
        raw = (container.get("Config") or {}).get("Image")
        if raw:
            name, version = _parse_image_reference(raw)
            return name, version, (container.get("State") or {}).get("StartedAt") or fallback_started

    pod = _k8s_pod()
    if pod:
        containers = pod.get("spec", {}).get("containers") or []
        target = next((c for c in containers if c.get("name") == "ntp-dashboard"), containers[0] if containers else {})
        raw = target.get("image")
        if raw:
            name, version = _parse_image_reference(raw)
            status = next((s for s in pod.get("status", {}).get("containerStatuses", []) if s.get("name") == target.get("name")), {})
            started = (status.get("state") or {}).get("running", {}).get("startedAt")
            return name, version, started or fallback_started

    if fallback_ref:
        name, version = _parse_image_reference(fallback_ref)
        return name, version, fallback_started
    return fallback_name, fallback_version, fallback_started


_STARTED_AT, _IMAGE_NAME, _IMAGE_VERSION = _image_info()


@app.context_processor
def runtime_metadata():
    return {
        "app_started_at": _STARTED_AT or _process_start_time(),
        "image_name": _IMAGE_NAME or "ntp-dashboard",
        "image_version": _IMAGE_VERSION or "unknown",
    }


if __name__ == "__main__":
    debug_mode_env = os.environ.get("DEBUG_MODE", "").lower()
    is_debug = debug_mode_env == "true" or os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"
    app.run(host="0.0.0.0", port=55234, debug=is_debug)
