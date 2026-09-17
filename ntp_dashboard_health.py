"""Lightweight health endpoint injected before the Flask application starts."""


def install():
    try:
        from flask import Flask, Response
    except Exception:
        return

    if getattr(Flask, "_ntp_dashboard_health_installed", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        @self.get("/healthz")
        def healthz():
            return Response("OK\\n", status=200, mimetype="text/plain")

    Flask.__init__ = patched_init
    Flask._ntp_dashboard_health_installed = True


install()