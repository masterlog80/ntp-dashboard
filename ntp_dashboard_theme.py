"""Theme mode support injected into the dashboard HTML at startup."""


def install():
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ntp_dashboard_theme_hook", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        @self.after_request
        def inject_theme_support(response):
            try:
                if not (response.content_type and response.content_type.startswith("text/html")):
                    return response
                document = response.get_data(as_text=True)
                if 'id="ntp-dashboard-theme"' in document:
                    return response

                css = """
<style id="ntp-dashboard-theme">
html[data-color-mode="light"] { --ui-bg:#f6f8fa; --ui-bg2:#ffffff; --ui-card:#ffffff; --ui-border:#d0d7de; --ui-text:#1f2328; --ui-muted:#656d76; --ui-green:#1a7f37; --ui-red:#cf222e; }
html[data-color-mode="light"] .app-header { background:rgba(255,255,255,.96); }
html[data-color-mode="dark"] { --ui-bg:#0d1117; --ui-bg2:#161b22; --ui-card:#1c2431; --ui-border:#30363d; --ui-text:#e6edf3; --ui-muted:#8b949e; --ui-green:#3fb950; --ui-red:#f85149; }
html[data-color-mode="dark"] .app-header { background:rgba(28,36,49,.96); }
@media (prefers-color-scheme: light) {
  html[data-color-mode="system"] { --ui-bg:#f6f8fa; --ui-bg2:#ffffff; --ui-card:#ffffff; --ui-border:#d0d7de; --ui-text:#1f2328; --ui-muted:#656d76; --ui-green:#1a7f37; --ui-red:#cf222e; }
  html[data-color-mode="system"] .app-header { background:rgba(255,255,255,.96); }
}
@media (prefers-color-scheme: dark) {
  html[data-color-mode="system"] { --ui-bg:#0d1117; --ui-bg2:#161b22; --ui-card:#1c2431; --ui-border:#30363d; --ui-text:#e6edf3; --ui-muted:#8b949e; --ui-green:#3fb950; --ui-red:#f85149; }
  html[data-color-mode="system"] .app-header { background:rgba(28,36,49,.96); }
}
#btn-light[aria-pressed="true"], #btn-system[aria-pressed="true"], #btn-dark[aria-pressed="true"] { box-shadow:inset 0 0 0 1px #58a6ff,0 0 0 1px rgba(88,166,255,.15); border-color:#58a6ff; }
</style>
"""
                script = """
<script id="ntp-dashboard-theme-script">
(function(){
  const KEY='ntp-dashboard-color-mode', MODES=['light','system','dark'];
  function stored(){ try { const v=localStorage.getItem(KEY); return MODES.includes(v)?v:'system'; } catch(_) { return 'system'; } }
  function apply(mode,save){
    if(!MODES.includes(mode)) mode='system';
    document.documentElement.setAttribute('data-color-mode',mode);
    document.documentElement.classList.toggle('dark',mode==='dark');
    if(save) try { localStorage.setItem(KEY,mode); } catch(_) {}
    MODES.forEach(function(n){ const b=document.getElementById('btn-'+n); if(b) b.setAttribute('aria-pressed',n===mode?'true':'false'); });
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta){ const light=mode==='light'||(mode==='system'&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches); meta.setAttribute('content',light?'#ffffff':'#1c2431'); }
  }
  window.setThemeMode=function(mode){apply(mode,true);};
  window.toggleThemeMenu=function(event){ if(event) event.stopPropagation(); const m=document.getElementById('themeMenu'); if(m) m.classList.toggle('hidden'); };
  function init(){
    apply(stored(),false);
    const media=window.matchMedia?window.matchMedia('(prefers-color-scheme: light)'):null;
    if(media){ const update=function(){if(stored()==='system') apply('system',false);}; if(media.addEventListener) media.addEventListener('change',update); else if(media.addListener) media.addListener(update); }
    const wrapper=document.getElementById('themeDropdownWrapper');
    if(wrapper) document.addEventListener('click',function(e){const m=document.getElementById('themeMenu');if(m&&!wrapper.contains(e.target))m.classList.add('hidden');});
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
</script>
"""
                if '</head>' not in document:
                    return response
                document=document.replace('</head>',css+script+'</head>',1)
                response.set_data(document)
            except Exception:
                pass
            return response

    Flask.__init__ = patched_init
    Flask._ntp_dashboard_theme_hook = True


install()
