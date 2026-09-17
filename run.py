"""Production entrypoint for NTP Dashboard.

Keeps the runtime metadata detection in server.py while making the footer
layout match the HLS Proxy style regardless of the original template markup.
"""
import html
import re

from server import app


FOOTER_HTML = re.compile(r'<footer class="app-footer">.*?</footer>', re.DOTALL)

FOOTER_CSS = """
/* HLS Proxy-style application footer */
#app-footer.app-footer {
    width: 100vw;
    margin-left: calc(50% - 50vw);
    border-top: 1px solid var(--ui-border);
    padding: 1rem max(1.5rem, calc((100vw - 1400px) / 2 + 1.5rem));
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: .75rem;
    color: var(--ui-muted);
    font-size: 11px;
}
#app-footer .footer-left {
    display: flex;
    align-items: center;
    gap: .75rem;
    flex-wrap: wrap;
    min-width: 0;
}
#app-footer .footer-name {
    font-weight: 600;
    color: var(--ui-text);
}
#app-footer .footer-sep {
    color: var(--ui-muted);
}
#app-footer .footer-image {
    color: var(--ui-text);
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    white-space: nowrap;
}
@media (max-width: 700px) {
    #app-footer.app-footer {
        align-items: flex-start;
        flex-direction: column;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
}
"""

FOOTER_SCRIPT = """
<script>
(function () {
    const el = document.getElementById('footer-started');
    if (!el) return;
    const raw = el.dataset.value || el.textContent.trim();
    if (!raw || raw === '—' || raw === '-') return;
    const date = new Date(raw);
    if (!Number.isNaN(date.getTime())) {
        el.textContent = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    }
})();
</script>
"""


def _footer_after_request(response):
    if not response.content_type or not response.content_type.startswith("text/html"):
        return response

    document = response.get_data(as_text=True)
    match = FOOTER_HTML.search(document)
    if not match:
        return response

    old = match.group(0)
    started_match = re.search(
        r'Started\s*<span[^>]*>(.*?)</span>', old, re.DOTALL
    )
    image_match = re.search(
        r'<span class="footer-image[^>]*>(.*?)</span>', old, re.DOTALL
    )

    started = html.unescape(started_match.group(1).strip()) if started_match else "—"
    image = html.unescape(image_match.group(1).strip()) if image_match else "ntp-dashboard:dev"

    if not started:
        started = "—"
    if not image or image == ":":
        image = "ntp-dashboard:dev"

    replacement = (
        '<footer id="app-footer" class="app-footer">'
        '<div class="footer-left">'
        '<span class="footer-name">⏱ NTP Dashboard</span>'
        '<span class="footer-sep">·</span>'
        f'<span>Started <span id="footer-started" data-value="{html.escape(started, quote=True)}">'
        f'{html.escape(started)}</span></span>'
        '</div>'
        f'<span id="footer-image" class="footer-image">{html.escape(image)}</span>'
        '</footer>'
    )

    document = document[:match.start()] + replacement + document[match.end():]
    document = document.replace('</style>', FOOTER_CSS + '</style>', 1)
    document = document.replace('</body>', FOOTER_SCRIPT + '</body>', 1)
    response.set_data(document)
    return response


app.after_request(_footer_after_request)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=55234, debug=False)
