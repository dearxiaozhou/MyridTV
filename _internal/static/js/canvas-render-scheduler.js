/* MyridTV 画布渲染调度与小地图（拆模块 ②：视口裁剪 / 静止升清 / minimap）
 *
 * 背景：smart-canvas.js 里「平移不卡」的三件套（视口裁剪、渐进升清、小地图渲染）
 * 和 minimap 拖拽状态散落各处，改渲染管线容易连带弄坏平移/缩放体验。
 * 本模块收拢：
 *  - 视口裁剪：只渲染视野+外扩缓冲内的节点（≥CULL_MIN_NODES 才启用）
 *  - 静止后升清：视口停稳把视野内低清缩略图换成高清（带内存预算）
 *  - 小地图：节点投影渲染、可视框计算、显隐持久化、拖拽定位换算
 *  - 交互态判定（正在拖/正在缩放则不打断）经注入函数从主文件拿，模块零全局假设
 *
 * 兼容：主文件（smart-canvas.js）以薄别名转调，旧调用点签名不变。
 */
(function (global) {
    'use strict';

    // ===== 注入点（configure 填充）=====
    var deps = {
        shell: null,               // 画布外壳元素
        world: null,               // 世界层元素
        viewport: null,            // CanvasViewport.viewport（引用共享，只改属性）
        getNodes: null,            // () => nodes 数组
        nodeRect: null,            // (node) => {x,y,width,height}
        canvasObjectsMode: null,   // () => bool 无线模式（不裁剪）
        canvasThumbnailUrl: null,  // (url, edge) => string
        forceNodeIds: null,        // () => Array 必须常驻 DOM 的节点 id（选中/拖拽/上传…）
        isInteracting: null,       // () => bool 正在拖拽/缩放/连线/缩略图拖
        render: null,              // () => void 全量渲染
        minimapEl: null,           // #minimap
        minimapContentEl: null,    // #minimapContent
        minimapToggleEl: null      // #minimapToggle
    };

    function configure(opts) {
        Object.assign(deps, opts || {});
    }

    // ── 视口裁剪 ─────────────────────────────────────────────────────────
    // 节点数超过阈值时，DOM 里只保留「视野内 + 外扩缓冲」的节点。
    // 配合 render() 的 renderKey 复用，平移时只有新进入视野的节点会被真正创建，
    // 已经在视野里的节点原地复用，所以平移中的补渲染几乎免费。
    const CULL_MIN_NODES = 80;      // 低于这个数量完全不裁剪，小画布行为与之前一致
    const CULL_MARGIN_RATIO = 0.6;  // 视口四周各外扩 60%，避免边缘闪进闪出
    let lastCullKey = '';
    let cullCheckTimer = 0;
    let lastCullCheckAt = 0;

    function cullEnabled() {
        return (deps.getNodes() || []).length >= CULL_MIN_NODES && !deps.canvasObjectsMode();
    }
    function viewportWorldRect() {
        const vp = deps.viewport;
        const k = CanvasViewport.safeScale(vp && vp.scale);
        const w = (deps.shell?.clientWidth || window.innerWidth || 1280) / k;
        const h = (deps.shell?.clientHeight || window.innerHeight || 800) / k;
        const x = -Number(vp && vp.x || 0) / k;
        const y = -Number(vp && vp.y || 0) / k;
        const mx = w * CULL_MARGIN_RATIO;
        const my = h * CULL_MARGIN_RATIO;
        return { x: x - mx, y: y - my, w: w + mx * 2, h: h + my * 2 };
    }
    function nodeCullRect(node) {
        const x = Number(node?.x) || 0;
        const y = Number(node?.y) || 0;
        let w = Number(node?.w);
        let h = Number(node?.h);
        if (!(w > 0) || !(h > 0)) {
            const r = deps.nodeRect(node);
            w = r.width;
            h = r.height;
        }
        return { x, y, w, h };
    }
    function visibleNodeList() {
        const nodes = deps.getNodes() || [];
        if (!cullEnabled()) return nodes;
        const rect = viewportWorldRect();
        // 选中/正在拖/正在缩放/正在上传的节点永远保留，避免交互目标在 DOM 里失踪
        const force = new Set(deps.forceNodeIds() || []);
        return nodes.filter(node => {
            if (force.has(node.id)) return true;
            const r = nodeCullRect(node);
            return r.x + r.w > rect.x && r.x < rect.x + rect.w && r.y + r.h > rect.y && r.y < rect.y + rect.h;
        });
    }
    function cullSignature() {
        if (!cullEnabled()) return 'off';
        return visibleNodeList().map(node => node.id).join(',');
    }
    function scheduleCullCheck() {
        if (!cullEnabled()) return;
        if (cullCheckTimer) return;
        const now = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
        const wait = Math.max(0, 130 - (now - lastCullCheckAt));
        cullCheckTimer = setTimeout(() => {
            cullCheckTimer = 0;
            lastCullCheckAt = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
            scheduleCullRender();
        }, wait);
    }
    function scheduleCullRender() {
        if (!cullEnabled()) return;
        // 正在输入 / 正在拖拽时不打断用户
        const active = document.activeElement;
        if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable)) return;
        if (deps.isInteracting()) return;
        if (cullSignature() === lastCullKey) return;   // 可见集合没变，一次 render 都不做
        deps.render();
    }
    // render() 完成后主文件调这个登记「当前可见集合」，避免下次重复渲染
    function markCullRendered() {
        lastCullKey = cullSignature();
    }

    // ── 静止后渐进升清 ───────────────────────────────────────────────────
    // 平移/缩放时继续用低清缩略图（便宜）；视口停稳后按「屏幕实际像素」把视野内的图换成更高分辨率。
    // 关键：只改 img.src，绝不动 HTML 模板里的 src —— 那个参与 renderKey，
    // 一旦随 viewport.scale 变化，每次缩放都会让所有节点 key 失效，把增量复用全部摧毁。
    const UPGRADE_MAX_EDGE = 2048;      // 后端 clamp 已同步放宽到 2048
    const UPGRADE_MEM_BUDGET_MB = 320;  // 一轮升清的位图内存预算，超了就不再升
    let upgradeRafId = 0;
    function scheduleImageUpgrade() {
        if (upgradeRafId) return;
        upgradeRafId = requestAnimationFrame(() => {
            upgradeRafId = 0;
            upgradeVisibleImageSources();
        });
    }
    function upgradeVisibleImageSources() {
        const world = deps.world;
        if (!world) return 0;
        const imgs = world.querySelectorAll('.image-node img.node-img[data-original-src]');
        if (!imgs.length) return 0;
        const vp = deps.viewport;
        const k = CanvasViewport.safeScale(vp && vp.scale);
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const shellW = (deps.shell?.clientWidth || 0) + 200;
        const shellH = (deps.shell?.clientHeight || 0) + 200;
        let budget = UPGRADE_MEM_BUDGET_MB;
        let upgraded = 0;
        imgs.forEach(imgEl => {
            const base = Number(imgEl.dataset.baseEdge) || 0;
            if (!(base > 0)) return;
            if (imgEl.dataset.upgrading === '1') return;
            const box = imgEl.getBoundingClientRect();
            if (box.right < -200 || box.left > shellW || box.bottom < -200 || box.top > shellH) return;
            const cur = Number(imgEl.dataset.currentEdge) || base;
            const cssMax = Math.max(parseFloat(imgEl.style.width) || 0, parseFloat(imgEl.style.height) || 0)
                || (Math.max(box.width, box.height) / (k || 1));
            if (!(cssMax > 0)) return;
            let want = Math.ceil(cssMax * k * dpr);
            if (!(want > cur * 1.15)) return;                      // 提升不明显就不折腾
            want = Math.max(384, Math.min(UPGRADE_MAX_EDGE, want));
            if (want <= cur) return;
            const estMb = (want * want * 4) / 1048576;            // 保守按正方形估算
            if (estMb > budget) return;
            const original = imgEl.getAttribute('data-original-src') || '';
            if (!original) return;
            budget -= estMb;
            upgraded += 1;
            imgEl.dataset.currentEdge = String(want);
            imgEl.dataset.upgrading = '1';
            // 先在后台把高清解码好，再替换 src —— 避免先白一下再变清晰
            const hi = new Image();
            const applySrc = () => {
                if (!imgEl.isConnected) return;
                if (String(imgEl.dataset.currentEdge || '') !== String(want)) return;  // 期间又变了，放弃
                imgEl.src = hi.src;
                imgEl.dataset.upgrading = '';
            };
            hi.onload = applySrc;
            hi.onerror = () => {
                // 高清生成失败就退回低清，绝不能掉到原图上（一张 4K 原图 31.7MB）
                imgEl.dataset.upgrading = '';
                imgEl.dataset.currentEdge = String(base);
                const back = deps.canvasThumbnailUrl(original, base);
                if (imgEl.getAttribute('src') !== back) imgEl.src = back;
            };
            hi.src = deps.canvasThumbnailUrl(original, want);
        });
        return upgraded;
    }

    // ── 小地图 ───────────────────────────────────────────────────────────
    let smartMinimapState = null;
    let minimapViewportEl = null;
    let minimapRenderFrame = 0;
    let minimapOpen = true;
    let smartMinimapDrag = false;
    try { minimapOpen = localStorage.getItem('smart_canvas_minimap_open') !== '0'; } catch (_) { }

    function scheduleMinimapRender() {
        if (minimapRenderFrame) return;
        minimapRenderFrame = requestAnimationFrame(() => {
            minimapRenderFrame = 0;
            renderMinimap();
        });
    }
    function renderMinimap() {
        const content = deps.minimapContentEl;
        if (!minimapViewportEl) minimapViewportEl = document.getElementById('minimapViewport');
        if (!content || !minimapViewportEl) return;
        const width = content.clientWidth || 170;
        const height = content.clientHeight || 108;
        const vp = deps.viewport;
        const viewW = deps.shell.clientWidth / vp.scale;
        const viewH = deps.shell.clientHeight / vp.scale;
        const viewX = -vp.x / vp.scale;
        const viewY = -vp.y / vp.scale;
        const rects = (deps.getNodes() || []).map(deps.nodeRect);
        // Keep the minimap coordinate system stable. The viewport is an overlay;
        // using it in these bounds makes the whole minimap resize while zooming.
        const worldBounds = { x: 0, y: 0, width: 6000, height: 4000 };
        const bounds = [worldBounds, ...rects];
        const minX = Math.min(...bounds.map(r => r.x), -200);
        const minY = Math.min(...bounds.map(r => r.y), -200);
        const maxX = Math.max(...bounds.map(r => r.x + r.width), 6200);
        const maxY = Math.max(...bounds.map(r => r.y + r.height), 4200);
        const scale = Math.min(width / Math.max(1, maxX - minX), height / Math.max(1, maxY - minY));
        const offsetX = (width - (maxX - minX) * scale) / 2;
        const offsetY = (height - (maxY - minY) * scale) / 2;
        smartMinimapState = { minX, minY, scale, offsetX, offsetY, width, height };
        const project = r => ({
            left: offsetX + (r.x - minX) * scale,
            top: offsetY + (r.y - minY) * scale,
            width: Math.max(4, r.width * scale),
            height: Math.max(4, r.height * scale)
        });
        const nodeHtml = rects.map(r => {
            const p = project(r);
            return `<div class="minimap-node" style="left:${p.left}px;top:${p.top}px;width:${p.width}px;height:${p.height}px"></div>`;
        }).join('');
        const view = project({ x: viewX, y: viewY, width: viewW, height: viewH });
        content.innerHTML = `${nodeHtml}<div id="minimapViewport" class="smart-minimap-viewport" style="left:${view.left}px;top:${view.top}px;width:${view.width}px;height:${view.height}px"></div>`;
        minimapViewportEl = document.getElementById('minimapViewport');
    }
    function minimapEventToWorld(event) {
        if (!smartMinimapState) renderMinimap();
        const state = smartMinimapState;
        if (!state) return CanvasViewport.viewportCenter();
        const rect = deps.minimapContentEl.getBoundingClientRect();
        const mx = event.clientX - rect.left;
        const my = event.clientY - rect.top;
        return {
            x: state.minX + (mx - state.offsetX) / Math.max(0.0001, state.scale),
            y: state.minY + (my - state.offsetY) / Math.max(0.0001, state.scale)
        };
    }
    function setMinimapOpen(open) {
        minimapOpen = Boolean(open);
        deps.minimapEl?.classList.toggle('is-hidden', !minimapOpen);
        deps.minimapToggleEl?.classList.toggle('active', minimapOpen);
        deps.minimapToggleEl?.setAttribute('aria-pressed', minimapOpen ? 'true' : 'false');
        try { localStorage.setItem('smart_canvas_minimap_open', minimapOpen ? '1' : '0'); } catch (_) { }
        if (minimapOpen) renderMinimap();
    }
    function isMinimapOpen() { return minimapOpen; }
    function beginMinimapDrag() { smartMinimapDrag = true; }
    function endMinimapDrag() { smartMinimapDrag = false; }
    function inMinimapDrag() { return smartMinimapDrag; }

    global.CanvasRenderScheduler = {
        configure: configure,
        // 裁剪
        scheduleCullCheck: scheduleCullCheck,
        scheduleCullRender: scheduleCullRender,
        visibleNodeList: visibleNodeList,
        cullSignature: cullSignature,
        markCullRendered: markCullRendered,
        // 升清
        scheduleImageUpgrade: scheduleImageUpgrade,
        upgradeVisibleImageSources: upgradeVisibleImageSources,
        // 小地图
        scheduleMinimapRender: scheduleMinimapRender,
        renderMinimap: renderMinimap,
        minimapEventToWorld: minimapEventToWorld,
        setMinimapOpen: setMinimapOpen,
        isMinimapOpen: isMinimapOpen,
        beginMinimapDrag: beginMinimapDrag,
        endMinimapDrag: endMinimapDrag,
        inMinimapDrag: inMinimapDrag
    };
})(typeof window !== 'undefined' ? window : globalThis);
