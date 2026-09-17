const state = {
    gpsBaseMs: null,
    gpsFetchMs: null,
    clients: [],
    sweepTimer: 30,
    ntpTimer: null,
    gpsTimer: null,
    metricsTimer: null,
    lastRefresh: 0
};

const themes = [
    ['blue','Default Blue','#58a6ff'], ['emerald','Emerald Green','#10b981'], ['rose','Rose Red','#f43f5e'],
    ['orange','Sunset Orange','#f97316'], ['amber','Amber Yellow','#f59e0b'], ['violet','Violet Purple','#8b5cf6'],
    ['midnight','Slate','#64748b'], ['cyan','Cyan','#06b6d4'], ['fuchsia','Fuchsia','#d946ef'],
    ['lime','Lime','#84cc16'], ['indigo','Indigo','#6366f1'], ['teal','Teal','#14b8a6']
];

function setThemeMode(mode) {
    localStorage.themeMode = mode;
    const dark = mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.classList.toggle('dark', dark);
    ['light','system','dark'].forEach(id => {
        const button = document.getElementById(`btn-${id}`);
        if (button) button.style.color = id === mode ? '#58a6ff' : '';
    });
}

function applyColorPalette(id) {
    localStorage.themeColor = id;
    document.documentElement.dataset.theme = id;
    const item = themes.find(t => t[0] === id);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta && item) meta.content = item[2];
    renderThemeMenu();
}

function renderThemeMenu() {
    const menu = document.getElementById('themeMenu');
    if (!menu) return;
    const current = localStorage.themeColor || 'blue';
    menu.innerHTML = themes.map(([id,name,color]) => `
        <button type="button" onclick="applyColorPalette('${id}')">
            <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-right:9px;"></span>${name}
            ${id === current ? '<span style="float:right;color:#58a6ff;">✓</span>' : ''}
        </button>`).join('');
}

function toggleThemeMenu(event) {
    if (event) event.stopPropagation();
    const menu = document.getElementById('themeMenu');
    if (menu) menu.classList.toggle('hidden');
    renderThemeMenu();
}

document.addEventListener('click', event => {
    const wrapper = document.getElementById('themeDropdownWrapper');
    const menu = document.getElementById('themeMenu');
    if (wrapper && menu && !wrapper.contains(event.target)) menu.classList.add('hidden');
});

function openSettings() { document.getElementById('settingsModal')?.classList.remove('hidden'); }
function closeSettings() { document.getElementById('settingsModal')?.classList.add('hidden'); }
function openClientsModal() { document.getElementById('clientsModal')?.classList.remove('hidden'); fetchClients(); }
function closeClientsModal() { document.getElementById('clientsModal')?.classList.add('hidden'); }
function toggleRemote() {
    const remote = document.getElementById('mode')?.value === 'remote';
    document.getElementById('remoteFields')?.classList.toggle('hidden', !remote);
}

function formatLocal(date) {
    return `${date.toLocaleDateString()}, ${date.toLocaleTimeString([], {hour12:true})}.${String(date.getMilliseconds()).padStart(3,'0')}`;
}
function formatUTC(date) {
    const p = n => String(n).padStart(2,'0');
    return `${date.getUTCFullYear()}-${p(date.getUTCMonth()+1)}-${p(date.getUTCDate())}, ${p(date.getUTCHours())}:${p(date.getUTCMinutes())}:${p(date.getUTCSeconds())}.${String(date.getUTCMilliseconds()).padStart(3,'0')} UTC`;
}
function updateClock() {
    const now = new Date();
    const local = document.getElementById('localTimeDisplay');
    if (local) local.textContent = formatLocal(now);
    if (state.gpsBaseMs !== null && state.gpsFetchMs !== null) {
        const gps = document.getElementById('gpsTimeDisplay');
        if (gps) gps.textContent = formatUTC(new Date(state.gpsBaseMs + now.getTime() - state.gpsFetchMs));
    }
}

async function loadUI() {
    try {
        const res = await fetch('/api/config', {cache:'no-store'});
        const conf = await res.json();
        document.getElementById('mode').value = conf.mode || 'local';
        document.getElementById('host').value = conf.host || '';
        document.getElementById('user').value = conf.user || '';
        document.getElementById('enable_monitor').checked = !!conf.enable_monitor;
        document.getElementById('ssh_key').value = conf.ssh_key ? '********' : '';
        document.getElementById('connMode').textContent = conf.mode === 'local' ? 'Local System' : `SSH Remote: ${conf.host}`;
        document.getElementById('resourceMonitor').classList.toggle('hidden', !conf.enable_monitor);
        toggleRemote();
        if (conf.enable_monitor) fetchMetrics();
    } catch (error) { console.error('Configuration load failed', error); }
}

document.getElementById('configForm').addEventListener('submit', async event => {
    event.preventDefault();
    try {
        const key = document.getElementById('ssh_key').value;
        const payload = {
            mode: document.getElementById('mode').value,
            host: document.getElementById('host').value,
            user: document.getElementById('user').value,
            password: document.getElementById('password').value,
            ssh_key: key === '********' ? '' : key,
            enable_monitor: document.getElementById('enable_monitor').checked
        };
        const res = await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
        if (!res.ok) throw new Error(`Save failed (${res.status})`);
        closeSettings();
        await loadUI();
        await Promise.all([fetchNTP(), fetchGPS()]);
    } catch (error) {
        console.error('Configuration save failed', error);
        alert('Configuration failed to save. Check the dashboard log for details.');
    }
});

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

async function fetchNTP() {
    try {
        const res = await fetch('/api/ntp', {cache:'no-store'});
        const data = await res.json();
        const offset = document.getElementById('sysOffset');
        const table = document.getElementById('ntpTableBody');
        if (data.error) {
            offset.textContent = 'Disconnected / Error';
            offset.style.color = '#f85149';
            table.innerHTML = `<tr><td colspan="7" style="color:#f85149;white-space:pre-wrap;">${escapeHtml(data.error)}</td></tr>`;
            return;
        }
        offset.textContent = data.offset || 'Waiting for sync...';
        offset.style.color = '#3fb950';
        const sources = data.sources || [];
        table.innerHTML = sources.length ? sources.map(s => {
            const focus = String(s.name).includes('PPS') || String(s.name).includes('GPS') || String(s.state).includes('*');
            return `<tr ${focus ? 'style="background:rgba(63,185,80,.07);"' : ''}>
                <td style="font-weight:${focus ? 700 : 400};color:${focus ? '#3fb950' : 'inherit'}">${escapeHtml(s.state)}</td>
                <td>${escapeHtml(s.name)}</td><td>${escapeHtml(s.stratum)}</td><td>${escapeHtml(s.poll)}</td>
                <td>${escapeHtml(s.reach)}</td><td>${escapeHtml(s.lastrx)}</td><td>${escapeHtml(s.last_sample)}</td>
            </tr>`;
        }).join('') : '<tr><td colspan="7" class="muted">No NTP sources reported.</td></tr>';
    } catch (error) { console.error('NTP fetch failed', error); }
}

async function fetchGPS() {
    try {
        const res = await fetch('/api/gps', {cache:'no-store'});
        const data = await res.json();
        const table = document.getElementById('satTableBody');
        const count = document.getElementById('satCount');
        if (data.error) {
            state.gpsBaseMs = null;
            document.getElementById('gpsTimeDisplay').textContent = data.gps_time || 'GPS unavailable';
            document.getElementById('satellitesLayer').innerHTML = '';
            table.innerHTML = `<tr><td colspan="5" style="color:#f85149;white-space:pre-wrap;">${escapeHtml(data.error)}</td></tr>`;
            count.textContent = 'Unavailable'; state.sweepTimer = 30; return;
        }
        if (data.gps_time && data.gps_time.includes('T')) {
            const parsed = new Date(data.gps_time);
            if (!Number.isNaN(parsed.getTime())) { state.gpsBaseMs = parsed.getTime(); state.gpsFetchMs = Date.now(); }
        } else {
            state.gpsBaseMs = null;
            document.getElementById('gpsTimeDisplay').textContent = data.gps_time || 'Waiting for lock...';
        }
        const sats = data.satellites || [];
        let locked = 0, svg = '', rows = '';
        for (const sat of sats) {
            if (sat.used) locked++;
            const r = 100 * (90 - Number(sat.el || 0)) / 90;
            const az = Number(sat.az || 0) * Math.PI / 180;
            const x = 100 + r * Math.sin(az), y = 100 - r * Math.cos(az);
            const color = sat.used ? '#3fb950' : '#f85149';
            if (sat.used) svg += `<circle cx="${x}" cy="${y}" r="4" fill="${color}" class="ping-slow"></circle>`;
            svg += `<circle cx="${x}" cy="${y}" r="3.5" fill="${color}"></circle><text x="${x+5}" y="${y+3}" font-size="7" font-weight="bold" fill="#fff">${escapeHtml(sat.PRN)}</text>`;
            rows += `<tr><td style="font-weight:700;">PRN ${escapeHtml(sat.PRN)}</td><td>${escapeHtml(sat.el)}°</td><td>${escapeHtml(sat.az)}°</td><td>${escapeHtml(sat.ss || 0)} dB</td><td style="color:${sat.used ? '#3fb950':'#8b949e'};font-weight:${sat.used ? 700:400};">${sat.used ? 'Locked':'Visible'}</td></tr>`;
        }
        document.getElementById('satellitesLayer').innerHTML = svg;
        table.innerHTML = rows || '<tr><td colspan="5" class="muted">No satellites reported.</td></tr>';
        count.textContent = `${locked} Locked`;
        state.sweepTimer = 30;
    } catch (error) { console.error('GPS fetch failed', error); }
}

function ipToInt(ip) { return ip.split('.').reduce((a,o)=>(a*256)+Number(o),0); }
function parseLastSeen(value) {
    if (!value || value === '-') return Infinity;
    const n = parseFloat(value);
    if (value.includes('s')) return n; if (value.includes('m')) return n*60; if (value.includes('h')) return n*3600;
    if (value.includes('d')) return n*86400; if (value.includes('y')) return n*31536000; return n;
}
function renderClientsTable() {
    const tbody = document.getElementById('clientsTableBody');
    const mode = document.getElementById('clientSort').value;
    if (!state.clients.length) { tbody.innerHTML = '<tr><td colspan="4" class="muted">No active clients found.</td></tr>'; return; }
    const sorted = [...state.clients].sort((a,b) => {
        if (mode === 'hits_desc') return Number(b.ntp_hits) - Number(a.ntp_hits);
        if (mode === 'ip_asc') return a.ip.includes('.') && b.ip.includes('.') ? ipToInt(a.ip)-ipToInt(b.ip) : a.ip.localeCompare(b.ip);
        return parseLastSeen(a.last_seen)-parseLastSeen(b.last_seen);
    });
    tbody.innerHTML = sorted.map(c => `<tr><td style="color:#58a6ff;font-weight:700;">${escapeHtml(c.ip)}</td><td>${escapeHtml(c.ntp_hits)}</td><td>${escapeHtml(c.ntp_drops)}</td><td>${escapeHtml(c.last_seen)}</td></tr>`).join('');
}
async function fetchClients() {
    const tbody = document.getElementById('clientsTableBody');
    tbody.innerHTML = '<tr><td colspan="4" class="muted">Fetching clients...</td></tr>';
    try {
        const res = await fetch('/api/clients', {cache:'no-store'}); const data = await res.json();
        if (data.error) { tbody.innerHTML = `<tr><td colspan="4" style="color:#f85149;">${escapeHtml(data.error)}</td></tr>`; return; }
        state.clients = data.clients || []; renderClientsTable();
    } catch (error) { tbody.innerHTML = '<tr><td colspan="4" style="color:#f85149;">Failed to communicate with API.</td></tr>'; console.error(error); }
}

async function fetchMetrics() {
    try {
        const res = await fetch('/api/system_metrics', {cache:'no-store'});
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json(); if (data.error) throw new Error(data.error);
        document.getElementById('cpuUsageText').textContent = `${data.cpu_percent}%`;
        document.getElementById('ramUsageText').textContent = `${data.ram_used_mb} / ${data.ram_total_mb} MB (${data.ram_percent}%)`;
        document.getElementById('cpuTempText').textContent = data.temperature_c === 'N/A' ? 'N/A' : `${data.temperature_c} °C`;
        document.getElementById('resourceStatus').className = 'status-dot status-ok';
    } catch (error) {
        document.getElementById('cpuUsageText').textContent = 'Error'; document.getElementById('ramUsageText').textContent = 'Error'; document.getElementById('cpuTempText').textContent = 'Error';
        document.getElementById('resourceStatus').className = 'status-dot status-error';
        console.error('Resource monitor error:', error);
    }
}

async function refreshNow() {
    const now = Date.now(); if (now - state.lastRefresh < 1000) return; state.lastRefresh = now;
    await Promise.all([fetchNTP(), fetchGPS()]);
    if (!document.getElementById('resourceMonitor').classList.contains('hidden')) fetchMetrics();
}

function startPolling() {
    if (!state.ntpTimer) state.ntpTimer = setInterval(fetchNTP, 2000);
    if (!state.gpsTimer) state.gpsTimer = setInterval(fetchGPS, 30000);
    if (!state.metricsTimer) state.metricsTimer = setInterval(() => { if (!document.getElementById('resourceMonitor').classList.contains('hidden')) fetchMetrics(); }, 5000);
}

setInterval(updateClock, 40);
setInterval(() => {
    state.sweepTimer = Math.max(0, state.sweepTimer - 1);
    const bar = document.getElementById('sweepBar'); if (bar) bar.style.width = `${(state.sweepTimer / 30) * 100}%`;
}, 1000);

window.addEventListener('focus', refreshNow);
window.addEventListener('online', refreshNow);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refreshNow(); });

setThemeMode(localStorage.themeMode || 'system');
applyColorPalette(localStorage.themeColor || 'blue');
loadUI();
refreshNow();
startPolling();

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(error => console.error('PWA registration failed:', error));
    });
}
