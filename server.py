"""Runtime wrapper that adds container metadata to the dashboard UI.

The application itself remains in app.py. This wrapper captures the process
start time and exposes image metadata to Jinja without requiring the Docker
socket in the normal case. When the Docker socket is available, the running
container's OCI labels and actual image reference are used automatically.
"""
import json
import os
import socket
import time
from datetime import datetime, timezone

from app import app


def _process_start_time():
    """Return PID 1 start time as a UTC ISO-8601 string when available."""
    try:
        hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        stat = open("/proc/self/stat", encoding="utf-8").read()
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
    if len(host) >= 12:
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


def _image_info():
    fallback_name = os.environ.get("IMAGE_NAME", "ntp-dashboard").strip() or "ntp-dashboard"
    fallback_version = os.environ.get("IMAGE_VERSION", os.environ.get("APP_VERSION", "dev")).strip() or "dev"

    cid = _container_id()
    container = _docker_request(f"/containers/{cid}/json") if cid else None
    if not container:
        return fallback_name, fallback_version

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

    # The OCI title is the application name; otherwise use the actual image name.
    title = labels.get("org.opencontainers.image.title")
    if title:
        name = title.strip()
    return name or fallback_name, version or fallback_version


_STARTED_AT = _process_start_time()
_IMAGE_NAME, _IMAGE_VERSION = _image_info()

# Make metadata available to every Jinja template while preserving app.py's
# existing / route and API implementation.
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
    startup_config = app.view_functions.get("index") and None
    # app.py's main block is intentionally not executed when imported. Keep
    # the same port and debug behaviour here.
    app.run(host="0.0.0.0", port=55234, debug=is_debug)
