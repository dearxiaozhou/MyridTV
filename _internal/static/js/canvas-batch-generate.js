/* 批量生成节点（原「循环节点」的位置，节点类型仍是 smart-loop）
 *
 * 老王 2026-10-22 定的四条功能：
 *  1. 提示词输入框（可加多段提示词）
 *  2. 图片生成引擎选择（与 smart-image 同一套数据源与视觉：API/火山/RH工作流/ComfyUI）
 *  3. 多张输入图片共用同一段提示词 → 每张图各出一个结果节点
 *  4. 一张输入图片配多段提示词 → 每段提示词各出一个结果节点
 *  5. 多参考图「主体 + 素材」拼装（老王 2026-10-27：参考图是一堆散件，逐个拼到同一主体上）
 * 输出数量 = 参与轮换的图片数 × 有效提示词数（老王拍板：两者相乘）。
 * 输入图片只能来自连线上游图片节点（不做无线引用、不自己上传）。
 * 指定某一张为「主体图」后：主体每次都带，其余图逐个轮换，
 * 输出 = 素材数 × 提示词数；没指定主体就是 3/4 那条旧语义。
 *
 * ⚠ 多参考图的适用面：直连引擎（API / 火山 / 通用 OpenAI 兼容平台 / RH 官方 img2img）
 * 的 reference_images 本就是数组，全链路按传入顺序 normalize 成「图片1 / 图片2」，
 * 主体恒排第 1 位，所以提示词里可以写「把图片2的部件装到图片1的主体上」。
 * ComfyUI / RH **工作流**分支能吃几张图取决于工作流自身有几个图像输入槽，本次未改。
 *
 * 节点数据：prompts（多段提示词）、runSettings（本节点自己的引擎设置）、
 * batchRunning / batchProgress（执行委托给官方 canvasAgentBatchRunNodes）。
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

    // ---------- 输入图角色：主体（固定）+ 素材（轮换）----------
    // 老王 2026-10-27：参考图是一堆散件，要逐个拼到同一个主体上、输出多张。
    // 模型：从连线上游里指定 **严格 1 张**「主体图」，其余为「素材图」；
    // 每次生成都带上主体 + 轮到的一张素材。没指定主体时完全退回原「全轮换」语义，
    // 老画布里没有 batchBaseRefKey 也不会有任何行为变化。
    // refKey 优先用 节点+图序号（重传图后仍对得上），没有 nodeId 才退回 url。
    function refKeyOf(img) {
        if (!img) return '';
        if (img.nodeId) return String(img.nodeId) + '#' + (img.imageIndex != null ? img.imageIndex : 0);
        return 'url:' + String(img.url || '');
    }
    function getBaseRefKey(node) { return String((node && node.batchBaseRefKey) || ''); }
    function setBaseRefKey(node, key) {
        if (!node) return;
        if (key) node.batchBaseRefKey = String(key);
        else delete node.batchBaseRefKey;
    }
    /** 当前生效的主体图（指定了但图已不在上游 → null，等于没指定）。 */
    function baseImageFor(node) {
        var key = getBaseRefKey(node);
        if (!key) return null;
        var hit = batchInputImages(node).filter(function (img) { return refKeyOf(img) === key; })[0];
        return hit || null;
    }
    /** 参与轮换的素材图。主体不存在 / 已失效 → 全部图照旧参与轮换（不静默变 0 张）。 */
    function varImagesFor(node) {
        var all = batchInputImages(node);
        var key = getBaseRefKey(node);
        if (!key) return all;
        var rest = all.filter(function (img) { return refKeyOf(img) !== key; });
        return rest.length ? rest : all;
    }
    /**
     * 点某一张输入图的完整语义：是当前主体 → 取消；否则 → 设为唯一主体。
     * 单独抽出来是为了 UI 和探针走同一份逻辑 —— 点击语义散在事件处理里就没法验收了。
     */
    function toggleBaseRef(node, key) {
        if (!node || !key) return false;
        setBaseRefKey(node, getBaseRefKey(node) === String(key) ? '' : key);
        return true;
    }
    /** 计划摘要：統一口径，bodyHtml / outputCount / runBatch 三处共用，不许各算各的。 */
    function batchPlanInfo(node) {
        var images = batchInputImages(node);
        var prompts = activePrompts(node).length;
        // 不足 2 张图时「主体制」不成立：没有素材可轮换，硬套会退化成「同一张图传两遍」
        if (images.length < 2) {
            return { images: images, base: null, vars: images, prompts: prompts, total: images.length * prompts, composable: false };
        }
        var base = getBaseRefKey(node) ? baseImageFor(node) : null;
        if (!base) return { images: images, base: null, vars: images, prompts: prompts, total: images.length * prompts, composable: true };
        var key = refKeyOf(base);
        var vars = images.filter(function (img) { return refKeyOf(img) !== key; });
        if (!vars.length) vars = images;   // 保险丝：理论上到不了（<2 已挡在前面）
        return { images: images, base: base, vars: vars, prompts: prompts, total: vars.length * prompts, composable: true };
    }
    function outputCount(node) {
        return batchPlanInfo(node).total;
    }

    // ---------- 引擎选项（与 smart-image 的统一选择器同源同 id 规则）----------

    /** 工作流类引擎 = 本地 ComfyUI + 云端 RunningHub（与 smart-canvas.js isWorkflowEngine 同口径）。
     *  比例/分辨率是 API 生图的规格，工作流的尺寸/参数由工作流自身字段决定，不在本节点摆。 */
    function isWorkflowEngineKey(engine) {
        var key = String(engine || '').toLowerCase();
        return key === 'comfy' || key === 'runninghub';
    }

    function engineItemId(s) {
        if (!s) return '';
        if (s.engine === 'runninghub' && s.rhConfigKey) return 'rh:' + s.rhConfigKey;
        if (s.engine === 'comfy' && s.comfyWorkflow) return 'comfy:' + s.comfyWorkflow;
        if ((s.engine === 'api' || s.engine === 'volcengine') && s.provider_id && s.model) return 'api:' + s.provider_id + ':' + s.model;
        return '';
    }
    /**
     * 引擎列表 = 直接复用图片/视频统一选择器的 buildGroups('image')。
     * 老王 2026-10-23 拍板：批量节点必须与图片生成同一数据源，否则 ComfyUI 动态列表、
     * 即梦模型过滤这些细节会各自漂移，工作流选不到也跑不通。
     * 这里只做「picker 条目形状 -> 本模块条目形状」的适配，不重新拼列表。
     */
    function buildEngineGroups() {
        var pickerGroups = [];
        try { pickerGroups = call('unifiedPickerGroups') || []; } catch (_) { pickerGroups = []; }
        var groups = [];
        pickerGroups.forEach(function (group) {
            var items = [];
            (group.items || []).forEach(function (item) {
                var apply = applyFromPickerItem(item);
                if (!apply) return;
                items.push({ id: item.id, label: item.display || item.title || item.id, apply: apply });
            });
            if (items.length) groups.push({ key: group.key, title: group.title, items: items });
        });
        return groups;
    }
    /**
     * 字段映射与 CanvasUnifiedPicker.select 同构（用 item 自带字段，不解析 id 前缀），
     * 保证写进 runSettings 的 engine / rhConfigKey / comfyWorkflow / provider_id / model
     * 与 composer 选出来的逐字一致，下游 runGeneration 才认。
     */
    function applyFromPickerItem(item) {
        if (!item || !item.id) return null;
        if (item.id.indexOf('rh:') === 0 && item.rhKey) {
            return { engine: 'runninghub', apiKind: 'image', rhConfigKey: item.rhKey };
        }
        if (item.id.indexOf('comfy:') === 0 && item.comfyWorkflow) {
            return { engine: 'comfy', apiKind: 'image', comfyMode: 'custom', comfyWorkflow: item.comfyWorkflow };
        }
        if (item.id.indexOf('api:') === 0 && item.apiProvider) {
            return {
                engine: item.apiProvider === 'volcengine' ? 'volcengine' : 'api',
                apiKind: 'image',
                provider_id: item.apiProvider,
                model: item.model
            };
        }
        return null;
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
    // ---------- 输入图缩略图网格 ----------
    // 2026-10-27 老王：「跟图片节点一样，放在节点最上方，不要多余的文字说明」。
    // 所以这里的结构完全照抄图片节点的多图网格（canvas-node-body-html.js:273-281 的
    // .ratio-thumb-grid + .thumb-item + thumbMediaHtml），一格也是等比缩放的原图，
    // 只有 class 换成 batch 前缀 —— **不能真用 .thumb-item 这个名字**：
    //   ① canvas-node-selection-controller 每次 syncSelectionUi 都遍历 .thumb-item/.image-wrap
    //      覆写 image-selected，主体标记会被它抹掉；
    //   ② canvas-image-node-interactions 会给 .thumb-item 绑 mousedown（选图/起裁剪），
    //      在批量节点里点了应该是「切换主体」而不是「选中这张图」。
    var REF_THUMB_MAX = 64;   // 单格最大边（与图片节点多图同密度；节点宽 420 一行排得下 5 张）
    var REF_GAP = 8;          // 与图片节点 .ratio-thumb-grid 的 gap 同值
    function refsGridCols(node, count) {
        var avail = Math.max(120, Number(node && node.w) || NODE_WIDTH) - 4;   // 扣去左右各 1px 描边
        return Math.max(1, Math.min(count || 1, Math.floor((avail + REF_GAP) / (REF_THUMB_MAX + REF_GAP))));
    }
    function refsRowHeight(node, images) {
        if (!images || !images.length) return 0;
        // 行高不能按 REF_THUMB_MAX 估：横图被等比压成 64×36，按 64 算每行会多留 28px 空白。
        // 直接用图片节点算多图网格总高的那个函数（同一套算法，不另写一份）。
        var bounds = call('aspectGroupGridBounds', images, REF_THUMB_MAX, refsGridCols(node, images.length), REF_GAP);
        return bounds && bounds.height ? Math.round(bounds.height) : images.length * REF_THUMB_MAX;
    }
    function inputRefThumbHtml(img, isBase, clickable) {
        var size = call('aspectGroupImageSize', img, REF_THUMB_MAX) || { width: REF_THUMB_MAX, height: REF_THUMB_MAX };
        // 媒体本体交给图片节点那套 helper 生成（含 video/file/audio 分支），别自己拼 <img>
        var media = '';
        try { media = call('thumbMediaHtml', img) || ''; } catch (_) { }
        if (!media) media = '<img src="' + esc(img.url) + '" alt="" draggable="false">';
        // 图上一律不放文字：可见标签会跟图片节点不一致。角色的唯一视觉信号是选中态描边，
        // 具体语义只留在 hover 的 title 里。
        var label = isBase ? tr('smart.batchRefBase', '主体') : tr('smart.batchRefPart', '素材');
        var title = !clickable
            ? tr('smart.batchRefNeedTwo', '至少两张输入图才能指定主体')
            : (isBase
                ? tr('smart.batchRefBaseHint', '主体图：每次生成都会带上它（在提示词里是「图片1」）；点击取消')
                : tr('smart.batchRefPartHint', '素材图：逐个轮换出图（在提示词里是「图片2」）；点击设为唯一主体'));
        return '<div class="batch-ref-thumb' + (isBase ? ' is-base' : '') + '"' +
            (clickable ? ' role="button" tabindex="0" data-batch-ref-toggle="' + esc(refKeyOf(img)) + '"' : '') +
            ' style="--thumb-w:' + Math.round(size.width) + 'px;--thumb-h:' + Math.round(size.height) + 'px"' +
            ' title="' + esc(title) + '" aria-label="' + esc(label) + '">' +
            media +
            '</div>';
    }
    function inputRefsGridHtml(node, plan) {
        if (!plan.images.length) return '';
        var baseKey = plan.base ? refKeyOf(plan.base) : '';
        return '<div class="batch-ref-grid">' +
            plan.images.map(function (img) {
                return inputRefThumbHtml(img, Boolean(baseKey) && refKeyOf(img) === baseKey, Boolean(plan.composable));
            }).join('') +
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
        // 注意 'wfparam:' 是 8 个字符（不是 7）—— 切错会留下前导冒号，
        // wfParamPickerHtml 认不出 'comfy:'/'rh:' 前缀直接返回空串（浮层打开却是空白）。
        if(kind.indexOf('wfparam:') === 0) return call('wfParamPickerHtmlForNode', kind.slice('wfparam:'.length), (node && node.runSettings) || {});
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
        var plan = batchPlanInfo(node);
        var images = plan.images;
        // 自愈（老王 2026-10-24：昨晚跑的节点到今天还在转）：
        // batchRunning 会随画布持久化，但页面一重载，跑批的那条 promise 就没了，
        // 没人执行 finally → 标志永远挂着。这里按「本轮是否真有在跑的节点」判定并复位。
        if (node.batchRunning) {
            var probe = batchLiveProgress(node);
            if (!probe || !probe.inflight) {
                node.batchRunning = false;
                node.batchStop = false;
                if (probe) node.batchProgress = { done: probe.done, total: probe.total, failed: probe.failed };
                call('scheduleSave');
            }
        }
        var engineKey = (node.runSettings && node.runSettings.engine) || '';
        var running = Boolean(node.batchRunning);
        // 运行中：官方批量器每完成一张都会 render，直接数本轮输出节点，不靠自维护计数器；
        // 结束后：用本轮上报的 batchProgress（不能拿历史输出反推，否则刷新后会串回上一轮的数字）
        var progress = running ? (batchLiveProgress(node) || node.batchProgress || null) : (node.batchProgress || null);
        var progressText = '';
        if (progress) {
            var pTotal = Math.max(0, Number(progress.total) || 0);
            var pDone = Math.max(0, Math.min(pTotal, Number(progress.done) || 0));
            var pFail = Math.max(0, Math.min(pTotal - pDone, Number(progress.failed) || 0));
            progressText = trf('smart.batchProgress', { done: pDone, total: pTotal }, '已出 {done}/{total}');
            if (pFail) progressText += trf('smart.batchFailedSuffix', { failed: pFail }, ' · 失败 {failed}');
        }
        // 工作流引擎：参数（含尺寸）由工作流自己的字段决定。
        // 老王 2026-10-25：批量节点不要底部面板 —— 参数平铺在它自己的卡片里（.batch-wf-params），
        // 由主文件选中本节点后填内容（字段要异步读盘，这里只出占位壳）。
        var planText = images.length
            ? (plan.base
                ? trf('smart.batchPlanCompose', { part: plan.vars.length, prompt: plan.prompts, total: plan.total },
                    '主体固定 × {part} 个素材 × {prompt} 段 = {total} 张')
                : trf('smart.batchPlan', { img: images.length, prompt: plan.prompts, total: plan.total },
                    '{img} 张图 × {prompt} 段提示词 = {total} 张'))
            : tr('smart.batchNoImage', '请把图片节点连到本节点输入口');
        return '<div class="batch-card">' +
            inputRefsGridHtml(node, plan) +
            '<div class="batch-prompt-list">' +
            prompts.map(function (value, index) { return promptFieldHtml(value, index, prompts.length); }).join('') +
            '</div>' +
            '<button class="batch-add-row" type="button" data-batch-prompt-add="1"><i data-lucide="plus"></i><span>' + esc(tr('smart.batchAddPrompt', '增加一段提示词')) + '</span></button>' +
            '<div class="batch-note-row"><span class="batch-note">' + esc(planText) + (progressText ? ' · ' + esc(progressText) : '') + '</span></div>' +
            // 老王 2026-10-25：工作流参数与引擎 pill 同排（footer 一行内，引擎给固定上限、
            // 参数区吃掉剩余宽度，排不下再隐藏溢出——卡片不许被撑高）
            '<div class="batch-footer">' + enginePickerHtml(node) +
            (isWorkflowEngineKey(engineKey) ? '' : specControlHtml(node, 'ratio') + specControlHtml(node, 'resolution')) +
            wfParamsBlock(node, engineKey) +
            '<button class="batch-run' + (running ? ' is-running' : '') + '" type="button" data-batch-run="' + esc(node.id) + '"' + (running ? ' disabled' : '') + '>' +
            '<i data-lucide="' + (running ? 'loader-2' : 'sparkles') + '"></i><span>' + esc(running ? tr('smart.batchRunning', '批量运行中') : tr('smart.batchRun', '批量生成')) + '</span>' +
            '</button></div>' +
            '</div>';   // ← 2026-10-27 修：原来这行前面是 `;`（return 提前结束），
                        //   `'</div>'` 成了孤儿表达式，.batch-card 的闭合标签从来没输出过
    }
    // 工作流参数区：**常驻**（2026-10-25 老王：「怎么还有隐藏机制？不点一下节点都看不到参数，
    // 图片节点是这样做的吗？」）——与图片节点的比例/分辨率 pill 同语义，bodyHtml 时就把
    // 参数 pill 一起渲染出来，不选中也看得见、点得动。字段要异步读盘的由主文件
    // batchWorkflowParamsHtmlForNode 内部兜底（先出空壳，拉到后局部重渲这张卡）。
    function wfParamsBlock(node, engineKey) {
        if (!isWorkflowEngineKey(engineKey)) return '';
        var html = '';
        try { html = call('batchWorkflowParamsHtmlForNode', node) || ''; } catch (_) { }
        return '<div class="batch-wf-params" data-batch-wf-params="' + esc(node.id) + '">' + html + '</div>';
    }
    // 参数区高度兜底阈值：并入 footer 后永远单行（30px），只有异常撑高才按它预留。
    var WF_PARAMS_MIN_H = 30;
    var wfParamsHeights = new WeakMap();
    function nodeSelector(node) {
        return '.image-node[data-id="' + String(node && node.id || '').replace(/["\\]/g, '\\$&') + '"]';
    }
    // 量出参数区真实高度 → 回写 node.h → 就地改卡片高度（不走全量 render，避免重建 DOM 把刚填的参数冲掉）。
    // 2026-10-25 三次改：参数区已并入 .batch-footer 与引擎同排，永远单行、高度被 30px 的 footer 锁死，
    // 不再预留独立行高。这里只做异常兜底：真被撑高（>34px）才回写 node.h；旧记录清 0 并缩回一次。
    function measureWfParams(node) {
        if (!node) return false;
        var host = document.querySelector(nodeSelector(node) + ' .batch-wf-params');
        if (!host) return false;
        var raw = Math.max(host.offsetHeight || 0, host.scrollHeight || 0);
        var h = raw > 34 ? Math.max(WF_PARAMS_MIN_H, Math.round(raw) + 6) : 0;
        if (wfParamsHeights.get(node) === h) return false;
        wfParamsHeights.set(node, h);
        fitNode(node);
        var card = host.closest('.image-node');
        if (card && node.h) card.style.height = Math.round(node.h) + 'px';
        return true;
    }

    // ---------- 尺寸 ----------

    var NODE_WIDTH = 420;
    // 常量档位（2026-10-26 校准：原值 60/30/16/30/26 是按老排版拍的，实测提示词段真实高 72、
    // 节点上下内边距合计 26、卡片 gap 8×3 —— 加总比真实排版少 30px 上下，底排会探出外框）。
    var PROMPT_ROW_H = 72;      // 单段提示词（.batch-prompt-text min-height 52 + 外框留白）
    var ADD_ROW_H = 30;         // 虚线「+ 增加一段提示词」排
    var NOTE_ROW_H = 15;        // 「N 张图 × N 段提示词」说明排
    var FOOTER_ROW_H = 30;      // 底排：引擎 / 比例 / 分辨率 / 工作流参数 / 生成按钮
    // REFS_ROW_H 已废（原写死一行 44px）：缩略图搬到最上方且改用真正的等比缩略图后，
    // 高度取决于图片数与节点宽度（会换行），改为 refsRowHeight() 动态算。
    var CARD_GAP = 8;           // .batch-card 的 gap
    // 竖向固定开销：.image-node 上下内边距 14+12=26，再加上下各 1px 描边 = 28
    // （量法：offsetHeight - clientHeight = 2 是描边，clientHeight - padding = 卡片高度）
    var NODE_PAD_V = 28;

    function bodyHeight(node) {
        var prompts = batchPrompts(node).length;
        var h = 0;
        h += prompts * PROMPT_ROW_H + Math.max(0, prompts - 1) * 7;   // 提示词列表自身 gap 7
        // 输入图缩略图网格在最上方（接了几张图就几格，会换行）——必须按真实等比尺寸算，
        // 否则卡片留白（估高偏大）或内容溢出节点（估高偏小，就是 2026-10-26 那次事故）。
        var refs = batchInputImages(node);
        if (refs.length) h += refsRowHeight(node, refs) + CARD_GAP;
        h += CARD_GAP + ADD_ROW_H;
        h += CARD_GAP + NOTE_ROW_H;
        h += CARD_GAP + FOOTER_ROW_H;
        h += NODE_PAD_V;
        if (node && node.batchProgress) h += 4;
        return Math.round(h);
    }
    function fitNode(node) {
        if (!node) return;
        node.w = NODE_WIDTH;
        node.h = bodyHeight(node);
    }

    // ---- 卡片高度自动贴合（2026-10-26 老王：「批量节点的选择按钮跑出外框」）----
    // 病根：node.h 是常量加总，跟真实排版对不上；而 .batch-card 是 height:100% + overflow:visible，
    // 于是卡片里最后那一排会有一截画到节点外框外面去；老王只能手动把节点拖大才框得住，
    // 而下次批量交互走 fitNode 又被打回原样（等于白拖）。
    // 正解：DOM 建完以后按真实排版量一次，把差值补回 node.h。只增不减——
    // 减的话会跟老王的手动拉伸打架，且内容变矮时下一轮 fitNode 会自然缩回。
    var batchFitRunning = false;
    function batchCardNaturalHeight(nodeEl, card) {
        if (!nodeEl || !card) return 0;
        var prevCardH = card.style.height;
        var prevNodeH = nodeEl.style.height;
        // 两个都放开：只放卡片的话，卡片仍被父盒（node.h）锁着量不出真实值
        card.style.height = 'auto';
        nodeEl.style.height = 'auto';
        var natural = Math.round(Math.max(card.offsetHeight || 0, card.scrollHeight || 0));
        card.style.height = prevCardH;
        nodeEl.style.height = prevNodeH;
        return natural;
    }
    /** 量所有批量节点的真实内容高度，必要时回写 node.h。返回是否有变化。 */
    function autoFitBatchNodeHeights(options) {
        if (batchFitRunning) return false;
        var list = D('nodes') || [];
        if (!list.length) return false;
        if (!document.querySelector('.batch-card')) return false;
        batchFitRunning = true;
        var changed = false;
        try {
            var maxPasses = (options && options.maxPasses) || 3;
            for (var pass = 0; pass < maxPasses; pass++) {
                var moved = false;
                list.forEach(function (node) {
                    if (!node || node.type !== 'smart-loop') return;
                    var el = document.querySelector(nodeSelector(node));
                    var card = el && el.querySelector('.batch-card');
                    if (!el || !card) return;
                    var current = Math.round(card.offsetHeight || 0);
                    var natural = batchCardNaturalHeight(el, card);
                    if (natural <= 0) return;
                    var delta = natural - current;
                    if (Math.abs(delta) < 1) return;              // 已经贴合
                    var base = Math.round(Number(node.h) || 0);
                    var next = Math.max(96, base + delta);  // 只增不减
                    if (next === base) return;
                    node.h = next;
                    el.style.height = next + 'px';
                    moved = true;
                    changed = true;
                });
                if (!moved) break;
            }
        } finally {
            batchFitRunning = false;
        }
        if (changed) {
            try { call('refreshConnectionLayer'); } catch (_) { }
            try { call('scheduleSave'); } catch (_) { }
            scheduleBatchNodeHeightFit();   // 下一帧再量一次（首帧字体未落地会量矮）
        }
        return changed;
    }
    var batchFitPending = false;
    function scheduleBatchNodeHeightFit() {
        if (batchFitPending) return;
        batchFitPending = true;
        requestAnimationFrame(function () {
            batchFitPending = false;
            if (global.CanvasBatchGenerate && typeof CanvasBatchGenerate.autoFitBatchNodeHeights === 'function') {
                CanvasBatchGenerate.autoFitBatchNodeHeights();
            }
        });
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
                        // 与 composer 共用同一份「最近用过」，两边选择互相可见
                        try { call('unifiedPickerRemember', id); } catch (_) { }
                        call('rememberRecentSmartSettings', target.runSettings, target);
                        // 换引擎顺手选中本节点：卡片里的参数区只在选中时可编辑（settings 归属跟着节点走），
                        // 否则选完工作流还是一片「选中后调参数」，看着像没生效。
                        call('selectNode', target.id);
                    }
                } else if (specOpt) {
                    event.preventDefault();
                    event.stopPropagation();
                    var patch = {};
                    patch[kind === 'resolution' ? 'resolution' : 'ratio'] = specOpt.getAttribute('data-batch-spec-item');
                    target.runSettings = Object.assign({}, target.runSettings || {}, patch);
                    call('rememberRecentSmartSettings', target.runSettings, target);
                } else {
                    var wfOpt = event.target.closest && event.target.closest('[data-batch-wfparam-item]');
                    if(!wfOpt) return;
                    event.preventDefault();
                    event.stopPropagation();
                    // 工作流参数：按这张卡自己的节点写（常驻参数不依赖选中，与 specOpt 同语义）
                    call('applyWorkflowParamValueForNode', target, wfOpt.getAttribute('data-batch-wfparam-item'), wfOpt.getAttribute('data-batch-wfparam-value'));
                }
                closePicker();
                render(target);
            });
            document.addEventListener('click', function (event) {
                if (!floatEl || !floatEl.classList.contains('open')) return;
                if (event.target.closest && event.target.closest('.batch-engine-float')) return;
                if (event.target.closest && event.target.closest('[data-batch-engine-toggle],[data-batch-spec-toggle]')) return;
                if (event.target.closest && event.target.closest('[data-batch-wfparam-toggle]')) return;
                closePicker();
            });
            window.addEventListener('resize', closePicker);
            // 参数 pill 的浮层开关（文档级兜底；正常路径是 bindWfParamsHost 里逐节点绑的
            // onclick —— 那条会 stopPropagation，所以这里不会双触发）
            document.addEventListener('click', function (event) {
                var toggle = event.target.closest && event.target.closest('[data-batch-wfparam-toggle]');
                if(!toggle) return;
                var card = toggle.closest('.image-node');
                var owner = card ? nodeById(card.getAttribute('data-id') || '') : null;
                if(!owner) return;
                event.preventDefault();
                event.stopPropagation();
                openPicker(owner, toggle, 'wfparam:' + (toggle.getAttribute('data-batch-wfparam-toggle') || ''));
            });
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
        var width = kind === 'engine' ? Math.min(300, window.innerWidth - 24)
            : (kind.indexOf('wfparam:') === 0 ? Math.min(220, window.innerWidth - 24)
                : Math.min(180, window.innerWidth - 24));
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
        var holder = anchor.closest('.batch-engine-control') || anchor.closest('.batch-spec-control') || anchor.closest('.wf-param-control');
        if (holder) holder.classList.add('pinned');
    }

    function bind(el, node) {
        if (!el || !node) return;
        el.querySelectorAll('.batch-prompt-text, .batch-prompt-del, .batch-add-row, .batch-run, .batch-engine-control, .batch-spec-control, .batch-ref-thumb').forEach(function (control) {
            ['mousedown', 'pointerdown', 'click', 'dblclick'].forEach(function (type) {
                control.addEventListener(type, function (event) { event.stopPropagation(); });
            });
        });
        // 输入图角色切换（2026-10-27）：严格 1 张主体 —— 点素材图把它顶上来，
        // 点当前主体图则取消，全员退回轮换。禁用的（不足两张图）不响应。
        el.querySelectorAll('[data-batch-ref-toggle]').forEach(function (thumb) {
            var toggle = function (event) {
                event.preventDefault();
                event.stopPropagation();
                var key = thumb.getAttribute('data-batch-ref-toggle') || '';
                if (!key) return;
                toggleBaseRef(node, key);
                render(node);
            };
            thumb.onclick = toggle;
            // 既然标了 role="button" + tabindex，就得能用键盘触发
            thumb.onkeydown = function (event) {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                toggle(event);
            };
        });
        // 参数区常驻（2026-10-25）：bodyHtml 首次渲染就把 pill 带出来了，这里补一次逐节点绑定
        // （幂等——onclick 赋值形式，重复调用不累积；异步填内容的 renderBatchNodeParams 也会再调）
        var wfHost = el.querySelector('.batch-wf-params');
        if (wfHost) bindWfParamsHost(wfHost, node);
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
        // 运行（执行中按钮置灰；要停某一张，去点那张输出节点自己的取消）
        el.querySelectorAll('[data-batch-run]').forEach(function (btn) {
            btn.onclick = function (event) {
                event.preventDefault();
                event.stopPropagation();
                syncFromDom();
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
    /**
     * refs = 本轮参与的全部参考图，**顺序即语义**：主体（若有）恒排第 1 位，素材排其后。
     * 后端 _agent_normalize_reference_items 会按传入顺序把 reference_images 编号成
     * 「图片1 / 图片2…」，所以「主体=图片1、素材=图片2」是靠这个顺序撑住的 —— 别乱排。
     */
    function createOutputNode(node, refs, prompt, index, total, baseKey) {
        var list = (refs || []).filter(function (img) { return img && img.url; });
        var pos = outputPosition(node, index);
        var target = call('createImageNodeAt',
            { x: pos.x + 130, y: pos.y + 130 },
            [],
            { select: false, skipUndo: true }
        );
        if (!target) return null;
        target.title = trf('smart.batchOutputTitle', { n: index + 1 }, '批量 {n}');
        target.runSettings = JSON.parse(JSON.stringify(node.runSettings || {}));
        // 官方批量执行器（canvasAgentBatchRunNodes）逐节点读这两个字段走 API 并行分支；
        // 与 Agent「执行」按钮同一条链路，缺任一个都会被当成「无自身提示词」回退。
        target.runPrompt = prompt || '';
        target.runPromptRefs = list.map(function (img) {
            var isBase = Boolean(baseKey) && refKeyOf(img) === baseKey;
            return {
                url: img.url,
                // 语义名：给前端 composer / 历史面板看；真正送进模型的是后端编号的「图片N」
                name: isBase ? tr('smart.refNameBase', '主体图')
                    : (list.length > 1 ? tr('smart.refNamePart', '素材图') : (img.name || ('图' + (index + 1)))),
                nodeId: img.nodeId || '',
                imageIndex: img.imageIndex != null ? img.imageIndex : '',
                kind: 'image'
            };
        });
        // ComfyUI / RunningHub 分支是逐个 patchSelection → runGeneration()，
        // 而那条链路的提示词取自 composer（选中节点时按 promptDraftText 回填）、
        // 参考图取自本节点的直接上游 —— 所以这两个也必须写，否则工作流会拿到空提示/空参考图。
        target.promptDraftText = prompt || '';
        target.promptDraftHtml = '';
        target.batchSourceId = node.id;
        target.batchRunId = node.batchRunId || '';
        target.batchIndex = index;
        target.batchTotal = total;
        target.pending = 1;
        target.running = true;
        target.runStartedAt = call('nowMs');
        delete target.w;
        delete target.h;
        call('addConnection', node.id, target.id, 'flow');
        // 本轮参与的全部参考图源节点都要直连过来：ComfyUI / RH 工作流分支取参考图
        // 只认**直接上游**（runGeneration 不走 runPromptRefs），少连一条就少一张图。
        var seen = {};
        seen[target.id] = 1;
        list.forEach(function (img) {
            var srcId = img && img.nodeId;
            if (!srcId || seen[srcId]) return;
            seen[srcId] = 1;
            var srcNode = (call('nodes') || []).find(function (n) { return n && n.id === srcId; });
            if (srcNode) call('addConnection', srcId, target.id, 'flow');
        });
        return target;
    }

    /**
     * 本轮要跑的全部 job = 素材图（逐个轮换）× 提示词（每段都跑）。
     * 抽成独立函数是为了能被探针直接调用验收 —— jobs 顺序一错，整个多图语义就崩了，
     * 不能只靠肉眼 review。job.refs 已排好「主体在前、素材在后」，
     * 这个顺序会被后端 normalize 成「图片1 / 图片2」，是提示词里称呼它们的唯一依据。
     */
    function batchJobs(node) {
        var plan = batchPlanInfo(node);
        var prompts = activePrompts(node);
        var jobs = [];
        plan.vars.forEach(function (image) {
            var refs = plan.base ? [plan.base, image] : [image];
            prompts.forEach(function (prompt) { jobs.push({ refs: refs, prompt: prompt }); });
        });
        return jobs;
    }

    async function runBatch(node) {
        var plan = batchPlanInfo(node);
        var prompts = activePrompts(node);
        if (!plan.images.length) { call('toast', tr('smart.batchNoImage', '请把图片节点连到本节点输入口')); return; }
        if (!prompts.length) { call('toast', tr('smart.batchNoPrompt', '请至少写一段提示词')); return; }
        if (!node.runSettings || !node.runSettings.engine) { call('toast', tr('smart.batchNoEngine', '请先选择生成引擎')); return; }

        var jobs = batchJobs(node);
        var baseKey = plan.base ? refKeyOf(plan.base) : '';

        call('pushUndo');
        // 轮次号：同一个批量节点跑第二次时，进度只数本轮输出，不要把两批叠在一起
        node.batchRunId = call('nowMs') + ':' + Math.random().toString(36).slice(2, 7);
        var targets = [];
        for (var i = 0; i < jobs.length; i++) {
            var target = createOutputNode(node, jobs[i].refs, jobs[i].prompt, i, jobs.length, baseKey);
            if (target) targets.push(target);
        }
        if (!targets.length) return;

        node.batchRunning = true;
        node.batchProgress = { done: 0, total: targets.length };
        render(node);

        try {
            // 执行完全交给官方批量器：API 类引擎并行提交、ComfyUI/RunningHub 逐节点走
            // runGeneration（这两个引擎的提交依赖 composer 状态，必须借道，否则工作流必挂）。
            // 日志、排队、断线重连、失败复位、完成 toast 都由那条链路负责，这里不再自己拼。
            var result = await call('batchRunNodes', targets);
            result = result || {};
            // 上报值不能盲信：夹到本轮目标数内，避免出现「已出 3/2」「失败 -1」这种脏数据
            // 上报值不能盲信：夹到本轮目标数内，避免出现「已出 3/2」「失败 -1」这种脏数据
            var doneCount = Math.max(0, Math.min(targets.length, Number(result.ok) || 0));
            var failCount = Math.max(0, Math.min(targets.length - doneCount, Number(result.failed) || 0));
            // 本轮实际出了几张图比上报值更可信，取两者较大（仍不超过本轮目标数）
            var live = batchLiveProgress(node);
            if (live) doneCount = Math.min(targets.length, Math.max(doneCount, live.done || 0));
            node.batchProgress = { done: doneCount, total: targets.length, failed: failCount };
        } catch (error) {
            node.batchProgress = { done: 0, total: targets.length, failed: targets.length };
            call('toast', ((error && error.message) || String(error)).slice(0, 160));
        } finally {
            node.batchRunning = false;
            call('scheduleSave');
            render(node);
        }
    }

    /**
     * 运行中进度实时回显：官方批量器每完成一个节点都会 render，
     * 这里直接按「本节点的输出里已有结果图的个数」数，不自己维护计数器。
     */
    function batchRoundNodes(node) {
        var all = call('nodes') || [];
        var runId = node.batchRunId || '';
        // 旧数据（加轮次号之前建的输出）没有 batchRunId：只认「无轮次号」的那批，不跨轮累加
        return all.filter(function (n) {
            if (!n || n.batchSourceId !== node.id) return false;
            return runId ? n.batchRunId === runId : !n.batchRunId;
        });
    }
    function batchHasInflight(list) {
        return (list || []).some(function (n) {
            return Boolean(n && (n.pending > 0 || n.running || n.apiRunning || n.jimengPending ||
                n.comfyStatus === 'running' || n.comfyStatus === 'queued' || n.comfyStatus === 'starting' ||
                (Array.isArray(n.pendingTasks) && n.pendingTasks.length)));
        });
    }
    function batchLiveProgress(node) {
        var mine = batchRoundNodes(node);
        if (!mine.length) return null;
        var done = mine.filter(function (n) {
            return (n.images || []).some(function (img) { return img && img.generatedResult && img.url; });
        }).length;
        var failed = mine.filter(function (n) { return Boolean(n.runError); }).length;
        var inflight = batchHasInflight(mine);
        return { done: done, total: mine.length, failed: failed, inflight: inflight };
    }


    // 参数 pill 控件的事件吞没：卡片在画布事件链上，点参数不能顺带拖动节点。
    // 参数区内容是选中节点后异步填进来的，所以由主文件每次填完调用一次。
    /* 参数 pill 的交互绑定（2026-10-25 参数常驻后，每张卡的 pill 都要能点）。
       与引擎/比例 pill 完全同款：**逐节点绑 onclick**（document 级委托会被上面
       mousedown/pointerdown 的 stopPropagation 挡死——stopPropagation 不阻止同元素
       其他监听器，但会阻止冒泡到 document，所以委托方案在这套卡片里天生残疾）。
       mousedown/pointerdown/dblclick 仍就地吞掉：防在卡片上点参数变成拖动节点。 */
    function bindWfParamsHost(host, node) {
        if (!host || !node) return;
        host.querySelectorAll('.wf-param-control').forEach(function (control) {
            ['mousedown', 'pointerdown', 'dblclick'].forEach(function (type) {
                control.addEventListener(type, function (event) { event.stopPropagation(); });
            });
            var pickBtn = control.querySelector('[data-batch-wfparam-toggle]');
            if (pickBtn) {
                pickBtn.onclick = function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    openPicker(node, pickBtn, 'wfparam:' + (pickBtn.getAttribute('data-batch-wfparam-toggle') || ''));
                };
            }
            var boolBtn = control.querySelector('[data-comfy-bool],[data-rh-bool]');
            if (boolBtn) {
                boolBtn.onclick = function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    var isComfy = boolBtn.hasAttribute('data-comfy-bool');
                    var uid = boolBtn.getAttribute(isComfy ? 'data-comfy-bool' : 'data-rh-bool') || '';
                    call('toggleWorkflowParamBoolForNode', node, (isComfy ? 'comfy:' : 'rh:') + uid);
                };
            }
            var input = control.querySelector('.wf-param-input');
            if (input) {
                var paramKey = function () { return control.getAttribute('data-wf-param-control') || ''; };
                // input 只写值不重绘（重绘会把用户正在打字的焦点冲掉），change/blur 时才刷新显示
                input.oninput = function () {
                    var pk = paramKey();
                    if (pk) call('applyWorkflowParamValueForNode', node, pk, input.value, {silent:true});
                };
                input.onchange = function () {
                    var pk = paramKey();
                    if (pk) call('applyWorkflowParamValueForNode', node, pk, input.value);
                };
                input.onclick = function (event) { event.stopPropagation(); };
            }
        });
    }

    global.CanvasBatchGenerate = {
        configure: configure,
        bodyHtml: bodyHtml,
        bind: bind,
        bindWfParamsHost: bindWfParamsHost,
        fitNode: fitNode,
        bodyHeight: bodyHeight,
        measureWfParams: measureWfParams,
        autoFitBatchNodeHeights: autoFitBatchNodeHeights,
        scheduleBatchNodeHeightFit: scheduleBatchNodeHeightFit,
        NODE_WIDTH: NODE_WIDTH,
        batchPrompts: batchPrompts,
        setBatchPrompts: setBatchPrompts,
        batchInputImages: batchInputImages,
        batchPlanInfo: batchPlanInfo,
        batchJobs: batchJobs,
        refKeyOf: refKeyOf,
        getBaseRefKey: getBaseRefKey,
        setBaseRefKey: setBaseRefKey,
        toggleBaseRef: toggleBaseRef,
        baseImageFor: baseImageFor,
        outputCount: outputCount,
        runBatch: runBatch,
        buildEngineGroups: buildEngineGroups,
        openPicker: openPicker,
        closePicker: closePicker
    };
})(typeof window !== 'undefined' ? window : globalThis);
