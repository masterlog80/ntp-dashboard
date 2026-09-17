/* NTP Dashboard UI refresh helpers.
 * Keep the dashboard focused on local NTP/GPS status; no upstream release
 * checks or external update notifications are displayed.
 */
(function () {
    // dashboard.js currently exposes these functions globally. Replace the
    // update checker so the refreshed UI never performs the legacy release
    // notification flow after dashboard.js has loaded.
    window.checkForUpdates = function () {};

    // Avoid calling the legacy update checker on visibility/focus refreshes.
    window.refreshNow = function () {
        const now = Date.now();
        if (typeof window.lastRefreshTime !== 'undefined' &&
            typeof window.REFRESH_DEBOUNCE_MS !== 'undefined' &&
            now - window.lastRefreshTime < window.REFRESH_DEBOUNCE_MS) {
            return;
        }
        if (typeof window.lastRefreshTime !== 'undefined') {
            window.lastRefreshTime = now;
        }
        if (typeof window.fetchNTP === 'function') window.fetchNTP();
        if (typeof window.fetchGPS === 'function') window.fetchGPS();
    };
})();
