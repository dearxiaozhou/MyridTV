(function(){
    const KEY = 'studio_theme';
    const LEGACY_KEY = 'canvas_theme';
    const SCALE_KEY = 'studio_ui_scale_mode';
    const SCALE_OPTIONS = ['auto', '100', '115', '125', '140'];

    /* 主题控制器允许浅色试验主题；默认仍保留深色。 */
    const LOCKED = null;

    function currentTheme(){
        if(LOCKED) return LOCKED;
        try {
            var stored = localStorage.getItem(KEY) || localStorage.getItem(LEGACY_KEY) || 'dark';
            return stored === 'light' ? 'light' : 'dark';
        } catch(e) {
            return 'dark';
        }
    }

    function applyTheme(theme){
        const next = LOCKED || (theme === 'dark' || theme === 'light' ? theme : currentTheme());
        const dark = next === 'dark';
        document.documentElement.classList.toggle('studio-theme-dark', dark);
        document.documentElement.classList.toggle('theme-dark', dark);
        document.documentElement.classList.toggle('theme-light', !dark);
        if(document.body){
            document.body.classList.toggle('studio-theme-dark', dark);
            document.body.classList.toggle('theme-dark', dark);
            document.body.classList.toggle('theme-light', !dark);
        }
        if(LOCKED){
            // 清掉历史遗留的浅色偏好，避免别处直接读 localStorage 时拿到 light
            try {
                localStorage.setItem(KEY, LOCKED);
                localStorage.setItem(LEGACY_KEY, LOCKED);
            } catch(e) {}
        }
        window.dispatchEvent(new CustomEvent('studio-theme-change', { detail: { theme: next } }));
    }

    function ensureScaleStyle(){
        if(document.getElementById('studio-scale-style')) return;
        const style = document.createElement('style');
        style.id = 'studio-scale-style';
        style.textContent = `
            html.studio-scale-managed {
                --studio-ui-scale: 1;
            }
            html.studio-ui-scaled body:not(.studio-scale-host) {
                width: calc(100% / var(--studio-ui-scale)) !important;
                min-height: calc(100vh / var(--studio-ui-scale)) !important;
                zoom: var(--studio-ui-scale);
            }
            html.studio-ui-scaled body.studio-scale-viewport:not(.studio-scale-host) {
                height: calc(100vh / var(--studio-ui-scale)) !important;
            }
            html.studio-ui-scaled body:not(.studio-scale-host) > .app-shell,
            html.studio-ui-scaled body:not(.studio-scale-host) > .shell,
            html.studio-ui-scaled body:not(.studio-scale-host) > .asset-page {
                width: calc(100% / var(--studio-ui-scale)) !important;
            }
            html.studio-ui-scaled body:not(.studio-scale-host) > .app-shell,
            html.studio-ui-scaled body:not(.studio-scale-host) > .shell {
                height: calc(100vh / var(--studio-ui-scale)) !important;
            }
            html.studio-ui-scaled body:not(.studio-scale-host) > .asset-page {
                min-height: calc(100vh / var(--studio-ui-scale)) !important;
            }
            @supports not (zoom: 1) {
                html.studio-ui-scaled body:not(.studio-scale-host) {
                    zoom: 1;
                    transform: scale(var(--studio-ui-scale));
                    transform-origin: 0 0;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function isFramed(){
        try {
            return window.self !== window.top;
        } catch(e) {
            return true;
        }
    }

    function normalizeScaleMode(mode){
        return SCALE_OPTIONS.includes(mode) ? mode : 'auto';
    }

    function currentScaleMode(){
        try {
            return normalizeScaleMode(localStorage.getItem(SCALE_KEY) || 'auto');
        } catch(e) {
            return 'auto';
        }
    }

    function autoScale(){
        const dpr = Math.max(1, Number(window.devicePixelRatio || 1));
        const screenLong = Math.max(window.screen?.width || 0, window.screen?.height || 0);
        const viewportLong = Math.max(window.innerWidth || 0, window.innerHeight || 0);
        const longEdge = Math.max(screenLong, viewportLong);
        if(dpr >= 1.35) return 1;
        if(longEdge >= 3600) return 1.22;
        if(longEdge >= 3000) return 1.16;
        if(longEdge >= 2500 && dpr <= 1.15) return 1.1;
        return 1;
    }

    function scaleForMode(mode){
        const next = normalizeScaleMode(mode);
        if(next === 'auto') return autoScale();
        return Math.max(1, Math.min(1.4, Number(next) / 100));
    }

    function updateScaleBodyClasses(){
        if(!document.body) return;
        const hasFrameHost = !!document.querySelector('.app-shell iframe, iframe.active');
        document.body.classList.toggle('studio-scale-host', hasFrameHost && !isFramed());
        const computed = window.getComputedStyle(document.body);
        const viewportLocked = computed.overflow === 'hidden' || computed.overflowY === 'hidden' || !!document.querySelector('.app-shell, .shell');
        document.body.classList.toggle('studio-scale-viewport', viewportLocked);
    }

    function scaleOptedOut(){
        return document.documentElement.dataset.studioScale === 'off';
    }

    function applyScale(mode){
        ensureScaleStyle();
        const next = normalizeScaleMode(mode);
        const optedOut = scaleOptedOut();
        const value = optedOut ? 1 : scaleForMode(next);
        const scaled = !optedOut && Math.abs(value - 1) > 0.01;
        document.documentElement.classList.add('studio-scale-managed');
        document.documentElement.classList.toggle('studio-ui-scaled', scaled);
        document.documentElement.style.setProperty('--studio-ui-scale', value.toFixed(3));
        updateScaleBodyClasses();
        window.dispatchEvent(new CustomEvent('studio-ui-scale-change', { detail: { mode: next, scale: value } }));
    }

    function broadcastScale(mode){
        document.querySelectorAll('iframe').forEach(frame => {
            try {
                frame.contentWindow?.postMessage({ type: 'studio-ui-scale', mode }, '*');
            } catch(e) {}
        });
    }

    function setScaleMode(mode, shouldBroadcast = true){
        const next = normalizeScaleMode(mode);
        try {
            localStorage.setItem(SCALE_KEY, next);
        } catch(e) {}
        applyScale(next);
        if(shouldBroadcast) broadcastScale(next);
    }

    let resizeTimer = null;
    function scheduleAutoScaleRefresh(){
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if(currentScaleMode() === 'auto') {
                applyScale('auto');
                broadcastScale('auto');
            }
        }, 160);
    }

    function blockBrowserCtrlWheelZoom(event){
        if(!(event?.ctrlKey || event?.metaKey)) return;
        event.preventDefault();
        event.stopPropagation();
    }

    window.addEventListener('wheel', blockBrowserCtrlWheelZoom, {capture:true, passive:false});
    document.addEventListener('wheel', blockBrowserCtrlWheelZoom, {capture:true, passive:false});

    function removeGptChatSurface(){
        try {
            if(localStorage.getItem('studio_active_page') === 'gpt-chat') {
                localStorage.setItem('studio_active_page', 'canvas');
            }
        } catch(e) {}
        const selectors = [
            '#frame-gpt-chat',
            'iframe[src*="gpt-chat"]',
            'iframe[data-src*="gpt-chat"]',
            '[onclick*="gpt-chat"]'
        ];
        document.querySelectorAll(selectors.join(',')).forEach(node => {
            const item = node.closest?.('.nav-item, .side-pill') || node;
            item.remove();
        });
        document.querySelectorAll('.nav-item, .side-pill').forEach(node => {
            const text = (node.textContent || '').trim();
            if(text === 'GPT 对话' || text === 'GPT Chat') node.remove();
        });
    }

    removeGptChatSurface();
    document.addEventListener('DOMContentLoaded', removeGptChatSurface);
    try {
        const observeThemeSurface = () => {
            const root = document.documentElement;
            if (!root) return;
            const observer = new MutationObserver(() => removeGptChatSurface());
            observer.observe(root, {childList:true, subtree:true});
        };
        if (document.documentElement) observeThemeSurface();
        else document.addEventListener('DOMContentLoaded', observeThemeSurface, {once:true});
    } catch(e) {}

    window.StudioTheme = {
        key: KEY,
        get: currentTheme,
        apply: applyTheme,
        set(theme){
            const next = LOCKED || (theme === 'dark' ? 'dark' : 'light');
            localStorage.setItem(KEY, next);
            localStorage.setItem(LEGACY_KEY, next);
            applyTheme(next);
        }
    };

    window.StudioScale = {
        key: SCALE_KEY,
        options: SCALE_OPTIONS.slice(),
        getMode: currentScaleMode,
        getScale: () => scaleForMode(currentScaleMode()),
        apply: applyScale,
        set: setScaleMode
    };

    applyTheme(currentTheme());
    applyScale(currentScaleMode());

    document.addEventListener('DOMContentLoaded', () => {
        applyTheme(currentTheme());
        applyScale(currentScaleMode());
    });
    window.addEventListener('message', event => {
        if(event.data?.type === 'studio-theme') applyTheme(event.data.theme);
        if(event.data?.type === 'studio-ui-scale') setScaleMode(event.data.mode, false);
    });
    window.addEventListener('storage', event => {
        if(event.key === KEY || event.key === LEGACY_KEY) applyTheme(currentTheme());
        if(event.key === SCALE_KEY) applyScale(currentScaleMode());
    });
    window.addEventListener('resize', scheduleAutoScaleRefresh);
})();
