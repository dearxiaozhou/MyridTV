(function(){
    const KEY = 'studio_theme';
    const LEGACY_KEY = 'canvas_theme';
    const THEME_ID_KEY = 'studio_theme_id';
    const THEMES = [
        {id:'dark', mode:'dark', zh:'石墨青绿', en:'Graphite Jade'},
        {id:'light', mode:'light', zh:'雾白青绿', en:'Mist Jade'},
        {id:'champagne', mode:'dark', zh:'暖灰香槟', en:'Warm Champagne'},
        {id:'obsidian', mode:'dark', zh:'黑曜电紫', en:'Obsidian Violet'},
        {id:'sakura', mode:'light', zh:'樱雪莓粉', en:'Sakura Berry'},
        {id:'taiyuan-yeyu', mode:'dark', zh:'苔原夜语', en:'Tundra Night'},
        {id:'nuanxuan-liujin', mode:'light', zh:'暖宣流金', en:'Warm Gilt'}
    ];
    const themeInfo = id => THEMES.find(item => item.id === id);
    const SCALE_KEY = 'studio_ui_scale_mode';
    const SCALE_OPTIONS = ['auto', '100', '115', '125', '140'];

    /* 主题控制器允许浅色试验主题；默认仍保留深色。 */
    const LOCKED = null;

    function ensureApplicationPalette(){
        if(document.getElementById('studio-application-palette')) return;
        const link = document.createElement('link');
        link.id = 'studio-application-palette';
        link.rel = 'stylesheet';
        link.href = '/static/css/application-palette.css?cb=card-hover-seven-v01318';
        const interactions = document.querySelector('link[href*="canvas-interaction-style.css"]');
        document.head.insertBefore(link, interactions || null);
    }
    ensureApplicationPalette();

    function currentTheme(){
        if(LOCKED) return LOCKED;
        try {
            var stored = localStorage.getItem(THEME_ID_KEY) || localStorage.getItem(KEY) || localStorage.getItem(LEGACY_KEY) || 'dark';
            return themeInfo(stored) ? stored : 'dark';
        } catch(e) {
            return 'dark';
        }
    }

    function applyTheme(theme){
        const next = LOCKED || (themeInfo(theme) ? theme : currentTheme());
        const dark = themeInfo(next).mode === 'dark';
        document.documentElement.dataset.studioTheme = next;
        document.documentElement.classList.toggle('studio-theme-dark', dark);
        document.documentElement.classList.toggle('theme-dark', dark);
        document.documentElement.classList.toggle('theme-light', !dark);
        if(document.body){
            document.body.dataset.studioTheme = next;
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
        // Keep dark/light for the native shell; named identity is independent.
        window.dispatchEvent(new CustomEvent('studio-theme-change', { detail: { theme: dark ? 'dark' : 'light', themeId: next } }));
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
        list: () => THEMES.map(item => ({...item})),
        isDark: id => (themeInfo(id || currentTheme()) || THEMES[0]).mode === 'dark',
        name: (id, lang='zh') => (themeInfo(id || currentTheme()) || THEMES[0])[lang === 'en' ? 'en' : 'zh'],
        apply: applyTheme,
        set(theme){
            if(!themeInfo(theme)) return;
            const next = LOCKED || theme;
            const mode = themeInfo(next).mode;
            localStorage.setItem(THEME_ID_KEY, next);
            localStorage.setItem(KEY, mode);
            localStorage.setItem(LEGACY_KEY, mode);
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
        // Load the common select adapter for every themed page, once.
        if(!window.StudioSelectMenu && !document.querySelector('script[src*="shared-native-select-menu.js"]')){
            const script = document.createElement('script');
            script.src = '/static/js/shared-native-select-menu.js?cb=card-hover-seven-v01317';
            document.head.appendChild(script);
        }
        // Keep the shared interaction sheet after all component/theme surfaces.
        const palette = document.getElementById('studio-application-palette');
        const interactions = document.querySelector('link[href*="canvas-interaction-style.css"]');
        if(palette && interactions) document.head.insertBefore(palette, interactions);
        applyTheme(currentTheme());
        applyScale(currentScaleMode());
    });
    window.addEventListener('message', event => {
        if(event.data?.type === 'studio-theme') applyTheme(event.data.theme);
        if(event.data?.type === 'studio-ui-scale') setScaleMode(event.data.mode, false);
    });
    window.addEventListener('storage', event => {
        if(event.key === THEME_ID_KEY || event.key === KEY || event.key === LEGACY_KEY) applyTheme(currentTheme());
        if(event.key === SCALE_KEY) applyScale(currentScaleMode());
    });
    window.addEventListener('resize', scheduleAutoScaleRefresh);
})();
