/* MyridTV 画布统一「平台·工作流/模型」选择面板（2026-09-25 定稿）
 *
 * 老王拍板：
 * - 图片/视频切换按钮 = 类别过滤器：只显示该类别的条目
 * - 平台名只作分组标题（不可点），可选的是标题下的工作流/模型；选条目=隐式选平台
 * - 引擎下拉框不再作为平台入口（隐藏）；切换后当前项失配时自动跳该类别最近用过的条目
 * - 无该类别条目的平台连标题都不出现（如平台没配视频模型，视频模式下不显示）
 *
 * 依赖宿主注入（CanvasUnifiedPicker.configure）：settings/comfyWorkflows/
 * runningHubEntries/runningHubEntryId/runningHubEntryKey/workflowOutputKindForComfy/
 * workflowOutputKindForRhEntry/imageProviders/videoApiProviders/volcengineProvider/
 * providerImageModels/providerVideoModels/filterJimengImageModels/filterJimengVideoModels/
 * setDynamicSetting/tr/escapeHtml/escapeAttr/refreshIcons/toast/renderDynamicParams
 */
(function (global) {
    'use strict';
    var deps = {
        getSettings: null, comfyWorkflows: null, runningHubEntries: null,
        runningHubEntryId: null, runningHubEntryKey: null,
        workflowOutputKindForComfy: null, workflowOutputKindForRhEntry: null,
        imageProviders: null, videoApiProviders: null, volcengineProvider: null,
        providerImageModels: null, providerVideoModels: null,
        providerModelDisplayName: null,
        filterJimengImageModels: null, filterJimengVideoModels: null,
        setDynamicProperty: null, tr: function (k) { return k; },
        escapeHtml: function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); },
        escapeAttr: function (s) { return String(s == null ? '' : s).replace(/"/g, '&quot;'); },
        refreshIcons: null, toast: null, renderDynamicParams: null
    };
    var RECENT_KEY = 'canvas_unified_recent_v1';

    function configure(patch) { Object.assign(deps, patch || {}); }
    function S() { return deps.getSettings ? deps.getSettings() : {}; }
    function kind() { return S().apiKind === 'video' ? 'video' : 'image'; }

    // ---- 最近使用记录：{image:[id...], video:[...]} 队首最新 ----
    function loadRecent() {
        try {
            var d = JSON.parse(localStorage.getItem(RECENT_KEY) || '{}');
            return { image: Array.isArray(d.image) ? d.image : [], video: Array.isArray(d.video) ? d.video : [] };
        } catch (_) { return { image: [], video: [] }; }
    }
    function remember(id) {
        if (!id) return;
        var r = loadRecent();
        var k = kind();
        r[k] = [id].concat((r[k] || []).filter(function (x) { return x !== id; })).slice(0, 30);
        try { localStorage.setItem(RECENT_KEY, JSON.stringify(r)); } catch (_) {}
    }

    // ---- 聚合：按平台分组，仅保留当前类别有内容的平台 ----
    function pushGroup(groups, key, title, items) {
        if (!items.length) return;
        var hit = groups.find(function (g) { return g.key === key; });
        if (hit) { hit.items = hit.items.concat(items); return; }
        groups.push({ key: key, title: title, items: items });
    }
    function buildGroups(k) {
        var groups = [];
        // RunningHub
        var rh = [];
        (deps.runningHubEntries ? deps.runningHubEntries('workflow') : []).forEach(function (e) {
            var id = String(deps.runningHubEntryId(e, 'workflow') || '');
            if (!id) return;
            if (deps.workflowOutputKindForRhEntry(e) === k) {
                rh.push({ id: 'rh:workflow:' + id, title: e.title || e.name || ('Workflow ' + id), rhKey: 'workflow:' + id });
            }
        });
        (deps.runningHubEntries ? deps.runningHubEntries('app') : []).forEach(function (e) {
            var id = String(deps.runningHubEntryId(e, 'app') || '');
            if (!id) return;
            if (deps.workflowOutputKindForRhEntry(e) === k) {
                rh.push({ id: 'rh:app:' + id, title: e.title || e.name || ('App ' + id), rhKey: 'app:' + id });
            }
        });
        pushGroup(groups, 'runninghub', 'RunningHub', rh);
        // ComfyUI
        var comfy = (global.comfyWorkflowsList ? global.comfyWorkflowsList() : (deps.comfyWorkflows ? (typeof deps.comfyWorkflows === 'function' ? deps.comfyWorkflows() : deps.comfyWorkflows) : []) || []);
        var cItems = comfy.map(function (w) {
            var name = w.name;
            if (!name) return null;
            var isVid = deps.workflowOutputKindForComfy(name) === 'video';
            if ((k === 'video') !== isVid) return null;
            return { id: 'comfy:' + name, title: w.title || name, comfyWorkflow: name };
        }).filter(Boolean);
        pushGroup(groups, 'comfy', 'ComfyUI', cItems);
        // API 平台（含火山；图片/视频模型列表天然分类，无该类别即不出现）
        var apiProviders = [];
        if (k === 'image') {
            apiProviders = (deps.imageProviders ? deps.imageProviders() : []) || [];
        } else {
            apiProviders = (deps.videoApiProviders ? deps.videoApiProviders() : []) || [];
            var volc = deps.volcengineProvider ? deps.volcengineProvider() : null;
            if (volc && !apiProviders.some(function (p) { return p.id === 'volcengine'; })) apiProviders = apiProviders.concat([volc]);
        }
        apiProviders.forEach(function (p) {
            var models = (k === 'image' ? deps.providerImageModels : deps.providerVideoModels)(p.id) || [];
            if (p.id === 'jimeng') models = (k === 'image' ? deps.filterJimengImageModels : deps.filterJimengVideoModels)(models) || models;
            models = models.filter(Boolean);
            if (!models.length) return;   // 拍板3：没有该类模型 → 标题都不显示
            pushGroup(groups, String(p.id), p.name || p.id, models.map(function (m) {
                var disp = m;
                if (deps.providerModelDisplayName) {
                    try { disp = deps.providerModelDisplayName(p.id, m) || m; } catch (_) {}
                }
                return { id: 'api:' + p.id + ':' + m, title: m, display: disp, apiProvider: p.id, model: m };
            }));
        });
        return groups;
    }

    // ---- 当前选中项 id（与 settings 对齐）----
    function currentId() {
        var s = S();
        var k = kind();
        if (s.engine === 'runninghub' && s.rhConfigKey) return 'rh:' + s.rhConfigKey;
        if (s.engine === 'comfy' && s.comfyWorkflow) return 'comfy:' + s.comfyWorkflow;
        if ((s.engine === 'api' || s.engine === 'volcengine') && !isApiVideoMode(s)) {
            if (s.provider_id && s.model) return 'api:' + s.provider_id + ':' + s.model;
        }
        if (isApiVideoMode(s) || (s.engine === 'api' && s.apiKind === 'video' && s.videoProvider && s.videoModel)) {
            if (k === 'video' && s.videoProvider && s.videoModel) return 'api:' + s.videoProvider + ':' + s.videoModel;
        }
        return '';
    }
    function isApiVideoMode(s) {
        if (s.engine !== 'api' && s.engine !== 'volcengine') return false;
        return s.apiKind === 'video';
    }

    // ---- 选择条目 → 写回 settings（engine 由条目类型隐式决定）----
    function select(item) {
        // 引擎/条目全部经宿主 applyToSubject：宿主负责 settings + composer 节点
        // runSettings 双轨同步（否则按节点渲染时会回灌旧引擎）。
        var applied = { apiKind: kind() };
        if (item.id.indexOf('rh:') === 0) {
            applied.engine = 'runninghub';
            applied.rhConfigKey = item.rhKey;
        } else if (item.id.indexOf('comfy:') === 0) {
            applied.engine = 'comfy';
            applied.comfyWorkflow = item.comfyWorkflow;
        } else if (kind() === 'video') {
            applied.engine = 'api';
            applied.videoProvider = item.apiProvider;
            applied.videoModel = item.model;
        } else {
            applied.engine = item.apiProvider === 'volcengine' ? 'volcengine' : 'api';
            applied.provider_id = item.apiProvider;
            if (item.model) applied.model = item.model;
        }
        if (deps.applyToSubject) deps.applyToSubject(applied);
        else Object.assign(S(), applied);
        remember(item.id);
        if (deps.renderDynamicParams) deps.renderDynamicParams();
        // 渲染链里 applyRecent/persist 可能整体换 settings 引用（旧引擎回灌），终态再钉一次
        if (deps.applyToSubject) deps.applyToSubject(applied);
        else Object.assign(S(), applied);
        if (deps.persist) deps.persist();
        if (deps.scheduleSave) deps.scheduleSave();
    }

    // ---- 类别切换后的失配兜底：跳到该类别最近用过（队首仍在该类别列表里），否则第一项 ----
    function autoPickForKind(k) {
        var groups = buildGroups(k);
        var flat = [];
        groups.forEach(function (g) { g.items.forEach(function (it) { flat.push(it); }); });
        if (!flat.length) return null;
        if (flat.some(function (it) { return it.id === currentId(); })) return null; // 当前项仍合法
        var recent = loadRecent()[k] || [];
        for (var i = 0; i < recent.length; i++) {
            var hit = flat.find(function (it) { return it.id === recent[i]; });
            if (hit) return hit;
        }
        return flat[0];
    }

    // ---- Pill 渲染（放进参数排首位；平台标题+条目弹层）----
    function renderPill() {
        var k = kind();
        var cur = currentId();
        var groups = buildGroups(k);
        var label = '选择工作流/模型';
        for (var a = 0; a < groups.length; a++) {
            var hit = groups[a].items.find(function (it) { return it.id === cur; });
            if (hit) { label = hit.display || hit.title; break; }
        }
        var esc = deps.escapeHtml;
        var popId = 'unifiedPickerPopover';
        return '<div class="param-item param-unified-picker">' +
            '<div class="smart-control unified-picker-control" id="unifiedPickerControl">' +
            '<button class="smart-pill unified-picker-pill" type="button" onclick="CanvasUnifiedPicker.onPillClick(event)" title="' + esc('平台·工作流/模型（图片/视频已过滤）') + '"><i data-lucide="layers"></i><span class="sub">' + esc(label) + '</span></button>' +
            '<div class="smart-popover unified-picker-popover" id="' + popId + '">' +
            '<div class="unified-picker-body">' + (groups.length ? groups.map(function (g) {
                return '<div class="unified-group"><div class="unified-group-title">' + esc(g.title) + '</div>' +
                    g.items.map(function (it) {
                        return '<button type="button" class="unified-option' + (it.id === cur ? ' active' : '') + '" data-unified-id="' + esc(deps.escapeAttr ? deps.escapeAttr(it.id) : it.id) + '" onclick="CanvasUnifiedPicker.onOptionClick(event, \'' + String(it.id).replace(/'/g, "\\'") + '\')">' +
                            '<span class="unified-option-name">' + esc(it.display || it.title) + '</span>' +
                            (it.id === cur ? '<span class="unified-option-check">✓</span>' : '') +
                            '</button>';
                    }).join('') + '</div>';
            }).join('') : '<div class="muted-note">当前类别没有可选的工作流或模型</div>') + '</div>' +
            '</div></div></div>';
    }

    // ---- 事件绑定（click 委托，宿主 DOMContentLoaded 后调用一次即可，pill 重建不影响）----
    var bound = false;
    function bindEvents() {
        if (bound) return; bound = true;
        document.addEventListener('click', function (e) {
            var pill = e.target.closest && e.target.closest('.unified-picker-pill');
            if (pill) {
                e.preventDefault(); e.stopPropagation();
                var ctrl = pill.closest('.unified-picker-control');
                var open = ctrl.classList.contains('pinned');
                document.querySelectorAll('.unified-picker-control.pinned').forEach(function (x) { x.classList.remove('pinned'); });
                if (!open) ctrl.classList.add('open');
                return;
            }
            var opt = e.target.closest && e.target.closest('[data-unified-id]');
            if (opt) {
                e.preventDefault(); e.stopPropagation();
                var id = opt.getAttribute('data-unified-id');
                var groups = buildGroups(kind());
                var item = null;
                groups.forEach(function (g) { g.items.forEach(function (it) { if (it.id === id) item = it; }); });
                if (item) { select(item); document.querySelectorAll('.unified-picker-control.pinned').forEach(function (x) { x.classList.remove('pinned'); }); }
                return;
            }
            if (!e.target.closest || !e.target.closest('.unified-picker-control')) {
                document.querySelectorAll('.unified-picker-control.pinned').forEach(function (x) { x.classList.remove('pinned'); });
            }
        });
    }

    function closeAll() {
        document.querySelectorAll('.unified-picker-control.pinned').forEach(function (x) { x.classList.remove('pinned'); });
    }
    function onPillClick(e) {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        var pill = e.target.closest ? e.target.closest('.unified-picker-pill') : null;
        var ctrl = pill && pill.closest('.unified-picker-control');
        if (!ctrl) return;
        var was = ctrl.classList.contains('pinned');
        closeAll();
        if (!was) ctrl.classList.add('pinned');
    }
    function onOptionClick(e, id) {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        var groups = buildGroups(kind());
        var item = null;
        groups.forEach(function (g) { g.items.forEach(function (it) { if (it.id === id) item = it; }); });
        closeAll();
        if (item) select(item);
    }

    global.CanvasUnifiedPicker = {
        onPillClick: onPillClick, onOptionClick: onOptionClick,
        configure: configure, bindEvents: bindEvents,
        buildGroups: buildGroups, currentId: currentId, select: select,
        renderPill: renderPill, autoPickForKind: autoPickForKind, remember: remember
    };
})(typeof window !== 'undefined' ? window : globalThis);
