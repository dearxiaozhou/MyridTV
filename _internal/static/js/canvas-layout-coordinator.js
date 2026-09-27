/* Smart canvas host layout: keep the floating dock clear of the Agent panel. */
(function (global) {
    'use strict';

    var deps = {
        panel: null,
        isOpen: function () { return false; },
        getLeftTools: function () { return null; }
    };
    var started = false;

    function configure(options) {
        Object.assign(deps, options || {});
    }

    function hostContext() {
        try {
            var host = global.parent;
            var frame = global.frameElement;
            if (host === global || !frame) return null;
            return { host: host, frame: frame };
        } catch (_) {
            return null;
        }
    }

    function clearPlacement(body) {
        if (body.classList.contains('smart-agent-open')) body.classList.remove('smart-agent-open');
        body.style.removeProperty('--smart-agent-dock-center');
    }

    function syncPlacement(context) {
        if (!context) return;
        var host = context.host;
        var frame = context.frame;
        var body = host.document.body;
        var dockShell = host.document.querySelector('.bottom-dock-shell');
        if (!dockShell) return;
        if (!deps.isOpen()) {
            clearPlacement(body);
            return;
        }

        var frameRect = frame.getBoundingClientRect();
        var scaleX = frameRect.width / Math.max(frame.clientWidth, 1);
        var panelLeft = frameRect.right - deps.panel.offsetWidth * scaleX;
        var shellWidth = dockShell.getBoundingClientRect().width;
        var naturalRight = host.innerWidth / 2 + shellWidth / 2;
        if (naturalRight <= panelLeft - 1) {
            clearPlacement(body);
            return;
        }

        var leftTools = deps.getLeftTools();
        var leftToolsRight = leftTools
            ? frameRect.left + leftTools.getBoundingClientRect().right * scaleX
            : frameRect.left;
        var desiredLeft = panelLeft - 1 - shellWidth;
        var safeLeft = Math.max(desiredLeft, leftToolsRight + 1);
        body.style.setProperty('--smart-agent-dock-center', Math.round(safeLeft + shellWidth / 2) + 'px');
        if (!body.classList.contains('smart-agent-open')) body.classList.add('smart-agent-open');
    }

    function syncClearance(context) {
        var panel = deps.panel;
        if (!panel) return;
        if (!deps.isOpen()) {
            panel.style.setProperty('--agent-dock-clearance', '0px');
            panel.classList.remove('dock-clearance');
            return;
        }

        var clearance = 0;
        try {
            context = context || hostContext();
            if (context) {
                var host = context.host;
                var frame = context.frame;
                var dock = host.document.querySelector('.bottom-dock');
                if (dock && !host.document.body.classList.contains('dock-collapsed')) {
                    var frameRect = frame.getBoundingClientRect();
                    var dockRect = dock.getBoundingClientRect();
                    var scaleX = frameRect.width / Math.max(frame.clientWidth, 1);
                    var scaleY = frameRect.height / Math.max(frame.clientHeight, 1);
                    var panelLeft = frameRect.right - panel.offsetWidth * scaleX;
                    if (dockRect.right > panelLeft && dockRect.left < frameRect.right && dockRect.bottom > frameRect.top) {
                        clearance = Math.max(0, Math.ceil((frameRect.bottom - dockRect.top + 6) / scaleY));
                    }
                }
            }
        } catch (_) {
            // A standalone canvas has no host dock; keep the panel full-height.
        }

        panel.style.setProperty('--agent-dock-clearance', clearance + 'px');
        panel.classList.toggle('dock-clearance', clearance > 0);
    }

    function sync() {
        var context = hostContext();
        try {
            syncPlacement(context);
        } catch (_) {
            // A standalone canvas has no host dock.
        }
        syncClearance(context);
    }

    function start() {
        if (started) return;
        started = true;
        global.addEventListener('resize', sync);
        var context = hostContext();
        if (!context) return;
        context.host.addEventListener('resize', sync);
        new MutationObserver(sync).observe(context.host.document.body, {
            attributes: true,
            attributeFilter: ['class']
        });
        var dockShell = context.host.document.querySelector('.bottom-dock-shell');
        if (dockShell) dockShell.addEventListener('transitionend', sync);
    }

    global.CanvasLayoutCoordinator = { configure: configure, sync: sync, start: start };
})(window);

