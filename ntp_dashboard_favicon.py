"""Inject the NTP Dashboard favicon into HTML responses."""


def install():
    try:
        from flask import Flask
    except Exception:
        return
    if getattr(Flask, "_ntp_dashboard_favicon", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        @self.after_request
        def favicon(response):
            try:
                if not (response.content_type and response.content_type.startswith("text/html")):
                    return response
                document = response.get_data(as_text=True)
                if 'rel="icon"' in document or "rel='icon'" in document:
                    return response
                marker = "</head>"
                if marker not in document:
                    return response
                link = '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">\n'
                response.set_data(document.replace(marker, link + marker, 1))
            except Exception:
                pass
            return response

    Flask.__init__ = patched_init
    Flask._ntp_dashboard_favicon = True


install()
