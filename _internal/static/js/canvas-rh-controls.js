/* MyridTV 画布 RunningHub 控件渲染层（拆模块 ⑤）
 *
 * 18 个「数据 → HTML 字符串 / key 解析」纯函数：工作流选择 pill、节点开关列表、
 * 参数入口、资源(密钥/机器)选择、配置弹层、RH entry key 解析与节点关闭判定。
 * 无 DOM 写入（composer innerHTML 与 sync 系列/事件绑定仍在主文件）；
 * settings/engineSelect 所有权在主文件（getter 注入），
 * 深依赖（renderRhInputsRow/renderRhSettingField/rhWorkflowNodeList/rhFieldRole）经函数注入。
 */
(function (global) {
    'use strict';

    var deps = {
        escapeHtml: null,
        tr: null,
        runningHubEntries: null,
        selectedRunningHubRef: null,
        rhNodeOffBucket: null,
        renderRhInputsRow: null,
        rhFieldRole: null,
        renderRhSettingField: null,
        rhWorkflowNodeList: null,
        getSettings: null,
        getEngineSelect: null
    };
    function configure(opts) {
        Object.assign(deps, opts || {});
    }

function runningHubEntryId(entry, kind){
    return String(kind === 'workflow'
        ? (entry?.workflowId || entry?.workflow_id || entry?.workflowID || entry?.id || '')
        : (entry?.appId || entry?.app_id || entry?.webappId || entry?.webapp_id || entry?.webappID || entry?.id || '')
    ).trim();
}
function runningHubEntryLabel(entry, kind){
    const id = runningHubEntryId(entry, kind);
    return entry?.title || entry?.name || (kind === 'workflow' ? `Workflow ${id}` : `AI App ${id}`);
}
function runningHubEntryKey(kind, id){
    return `${kind}:${String(id || '').trim()}`;
}
function parseRunningHubEntryKey(value){
    const text = String(value || '').trim();
    const match = text.match(/^(app|workflow):(.+)$/);
    return match ? {kind:match[1], id:match[2].trim()} : null;
}
function rhEntryFields(entry){
    return Array.isArray(entry?.fields) ? entry.fields : [];
}
function rhWorkflowJsonFromSources(...sources){
    for(const source of sources){
        if(source && typeof source === 'object' && Object.keys(source).length) return source;
    }
    return {};
}
function rhNodeOffIds(sourceSettings=deps.getSettings()){
    return Object.entries(deps.rhNodeOffBucket(sourceSettings)).filter(([,off]) => off === true).map(([id]) => String(id));
}
function rhNodeIsOff(nodeId, sourceSettings=deps.getSettings()){
    const id = String(nodeId ?? '');
    if(!id) return false;
    return deps.rhNodeOffBucket(sourceSettings)[id] === true;
}
function renderRhWorkflowControl(ref){
    const apps = deps.runningHubEntries('app');
    const workflows = deps.runningHubEntries('workflow');
    const selected = ref ? runningHubEntryKey(ref.kind, ref.id) : '';
    const groupHtml = (kind, entries, label) => entries.length ? `
        <div class="model-list-label rh-list-label">${deps.escapeHtml(label)}<span class="count">${entries.length}</span></div>
        ${entries.map(entry => {
            const id = runningHubEntryId(entry, kind);
            const key = runningHubEntryKey(kind, id);
            return `<button type="button" class="direct-option rh-entry-option ${key === selected ? 'active' : ''}" data-smart-param="rhConfigKey" data-smart-value="${deps.escapeHtml(key)}"><i data-lucide="${kind === 'workflow' ? 'workflow' : 'sparkles'}"></i><span>${deps.escapeHtml(runningHubEntryLabel(entry, kind))}</span></button>`;
        }).join('')}
    ` : '';
    const engineLabels = {};
    if(deps.getEngineSelect()) [...engineSelect.options].forEach(o => { engineLabels[o.value] = o.textContent.trim(); });
    const engineRow = Object.entries(engineLabels).map(([key, label]) =>
        `<button type="button" class="direct-option ${key === deps.getSettings().engine ? 'active' : ''}" data-combo-engine="${deps.escapeHtml(key)}"><span>${deps.escapeHtml(label)}</span></button>`).join('');
    const caption = ref ? runningHubEntryLabel(ref.entry, ref.kind) : deps.tr('smart.rhConfig');
    return `<div class="smart-control rh-merge-control rh-workflow-control">
        <button class="smart-pill" type="button" title="${deps.escapeHtml(caption)}"><span class="sub">${deps.escapeHtml(caption)}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover rh-picker-popover rh-unified-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.rhConfig'))}</div>
            <div class="model-list rh-config-list">
                ${groupHtml('app', apps, 'AI 应用')}${groupHtml('workflow', workflows, '工作流')}
            </div>
            ${engineRow ? `<div class="model-list-label rh-list-label rh-inline-group-label">生成引擎</div><div class="model-list rh-inline-group">${engineRow}</div>` : ''}
        </div>
    </div>`;
}
function rhNodesPillText(nodes){
    const total = (nodes || []).length;
    const offCount = (nodes || []).filter(node => rhNodeIsOff(node.id)).length;
    return offCount
        ? `${deps.tr('smart.comfyExposedNodes')} ${total} · ${deps.tr('smart.comfyOff')} ${offCount}`
        : `${deps.tr('smart.comfyExposedNodes')} ${total}`;
}
function renderRhNodesControl(ref){
    const nodes = deps.rhWorkflowNodeList(ref);
    if(!nodes.length) return '';
    const pillText = rhNodesPillText(nodes);
    const rows = nodes.map(node => {
        const off = rhNodeIsOff(node.id);
        const hint = `${node.label}${node.cls ? ` · ${node.cls}` : ''}`;
        return `<div class="cfm-row ${off ? 'cfm-row-off' : ''}">
            <span class="cfm-name" title="${deps.escapeHtml(hint)}">${deps.escapeHtml(node.label)}</span>
            <button type="button" class="cfm-toggle ${off ? '' : 'on'}" data-rh-node-mode="${deps.escapeHtml(node.id)}" title="${deps.escapeHtml(off ? deps.tr('smart.comfyNodeOff') : deps.tr('smart.comfyNodeOn'))}">${off ? deps.tr('smart.comfyOff') : deps.tr('smart.comfyOn')}</button>
        </div>`;
    }).join('');
    const headTitle = String(ref?.entry?.title || ref?.id || '').slice(0, 24);
    return `<div class="smart-control comfy-nodes-control rh-nodes-control">
        <button class="smart-pill" type="button" title="${deps.escapeHtml(pillText)}"><span class="sub">${deps.escapeHtml(pillText)}</span></button>
        <div class="smart-popover compact-popover comfy-nodes-popover rh-nodes-popover">
            <div class="smart-popover-title">${deps.escapeHtml(headTitle)}<span class="count">${nodes.length}</span></div>
            <div class="cfm-list">${rows}</div>
        </div>
    </div>`;
}
function renderRhDetailsHtml(){
    return `<div class="cfn-details rh-details">
        ${deps.renderRhInputsRow()}
    </div>`;
}
function rhParamFields(fields){
    return (fields || []).filter(f => !['image','video','audio','prompt'].includes(deps.rhFieldRole(f)));
}
function renderRhParamsControl(fields){
    const paramFields = rhParamFields(fields);
    if(!paramFields.length) return '';
    const title = deps.tr('smart.workflowParams') || '工作流参数';
    return `<div class="smart-control rh-params-control">
        <button class="smart-pill" type="button" title="${deps.escapeHtml(title)}"><span class="sub">${deps.escapeHtml(title)} ${paramFields.length}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover rh-picker-popover rh-param-popover rh-params-popover">
            <div class="smart-popover-title">${deps.escapeHtml(title)}</div>
            <div class="cfn-params-body">${paramFields.map(deps.renderRhSettingField).join('')}</div>
        </div>
    </div>`;
}
function renderRhResourceControl(){
    const rhPaymentLabels = {free:deps.tr('smart.rhFreeKey'), wallet:deps.tr('smart.rhWalletKey')};
    const rhPaymentValue = deps.getSettings().rhPayment === 'wallet' ? 'wallet' : 'free';
    const rhMachineLabels = {'':'24G', plus:'48G'};
    const rhMachineValue = deps.getSettings().rhInstanceType === 'plus' ? 'plus' : '';
    const optionRow = (param, labels, value) => Object.entries(labels).map(([key, label]) =>
        `<button type="button" class="direct-option ${key === value ? 'active' : ''}" data-smart-param="${param}" data-smart-value="${deps.escapeHtml(key)}"><span>${deps.escapeHtml(label)}</span></button>`).join('');
    const caption = [rhPaymentLabels[rhPaymentValue], rhMachineLabels[rhMachineValue]].join(' · ');
    return `<div class="smart-control rh-merge-control rh-resource-control">
        <button class="smart-pill" type="button" title="${deps.escapeHtml(caption)}"><span class="sub">${deps.escapeHtml(caption)}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover rh-picker-popover rh-unified-popover">
            <div class="model-list-label rh-list-label rh-inline-group-label">${deps.escapeHtml(deps.tr('smart.rhKey'))}</div>
            <div class="model-list rh-inline-group">${optionRow('rhPayment', rhPaymentLabels, rhPaymentValue)}</div>
            <div class="model-list-label rh-list-label rh-inline-group-label">${deps.escapeHtml(deps.tr('smart.rhMachine'))}</div>
            <div class="model-list rh-inline-group">${optionRow('rhInstanceType', rhMachineLabels, rhMachineValue)}</div>
        </div>
    </div>`;
}
function renderRhConfigControl(ref){
    const apps = deps.runningHubEntries('app');
    const workflows = deps.runningHubEntries('workflow');
    const selected = ref ? runningHubEntryKey(ref.kind, ref.id) : '';
    const groupHtml = (kind, entries, label) => entries.length ? `
        <div class="model-list-label rh-list-label">${deps.escapeHtml(label)}<span class="count">${entries.length}</span></div>
        ${entries.map(entry => {
            const id = runningHubEntryId(entry, kind);
            const key = runningHubEntryKey(kind, id);
            return `<button type="button" class="direct-option rh-entry-option ${key === selected ? 'active' : ''}" data-smart-param="rhConfigKey" data-smart-value="${deps.escapeHtml(key)}"><i data-lucide="${kind === 'workflow' ? 'workflow' : 'sparkles'}"></i><span>${deps.escapeHtml(runningHubEntryLabel(entry, kind))}</span></button>`;
        }).join('')}
    ` : '';
    return `<div class="smart-control rh-config-control">
        <button class="smart-pill" type="button"><i data-lucide="workflow"></i><span class="sub">${deps.escapeHtml(ref ? runningHubEntryLabel(ref.entry, ref.kind) : deps.tr('smart.rhConfig'))}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover rh-picker-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.rhConfig'))}</div>
            <div class="model-list rh-config-list">
                ${groupHtml('app', apps, 'AI 应用')}${groupHtml('workflow', workflows, '工作流') || ''}
            </div>
        </div>
    </div>`;
}
function renderRhPaymentControl(){
    const value = deps.getSettings().rhPayment === 'wallet' ? 'wallet' : 'free';
    const labels = {free:deps.tr('smart.rhFreeKey'), wallet:deps.tr('smart.rhWalletKey')};
    return `<div class="smart-control rh-payment-control">
        <button class="smart-pill" type="button"><i data-lucide="key-round"></i><span>${deps.escapeHtml(labels[value])}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover rh-picker-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.rhKey'))}</div>
            <div class="model-list">
                ${Object.entries(labels).map(([key, label]) => `<button type="button" class="direct-option ${key === value ? 'active' : ''}" data-smart-param="rhPayment" data-smart-value="${deps.escapeHtml(key)}"><span>${deps.escapeHtml(label)}</span></button>`).join('')}
            </div>
        </div>
    </div>`;
}
function renderRhMachineControl(){
    const value = deps.getSettings().rhInstanceType === 'plus' ? 'plus' : '';
    const labels = {'':'24G', plus:'48G'};
    return `<div class="smart-control rh-machine-control">
        <button class="smart-pill" type="button"><i data-lucide="cpu"></i><span>${deps.escapeHtml(labels[value])}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover rh-picker-popover">
            <div class="smart-popover-title">${deps.escapeHtml(deps.tr('smart.rhMachine'))}</div>
            <div class="model-list">
                ${Object.entries(labels).map(([key, label]) => `<button type="button" class="direct-option ${key === value ? 'active' : ''}" data-smart-param="rhInstanceType" data-smart-value="${deps.escapeHtml(key)}"><span>${deps.escapeHtml(label)}</span></button>`).join('')}
            </div>
        </div>
    </div>`;
}

    global.CanvasRhControls = {
        configure: configure,
        runningHubEntryId: runningHubEntryId,
        runningHubEntryLabel: runningHubEntryLabel,
        runningHubEntryKey: runningHubEntryKey,
        parseRunningHubEntryKey: parseRunningHubEntryKey,
        rhEntryFields: rhEntryFields,
        rhWorkflowJsonFromSources: rhWorkflowJsonFromSources,
        rhNodeOffIds: rhNodeOffIds,
        rhNodeIsOff: rhNodeIsOff,
        renderRhWorkflowControl: renderRhWorkflowControl,
        rhNodesPillText: rhNodesPillText,
        renderRhNodesControl: renderRhNodesControl,
        renderRhDetailsHtml: renderRhDetailsHtml,
        rhParamFields: rhParamFields,
        renderRhParamsControl: renderRhParamsControl,
        renderRhResourceControl: renderRhResourceControl,
        renderRhConfigControl: renderRhConfigControl,
        renderRhPaymentControl: renderRhPaymentControl,
        renderRhMachineControl: renderRhMachineControl
    };
})(typeof window !== 'undefined' ? window : globalThis);
