/* NTP Dashboard UI refresh helpers.
 * Keep the dashboard focused on local NTP/GPS status; no upstream release
 * checks or external update notifications are displayed.
 */
(function () {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.includes('/api/update')) {
            return Promise.resolve(new Response(JSON.stringify({
                current: null,
                latest: null,
                update: false,
                error: null
            }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
        }
        return nativeFetch(input, init);
    };
})();
