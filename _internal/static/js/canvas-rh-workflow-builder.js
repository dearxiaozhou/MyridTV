/** Routes RunningHub workflow pruning / nodeInfoList building / setting-field rendering. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function rhRequiredLabel(field){
    return field?.label || field?.fieldName || `#${field?.nodeId || ''}`;
}
function rhPruneWorkflowForMissingFields(workflowJson, missingFields){
    if(!workflowJson || typeof workflowJson !== 'object' || !missingFields?.length) return null;
    const workflow = JSON.parse(JSON.stringify(workflowJson));
    const removeIds = new Set();
    missingFields.forEach(field => {
        const node = workflow[String(field.nodeId)];
        if(node?.inputs && Object.prototype.hasOwnProperty.call(node.inputs, field.fieldName)){
            delete node.inputs[field.fieldName];
        }
        if(node && (!node.inputs || !Object.keys(node.inputs).length)){
            removeIds.add(String(field.nodeId));
        }
    });
    removeIds.forEach(id => delete workflow[id]);
    Object.values(workflow).forEach(node => {
        if(!node?.inputs || typeof node.inputs !== 'object') return;
        Object.entries(node.inputs).forEach(([name, value]) => {
            if(deps.rhIsWorkflowLinkValue(value) && removeIds.has(String(value[0]))) delete node.inputs[name];
        });
    });
    return workflow;
}
// 节点开关：把指定节点整节点从 workflow JSON 中移除，并断开下游对它的引用（等同 ComfyUI 的旁路/跳过）。
function rhPruneWorkflowNodes(workflowJson, nodeIds){
    const ids = new Set((nodeIds || []).map(id => String(id)));
    if(!workflowJson || typeof workflowJson !== 'object' || !ids.size) return null;
    const workflow = JSON.parse(JSON.stringify(workflowJson));
    ids.forEach(id => delete workflow[id]);
    Object.values(workflow).forEach(node => {
        if(!node?.inputs || typeof node.inputs !== 'object') return;
        Object.entries(node.inputs).forEach(([name, value]) => {
            if(deps.rhIsWorkflowLinkValue(value) && ids.has(String(value[0]))) delete node.inputs[name];
        });
    });
    return workflow;
}
async function rhBuildWorkflowRequestExtras(media, nodeInfoList, sourceSettings=D("settings")){
    const config = await deps.currentRunningHubWorkflowConfig(sourceSettings);
    if(!config) return {};
    const pruneMode = (config.optionalImageMode || 'prune-workflow') === 'prune-workflow';
    const fields = deps.rhActiveFields(sourceSettings);
    const indexes = deps.rhFieldIndexes(fields, sourceSettings);
    const missingOptional = [];
    // 未暴露的图片槽位缺图时，按 nodeId 整节点裁掉（LoadImage 只有 image 一个输入，等价于旁路）。
    const missingSlotNodeIds = [];
    if(pruneMode){
        const imageSlots = deps.rhWorkflowImageSlots(deps.selectedRunningHubRef(sourceSettings));
        if(imageSlots.length){
            // 图片槽位由工作流自动识别 → 覆盖「全部」槽位，不要求先在 API 设置里暴露。
            imageSlots.forEach((slot, idx) => {
                if(deps.rhNodeIsOff(slot.nodeId, sourceSettings)) return; // 已被节点开关关掉，交给 offNodeIds 处理
                const field = fields.find(f => String(f.nodeId) === String(slot.nodeId));
                const hasInput = Boolean(media.image?.[idx]?.url);
                if(field?.required === true && !hasInput) throw new Error(`RunningHub 工作流缺少必选图片：${rhRequiredLabel(field)}`);
                if(hasInput) return;
                if(field) missingOptional.push(field);
                else missingSlotNodeIds.push(String(slot.nodeId));
            });
        } else {
            // 兜底：工作流识别不出图片槽位时，沿用原来「按已暴露字段」的逻辑。
            for(const field of fields){
                if(deps.rhFieldKind(field) !== 'image') continue;
                const key = deps.rhParamKey(field.nodeId, field.fieldName);
                const idx = indexes[key] || 0;
                const hasInput = Boolean(media.image?.[idx]?.url);
                if(field.required === true && !hasInput) throw new Error(`RunningHub 工作流缺少必选图片：${rhRequiredLabel(field)}`);
                if(field.required !== true && !hasInput) missingOptional.push(field);
            }
        }
    }
    // 节点开关关掉的节点：不依赖 optionalImageMode 策略，始终裁剪。
    // 注意 rhActiveFields 已把被关节点的字段过滤掉，所以 nodeInfoList 里通常本就没有它们的参数，
    // 这里再按 nodeId 兜底清一次，防止本地缓存与云端字段不一致时把参数带上去。
    const offNodeIds = deps.rhNodeOffIds(sourceSettings);
    // 2026-09-29：VHS_VideoCombine 等输出节点 save_output=false 时视频只写 temp（预览）目录，
    // RunningHub 只收集 output 目录文件 → 任务 SUCCESS 但"暂无生成结果"、积分照扣。
    // 存在此类节点时不能提前返回，必须走到下面强制 save_output=true 的改写。
    const hasSaveOutputOff = Object.values(config.workflowJson || {}).some(n => n?.inputs && n.inputs.save_output === false);
    if(!missingOptional.length && !missingSlotNodeIds.length && !offNodeIds.length && !media?.prompt && !hasSaveOutputOff) return {};
    const dropKeys = new Set();
    missingOptional.forEach(field => dropKeys.add(deps.rhParamKey(field.nodeId, field.fieldName)));
    offNodeIds.forEach(id => {
        fields.forEach(field => { if(String(field.nodeId) === String(id)) dropKeys.add(deps.rhParamKey(field.nodeId, field.fieldName)); });
    });
    for(let i = nodeInfoList.length - 1; i >= 0; i--){
        if(dropKeys.has(deps.rhParamKey(nodeInfoList[i].nodeId, nodeInfoList[i].fieldName))) nodeInfoList.splice(i, 1);
    }
    let workflow = config.workflowJson ? JSON.parse(JSON.stringify(config.workflowJson)) : {};
    // 2026-09-29：强制 save_output=true——RH 云端教程明确「Save Output 关闭时视频不会出现在
    // 云端任务列表」。画布跑 RH 必须有产物可回填，否则 SUCCESS 但 results 空、积分白扣。
    Object.values(workflow).forEach(node => {
        if(node?.inputs && node.inputs.save_output === false) node.inputs.save_output = true;
    });
    if(missingOptional.length) workflow = rhPruneWorkflowForMissingFields(workflow, missingOptional) || workflow;
    if(offNodeIds.length) workflow = rhPruneWorkflowNodes(workflow, offNodeIds) || workflow;
    if(missingSlotNodeIds.length) workflow = rhPruneWorkflowNodes(workflow, missingSlotNodeIds) || workflow;
    // 2026-09-29：画布主提示词同时写回 workflow 字符串里「被 prompt 输入引用的文本节点」，
    // 与 nodeInfoList 的 263 覆盖形成双保险——即使 RH 端忽略 nodeInfoList 覆盖，也能靠 workflow
    // 字符串本身生效（提交给 RH 的字符串即它实际执行的 workflow）。
    if(media?.prompt){
        const promptSourceIds = new Set();
        for(const [oid, onode] of Object.entries(workflow)){
            if(!onode || !onode.inputs) continue;
            for(const [k, v] of Object.entries(onode.inputs)){
                if(k === 'prompt' && Array.isArray(v) && v.length && String(v[0]) !== String(oid))
                    promptSourceIds.add(String(v[0]));
            }
        }
        for(const sid of promptSourceIds){
            const snode = workflow[sid];
            if(!snode || !snode.inputs) continue;
            const textKey = Object.keys(snode.inputs).find(k => typeof snode.inputs[k] === 'string' && !Array.isArray(snode.inputs[k]));
            if(textKey) snode.inputs[textKey] = media.prompt;
        }
    }
    // RH 的 /task/openapi/create 只认 JSON 字符串（官方文档：workflow string - Custom full workflow
    // in JSON string format）。传对象会被判为非法 → {"code":404,"msg":"NOT_FOUND"}（2026-09-16 实测复现）。
    return Object.keys(workflow || {}).length ? {workflow: JSON.stringify(workflow)} : {};
}
async function rhUploadValueIfNeeded(value, sourceSettings=D("settings")){
    const text = String(value || '').trim();
    if(!text) return '';
    if(!/^https?:\/\//i.test(text) && !text.startsWith('/output/') && !text.startsWith('/assets/')) return text;
    const res = await fetch('/api/runninghub/upload-asset', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url:text, useWallet:(sourceSettings || D("settings")).rhPayment === 'wallet'})
    });
    const data = await res.json();
    if(!res.ok || data.success === false) throw new Error(data.detail || data.error || tr('smart.rhUploadFailed'));
    return data.data?.fileName || text;
}
async function rhBuildNodeInfoList(media, sourceSettings=D("settings"), randomValues=D("smartRhRandomValues")){
    const fields = deps.rhActiveFields(sourceSettings);
    const result = [];
    const indexes = deps.rhFieldIndexes(fields, sourceSettings);
    const mode = deps.rhCurrentKind(sourceSettings);
    for(const field of fields){
        const kind = deps.rhFieldKind(field);
        const key = deps.rhParamKey(field.nodeId, field.fieldName);
        // workflow 模式：非媒体字段默认不覆盖云端工作流的默认值（保持原设计），
        // 但用户在节点上显式改过值的必须提交 —— 否则「参数设置好了」等于没设置（2026-09-16）。
        // 2026-09-29：画布主提示词框内容（media.prompt）视为「上游注入」，即便字段为
        // sourceFromUpstream=false 也提交；仅当用户显式「保留原生」且未编辑、且无画布提示词时退回原生。
        const userEdited = String(sourceSettings?.rhParams?.[key]?.value ?? '').trim() !== '';
        const promptFromCanvas = deps.rhFieldRole(field) === 'prompt' && Boolean((media?.prompt || '').trim());
        if(mode === 'workflow' && field.sourceFromUpstream === false && !['image','video','audio'].includes(kind) && !userEdited && !promptFromCanvas) continue;
        if(mode === 'workflow' && ['image','video','audio'].includes(kind)){
            const idx = indexes[key] || 0;
            if(field.required !== true && !media?.[kind]?.[idx]?.url) continue;
        }
        let value = deps.rhParamValue(field, media, sourceSettings, fields, randomValues);
        if(deps.rhFieldRole(field) === 'prompt' && !String(value || '').trim()) value = deps.rhDefaultValue(field);
        if(['image','video','audio'].includes(kind)) value = await rhUploadValueIfNeeded(value, sourceSettings);
        if(['number','slider'].includes(kind) && String(value ?? '').trim() !== '' && !Number.isNaN(Number(value))) value = Number(value);
        if(typeof value === 'string' && /[\r\n]/.test(value)) value = value.split(/\r?\n/).map(s => s.trim()).filter(Boolean)[0] || '';
        result.push({nodeId:field.nodeId, fieldName:field.fieldName, fieldValue:value});
    }
    // 图片槽位自动补全（零配置，2026-09-16）：工作流里自动识别出的图片槽位，即使没在 API 设置里暴露，
    // 只要画布上传了对应序号的图片也要提交 —— 否则「不暴露就传不进去」，后面自动裁剪还会把用户的图一起裁掉。
    if(mode === 'workflow'){
        const slots = deps.rhWorkflowImageSlots(deps.selectedRunningHubRef(sourceSettings));
        const covered = new Set(result.map(item => deps.rhParamKey(item.nodeId, item.fieldName)));
        for(let idx = 0; idx < slots.length; idx++){
            const slot = slots[idx];
            if(fields.some(f => String(f.nodeId) === String(slot.nodeId))) continue; // 已暴露 → 上面的循环已处理
            if(deps.rhNodeIsOff(slot.nodeId, sourceSettings)) continue;
            const url = media?.image?.[idx]?.url;
            if(!url) continue;
            const key = deps.rhParamKey(slot.nodeId, slot.fieldName);
            if(covered.has(key)) continue;
            covered.add(key);
            const value = await rhUploadValueIfNeeded(url, sourceSettings);
            result.push({nodeId:String(slot.nodeId), fieldName:slot.fieldName, fieldValue:value});
        }
    }
    // 2026-09-29：workflow 模式下，自动把画布主提示词注入到「被 prompt 输入引用的文本节点」
    // （如 MiniMax H3 Reference to Video 的提示词 Text 节点），覆盖 workflow 原生写死的提示词。
    // 仅当画布提示词非空、且该节点尚未被显式字段覆盖时注入。
    if(mode === 'workflow' && media?.prompt){
        try {
            const cfg = await deps.currentRunningHubWorkflowConfig(sourceSettings);
            const workflow = cfg && cfg.workflowJson;
            if(workflow && typeof workflow === 'object'){
                const covered = new Set(result.map(i => String(i.nodeId)));
                const promptSourceIds = new Set();
                for(const [oid, onode] of Object.entries(workflow)){
                    if(!onode || !onode.inputs) continue;
                    for(const [k, v] of Object.entries(onode.inputs)){
                        if(k === 'prompt' && Array.isArray(v) && v.length && String(v[0]) !== String(oid))
                            promptSourceIds.add(String(v[0]));
                    }
                }
                for(const sid of promptSourceIds){
                    if(covered.has(sid)) continue;
                    const snode = workflow[sid];
                    if(!snode || !snode.inputs) continue;
                    const textKey = Object.keys(snode.inputs).find(k => typeof snode.inputs[k] === 'string' && !Array.isArray(snode.inputs[k]));
                    if(textKey) result.push({nodeId:String(sid), fieldName:textKey, fieldValue: media.prompt});
                }
            }
        } catch(e){ /* 容错：注入失败不阻断正常提交 */ }
    }
    return result;
}
function renderRhSettingField(field){
    const key = deps.rhParamKey(field.nodeId, field.fieldName);
    const kind = deps.rhFieldRole(field);
    const label = field.label || field.fieldName || 'Field';
    const value = deps.rhParamValue(field, null);
    const options = deps.rhExtractFieldOptions(field);
    if(kind === 'boolean'){
        const active = String(value).toLowerCase() === 'true';
        return `<button type="button" class="setting-check ${active ? 'active' : ''}" data-rh-bool="${deps.escapeHtml(key)}"><span class="check-box"></span><span>${deps.escapeHtml(label)}</span></button>`;
    }
    if(kind === 'slider'){
        const min = Number.isFinite(Number(field.min)) ? Number(field.min) : 0;
        const max = Number.isFinite(Number(field.max)) && Number(field.max) > min ? Number(field.max) : 1;
        const step = Number.isFinite(Number(field.step)) && Number(field.step) > 0 ? Number(field.step) : 0.01;
        const numericValue = Number.isFinite(Number(value)) ? Number(value) : min;
        return `<div class="smart-control rh-slider-control" title="${deps.escapeHtml(label)}">
            <button class="smart-pill" type="button"><span class="sub">${deps.escapeHtml(label)}</span><span class="rh-slider-pill-value">${deps.escapeHtml(numericValue)}</span></button>
            <div class="smart-popover compact-popover rh-picker-popover rh-param-popover rh-slider-popover">
                <div class="smart-popover-title"><span>${deps.escapeHtml(label)}</span><span class="rh-slider-value">${deps.escapeHtml(numericValue)}</span></div>
                <input type="range" class="smart-range rh-slider-input" data-rh-param="${deps.escapeHtml(key)}" data-rh-type="slider" min="${deps.escapeHtml(min)}" max="${deps.escapeHtml(max)}" step="${deps.escapeHtml(step)}" value="${deps.escapeHtml(numericValue)}">
            </div>
        </div>`;
    }
    if(options?.length){
        const curLabel = String(value || options[0] || label);
        return `<div class="smart-control rh-dropdown-control" title="${deps.escapeHtml(label)}">
            <button class="smart-pill" type="button"><span class="sub">${deps.escapeHtml(curLabel)}</span><i data-lucide="chevron-down" class="pill-caret"></i></button>
            <div class="smart-popover compact-popover rh-picker-popover rh-param-popover">
                <div class="smart-popover-title">${deps.escapeHtml(label)}</div>
                <div class="model-list rh-param-list">
                    ${options.map(o => `<button type="button" class="direct-option ${String(o) === String(value) ? 'active' : ''}" data-rh-pick="${deps.escapeHtml(key)}" data-rh-value="${deps.escapeHtml(o)}"><span>${deps.escapeHtml(o)}</span></button>`).join('') || `<div class="muted-note">${deps.escapeHtml(tr('smart.noOption'))}</div>`}
                </div>
            </div>
        </div>`;
    }
    const type = kind === 'number' ? 'number' : 'text';
    const inputHtml = `<input type="${type}" data-rh-param="${deps.escapeHtml(key)}" value="${deps.escapeHtml(value)}">`;
    if(kind === 'number' && deps.rhRandomEnabled(field)){
        const active = deps.smartRhRandomActive(key);
        return `<div class="num-with-dice" title="${deps.escapeHtml(label)}">
            <span class="num-label">${deps.escapeHtml(label)}</span>
            ${inputHtml}
            <button type="button" class="dice-btn ${active ? 'active' : ''}" data-rh-random="${deps.escapeHtml(key)}" title="${deps.escapeHtml(active ? tr('smart.diceOn') : tr('smart.diceOff'))}"><i data-lucide="dice-5"></i></button>
        </div>`;
    }
    return `<div class="num-compact ${type === 'text' ? 'rh-text-param' : ''}" title="${deps.escapeHtml(label)}"><span class="num-label">${deps.escapeHtml(label)}</span>${inputHtml}</div>`;
}

    global.CanvasRhWorkflowBuilder = {
        configure,
        rhRequiredLabel,
        rhPruneWorkflowForMissingFields,
        rhPruneWorkflowNodes,
        rhBuildWorkflowRequestExtras,
        rhUploadValueIfNeeded,
        rhBuildNodeInfoList,
        renderRhSettingField,
    };
})(typeof window !== 'undefined' ? window : this);
