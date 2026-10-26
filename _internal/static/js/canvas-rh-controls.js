/* MyridTV 画布 RunningHub 控件渲染层（拆模块 ⑤）
 *
 * 「工作流 JSON 识别 + 数据 → HTML 字符串 / key 解析」纯函数：图片槽位与节点识别、
 * 工作流选择 pill、节点开关列表、参数入口、资源(密钥/机器)选择、配置弹层等。
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
        getRunningHubWorkflowCache: null,
        rhIsWorkflowLinkValue: null,
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
/* 节点开关：只列「API 设置里勾选过」的节点（= 该工作流已暴露字段所属的节点），
   与本地 ComfyUI 的「已暴露节点」语义一致（canvas-comfy-controls.js: renderedComfyNodeModesControl）。
   图片槽位自动从图结构推导，优先尊重 ref_images.ref_image_N 等命名连线，其次按节点 ID 排序。 */
function rhWorkflowJsonForRef(ref){
    if(!ref) return {};
    const cache = deps.getRunningHubWorkflowCache ? deps.getRunningHubWorkflowCache() : {};
    return rhWorkflowJsonFromSources(
        cache[ref.id]?.workflowJson,
        ref.entry?.workflowJson,
        ref.entry?.raw?.workflowJson,
        ref.entry?.raw?.prompt
    );
}
function rhWorkflowNodeList(ref){
    if(!ref || ref.kind !== 'workflow') return [];
    const workflow = rhWorkflowJsonForRef(ref);
    // 2026-09-26 修复：原实现列出 workflow JSON 里的全部节点（Krea2 = 46 个），
    // 而「节点开关」关节点走的是「裁剪该节点的字段」——内部节点没有暴露字段可裁，
    // 开关是空操作，列表也跟用户在 API 设置里勾的节点对不上。
    // 改为只列勾选/暴露过字段的节点（rhEntryFields 同源：缓存配置优先于 entry 快照）。
    const cached = deps.getRunningHubWorkflowCache ? deps.getRunningHubWorkflowCache() : {};
    const cachedFields = cached[ref.id]?.fields;
    const fields = (Array.isArray(cachedFields) && cachedFields.length)
        ? cachedFields
        : (Array.isArray(ref.entry?.fields) ? ref.entry.fields : []);
    // 2026-10-20 老王：与本地「已暴露节点」同口径 + 自动接管的媒体节点也要有开关。
    // 之前只收 enabled === true 的字段所属节点，而图片/音频节点（LoadImage/LoadAudio…）
    // 的字段在配置里 enabled=false（它们的输入是「工作流自动识别图片槽位」自动接线的），
    // 于是这些节点的开关整批消失 —— 老王问「图片/音频节点开关哪去了」。现在：
    //   ① 已暴露字段所属节点（同本地语义）；② 带图片/视频/音频字段的节点（自动接管的那些）。
    const ids = [...new Set(fields
        .filter(field => field && (field.enabled === true || ['image','video','audio'].includes(deps.rhFieldRole(field))))
        .map(field => String(field.nodeId || '').trim())
        .filter(id => id && workflow[id] && typeof workflow[id] === 'object'))];
    if(!ids.length) return [];
    ids.sort((a, b) => {
        const an = Number(a), bn = Number(b);
        if(Number.isFinite(an) && Number.isFinite(bn) && an !== bn) return an - bn;
        return String(a).localeCompare(String(b), undefined, {numeric:true});
    });
    const names = ids.map(id => String(workflow[id]?._meta?.title || workflow[id]?.class_type || id).trim() || id);
    const total = {};
    names.forEach(name => { total[name] = (total[name] || 0) + 1; });
    const seen = {};
    return ids.map((id, index) => {
        const name = names[index];
        let label = name;
        if(total[name] > 1){
            seen[name] = (seen[name] || 0) + 1;
            label = `${name} #${seen[name]}`;
        }
        return {id, label, cls:String(workflow[id]?.class_type || '')};
    });
}
function rhIsImageLoaderClass(cls){
    return /loadimage|imageload|load[\s_-]*image|image[\s_-]*load/i.test(String(cls || ''));
}
function rhWorkflowImageFieldName(node){
    const inputs = node?.inputs;
    if(!inputs || typeof inputs !== 'object') return '';
    const known = ['image','image_path','filename','file','img'];
    for(const key of known){
        if(Object.prototype.hasOwnProperty.call(inputs, key) && !deps.rhIsWorkflowLinkValue(inputs[key])) return key;
    }
    for(const key of known){
        if(Object.prototype.hasOwnProperty.call(inputs, key)) return key;
    }
    return '';
}
function rhWorkflowImageSlots(ref){
    if(!ref || ref.kind !== 'workflow') return [];
    const workflow = rhWorkflowJsonForRef(ref);
    const ids = Object.keys(workflow || {}).filter(id => workflow[id] && typeof workflow[id] === 'object');
    if(!ids.length) return [];
    const imageIds = ids.filter(id => rhIsImageLoaderClass(workflow[id]?.class_type));
    if(!imageIds.length) return [];
    const imageIdSet = new Set(imageIds.map(String));
    const groups = new Map();
    ids.forEach(id => {
        const inputs = workflow[id]?.inputs;
        if(!inputs || typeof inputs !== 'object') return;
        Object.entries(inputs).forEach(([key, value]) => {
            if(!deps.rhIsWorkflowLinkValue(value) || !imageIdSet.has(String(value[0]))) return;
            const match = /^(.*?)(\d+)$/.exec(String(key));
            if(!match) return;
            const order = Number(match[2]);
            if(!Number.isFinite(order)) return;
            if(!groups.has(match[1])) groups.set(match[1], []);
            groups.get(match[1]).push({order, nodeId:String(value[0])});
        });
    });
    let ordered = [];
    const candidates = [...groups.values()].map(items => {
        const uniq = new Map();
        items.forEach(item => {
            const prev = uniq.get(item.nodeId);
            if(!prev || prev.order > item.order) uniq.set(item.nodeId, item);
        });
        return [...uniq.values()].sort((a, b) => a.order - b.order).map(item => item.nodeId);
    }).filter(list => list.length >= 2);
    if(candidates.length){
        candidates.sort((a, b) => b.length - a.length);
        ordered = candidates[0];
    }
    if(!ordered.length){
        ordered = [...imageIds].sort((a, b) => {
            const an = Number(a), bn = Number(b);
            if(Number.isFinite(an) && Number.isFinite(bn) && an !== bn) return an - bn;
            return String(a).localeCompare(String(b), undefined, {numeric:true});
        });
    }
    const seen = new Set();
    return ordered.filter(id => {
        const key = String(id);
        if(seen.has(key)) return false;
        seen.add(key);
        return true;
    }).map(nodeId => {
        const node = workflow[nodeId];
        const title = String(node?._meta?.title || node?.class_type || `#${nodeId}`).trim() || `#${nodeId}`;
        return {nodeId:String(nodeId), fieldName:rhWorkflowImageFieldName(node) || 'image', label:title};
    });
}
function rhImageSlotOrderMap(sourceSettings=deps.getSettings()){
    const map = new Map();
    rhWorkflowImageSlots(deps.selectedRunningHubRef(sourceSettings)).forEach((slot, index) => {
        if(!map.has(String(slot.nodeId))) map.set(String(slot.nodeId), index);
    });
    return map;
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
    return deps.tr('smart.nodesPill') || '节点开关';
}
function renderRhNodesControl(ref){
    const nodes = rhWorkflowNodeList(ref);
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
    // 2026-09-25 老王：自动裁剪已接管输入接线，「素材：接收…」计数行删除
    return '';
}
function rhParamFields(fields){
    return (fields || []).filter(f => !['image','video','audio','prompt'].includes(deps.rhFieldRole(f)));
}
function renderRhParamsControl(fields){
    const paramFields = rhParamFields(fields);
    if(!paramFields.length) return '';
    const title = deps.tr('smart.workflowParams') || '工作流参数';
    const pillLabel = deps.tr('smart.paramsPill') || '参数调整';
    return `<div class="smart-control rh-params-control">
        <button class="smart-pill" type="button" title="${deps.escapeHtml(title)}"><span class="sub">${deps.escapeHtml(pillLabel)} ${paramFields.length}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
        <div class="smart-popover compact-popover rh-picker-popover rh-param-popover rh-params-popover">
            <div class="smart-popover-title">${deps.escapeHtml(title)}</div>
            <div class="cfn-params-body">${paramFields.map(deps.renderRhSettingField).join('')}</div>
        </div>
    </div>`;
}
// 2026-10-24 老王：批量节点底部面板不要弹层——参数直接平铺（同一套字段渲染，只是去掉 pill+弹层）。
function renderRhParamsInline(fields){
    const paramFields = rhParamFields(fields);
    if(!paramFields.length) return '';
    return `<div class="batch-inline-params rh-inline-params">${paramFields.map(deps.renderRhSettingField).join('')}</div>`;
}
/* 2026-10-25 老王：批量节点卡片里那一排参数（RH 工作流）。字段与取值通道和上面那份一致，
 * 外壳换成「短标签 + 下拉 pill」，一行排开。 */
function renderRhParamsPillInline(fields, sourceSettings){
    const pills = rhParamFields(fields).map(field => renderRhParamPill(field, sourceSettings)).filter(Boolean);
    if(!pills.length) return '';
    return `<div class="batch-inline-params rh-inline-params wf-pill-row">${pills.join('')}</div>`;
}
function renderRhParamPill(field, sourceSettings){
    if(!field) return '';
    const engine = global.CanvasDynamicParamEngine;
    const key = engine.rhParamKey(field.nodeId, field.fieldName);
    const label = field.label || field.fieldName || 'Field';
    const kind = deps.rhFieldRole(field);
    // sourceSettings：参数常驻在批量卡片上，按节点自己的 runSettings 取值（不读全局 settings）
    const value = engine.rhParamValue(field, null, sourceSettings || deps.getSettings());
    const attrs = ` data-rh-param="${deps.escapeHtml(key)}"`;
    if(kind === 'boolean'){
        return engine.wfParamTogglePillHtml({
            label, on:String(value).toLowerCase() === 'true', boolAttr:'rh-bool', boolKey:key
        });
    }
    const options = deps.rhExtractFieldOptions(field);
    if(options && options.length){
        return engine.wfParamPillHtml({label, value:String(value ?? ''), attrs:attrs, options:options.map(String), paramKey:`rh:${key}`, hideKey:true});
    }
    if(kind === 'slider' || kind === 'number'){
        const list = engine.wfParamNumberOptions({min:field.min, max:field.max, step:field.step}, value);
        return engine.wfParamPillHtml({
            label, value:value ?? 0, attrs:attrs, options:list, numeric:true, paramKey:`rh:${key}`, hideKey:false,
            inputType:list ? 'text' : 'number'
        });
    }
    if(kind === 'prompt') return '';
    return engine.wfParamPillHtml({label, value:String(value ?? ''), attrs:attrs, inputType:'text', paramKey:`rh:${key}`, hideKey:true});
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
        rhWorkflowJsonForRef: rhWorkflowJsonForRef,
        rhWorkflowNodeList: rhWorkflowNodeList,
        rhIsImageLoaderClass: rhIsImageLoaderClass,
        rhWorkflowImageFieldName: rhWorkflowImageFieldName,
        rhWorkflowImageSlots: rhWorkflowImageSlots,
        rhImageSlotOrderMap: rhImageSlotOrderMap,
        renderRhWorkflowControl: renderRhWorkflowControl,
        rhNodesPillText: rhNodesPillText,
        renderRhNodesControl: renderRhNodesControl,
        renderRhDetailsHtml: renderRhDetailsHtml,
        rhParamFields: rhParamFields,
        renderRhParamsControl: renderRhParamsControl,
        renderRhParamsInline: renderRhParamsInline,
        renderRhParamsPillInline: renderRhParamsPillInline,
        renderRhResourceControl: renderRhResourceControl,
        renderRhConfigControl: renderRhConfigControl,
        renderRhPaymentControl: renderRhPaymentControl,
        renderRhMachineControl: renderRhMachineControl
    };
})(typeof window !== 'undefined' ? window : globalThis);
