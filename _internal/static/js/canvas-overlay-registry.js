/* MyridTV 画布浮层注册表（状态机改造·第8步：OverlayRegistry）
 *
 * 病根：浮层与画布的交互边界以前靠 6 条硬编码 closest(...) 排除链维护，
 * 每加一个浮层就要记得往每条链补选择器，漏一条=画布穿透误触发。
 *
 * 现在：每个 kind 一个 base 链（逐字迁移自原链，行为数学等价）+ 一个
 * 动态选择器数组。新浮层只调 CanvasOverlayRegistry.register(sel, kinds?)
 * 一处声明，所有判定自动生效。
 *
 * kinds（base 链与迁移前逐字节一致）：
 *   'overlay'          通用画布浮层（mousedown/dblclick/contextmenu 排除）
 *   'pan-exclude'      中键平移排除（比 overlay 少 .composer）
 *   'wheel-exclude'    滚轮不缩放画布的浮层
 *   'wheel-scrollable' 滚轮由浮层自身消化的容器
 *   'zoom-preview'     缩放预览期间的吞事件浮层
 *   'click-empty'      空白点击清选中排除（含 .image-node，原链语义保留）
 */
(function (global) {
    'use strict';

    var BASE = {
        'overlay': '.composer,.smart-back,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.create-menu,.smart-minimap,.smart-image-context-menu,#smartImageContextMenu',
        'pan-exclude': '.smart-back,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.create-menu,.smart-minimap,.smart-image-context-menu,#smartImageContextMenu',
        'wheel-exclude': '.composer,.smart-back,.canvas-tool-dock,.canvas-bottom-tools,.image-edit-modal,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.prompt-template-panel,.prompt-preset-panel',
        'wheel-scrollable': '.asset-panel,.asset-grid,.style-panel,.style-grid,.canvas-agent-panel,.canvas-agent-messages,.prompt-template-panel,.prompt-template-list,.prompt-template-preview-content,.mention-picker,.smart-table-wrap,.prompt-node-text,.loop-smart-text,.loop-smart-upstream-text,textarea,[contenteditable="true"]',
        'zoom-preview': '.composer,.smart-back,.asset-panel,.asset-toggle,.style-panel,.style-toggle,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.create-menu,.smart-minimap',
        'click-empty': '.image-node,.composer,.smart-back,.canvas-tool-dock,.canvas-bottom-tools,.canvas-agent-panel,.canvas-agent-toggle,.smart-log-toggle,.smart-shortcut-toggle,.log-modal,.shortcut-modal,.image-edit-modal,.create-menu'
    };

    var dynamic = {};   // kind -> [selector,...]
    function register(selector, kinds) {
        var sel = String(selector || '').trim();
        if (!sel) return false;
        var list = Array.isArray(kinds) ? kinds : (kinds ? [kinds] : Object.keys(BASE));
        list.forEach(function (kind) {
            if (!(kind in BASE)) return;
            (dynamic[kind] = dynamic[kind] || []).indexOf(sel) < 0 && dynamic[kind].push(sel);
        });
        return true;
    }
    function unregister(selector) {
        var sel = String(selector || '').trim();
        Object.keys(dynamic).forEach(function (kind) {
            var arr = dynamic[kind], i = arr ? arr.indexOf(sel) : -1;
            if (i >= 0) arr.splice(i, 1);
        });
    }
    function isOverlay(target, kind) {
        if (!target || !target.closest) return false;
        if (BASE[kind] && target.closest(BASE[kind])) return true;
        var arr = dynamic[kind];
        if (!arr || !arr.length) return false;
        for (var i = 0; i < arr.length; i++) {
            try { if (target.closest(arr[i])) return true; } catch (_e) { /* 坏选择器跳过 */ }
        }
        return false;
    }
    function snapshot() {
        var out = { base: {}, dynamic: {} };
        Object.keys(BASE).forEach(function (k) { out.base[k] = (BASE[k].match(/,/g) || []).length + 1; });
        // 只报非空动态条目：register→unregister 往返后应回到初始态（不留空壳键）
        Object.keys(dynamic).forEach(function (k) { if (dynamic[k] && dynamic[k].length) out.dynamic[k] = dynamic[k].slice(); });
        return out;
    }

    global.CanvasOverlayRegistry = {
        register: register,
        unregister: unregister,
        isOverlay: isOverlay,
        snapshot: snapshot,
        BASE: BASE
    };
})(typeof window !== 'undefined' ? window : globalThis);
