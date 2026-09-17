"""Runtime wrapper that adds container metadata to the dashboard UI.

The application itself remains in app.py. This wrapper captures the process
start time and exposes image metadata to Jinja. Metadata detection prefers the
Docker Engine API when available and falls back to the Kubernetes API when the
application is running in a Pod with an appropriately scoped ServiceAccount.
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


def _process_start_time():
    """Return PID 1 start time as an ISO-8601 string when available."""
    try:
        hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        with open("/proc/self/stat", encoding="utf-8") as f:
            stat = f.read()
        start_ticks = int(stat.rsplit(") ", 1)[1].split()[19])
        boot_time = None
        with open("/proc/stat", encoding="utf-8") as proc_stat:
            for line in proc_stat:
                if line.startswith("btime "):
                    boot_time = float(line.split()[1])
                    break
        if boot_time is not None:
            started = datetime.fromtimestamp(boot_time + start_ticks / hz, tz=timezone.utc)
            return started.isoformat(timespec="seconds")
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _docker_request(path):
    """Read a Docker Engine API endpoint through the local Unix socket."""
    if not os.path.exists("/var/run/docker.sock"):
        return None
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect("/var/run/docker.sock")
        sock.sendall(f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        header, _, body = raw.partition(b"\r\n\r\n")
        if not header.startswith(b"HTTP/") or b" 200 " not in header.split(b"\r\n", 1)[0]:
            return None
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None
    finally:
        sock.close()


def _container_id():
    host = os.environ.get("HOSTNAME", "").strip()
    if len(host) >= 12 and all(c in "0123456789abcdef" for c in host.lower()):
        return host
    try:
        with open("/proc/self/cgroup", encoding="utf-8") as f:
            for line in f:
                for part in line.strip().split("/"):
                    if len(part) >= 12 and all(c in "0123456789abcdef" for c in part.lower()):
                        return part[:64]
    except Exception:
        pass
    return None


def _k8s_request(path):
    """Read a Kubernetes API endpoint using the Pod's projected SA token."""
    sa_dir = "/var/run/secrets/kubernetes.io/serviceaccount"
    token_file = os.path.join(sa_dir, "token")
    namespace_file = os.path.join(sa_dir, "namespace")
    ca_file = os.path.join(sa_dir, "ca.crt")

    if not all(os.path.exists(p) for p in (token_file, namespace_file, ca_file)):
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
        url = f"https://{host}:{port}{path}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        context = ssl.create_default_context(cadata=ca_data.decode("utf-8"))
        with urllib.request.urlopen(request, context=context, timeout=5) as response:
            return json.loads(response.read().decode("utf-8")), namespace
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _detect_via_kubernetes():
    """Detect image name/version and actual container start time from the Pod."""
    pod_name = os.environ.get("HOSTNAME", "").strip()
    if not pod_name:
        return None

    result = _k8s_request(
        f"/api/v1/namespaces/{{namespace}}/pods/{urllib.parse.quote(pod_name, safe='')}"
    )
    if not result:
        return None

    pod, namespace = result
    # The namespace placeholder is resolved by retrying with the namespace
    # discovered from the projected ServiceAccount. This avoids trusting an
    # environment variable supplied by the container image.
    if "{namespace}" in f"/api/v1/namespaces/{{namespace}}/pods/{urllib.parse.quote(pod_name, safe='')}":
        result = _k8s_request(
            f"/api/v1/namespaces/{urllib.parse.quote(namespace, safe='')}/pods/{urllib.parse.quote(pod_name, safe='')}"
        )
        if not result:
            return None
        pod, namespace = result

    containers = pod.get("spec", {}).get("containers") or []
    statuses = pod.get("status", {}).get("containerStatuses") or []
    if not containers:
        return None

    raw = (containers[0].get("image") or "").strip()
    if not raw and statuses:
        raw = (statuses[0].get("image") or "").strip()
    if not raw:
        return None

    short = raw.rsplit("/", 1)[-1]
    if ":" in short:
        name, version = short.rsplit(":", 1)
    else:
        name, version = short, None

    if version and "@sha256:" in version:
        version = None
    if not version or version == "latest":
        version = os.environ.get("IMAGE_VERSION") or os.environ.get("APP_VERSION")

    started_at = None
    for status in statuses:
        state = status.get("state") or {}
        running = state.get("running") or {}
        if running.get("startedAt"):
            started_at = running["startedAt"]
            break

    return name or "ntp-dashboard", version or "unknown", started_at


def _image_info():
    fallback_name = os.environ.get("IMAGE_NAME", "ntp-dashboard").strip() or "ntp-dashboard"
    fallback_version = os.environ.get("IMAGE_VERSION", os.environ.get("APP_VERSION", "dev")).strip() or "dev"
    fallback_started = _process_start_time()

    cid = _container_id()
    container = _docker_request(f"/containers/{cid}/json") if cid else None
    if container:
        labels = (container.get("Config") or {}).get("Labels") or {}
        raw = ((container.get("Config") or {}).get("Image") or "").strip()
        name = raw.rsplit("/", 1)[-1].split(":", 1)[0] if raw else fallback_name
        version = labels.get("org.opencontainers.image.version") or None

        if not version and ":" in raw:
            version = raw.rsplit(":", 1)[-1]
        if not version or version == "latest":
            image_id = container.get("Image")
            if image_id:
                image = _docker_request(f"/images/{image_id}/json")
                if image:
                    image_labels = (image.get("Config") or {}).get("Labels") or {}
                    version = image_labels.get("org.opencontainers.image.version") or version
                    if not version or version == "latest":
                        tags = image.get("RepoTags") or []
                        if tags:
                            version = tags[0].rsplit(":", 1)[-1]

        started_at = (container.get("State") or {}).get("StartedAt") or fallback_started
        return name or fallback_name, version or fallback_version, started_at

    k8s_info = _detect_via_kubernetes()
    if k8s_info:
        return k8s_info

    return fallback_name, fallback_version, fallback_started


_STARTED_AT, _IMAGE_NAME, _IMAGE_VERSION = _image_info()


@app.context_processor
def runtime_metadata():
    return {
        "app_started_at": _STARTED_AT,
        "image_name": _IMAGE_NAME,
        "image_version": _IMAGE_VERSION,
    }


if __name__ == "__main__":
    debug_mode_env = os.environ.get("DEBUG_MODE", "").lower()
    is_debug = debug_mode_env == "true" or os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"
    app.run(host="0.0.0.0", port=55234, debug=is_debug)
