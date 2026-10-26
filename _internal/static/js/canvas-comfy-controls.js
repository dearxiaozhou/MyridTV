/* MyridTV 画布 ComfyUI 控件渲染层（拆模块 ⑥）
 *
 * 9 个「工作流数据 → HTML 字符串」纯渲染函数 + 字段旁路判定：
 * 工作流选择 pill、节点模式开关、参数入口、字段分组(数字并排/媒体跳过)、放大 pill、
 * details 壳、引擎短标签。无 DOM 写入（renderComfyParams 的 dynamicParams.innerHTML
 * 编排与全部事件绑定仍在主文件）；settings/engineSelect/comfyWorkflows 所有权在主文件
 * 经 getter 注入（settings/comfyWorkflows 存在整体重赋值，绝不缓存引用）；
 * comfyWorkflowCache 直连 CanvasComfyJobEngine 单例。
 */
(function (global) {
    'use strict';

    var deps = {
        escapeHtml: null,
        tr: null,
        renderComfyInputsRow: null,
        renderComfySettingField: null,
        comfyFieldKind: null,
        visibleComfyFields: null,
        comfyParamValue: null,
        smartComfyRandomActive: null,
        comfyModesForWorkflow: null,
        resolveComfyWorkflowName: null,
        getSettings: null,
        getEngineSelect: null,
        getWorkflows: null
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

function renderComfyDetailsHtml(wf, fields){
    // 2026-09-25 老王：自动裁剪已接管输入接线，「素材：接收…」计数行删除（仅留无工作流提示）
    if (deps.getSettings().comfyWorkflow) return '';
    return `<div class="cfn-details"><div class="muted-note">${deps.escapeHtml(deps.tr('smart.noWorkflow'))}</div></div>`;
}
function renderComfyParamsControl(wf, fields){
    const visibleFields = deps.visibleComfyFields(fields || [], deps.getSettings().comfyWorkflow);
    const editableFields = visibleFields.filter(field => {
        const kind = deps.comfyFieldKind(field);
        return kind !== 'prompt' && kind !== 'image' && kind !== 'video' && kind !== 'audio';
    });
    if(!editableFields.length) return '';
    const title = deps.tr('smart.workflowParams') || '工作流参数';
    const pillLabel = deps.tr('smart.paramsPill') || '参数调整';
    return `<div class="smart-control comfy-params-control">
        <button class="smart-pill" type="button" title="${deps.escapeHtml(title)}"><i data-lucide="sliders-horizontal"></i><span class="sub">${deps.escapeHtml(pillLabel)} ${editableFields.length}</span></button>
        <div class="smart-popover compact-popover comfy-params-popover">
            <div class="smart-popover-title">${deps.escapeHtml(title)}</div>
            <div class="cfn-params-body">${renderComfyFields(visibleFields)}</div>
        </div>
    </div>`;
}
// 2026-10-24 老王：批量节点底部面板不要弹层——参数直接平铺（同一套字段渲染，去掉 pill+弹层）。
function renderComfyParamsInline(wf, fields){
    const visibleFields = deps.visibleComfyFields(fields || [], deps.getSettings().comfyWorkflow);
    const editableFields = visibleFields.filter(field => {
        const kind = deps.comfyFieldKind(field);
        return kind !== 'prompt' && kind !== 'image' && kind !== 'video' && kind !== 'audio';
    });
    if(!editableFields.length) return '';
    return `<div class="batch-inline-params comfy-inline-params">${renderComfyFields(visibleFields)}</div>`;
}
/* 2026-10-25 老王：删掉「连续数字合并成一行 .cfn-size-row」的特例 —— RH 面板没有这一步，
 * 每个参数各占一格交给外层两列网格排。合并出来的 .cfn-size-cell 是另一套行高(36px)/
 * 圆角(8px)/底色(var(--soft))，正是「同一个面板里有的大有的小、有的圆有的方」的来源。
 * prompt/image/video/audio 四种字段不进参数区（提示词复用画布大输入框，素材走自动裁剪）。 */
/* 2026-10-25 老王：批量节点卡片里那一排参数。与 renderComfyParamsInline 用同一批字段、
 * 同一个取值/写值通道，只是外壳换成「短标签 + 下拉 pill」：一行排开，卡片不再被撑成三行高。 */
function renderComfyParamsPillInline(wf, fields, sourceSettings){
    // sourceSettings：批量节点参数常驻在卡片上（2026-10-25 老王：图片节点的比例 pill 就是不选中也能看），
    // 取值/关节点判定都要按卡片所属节点的 runSettings，不读全局 settings。
    const src = sourceSettings || deps.getSettings();
    const visibleFields = deps.visibleComfyFields(fields || [], src.comfyWorkflow);
    const pills = visibleFields.map(field => renderComfyParamPill(field, src)).filter(Boolean);
    if(!pills.length) return '';
    return `<div class="batch-inline-params comfy-inline-params wf-pill-row">${pills.join('')}</div>`;
}
function renderComfyParamPill(field, sourceSettings){
    if(!field) return '';
    const src = sourceSettings || deps.getSettings();
    const kind = deps.comfyFieldKind(field);
    if(['prompt', 'image', 'video', 'audio'].includes(kind)) return '';
    const labelText = field.name || field.input || field.id;
    const value = deps.comfyParamValue(field, src);
    const uid = String(field.id || '');
    const paramKey = `comfy:${uid}`;
    const attrs = ` data-comfy-param="${deps.escapeHtml(uid)}"`;
    // 选项一律走 engine.wfParamOptionsFor：与浮层同源（浮层也调它），
    // 不会再出现「pill 能点、点开显示无选项」的错位。
    const options = global.CanvasDynamicParamEngine.wfParamOptionsFor(field, value);
    if(field.type === 'boolean'){
        return global.CanvasDynamicParamEngine.wfParamTogglePillHtml({
            label:labelText, on:!!value, boolAttr:'comfy-bool', boolKey:uid
        });
    }
    if(field.type === 'dropdown' && Array.isArray(options) && options.length){
        return global.CanvasDynamicParamEngine.wfParamPillHtml({
            label:labelText, value:value ?? '', attrs:attrs, options, paramKey, hideKey:true
        });
    }
    if(field.type === 'slider' || field.type === 'number'){
        return global.CanvasDynamicParamEngine.wfParamPillHtml({
            label:labelText, value:value ?? 0, attrs:attrs, options:options, numeric:true, paramKey, hideKey:false,
            // 档位拉不出来（种子那种）才退回数字输入
            inputType:options ? 'text' : 'number'
        });
    }
    if(field.type === 'textarea') return '';   // 长文本不进 pill 排
    // 文本：命中官方比例枚举的走下拉（值本身可读，同图片节点的比例 pill，不带标签）；
    // 其余自由文本用户自己填的内容也可读 —— 只有「光秃秃一个数字」才必须带短标签（老王 10/25：「你看这个 2 我知道它是什么东西吗」）
    return global.CanvasDynamicParamEngine.wfParamPillHtml({
        label:labelText, value:value ?? '', attrs:attrs, options:options, paramKey, inputType:'text', hideKey:true
    });
}
function renderComfyFields(fields){
    return (fields || []).filter(field => {
        const kind = deps.comfyFieldKind(field);
        return kind !== 'prompt' && kind !== 'image' && kind !== 'video' && kind !== 'audio';
    }).map(field => deps.renderComfySettingField(field)).join('');
}
function renderUpscalePill(paramKey, current){
    const opts = [2048, 4096];
    const labels = {2048:'2X / 2048', 4096:'4X / 4096'};
    return `<div class="smart-control upscale-control">
        <button class="smart-pill" type="button"><i data-lucide="maximize-2"></i><span>${deps.escapeHtml(labels[current] || `${current}px`)}</span></button>
        <div class="smart-popover compact-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.upscaleTarget'))}</div>
            <div class="model-list">
                ${opts.map(v => `<button type="button" class="direct-option ${v === current ? 'active' : ''}" data-smart-param="${deps.escapeHtml(paramKey)}" data-smart-value="${v}"><span>${deps.escapeHtml(labels[v])}</span></button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderComfyNodeModesControl(wf){
    const workflowName = deps.getSettings().comfyWorkflow;
    const workflow = wf?.workflow;
    if(!workflowName || !workflow || !Object.keys(workflow).length) return '';
    const exposedNodes = [...new Set((wf?.config?.fields || []).map(f => String(f?.node || '')).filter(Boolean))];
    if(!exposedNodes.length) return '';
    const modes = deps.comfyModesForWorkflow(workflowName);
    const fieldNames = {};
    (wf?.config?.fields || []).forEach(f => {
        const nid = String(f?.node || '');
        const nm = String(f?.name || '').trim();
        if(nid && nm && !fieldNames[nid]) fieldNames[nid] = nm;
    });
    const rows = exposedNodes.map(id => {
        const node = workflow[id] || {};
        const title = String(fieldNames[id] || node?._meta?.title || node?.class_type || id).slice(0, 40);
        const off = modes[id] === 'bypass' || modes[id] === 'mute';
        return `<div class="cfm-row ${off ? 'cfm-row-off' : ''}">
            <span class="cfm-name" title="${deps.escapeHtml(title)}">${deps.escapeHtml(title)}</span>
            <button type="button" class="cfm-toggle ${off ? '' : 'on'}" data-comfy-node-mode="${deps.escapeHtml(id)}" title="${deps.escapeHtml(off ? (deps.tr('smart.comfyNodeOff') || '关 = 跳过，点击恢复执行') : (deps.tr('smart.comfyNodeOn') || '开 = 使用，点击跳过该节点'))}">${off ? (deps.tr('smart.comfyOff') || '关') : (deps.tr('smart.comfyOn') || '开')}</button>
        </div>`;
    }).join('');
    return `<div class="smart-control comfy-nodes-control">
        <button class="smart-pill" type="button"><i data-lucide="toggle-left"></i><span class="sub">${deps.escapeHtml(deps.tr('smart.nodesPill') || '节点开关')}</span></button>
        <div class="smart-popover compact-popover comfy-nodes-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.comfyExposedNodes') || '已暴露节点')} · ${deps.escapeHtml((deps.getWorkflows().find(w => w.name === workflowName)?.title || workflowName.replace(/\.json$/,'')).slice(0, 24))}</div>
            <div class="cfm-list">${rows}</div>
            <div class="cfm-hint">${deps.escapeHtml(deps.tr('smart.comfyToggleHint') || '开 = 使用 · 关 = 跳过（Ctrl+B 旁路，下游自动接上游）')}</div>
        </div>
    </div>`;
}
function comfyFieldNodeIsOff(field, workflowName=deps.getSettings().comfyWorkflow){
    const nodeId = String(field?.node || '');
    if(!nodeId) return false;
    const mode = deps.comfyModesForWorkflow(workflowName)[nodeId];
    return mode === 'bypass' || mode === 'mute';
}

    global.CanvasComfyControls = {
        configure: configure,
        renderComfyDetailsHtml: renderComfyDetailsHtml,
        renderComfyParamsControl: renderComfyParamsControl,
        renderComfyParamsInline: renderComfyParamsInline,
        renderComfyParamsPillInline: renderComfyParamsPillInline,
        renderComfyFields: renderComfyFields,
        renderUpscalePill: renderUpscalePill,
        renderComfyNodeModesControl: renderComfyNodeModesControl,
        comfyFieldNodeIsOff: comfyFieldNodeIsOff
    };
})(typeof window !== 'undefined' ? window : globalThis);
