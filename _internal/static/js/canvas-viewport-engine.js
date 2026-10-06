/* MyridTV 画布视口内核（拆模块 ①：viewport 状态 + 坐标换算 + 缩放 + 滚动锁）
 *
 * 背景：smart-canvas.js 23818 行巨型单文件，视口状态（viewport）被 40+ 处直接读写，
 * 缩放/平移/框选/拖拽各自散落改它 —— 是"改 A 坏 B"的重灾区。
 * 本模块把「视口几何」收成一个内聚单元：
 *  - viewport{x,y,scale} 是模块唯一权威状态；外部只拿到对象引用（改属性可以，整体赋值禁用）
 *  - 屏幕↔世界坐标换算、滚轮缩放锚点、缩放预览态、页面滚动锁全在这里
 *  - 依赖（DOM 元素、保存/渲染调度）全部 configure() 注入，模块零全局假设
 *
 * 兼容：主文件（smart-canvas.js）以薄别名转调本模块，旧调用点签名不变。
 */
(function (global) {
    'use strict';

    // ===== 注入点（configure 填充）=====
    var deps = {
        shell: null,          // 画布外壳元素（clientWidth/getBoundingClientRect）
        world: null,          // 世界层元素（transform 目标）
        scheduleSave: null,   // () => void
        scheduleCullCheck: null,     // () => void
        scheduleMinimapRender: null, // () => void
        scheduleImageUpgrade: null,  // () => void
        closeCreateMenu: null,       // () => void
        getNodes: null,              // () => Array 当前节点列表
        nodeRect: null               // (node) => {x,y,width,height} 世界系矩形
    };

    function configure(opts) {
        Object.assign(deps, opts || {});
    }

    // ===== 视口状态（唯一权威；禁止整体重新赋值，只改属性）=====
    var viewport = { x: 0, y: 0, scale: 1 };
    var viewportApplyFrame = 0;
    var viewportMotionTimer = 0;
    var zoomPreviewState = null;
    var lastCanvasPointerClient = null;
    var smartCanvasScrollLockUntil = 0;

    // ===== 基础工具 =====
    function safeScale(value) {
        const n = Number(value);
        return Number.isFinite(n) && n > 0 ? n : 1;
    }

    // ===== 视口应用与坐标换算 =====
    function applyViewport() {
        if (!deps.world || !deps.shell) return;
        // Prompt controls stay at a stable screen size while the canvas world zooms.
        deps.world.style.setProperty('--canvas-prompt-fixed-zoom', String(1 / safeScale(viewport.scale)));
        deps.world.style.transform = `translate3d(${viewport.x}px, ${viewport.y}px, 0) scale(${viewport.scale})`;
        if (deps.positionComposer) deps.positionComposer();
        deps.shell.classList.add('viewport-motion');
        deps.world.classList.add('is-viewport-motion');
        clearTimeout(viewportMotionTimer);
        viewportMotionTimer = setTimeout(() => {
            deps.shell.classList.remove('viewport-motion');
            // 摘掉合成层提升 + 强制回流，让 Chrome 按最终缩放重新栅格化，文字恢复清晰
            deps.world.classList.remove('is-viewport-motion');
            void deps.world.offsetWidth;
            if (deps.scheduleCullCheck) deps.scheduleCullCheck();
            if (deps.scheduleImageUpgrade) deps.scheduleImageUpgrade();
            if (deps.scheduleMinimapRender) deps.scheduleMinimapRender();
        }, 140);
        if (deps.scheduleCullCheck) deps.scheduleCullCheck();
    }

    function scheduleViewportApply() {
        if (viewportApplyFrame) return;
        viewportApplyFrame = requestAnimationFrame(() => {
            viewportApplyFrame = 0;
            applyViewport();
        });
    }

    function screenToWorld(event) {
        const rect = deps.shell.getBoundingClientRect();
        return {
            x: (event.clientX - rect.left - viewport.x) / viewport.scale,
            y: (event.clientY - rect.top - viewport.y) / viewport.scale
        };
    }

    function viewportCenter() {
        return {
            x: (deps.shell.clientWidth / 2 - viewport.x) / viewport.scale,
            y: (deps.shell.clientHeight / 2 - viewport.y) / viewport.scale
        };
    }

    function centerViewportOnWorldPoint(point) {
        viewport.x = deps.shell.clientWidth / 2 - point.x * viewport.scale;
        viewport.y = deps.shell.clientHeight / 2 - point.y * viewport.scale;
        applyViewport();
        if (deps.scheduleSave) deps.scheduleSave();
    }

    function fitAllNodesViewport() {
        const nodes = deps.getNodes ? deps.getNodes() : [];
        if (!nodes.length) {
            viewport.scale = 0.45;
            viewport.x = deps.shell.clientWidth / 2;
            viewport.y = deps.shell.clientHeight / 2;
            applyViewport();
            if (deps.scheduleSave) deps.scheduleSave();
            return;
        }
        const rects = nodes.map(deps.nodeRect);
        const minX = Math.min(...rects.map(r => r.x));
        const minY = Math.min(...rects.map(r => r.y));
        const maxX = Math.max(...rects.map(r => r.x + r.width));
        const maxY = Math.max(...rects.map(r => r.y + r.height));
        const pad = 160;
        const width = Math.max(1, maxX - minX + pad * 2);
        const height = Math.max(1, maxY - minY + pad * 2);
        const nextScale = Math.max(0.06, Math.min(0.82, (deps.shell.clientWidth - 80) / width, (deps.shell.clientHeight - 80) / height));
        const cx = (minX + maxX) / 2;
        const cy = (minY + maxY) / 2;
        viewport.scale = nextScale;
        viewport.x = deps.shell.clientWidth / 2 - cx * viewport.scale;
        viewport.y = deps.shell.clientHeight / 2 - cy * viewport.scale;
        applyViewport();
        if (deps.scheduleSave) deps.scheduleSave();
    }

    // ===== 缩放预览（总览模式）=====
    function enterZoomPreview() {
        if (zoomPreviewState) return;
        zoomPreviewState = { ...viewport };
        deps.shell.classList.add('zoom-preview');
        if (deps.closeCreateMenu) deps.closeCreateMenu();
        fitAllNodesViewport();
    }

    function exitZoomPreview(point = null) {
        if (!zoomPreviewState) return false;
        const prev = zoomPreviewState;
        zoomPreviewState = null;
        deps.shell.classList.remove('zoom-preview');
        viewport.scale = prev.scale;
        if (point) {
            viewport.x = deps.shell.clientWidth / 2 - point.x * viewport.scale;
            viewport.y = deps.shell.clientHeight / 2 - point.y * viewport.scale;
        } else {
            viewport.x = prev.x;
            viewport.y = prev.y;
        }
        applyViewport();
        if (deps.scheduleSave) deps.scheduleSave();
        return true;
    }

    function exitZoomPreviewToNode(nodeId) {
        if (!zoomPreviewState) return false;
        const nodes = deps.getNodes ? deps.getNodes() : [];
        const node = nodes.find(n => n.id === nodeId);
        if (!node) return exitZoomPreview();
        const prev = zoomPreviewState;
        const rect = deps.nodeRect(node);
        const cx = rect.x + rect.width / 2;
        const cy = rect.y + rect.height / 2;
        const fitScale = Math.min(
            1.15,
            (deps.shell.clientWidth - 160) / Math.max(1, rect.width),
            (deps.shell.clientHeight - 160) / Math.max(1, rect.height)
        );
        const readableScale = Math.min(1.15, Math.max(0.72, fitScale));
        zoomPreviewState = null;
        deps.shell.classList.remove('zoom-preview');
        viewport.scale = Math.max(safeScale(prev.scale), readableScale);
        viewport.x = deps.shell.clientWidth / 2 - cx * viewport.scale;
        viewport.y = deps.shell.clientHeight / 2 - cy * viewport.scale;
        applyViewport();
        if (deps.scheduleSave) deps.scheduleSave();
        return true;
    }

    function toggleZoomPreview() {
        if (zoomPreviewState) exitZoomPreview();
        else enterZoomPreview();
    }

    function inZoomPreview() {
        return !!zoomPreviewState;
    }

    // ===== 滚轮归属判定（画布 vs 浮层）=====
    function isCanvasWheelExcludedTarget(target) {
        if (typeof CanvasOverlayRegistry !== 'undefined') return CanvasOverlayRegistry.isOverlay(target, 'wheel-exclude');
        return !!target?.closest?.('.composer,.smart-back,.canvas-tool-dock,.canvas-bottom-tools,.image-edit-modal,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.prompt-template-panel,.prompt-preset-panel');
    }

    function isCanvasWheelScrollableOverlay(target) {
        if (typeof CanvasOverlayRegistry !== 'undefined') return CanvasOverlayRegistry.isOverlay(target, 'wheel-scrollable');
        return !!target?.closest?.('.asset-panel,.asset-grid,.style-panel,.style-grid,.canvas-agent-panel,.canvas-agent-messages,.prompt-template-panel,.prompt-template-list,.prompt-template-preview-content,.mention-picker,.smart-table-wrap,.prompt-node-text,.loop-smart-text,.loop-smart-upstream-text,textarea,[contenteditable="true"]');
    }

    // ===== 页面根滚动锁（画布吞滚轮时防止整页被滚走）=====
    function resetSmartCanvasRootScroll() {
        const root = document.scrollingElement || document.documentElement;
        if (root && (root.scrollTop || root.scrollLeft)) {
            root.scrollTop = 0;
            root.scrollLeft = 0;
        }
        if (document.documentElement) {
            document.documentElement.scrollTop = 0;
            document.documentElement.scrollLeft = 0;
        }
        if (document.body) {
            document.body.scrollTop = 0;
            document.body.scrollLeft = 0;
        }
        if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
        try { window.parent?.postMessage({ type: 'smart-canvas-lock-scroll' }, '*'); } catch (_) { }
    }

    function lockSmartCanvasRootScroll() {
        smartCanvasScrollLockUntil = Math.max(smartCanvasScrollLockUntil, performance.now() + 320);
        resetSmartCanvasRootScroll();
    }

    function maintainSmartCanvasScrollLock() {
        resetSmartCanvasRootScroll();
        if (performance.now() < smartCanvasScrollLockUntil) requestAnimationFrame(maintainSmartCanvasScrollLock);
    }

    function beginSmartCanvasScrollLock() {
        const wasInactive = performance.now() >= smartCanvasScrollLockUntil;
        lockSmartCanvasRootScroll();
        if (wasInactive) requestAnimationFrame(maintainSmartCanvasScrollLock);
    }

    // ===== 指针记忆与滚轮缩放锚点 =====
    function rememberCanvasPointerClient(event) {
        const rect = deps.shell.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        if (x < 0 || y < 0 || x > rect.width || y > rect.height) return;
        lastCanvasPointerClient = { x, y, at: performance.now() };
    }

    function canvasWheelAnchorPoint(event) {
        const rect = deps.shell.getBoundingClientRect();
        const eventX = event.clientX - rect.left;
        const eventY = event.clientY - rect.top;
        const eventInside = eventX >= 0 && eventY >= 0 && eventX <= rect.width && eventY <= rect.height;
        const recentPointer = lastCanvasPointerClient && performance.now() - lastCanvasPointerClient.at < 15000;
        const point = recentPointer ? lastCanvasPointerClient : { x: eventX, y: eventY };
        const x = eventInside || recentPointer ? point.x : rect.width / 2;
        const y = eventInside || recentPointer ? point.y : rect.height / 2;
        return {
            x: Math.max(0, Math.min(rect.width, x)),
            y: Math.max(0, Math.min(rect.height, y))
        };
    }

    function zoomViewportAtClientPoint(event) {
        const oldScale = safeScale(viewport.scale);
        const pointer = canvasWheelAnchorPoint(event);
        const pointerX = pointer.x;
        const pointerY = pointer.y;
        const worldX = (pointerX - viewport.x) / oldScale;
        const worldY = (pointerY - viewport.y) / oldScale;
        const deltaPixels = Math.max(-180, Math.min(180, Number(event.deltaY || 0) * (event.deltaMode === 1 ? 16 : 1)));
        const factor = Math.exp(-deltaPixels * 0.001);
        const nextScale = Math.max(0.15, Math.min(3, safeScale(oldScale * factor)));
        if (Math.abs(nextScale - oldScale) < 0.0001) return false;
        viewport.scale = nextScale;
        viewport.x = pointerX - worldX * nextScale;
        viewport.y = pointerY - worldY * nextScale;
        applyViewport();
        if (deps.scheduleSave) deps.scheduleSave();
        return true;
    }

    // ===== 状态整体装载（画布加载/草稿恢复用；只改属性不换对象）=====
    function resetViewport(next) {
        const src = next || {};
        viewport.x = Number(src.x) || 0;
        viewport.y = Number(src.y) || 0;
        viewport.scale = safeScale(src.scale);
    }

    global.CanvasViewport = {
        configure: configure,
        viewport: viewport,
        resetViewport: resetViewport,
        safeScale: safeScale,
        applyViewport: applyViewport,
        scheduleViewportApply: scheduleViewportApply,
        screenToWorld: screenToWorld,
        viewportCenter: viewportCenter,
        centerViewportOnWorldPoint: centerViewportOnWorldPoint,
        fitAllNodesViewport: fitAllNodesViewport,
        enterZoomPreview: enterZoomPreview,
        exitZoomPreview: exitZoomPreview,
        exitZoomPreviewToNode: exitZoomPreviewToNode,
        toggleZoomPreview: toggleZoomPreview,
        inZoomPreview: inZoomPreview,
        isCanvasWheelExcludedTarget: isCanvasWheelExcludedTarget,
        isCanvasWheelScrollableOverlay: isCanvasWheelScrollableOverlay,
        resetSmartCanvasRootScroll: resetSmartCanvasRootScroll,
        lockSmartCanvasRootScroll: lockSmartCanvasRootScroll,
        beginSmartCanvasScrollLock: beginSmartCanvasScrollLock,
        rememberCanvasPointerClient: rememberCanvasPointerClient,
        canvasWheelAnchorPoint: canvasWheelAnchorPoint,
        zoomViewportAtClientPoint: zoomViewportAtClientPoint
    };
})(typeof window !== 'undefined' ? window : globalThis);
