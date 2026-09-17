"""Runtime wrapper that adds container metadata to the dashboard UI.

The application itself remains in app.py. This wrapper captures the actual
container/process start time and exposes image metadata to Jinja. Detection
prefers the Docker Engine API when available, then the Kubernetes Pod API,
then explicit environment variables.
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

        # /proc/[pid]/stat field 22 is starttime, i.e. field index 19 after
        # splitting off the executable name in parentheses.
        start_ticks = int(stat.rsplit(") ", 1)[1].split()[19])
        boot_time = None
        with open("/proc/stat", encoding="utf-8") as f:
            for line in f:
                if line.startswith("btime "):
                    boot_time = float(line.split()[1])
                    break

        if boot_time is not None:
            return datetime.fromtimestamp(
                boot_time + start_ticks / hz, tz=timezone.utc
            ).isoformat(timespec="seconds")
    except Exception:
        pass

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _docker_request(path):
    """Read a Docker Engine API endpoint through the local Unix socket."""
    socket_path = "/var/run/docker.sock"
    if not os.path.exists(socket_path):
        return None

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(3)
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


def _container_id():
    """Find a Docker container ID when running under Docker."""
    hostname = os.environ.get("HOSTNAME", "").strip()
    if len(hostname) >= 12 and all(c in "0123456789abcdef" for c in hostname.lower()):
        return hostname

    try:
        with open("/proc/self/cgroup", encoding="utf-8") as f:
            for line in f:
                for part in line.strip().split("/"):
                    if len(part) >= 12 and all(
                        c in "0123456789abcdef" for c in part.lower()
                    ):
                        return part[:64]
    except Exception:
        pass

    return None


def _k8s_pod():
    """Read the current Pod using its projected ServiceAccount token."""
    token_file = os.path.join(SA_DIR, "token")
    namespace_file = os.path.join(SA_DIR, "namespace")
    ca_file = os.path.join(SA_DIR, "ca.crt")
    pod_name = os.environ.get("HOSTNAME", "").strip()

    if not pod_name or not all(
        os.path.exists(p) for p in (token_file, namespace_file, ca_file)
    ):
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
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        context = ssl.create_default_context(cadata=ca_data.decode("utf-8"))
        with urllib.request.urlopen(req, context=context, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _parse_image_reference(raw):
    """Return (short image name, tag) from a Docker/Kubernetes image reference."""
    raw = (raw or "").strip()
    if not raw:
        return None, None

    short = raw.rsplit("/", 1)[-1]

    # A digest is not a useful human-readable version for this footer.
    if "@" in short:
        name, digest = short.split("@", 1)
        if digest.startswith("sha256:"):
            return name, None

    # Only a colon after the final slash is a tag separator. At this point the
    # registry portion has already been removed, so a normal name:tag is safe.
    if ":" in short:
        name, tag = short.rsplit(":", 1)
        return name, tag

    return short, None


def _detect_via_kubernetes():
    """Detect image name/tag and actual container start time from this Pod."""
    pod = _k8s_pod()
    if not pod:
        return None

    containers = pod.get("spec", {}).get("containers") or []
    statuses = pod.get("status", {}).get("containerStatuses") or []
    if not containers:
        return None

    # This dashboard Deployment has one application container. Prefer the
    # status entry with the same name so multi-container Pods remain safe.
    container = containers[0]
    container_name = container.get("name")
    status = next(
        (s for s in statuses if s.get("name") == container_name),
        statuses[0] if statuses else {},
    )

    raw = container.get("image") or status.get("image") or ""
    name, version = _parse_image_reference(raw)

    if not version or version == "latest":
        version = (
            os.environ.get("IMAGE_VERSION")
            or os.environ.get("APP_VERSION")
            or "unknown"
        )

    running = (status.get("state") or {}).get("running") or {}
    started_at = running.get("startedAt")

    return name or "ntp-dashboard", version, started_at


def _image_info():
    """Return (image_name, image_version, started_at)."""
    fallback_name = os.environ.get("IMAGE_NAME", "ntp-dashboard").strip() or "ntp-dashboard"
    fallback_version = (
        os.environ.get("IMAGE_VERSION")
        or os.environ.get("APP_VERSION")
        or "dev"
    ).strip() or "dev"
    fallback_started = _process_start_time()

    # Docker: use the actual container metadata when the socket is mounted.
    container_id = _container_id()
    container = (
        _docker_request(f"/containers/{container_id}/json")
        if container_id
        else None
    )
    if container:
        config = container.get("Config") or {}
        labels = config.get("Labels") or {}
        raw = (config.get("Image") or "").strip()
        name, version = _parse_image_reference(raw)
        name = name or fallback_name

        version = labels.get("org.opencontainers.image.version") or version

        image_id = container.get("Image")
        if (not version or version == "latest") and image_id:
            image = _docker_request(f"/images/{image_id}/json")
            if image:
                image_config = image.get("Config") or {}
                image_labels = image_config.get("Labels") or {}
                version = image_labels.get("org.opencontainers.image.version") or version
                if not version or version == "latest":
                    tags = image.get("RepoTags") or []
                    if tags:
                        _, version = _parse_image_reference(tags[0])

        started_at = (container.get("State") or {}).get("StartedAt") or fallback_started
        return name, version or fallback_version, started_at

    # Kubernetes: query only the current Pod. RBAC is intentionally limited to
    # GET on Pods in the namespace.
    k8s_info = _detect_via_kubernetes()
    if k8s_info:
        name, version, started_at = k8s_info
        return name, version, started_at or fallback_started

    return fallback_name, fallback_version, fallback_started


_STARTED_AT, _IMAGE_NAME, _IMAGE_VERSION = _image_info()


@app.context_processor
def runtime_metadata():
    """Expose non-empty runtime metadata to every Jinja template."""
    return {
        "app_started_at": _STARTED_AT or _process_start_time(),
        "image_name": _IMAGE_NAME or os.environ.get("IMAGE_NAME", "ntp-dashboard"),
        "image_version": _IMAGE_VERSION or os.environ.get("APP_VERSION", "dev"),
    }


if __name__ == "__main__":
    debug_mode_env = os.environ.get("DEBUG_MODE", "").lower()
    is_debug = debug_mode_env == "true" or os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG"
    app.run(host="0.0.0.0", port=55234, debug=is_debug)
