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
function renderComfyFields(fields){
    const out = [];
    let pendingNumbers = [];
    const flushNumbers = () => {
        if(!pendingNumbers.length) return;
        if(pendingNumbers.length === 1) out.push(deps.renderComfySettingField(pendingNumbers[0]));
        else out.push(`<div class="cfn-size-row">${pendingNumbers.map(renderComfyNumberCell).join('')}</div>`);
        pendingNumbers = [];
    };
    fields.forEach(field => {
        const kind = deps.comfyFieldKind(field);
        // prompt 字段直接复用画布顶部原生 #promptInput，不在参数区重复渲染。
        if(kind === 'prompt'){ flushNumbers(); return; }
        if(kind === 'image' || kind === 'video' || kind === 'audio'){ flushNumbers(); return; }
        if(field.type === 'number'){ pendingNumbers.push(field); return; }
        flushNumbers();
        out.push(deps.renderComfySettingField(field));
    });
    flushNumbers();
    return out.join('');
}
function renderComfyNumberCell(field){
    const value = deps.comfyParamValue(field);
    const min = field.min !== undefined ? ` min="${deps.escapeHtml(field.min)}"` : '';
    const max = field.max !== undefined ? ` max="${deps.escapeHtml(field.max)}"` : '';
    const step = field.step !== undefined ? ` step="${deps.escapeHtml(field.step)}"` : '';
    const dice = field.random_enabled === true
        ? `<button type="button" class="random-btn ${deps.smartComfyRandomActive(field.id) ? 'active' : ''}" data-comfy-random="${deps.escapeHtml(field.id)}" title="${deps.escapeHtml(deps.smartComfyRandomActive(field.id) ? deps.tr('smart.diceOn') : deps.tr('smart.diceOff'))}"><i data-lucide="dice-5"></i></button>`
        : '';
    const labelText = field.name || field.input || field.id;
    return `<div class="cfn-size-cell">
        <div class="cfn-size-label">${deps.escapeHtml(labelText)}</div>
        <div class="cfn-size-inputs">
            <input class="cfn-size-input" type="number" data-comfy-param="${deps.escapeHtml(field.id)}" value="${deps.escapeHtml(value ?? 0)}"${min}${max}${step}>${dice}
        </div>
    </div>`;
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
        renderComfyFields: renderComfyFields,
        renderComfyNumberCell: renderComfyNumberCell,
        renderUpscalePill: renderUpscalePill,
        renderComfyNodeModesControl: renderComfyNodeModesControl,
        comfyFieldNodeIsOff: comfyFieldNodeIsOff
    };
})(typeof window !== 'undefined' ? window : globalThis);
