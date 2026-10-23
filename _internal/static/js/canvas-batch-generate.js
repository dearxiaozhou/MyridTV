/* 批量生成节点（原「循环节点」的位置，节点类型仍是 smart-loop）
 *
 * 老王 2026-10-22 定的四条功能：
 *  1. 提示词输入框（可加多段提示词）
 *  2. 图片生成引擎选择（与 smart-image 同一套数据源与视觉：API/火山/RH工作流/ComfyUI）
 *  3. 多张输入图片共用同一段提示词 → 每张图各出一个结果节点
 *  4. 一张输入图片配多段提示词 → 每段提示词各出一个结果节点
 * 输出数量 = 输入图片数 × 有效提示词数（老王拍板：两者相乘）。
 * 输入图片只能来自连线上游图片节点（不做无线引用、不自己上传）。
 *
 * 节点数据：prompts（多段提示词）、runSettings（本节点自己的引擎设置）、
 * batchRunning / batchStop / batchProgress。
 */
(function (global) {
    'use strict';

    var deps = {};
    function configure(options) { Object.assign(deps, options || {}); }
    function D(name) { return typeof deps[name] === 'function' ? deps[name]() : deps[name]; }
    function call(name) {
        var fn = deps[name];
        if (typeof fn !== 'function') return undefined;
        return fn.apply(null, Array.prototype.slice.call(arguments, 1));
    }
    function tr(key, fallback) {
        var value = call('tr', key);
        return value && value !== key ? value : (fallback || key);
    }
    function trf(key, vars, fallback) {
        var value = call('trf', key, vars);
        if (value && value !== key) return value;
        return String(fallback || key).replace(/\{(\w+)\}/g, function (m, name) {
            return vars && vars[name] != null ? String(vars[name]) : m;
        });
    }
    function esc(value) { return call('escapeHtml', value == null ? '' : value) || ''; }
    function nodeById(id) { return (D('nodes') || []).find(function (n) { return n.id === id; }) || null; }

    // ---------- 数据归一化 ----------

    function batchPrompts(node) {
        var list = Array.isArray(node && node.prompts) ? node.prompts : [];
        if (!list.length && node && Array.isArray(node.variablePrompts)) list = node.variablePrompts;
        if (!list.length && node && typeof node.variablePrompt === 'string') list = [node.variablePrompt];
        if (!list.length && node && typeof node.prompt === 'string') list = [node.prompt];
        list = list.map(function (text) { return String(text == null ? '' : text); });
        if (!list.length) list = [''];
        return list;
    }
    function activePrompts(node) {
        return batchPrompts(node).map(function (t) { return t.trim(); }).filter(Boolean);
    }
    function setBatchPrompts(node, values) {
        if (!node) return;
        var list = (values || []).map(function (text) { return String(text == null ? '' : text); });
        node.prompts = list.length ? list : [''];
        delete node.prompt;
        delete node.variablePrompt;
        delete node.variablePrompts;
    }
    function batchInputImages(node) {
        var images = call('lineImagesFor', node);
        return (images || []).filter(function (img) { return img && img.url; });
    }
    function outputCount(node) {
        return batchInputImages(node).length * activePrompts(node).length;
    }

    // ---------- 引擎选项（与 smart-image 的统一选择器同源同 id 规则）----------

    function engineItemId(s) {
        if (!s) return '';
        if (s.engine === 'runninghub' && s.rhConfigKey) return 'rh:' + s.rhConfigKey;
        if (s.engine === 'comfy' && s.comfyWorkflow) return 'comfy:' + s.comfyWorkflow;
        if ((s.engine === 'api' || s.engine === 'volcengine') && s.provider_id && s.model) return 'api:' + s.provider_id + ':' + s.model;
        return '';
    }
    function buildEngineGroups() {
        var groups = [];
        function push(key, title, items) {
            if (items.length) groups.push({ key: key, title: title, items: items });
        }
        var rhItems = [];
        ['workflow', 'app'].forEach(function (kind) {
            var entries = call('runningHubEntries', kind) || [];
            entries.forEach(function (entry) {
                var id = call('runningHubEntryId', entry, kind);
                if (!id) return;
                if (call('workflowOutputKindForRhEntry', entry) !== 'image') return;
                rhItems.push({
                    id: 'rh:' + kind + ':' + id,
                    label: entry.title || entry.name || (kind === 'workflow' ? 'Workflow ' + id : 'App ' + id),
                    apply: { engine: 'runninghub', apiKind: 'image', rhConfigKey: kind + ':' + id }
                });
            });
        });
        push('runninghub', 'RunningHub', rhItems);

        var comfyItems = (call('comfyWorkflows') || []).map(function (w) {
            var name = w && w.name;
            if (!name) return null;
            if (call('workflowOutputKindForComfy', name) === 'video') return null;
            return {
                id: 'comfy:' + name,
                label: (w.title || name),
                apply: { engine: 'comfy', apiKind: 'image', comfyMode: 'custom', comfyWorkflow: name }
            };
        }).filter(Boolean);
        push('comfy', 'ComfyUI', comfyItems);

        (call('imageProviders') || []).forEach(function (provider) {
            var models = call('providerImageModels', provider.id) || [];
            models = models.filter(Boolean);
            if (!models.length) return;
            push(String(provider.id), provider.name || provider.id, models.map(function (model) {
                var label = model;
                try { label = call('providerModelDisplayName', provider.id, model) || model; } catch (_) { }
                return {
                    id: 'api:' + provider.id + ':' + model,
                    label: label,
                    apply: {
                        engine: provider.id === 'volcengine' ? 'volcengine' : 'api',
                        apiKind: 'image',
                        provider_id: provider.id,
                        model: model
                    }
                };
            }));
        });
        return groups;
    }
    function currentEngineLabel(node) {
        var s = node && node.runSettings;
        var currentId = engineItemId(s);
        var groups = buildEngineGroups();
        for (var g = 0; g < groups.length; g++) {
            for (var i = 0; i < groups[g].items.length; i++) {
                if (groups[g].items[i].id === currentId) return groups[g].items[i].label;
            }
        }
        return '';
    }

    // ---------- 节点主体 HTML ----------

    function promptFieldHtml(value, index, total) {
        // 老王 2026-10-23：提示词框不要加序号
        return '<div class="batch-prompt-item">' +
            '<div class="batch-prompt-text" contenteditable="true" data-batch-prompt="' + index + '" data-placeholder="' + esc(tr('smart.batchPromptPlaceholder', '输入提示词')) + '">' + esc(value || '') + '</div>' +
            '<button class="batch-prompt-del" type="button" data-batch-prompt-del="' + index + '" title="' + esc(tr('common.delete', '删除')) + '" aria-label="' + esc(tr('common.delete', '删除')) + '"' + (total <= 1 ? ' disabled' : '') + '>×</button>' +
            '</div>';
    }
    // 比例/分辨率选项与 composer 的规格控件同一套取值（写进节点自己的 runSettings）
    var RATIO_OPTIONS = [
        ['square', '1:1'], ['portrait', '2:3'], ['landscape', '3:2'],
        ['portrait43', '3:4'], ['landscape43', '4:3'], ['story', '9:16'],
        ['wide', '16:9'], ['ultrawide', '21:9'], ['ultratall', '9:21']
    ];
    var RESOLUTION_OPTIONS = [['1k', '1K'], ['2k', '2K'], ['4k', '4K']];
    function ratioLabel(value) {
        var hit = RATIO_OPTIONS.find(function (item) { return item[0] === value; });
        return hit ? hit[1] : (value || '1:1');
    }
    function resolutionLabel(value) {
        var hit = RESOLUTION_OPTIONS.find(function (item) { return item[0] === value; });
        return hit ? hit[1] : String(value || '1K').toUpperCase();
    }
    function specControlHtml(node, kind) {
        var settings = node && node.runSettings || {};
        var value = kind === 'ratio' ? (settings.ratio || 'square') : (settings.resolution || '1k');
        var label = kind === 'ratio' ? ratioLabel(value) : resolutionLabel(value);
        var icon = kind === 'ratio' ? 'scan' : 'monitor';
        var title = kind === 'ratio' ? tr('smart.ratio', '比例') : tr('smart.resolution', '分辨率');
        return '<div class="batch-spec-control" data-batch-spec-kind="' + kind + '">' +
            '<button class="batch-spec-pill" type="button" data-batch-spec-toggle="' + kind + '">' +
            '<i data-lucide="' + icon + '"></i><span>' + esc(label) + '</span><i data-lucide="chevron-down" class="pill-caret"></i>' +
            '</button></div>';
    }
    function popoverInnerHtml(node, kind) {
        var settings = node && node.runSettings || {};
        if (kind === 'ratio' || kind === 'resolution') {
            var options = kind === 'ratio' ? RATIO_OPTIONS : RESOLUTION_OPTIONS;
            var current = kind === 'ratio' ? (settings.ratio || 'square') : (settings.resolution || '1k');
            return '<div class="batch-engine-group"><div class="batch-engine-group-title">' + esc(kind === 'ratio' ? tr('smart.ratio', '比例') : tr('smart.resolution', '分辨率')) + '</div>' +
                options.map(function (item) {
                    return '<button type="button" class="batch-engine-option' + (item[0] === current ? ' active' : '') + '" data-batch-spec-item="' + esc(item[0]) + '">' +
                        '<span class="batch-engine-option-name">' + esc(item[1]) + '</span>' +
                        (item[0] === current ? '<span class="batch-engine-option-check">✓</span>' : '') +
                        '</button>';
                }).join('') + '</div>';
        }
        var groups = buildEngineGroups();
        var currentId = engineItemId(settings);
        if (!groups.length) return '<div class="batch-engine-empty">' + esc(tr('smart.batchEngineEmpty', '当前没有可用的图片引擎')) + '</div>';
        return groups.map(function (group) {
            return '<div class="batch-engine-group"><div class="batch-engine-group-title">' + esc(group.title) + '</div>' +
                group.items.map(function (item) {
                    return '<button type="button" class="batch-engine-option' + (item.id === currentId ? ' active' : '') + '" data-batch-engine-item="' + esc(item.id) + '">' +
                        '<span class="batch-engine-option-name">' + esc(item.label) + '</span>' +
                        (item.id === currentId ? '<span class="batch-engine-option-check">✓</span>' : '') +
                        '</button>';
                }).join('') + '</div>';
        }).join('');
    }
    function enginePickerHtml(node) {
        var label = currentEngineLabel(node);
        // 弹层不放在节点 DOM 里：节点在 #world 的 scale/translate 变换层内，
        // 绝对/固定定位都会被画布变换和顶部工具条影响（老王 2026-10-23：弹层被遮挡）。
        // 改为挂到 document.body 的浮层，按 pill 的视口矩形定位并自动上下翻转。
        return '<div class="batch-engine-control">' +
            '<button class="batch-engine-pill" type="button" data-batch-engine-toggle="' + esc(node.id) + '" title="' + esc(tr('smart.batchEngine', '生成引擎')) + '">' +
            '<i data-lucide="layers"></i><span class="sub">' + esc(label || tr('smart.batchEnginePick', '选择生成引擎')) + '</span><i data-lucide="chevron-down" class="pill-caret"></i>' +
            '</button></div>';
    }
    function bodyHtml(node) {
        var prompts = batchPrompts(node);
        var images = batchInputImages(node);
        var active = activePrompts(node).length;
        var total = images.length * active;
        var running = Boolean(node.batchRunning);
        var stopping = Boolean(node.batchStop);
        var progress = node.batchProgress || null;
        var progressText = progress ? trf('smart.batchProgress', { done: progress.done || 0, total: progress.total || 0 }, '已出 {done}/{total}') : '';
        var planText = images.length
            ? trf('smart.batchPlan', { img: images.length, prompt: active, total: total }, '{img} 张图 × {prompt} 段提示词 = {total} 张')
            : tr('smart.batchNoImage', '请把图片节点连到本节点输入口');
        return '<div class="batch-card">' +
            '<div class="batch-prompt-list">' +
            prompts.map(function (value, index) { return promptFieldHtml(value, index, prompts.length); }).join('') +
            '</div>' +
            '<button class="batch-add-row" type="button" data-batch-prompt-add="1"><i data-lucide="plus"></i><span>' + esc(tr('smart.batchAddPrompt', '增加一段提示词')) + '</span></button>' +
            '<div class="batch-note-row"><span class="batch-note">' + esc(planText) + (progressText ? ' · ' + esc(progressText) : '') + '</span></div>' +
            '<div class="batch-footer">' + enginePickerHtml(node) + specControlHtml(node, 'ratio') + specControlHtml(node, 'resolution') +
            '<button class="batch-run' + (running ? ' is-stop' : '') + '" type="button" data-batch-run="' + esc(node.id) + '"' + (stopping ? ' disabled' : '') + '>' +
            '<i data-lucide="' + (running ? 'square' : 'sparkles') + '"></i><span>' + esc(running ? (stopping ? tr('smart.batchStopping', '停止中…') : tr('smart.batchStop', '停止')) : tr('smart.batchRun', '批量生成')) + '</span>' +
            '</button></div>' +
            '</div>';
    }

    // ---------- 尺寸 ----------

    var NODE_WIDTH = 420;
    function bodyHeight(node) {
        var prompts = batchPrompts(node).length;
        var h = prompts * 60;       // 提示词段
        h += 30;                    // 虚线加号排
        h += 16;                    // 说明文字（单排）
        h += 30;                    // 引擎 + 比例 + 分辨率 + 生成按钮
        h += 26;                    // 间隔
        if (node && node.batchProgress) h += 4;
        return Math.round(h);
    }
    function fitNode(node) {
        if (!node) return;
        node.w = NODE_WIDTH;
        node.h = bodyHeight(node);
    }

    // ---------- 交互绑定 ----------

    // ---------- 引擎浮层（挂 body，避开画布变换层）----------

    var floatEl = null;
    var floatBound = false;
    function ensureFloat() {
        if (floatEl && document.body.contains(floatEl)) return floatEl;
        floatEl = document.createElement('div');
        floatEl.className = 'batch-engine-float';
        document.body.appendChild(floatEl);
        if (!floatBound) {
            floatBound = true;
            floatEl.addEventListener('mousedown', function (event) { event.stopPropagation(); });
            floatEl.addEventListener('click', function (event) {
                var kind = floatEl.getAttribute('data-owner-kind') || 'engine';
                var target = nodeById(floatEl.getAttribute('data-owner-node') || '');
                if (!target) { closePicker(); return; }
                var engineOpt = event.target.closest && event.target.closest('[data-batch-engine-item]');
                var specOpt = event.target.closest && event.target.closest('[data-batch-spec-item]');
                if (engineOpt) {
                    event.preventDefault();
                    event.stopPropagation();
                    var id = engineOpt.getAttribute('data-batch-engine-item');
                    var hit = null;
                    buildEngineGroups().forEach(function (group) {
                        group.items.forEach(function (item) { if (item.id === id) hit = item; });
                    });
                    if (hit) {
                        target.runSettings = Object.assign({}, target.runSettings || {}, hit.apply);
                        call('rememberRecentSmartSettings', target.runSettings, target);
                    }
                } else if (specOpt) {
                    event.preventDefault();
                    event.stopPropagation();
                    var patch = {};
                    patch[kind === 'resolution' ? 'resolution' : 'ratio'] = specOpt.getAttribute('data-batch-spec-item');
                    target.runSettings = Object.assign({}, target.runSettings || {}, patch);
                    call('rememberRecentSmartSettings', target.runSettings, target);
                } else {
                    return;
                }
                closePicker();
                render(target);
            });
            document.addEventListener('click', function (event) {
                if (!floatEl || !floatEl.classList.contains('open')) return;
                if (event.target.closest && event.target.closest('.batch-engine-float')) return;
                if (event.target.closest && event.target.closest('[data-batch-engine-toggle],[data-batch-spec-toggle]')) return;
                closePicker();
            });
            window.addEventListener('resize', closePicker);
        }
        return floatEl;
    }
    function closePicker() {
        if (floatEl) {
            floatEl.classList.remove('open');
            floatEl.removeAttribute('data-owner-node');
            floatEl.removeAttribute('data-owner-kind');
        }
        document.querySelectorAll('.batch-engine-control.pinned, .batch-spec-control.pinned').forEach(function (item) { item.classList.remove('pinned'); });
    }
    function openPicker(node, anchor, kind) {
        var box = ensureFloat();
        var sameTarget = box.getAttribute('data-owner-node') === node.id && box.getAttribute('data-owner-kind') === kind;
        var alreadyOpen = box.classList.contains('open') && sameTarget;
        closePicker();
        if (alreadyOpen) return;
        box.innerHTML = popoverInnerHtml(node, kind);
        box.setAttribute('data-owner-node', node.id);
        box.setAttribute('data-owner-kind', kind);
        box.classList.add('open');
        var rect = anchor.getBoundingClientRect();
        var width = kind === 'engine' ? Math.min(300, window.innerWidth - 24) : Math.min(180, window.innerWidth - 24);
        box.style.width = width + 'px';
        var height = box.offsetHeight || 240;
        var top = rect.bottom + 8;                       // 默认向下
        if (top + height > window.innerHeight - 12) {    // 下方放不下就翻到上方
            var above = rect.top - height - 8;
            top = above > 12 ? above : Math.max(12, window.innerHeight - height - 12);
        }
        var left = rect.left;
        if (left + width > window.innerWidth - 12) left = Math.max(12, window.innerWidth - 12 - width);
        box.style.left = Math.round(left) + 'px';
        box.style.top = Math.round(top) + 'px';
        var holder = anchor.closest('.batch-engine-control') || anchor.closest('.batch-spec-control');
        if (holder) holder.classList.add('pinned');
    }

    function bind(el, node) {
        if (!el || !node) return;
        el.querySelectorAll('.batch-prompt-text, .batch-prompt-del, .batch-add-row, .batch-run, .batch-engine-control, .batch-spec-control').forEach(function (control) {
            ['mousedown', 'pointerdown', 'click', 'dblclick'].forEach(function (type) {
                control.addEventListener(type, function (event) { event.stopPropagation(); });
            });
        });
        // 引擎 / 比例 / 分辨率浮层
        var toggle = el.querySelector('[data-batch-engine-toggle]');
        if (toggle) {
            toggle.onclick = function (event) {
                event.preventDefault();
                event.stopPropagation();
                openPicker(node, toggle, 'engine');
            };
        }
        el.querySelectorAll('[data-batch-spec-toggle]').forEach(function (specToggle) {
            specToggle.onclick = function (event) {
                event.preventDefault();
                event.stopPropagation();
                openPicker(node, specToggle, specToggle.getAttribute('data-batch-spec-toggle'));
            };
        });
        // 提示词编辑
        var syncFromDom = function () {
            var values = Array.prototype.slice.call(el.querySelectorAll('[data-batch-prompt]'))
                .sort(function (a, b) { return Number(a.dataset.batchPrompt) - Number(b.dataset.batchPrompt); })
                .map(function (input) { return input.innerText || input.textContent || ''; });
            setBatchPrompts(node, values);
        };
        el.querySelectorAll('.batch-prompt-text').forEach(function (text) {
            call('bindScrollableText', text);
            text.oninput = function () { syncFromDom(); call('scheduleSave'); };
            text.addEventListener('keydown', function (event) { event.stopPropagation(); });
        });
        el.querySelectorAll('[data-batch-prompt-del]').forEach(function (btn) {
            btn.onclick = function (event) {
                event.preventDefault();
                event.stopPropagation();
                syncFromDom();
                var values = batchPrompts(node);
                if (values.length <= 1) return;
                values.splice(Number(btn.dataset.batchPromptDel), 1);
                setBatchPrompts(node, values);
                render(node);
            };
        });
        el.querySelectorAll('[data-batch-prompt-add]').forEach(function (btn) {
            btn.onclick = function (event) {
                event.preventDefault();
                event.stopPropagation();
                syncFromDom();
                setBatchPrompts(node, batchPrompts(node).concat(['']));
                render(node);
            };
        });
        // 运行 / 停止
        el.querySelectorAll('[data-batch-run]').forEach(function (btn) {
            btn.onclick = function (event) {
                event.preventDefault();
                event.stopPropagation();
                syncFromDom();
                if (node.batchRunning) {
                    node.batchStop = true;
                    render(node);
                    return;
                }
                runBatch(node).catch(function (error) {
                    call('toast', (error && error.message) || String(error));
                });
            };
        });
    }
    function render(node) {
        closePicker();
        fitNode(node);
        call('render');
        call('scheduleSave');
    }

    // ---------- 运行器 ----------

    function outputPosition(node, index) {
        var rect = call('nodeRect', node) || { x: node.x || 0, y: node.y || 0, width: NODE_WIDTH, height: node.h || 200 };
        var startX = Math.round((Number(node.x) || 0) + (Number(rect.width) || NODE_WIDTH) + 90);
        var startY = Math.round(Number(node.y) || 0);
        var box = 260;
        var stepY = box + 28;
        var perColumn = 4;
        var column = Math.floor(index / perColumn);
        var row = index % perColumn;
        var x = startX + column * (box + 28);
        var y = startY + row * stepY;
        return call('agentFindEmptySpot', x, y, box, box) || { x: x, y: y };
    }
    function createOutputNode(node, image, prompt, index, total) {
        var pos = outputPosition(node, index);
        var target = call('createImageNodeAt',
            { x: pos.x + 130, y: pos.y + 130 },
            [],
            { select: false, skipUndo: true }
        );
        if (!target) return null;
        target.title = trf('smart.batchOutputTitle', { n: index + 1 }, '批量 {n}');
        target.runSettings = JSON.parse(JSON.stringify(node.runSettings || {}));
        target.batchSourceId = node.id;
        target.batchIndex = index;
        target.batchTotal = total;
        target.pending = 1;
        target.running = true;
        target.runStartedAt = call('nowMs');
        delete target.w;
        delete target.h;
        call('addConnection', node.id, target.id, 'flow');
        return target;
    }

    function jobRunSnapshot(runSettings, target, prompt, refs){
        return {
            nodeId: target && target.id || '', nodeType: 'smart-image', kind: 'image',
            settings: JSON.parse(JSON.stringify(runSettings || {})),
            prompt: prompt || '',
            refs: (refs || []).map(function (ref) { return { url: ref.url || '', name: ref.name || 'image', kind: ref.kind || 'image' }; }).filter(function (ref) { return ref.url; }),
            size: ''
        };
    }

    async function runBatch(node) {
        var images = batchInputImages(node);
        var prompts = activePrompts(node);
        if (!images.length) { call('toast', tr('smart.batchNoImage', '请把图片节点连到本节点输入口')); return; }
        if (!prompts.length) { call('toast', tr('smart.batchNoPrompt', '请至少写一段提示词')); return; }
        var runSettings = JSON.parse(JSON.stringify(node.runSettings || {}));
        if (!runSettings.engine) { call('toast', tr('smart.batchNoEngine', '请先选择生成引擎')); return; }

        var jobs = [];
        images.forEach(function (image) {
            prompts.forEach(function (prompt) {
                jobs.push({ image: image, prompt: prompt });
            });
        });

        node.batchRunning = true;
        node.batchStop = false;
        node.batchProgress = { done: 0, total: jobs.length };
        call('pushUndo');
        render(node);

        var done = 0;
        var failed = 0;
        try {
            for (var i = 0; i < jobs.length; i++) {
                if (node.batchStop) break;
                var job = jobs[i];
                var target = createOutputNode(node, job.image, job.prompt, i, jobs.length);
                if (!target) { failed += 1; continue; }
                var refs = [{
                    url: job.image.url,
                    name: job.image.name || ('图' + (i + 1)),
                    nodeId: job.image.nodeId || '',
                    imageIndex: job.image.imageIndex != null ? job.image.imageIndex : '',
                    kind: 'image'
                }];
                var meta = {
                    prompt: job.prompt, displayPrompt: job.prompt,
                    promptRefs: refs.map(function (r) { return { url: r.url, name: r.name, nodeId: r.nodeId, imageIndex: r.imageIndex }; }),
                    inputRefs: refs,
                    settings: JSON.parse(JSON.stringify(runSettings)),
                    sourceNodeId: node.id, createdAt: Date.now()
                };
                var startedAt = Date.now();
                node.batchProgress = { done: done, total: jobs.length };
                render(node);
                try {
                    var result = await call('generate', target, job.prompt, refs, runSettings);
                    var urls = (result && result.urls) || [];
                    if (!urls.length) throw new Error(tr('smart.errNoOutImages', '没有生成图片'));
                    await call('finalizePendingNode', target, urls, meta, 'image');
                    done += 1;
                    // 运行记录进画布日志（与单节点生成同一条路径，老王 2026-10-23：之前批量生成不写日志）
                    call('addSmartGenerationLog', {
                        run: jobRunSnapshot(runSettings, target, job.prompt, refs),
                        outputs: (target.images || []).map(function (img) { return img.url; }).filter(Boolean),
                        runMs: Date.now() - startedAt
                    });
                } catch (error) {
                    failed += 1;
                    target.pending = 0;
                    target.running = false;
                    target.runError = ((error && error.message) || String(error)).slice(0, 160);
                    call('addSmartGenerationLog', {
                        run: jobRunSnapshot(runSettings, target, job.prompt, refs),
                        outputs: [], runMs: Date.now() - startedAt, error: target.runError
                    });
                    call('toast', trf('smart.batchJobFailed', { n: i + 1 }, '第 {n} 张失败') + '：' + target.runError);
                }
                node.batchProgress = { done: done, total: jobs.length, failed: failed };
                render(node);
            }
        } finally {
            node.batchRunning = false;
            node.batchStop = false;
            call('render');
            call('scheduleSave');
        }
        call('toast', trf('smart.batchDone', { ok: done, failed: failed }, '批量生成完成：成功 {ok} 张，失败 {failed} 张'));
        return { ok: done, failed: failed };
    }

    global.CanvasBatchGenerate = {
        configure: configure,
        bodyHtml: bodyHtml,
        bind: bind,
        fitNode: fitNode,
        bodyHeight: bodyHeight,
        NODE_WIDTH: NODE_WIDTH,
        batchPrompts: batchPrompts,
        setBatchPrompts: setBatchPrompts,
        batchInputImages: batchInputImages,
        outputCount: outputCount,
        runBatch: runBatch,
        buildEngineGroups: buildEngineGroups,
        openPicker: openPicker,
        closePicker: closePicker
    };
})(typeof window !== 'undefined' ? window : globalThis);
