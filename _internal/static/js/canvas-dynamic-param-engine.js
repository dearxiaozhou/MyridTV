//** Renders and manages Comfy/RunningHub dynamic parameter fields, media refs and cloud-link state. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

// 2026-10-21 老王：ComfyUI/RH 端的浮点数会带二进制误差尾巴（0.6000000000000001）。
// 我们只负责「显示干净、传干净」，不改云端 workflow 的原始数据。
// 规则保守：整数（含大整数 seed）绝不转浮点；浮点只在误差极小时才收敛；非数字原样。
function rhCleanNumber(value){
    if(value === null || value === undefined) return value;
    if(typeof value === 'boolean') return value;
    if(typeof value === 'number'){
        if(!Number.isFinite(value)) return value;
        if(Number.isInteger(value)) return value;
        for(let digits = 1; digits <= 12; digits++){
            const factor = Math.pow(10, digits);
            const rounded = Math.round(value * factor) / factor;
            if(Math.abs(rounded - value) <= 1e-9) return Math.abs(rounded) < 1e15 && Number.isInteger(rounded) ? rounded : rounded;
        }
        return value;
    }
    const text = String(value).trim();
    if(/^-?\d+$/.test(text)) return value;          // 整数文本原样
    if(!/^-?\d*\.\d+$/.test(text)) return value;   // 非数字原样
    const num = Number(text);
    if(!Number.isFinite(num)) return value;
    const cleaned = rhCleanNumber(num);
    return cleaned === num ? value : String(cleaned);
}
function rhCleanNumberText(value){
    return String(rhCleanNumber(value));
}
function renderComfySettingField(field){
    const labelText = field.name || field.input || field.id;
    const label = `<div class="pfield-label">${deps.escapeHtml(labelText)}</div>`;
    const value = rhCleanNumber(deps.comfyParamValue(field));
    if(field.type === 'boolean'){
        const on = !!value;
        return `<div class="pfield pfield-inline"><div class="pfield-inline-label">${deps.escapeHtml(labelText)}</div><div class="pfield-bool"><div class="pfield-bool-track ${on ? 'on' : ''}" data-comfy-bool="${deps.escapeHtml(field.id)}"><div class="pfield-bool-thumb"></div></div></div></div>`;
    }
    if(field.type === 'dropdown'){
        const opts = field.options || [];
        const v = value ?? '';
        const optsHtml = opts.map(o => `<option value="${deps.escapeHtml(o)}" ${String(v)===String(o)?'selected':''}>${deps.escapeHtml(o)}</option>`).join('');
        return `<div class="pfield pfield-inline"><div class="pfield-inline-label">${deps.escapeHtml(labelText)}</div><select class="pfield-select pfield-inline-select" data-comfy-param="${deps.escapeHtml(field.id)}">${optsHtml || `<option value="">${deps.escapeHtml(tr('smart.noOption'))}</option>`}</select></div>`;
    }
    // 2026-10-24：本地工作流的「比例」字段（上游 ResolutionSelector.aspect_ratio）在暴露配置里
    // 只有 type:text、没有 options，之前渲染成自由文本框（要手打 "16:9 (Widescreen)"）。
    // 值命中官方 8 枚举时改用和 RH 侧完全同一个下拉（同 class、同取值域），两条路一致。
    if(!field.type || field.type === 'text'){
        const aspectList = comfyAspectOptionList(field);
        if(aspectList){
            const v = value ?? '';
            const aspectHtml = aspectList.map(o => `<option value="${deps.escapeHtml(o)}" ${String(v)===String(o)?'selected':''}>${deps.escapeHtml(o)}</option>`).join('');
            return `<div class="pfield pfield-inline"><div class="pfield-inline-label">${deps.escapeHtml(labelText)}</div><select class="pfield-select pfield-inline-select" data-comfy-param="${deps.escapeHtml(field.id)}">${aspectHtml}</select></div>`;
        }
    }
    if(field.type === 'textarea'){
        return `<div class="pfield">${label}<textarea class="pfield-textarea" data-comfy-param="${deps.escapeHtml(field.id)}" placeholder="${deps.escapeHtml(labelText)}">${deps.escapeHtml(value ?? '')}</textarea></div>`;
    }
    if(field.type === 'slider'){
        const min = field.min ?? 0, max = field.max ?? 10, step = field.step ?? 1;
        const displayValue = deps.formatComfySliderValue(value ?? 0, step);
        return `<div class="pfield pfield-inline pfield-inline-slider"><div class="pfield-inline-label">${deps.escapeHtml(labelText)}</div><div class="pfield-slider">
            <input type="range" data-comfy-param="${deps.escapeHtml(field.id)}" min="${min}" max="${max}" step="${step}" value="${deps.escapeHtml(value ?? 0)}">
            <span class="pfield-slider-val" data-slider-val="${deps.escapeHtml(field.id)}">${deps.escapeHtml(displayValue)}</span>
        </div></div>`;
    }
    if(field.type === 'number'){
        const min = field.min !== undefined ? ` min="${deps.escapeHtml(field.min)}"` : '';
        const max = field.max !== undefined ? ` max="${deps.escapeHtml(field.max)}"` : '';
        const step = field.step !== undefined ? ` step="${deps.escapeHtml(field.step)}"` : '';
        const dice = field.random_enabled === true
            ? `<button type="button" class="random-btn ${deps.smartComfyRandomActive(field.id) ? 'active' : ''}" data-comfy-random="${deps.escapeHtml(field.id)}" title="${deps.escapeHtml(deps.smartComfyRandomActive(field.id) ? tr('smart.diceOn') : tr('smart.diceOff'))}"><i data-lucide="dice-5"></i></button>`
            : '';
        const rowStyle = dice ? '' : 'grid-template-columns:1fr';
        return `<div class="pfield pfield-number-inline"><div class="pfield-inline-label">${deps.escapeHtml(labelText)}</div><div class="pfield-random-row" style="${rowStyle}"><input class="pfield-input" type="number" data-comfy-param="${deps.escapeHtml(field.id)}" value="${deps.escapeHtml(value ?? 0)}"${min}${max}${step}>${dice}</div></div>`;
    }
    // 文本字段：横向紧凑（标题左、输入右），与数值/下拉一致
    return `<div class="pfield pfield-inline"><div class="pfield-inline-label">${deps.escapeHtml(labelText)}</div><input class="pfield-input pfield-inline-input" type="text" data-comfy-param="${deps.escapeHtml(field.id)}" value="${deps.escapeHtml(value ?? '')}" placeholder="${deps.escapeHtml(labelText)}"></div>`;
}
const RH_KNOWN_FIELD_OPTIONS = {
    // 2026-10-20 老王：比例字段用 ComfyUI 内置 ResolutionSelector 的**真实枚举**（官方源码核对过），
    // 之前那串裸比例（16:9）根本不是工作流认的值（它要 "16:9 (Widescreen)"），选了也不生效。
    aspectRatio:['1:1 (Square)','2:3 (Portrait Photo)','3:2 (Photo)','3:4 (Portrait Standard)','4:3 (Standard)','9:16 (Portrait Widescreen)','16:9 (Widescreen)','21:9 (Ultrawide)'],
    aspect_ratio:['1:1 (Square)','2:3 (Portrait Photo)','3:2 (Photo)','3:4 (Portrait Standard)','4:3 (Standard)','9:16 (Portrait Widescreen)','16:9 (Widescreen)','21:9 (Ultrawide)'],
    ratio:['1:1','16:9','9:16','21:9','9:21','4:3','3:4','4:5','5:4','3:2','2:3'],
    resolution:['1k','2k','4k','8k'],
    size:['512','768','1024','1280','1536','2048'],
    quality:['low','medium','high','best'],
    scheduler:['normal','karras','exponential','sgm_uniform','simple','ddim_uniform'],
    sampler:['euler','euler_ancestral','heun','dpm_2','dpm_2_ancestral','lms','dpmpp_2m','dpmpp_sde','ddim','uni_pc']
};
// 本地工作流比例字段 → 官方 8 枚举下拉（只在值命中枚举时转，避免误伤自由文本字段）
function comfyAspectOptionList(field){
    const key = String(field?.input || '').trim();
    const name = String(field?.name || '').trim();
    const isAspect = key === 'aspect_ratio' || key === 'aspectRatio'
        || /^(视频?比例|比例|宽高比|画面比例)$/.test(name);
    if(!isAspect) return null;
    const list = RH_KNOWN_FIELD_OPTIONS.aspect_ratio;
    const current = String((typeof deps.comfyParamValue === 'function' ? deps.comfyParamValue(field) : '') ?? field?.default ?? '').trim();
    return list.includes(current) ? list : null;
}
function rhParamKey(nodeId, fieldName){
    return `${nodeId ?? ''}::${fieldName ?? ''}`;
}
function rhFieldKind(field){
    const type = String(field?.fieldType || '').trim().toUpperCase();
    if(type === 'IMAGE') return 'image';
    if(type === 'VIDEO') return 'video';
    if(type === 'AUDIO') return 'audio';
    if(type === 'SLIDER') return 'slider';
    if(['NUMBER','FLOAT','INTEGER','INT'].includes(type)) return 'number';
    if(['BOOLEAN','BOOL'].includes(type)) return 'boolean';
    const key = `${field?.fieldName || ''} ${field?.fieldValue || ''}`.toLowerCase();
    if(/\b(image|img|mask|photo|picture)\b/.test(key) || /\.(png|jpe?g|webp|gif|bmp)(\?|$)/i.test(key)) return 'image';
    if(/\b(video|movie|mp4)\b/.test(key) || /\.(mp4|webm|mov|m4v|mkv)(\?|$)/i.test(key)) return 'video';
    if(/\b(audio|sound|music|voice)\b/.test(key) || /\.(mp3|wav|ogg|m4a|flac|aac)(\?|$)/i.test(key)) return 'audio';
    return 'text';
}
function rhFieldRole(field){
    const kind = rhFieldKind(field);
    if(['image','video','audio','number','slider','boolean'].includes(kind)) return kind;
    const text = `${field?.fieldName || ''} ${field?.label || ''} ${field?.group || ''}`.toLowerCase();
    if(/prompt|positive|negative|text|caption|description|关键词|提示词|正向|负向/.test(text)) return 'prompt';
    return 'text';
}
function rhExtractFieldOptions(field){
    const candidates = [field?.fieldData, field?.options, field?.list, field?.values, field?.enum, field?.choices, field?.items, field?.selectOptions, field?.dropdown];
    for(const candidate of candidates){
        if(!Array.isArray(candidate) || !candidate.length) continue;
        if(candidate.every(x => ['string','number'].includes(typeof x))) return candidate.map(String);
        if(candidate.every(x => x && typeof x === 'object' && ('value' in x || 'label' in x || 'name' in x))){
            return candidate.map(x => x.value ?? x.label ?? x.name).filter(v => v !== undefined && v !== null).map(String);
        }
    }
    const name = String(field?.fieldName || '').trim();
    if(name){
        if(RH_KNOWN_FIELD_OPTIONS[name]) return RH_KNOWN_FIELD_OPTIONS[name].map(String);
        const hit = Object.keys(RH_KNOWN_FIELD_OPTIONS).find(k => k.toLowerCase() === name.toLowerCase());
        if(hit) return RH_KNOWN_FIELD_OPTIONS[hit].map(String);
    }
    return null;
}
function rhDefaultValue(field){
    let value = field?.fieldValue;
    if(Array.isArray(value)) value = value[0];
    if(value === undefined || value === null || typeof value === 'object') return '';
    return String(value);
}
function rhIsWorkflowLinkValue(value){
    return Array.isArray(value) && value.length === 2 && typeof value[0] === 'string' && Number.isInteger(value[1]);
}
function rhRandomEnabled(field){
    return rhFieldKind(field) === 'number' && field?.random_enabled === true;
}
function smartRhRandomActive(key){
    return smartRhRandomActiveFor(D("settings"), key);
}
function smartRhRandomActiveFor(sourceSettings=D("settings"), key){
    sourceSettings = sourceSettings || D("settings");
    sourceSettings.rhRandomActive = sourceSettings.rhRandomActive || {};
    return sourceSettings.rhRandomActive[key] !== false;
}
function toggleSmartRhRandom(key){
    const field = deps.rhActiveFields().find(f => rhParamKey(f.nodeId, f.fieldName) === key);
    if(!rhRandomEnabled(field)) return;
    D("settings").rhRandomActive = D("settings").rhRandomActive || {};
    D("settings").rhRandomActive[key] = !smartRhRandomActive(key);
    deps.persistActiveSmartSettings();
    deps.renderDynamicParams();
    deps.scheduleSave();
}
function smartRhRandomValue(field){
    return deps.smartComfyRandomValue({
        input:field.fieldName,
        name:field.label || field.fieldName,
        min:field.min,
        max:field.max,
        step:field.step,
        type:'number'
    });
}
function rhParamValue(field, media=null, sourceSettings=D("settings"), fields=null, randomValues=D("smartRhRandomValues")){
    sourceSettings = sourceSettings || D("settings");
    sourceSettings.rhParams = sourceSettings.rhParams || {};
    const key = rhParamKey(field.nodeId, field.fieldName);
    const param = sourceSettings.rhParams[key];
    const kind = rhFieldKind(field);
    if(['image','video','audio'].includes(kind)){
        const idx = rhFieldIndexes(fields || deps.rhActiveFields(sourceSettings), sourceSettings)[key] || 0;
        const up = media?.[kind]?.[idx]?.url || '';
        if(deps.rhCurrentKind(sourceSettings) === 'workflow' && kind === 'image' && field.required !== true && !up) return '';
        return up || param?.value || rhDefaultValue(field);
    }
    if(rhRandomEnabled(field) && smartRhRandomActiveFor(sourceSettings, key)){
        if(randomValues[key] === undefined) randomValues[key] = smartRhRandomValue(field);
        return randomValues[key];
    }
    if(rhFieldRole(field) === 'prompt') return param?.value ?? (media?.prompt || rhDefaultValue(field));
    return param?.value ?? rhDefaultValue(field);
}
function rhUserParamValue(field){
    D("settings").rhParams = D("settings").rhParams || {};
    const key = rhParamKey(field.nodeId, field.fieldName);
    return D("settings").rhParams[key]?.value ?? '';
}
function rhPromptPlaceholder(field){
    return rhDefaultValue(field) || field?.label || field?.fieldName || tr('smart.promptPlaceholder');
}
function rhDefaultPromptSuggestion(){
    if(D("settings").engine !== 'runninghub') return '';
    const fields = deps.rhActiveFields().filter(field => rhFieldRole(field) === 'prompt');
    for(const field of fields){
        const value = rhDefaultValue(field).trim();
        if(value) return value;
    }
    return '';
}
function promptInputHasContent(){
    if(!D("promptInput")) return false;
    if(D("promptInput").querySelector('.mention-image-token')) return true;
    return Boolean(String(D("promptInput").textContent || '').replace(/\u200b/g, '').trim());
}
function refreshPromptPlaceholderVisible(){
    if(!D("promptInput")) return;
    // 占位提示按「文本内容是否为空」显示：有字隐藏，删空(含删剩 <br>/零宽空格)重新显示。
    // 不能只靠 CSS :empty —— contenteditable 删空后浏览器常残留节点导致 :empty 失配。
    D("promptInput").classList.toggle('show-placeholder', !promptInputHasContent());
}
function updatePromptPlaceholder(){
    if(!D("promptInput")) return;
    const suggestion = rhDefaultPromptSuggestion();
    D("promptInput").dataset.placeholder = suggestion || tr('smart.promptPlaceholder');
    refreshPromptPlaceholderVisible();
}
function rhFieldIndexes(fields, sourceSettings=D("settings")){
    // 图片槽位序号优先用「工作流自动识别」的顺序（零配置）：MM-H3 的 6 个参考图槽位直接由
    // ref_images.ref_image_0..5 的连线顺序决定，与字段有没有暴露、imageOrder 填没填无关。
    const slotOrder = deps.rhImageSlotOrderMap(sourceSettings);
    // 不在槽位表里的图片字段从 slotOrder.size 往后编号，避免和槽位号撞号。
    const counters = {image:slotOrder.size, video:0, audio:0};
    const map = {};
    deps.sortRunningHubFields(fields).forEach(field => {
        const kind = rhFieldKind(field);
        if(!['image','video','audio'].includes(kind)) return;
        const key = rhParamKey(field.nodeId, field.fieldName);
        if(kind === 'image'){
            const slot = slotOrder.get(String(field.nodeId));
            if(slot !== undefined){ map[key] = slot; return; }
        }
        map[key] = counters[kind]++;
    });
    return map;
}
async function ensureRunningHubWorkflow(workflowId){
    workflowId = String(workflowId || '').trim();
    if(!workflowId) return null;
    if(D("runningHubWorkflowCache")[workflowId]) return D("runningHubWorkflowCache")[workflowId];
    const res = await fetch(`/api/runninghub/workflows/${encodeURIComponent(workflowId)}`);
    if(!res.ok){
        delete D("runningHubWorkflowCache")[workflowId];
        return null;
    }
    const data = await res.json();
    // 兼容后端两种响应形状：{"ok":true,"data":{...}} 与 {"workflow":{...}}。
    // 取错字段会拿到 undefined，缓存失效后画布只能退到 entry 里的旧快照。
    D("runningHubWorkflowCache")[workflowId] = data.workflow || data.data || null;
    return D("runningHubWorkflowCache")[workflowId];
}
async function currentRunningHubWorkflowConfig(sourceSettings=D("settings")){
    const ref = deps.selectedRunningHubRef(sourceSettings);
    if(ref?.kind !== 'workflow') return null;
    const cached = await ensureRunningHubWorkflow(ref.id).catch(() => null);
    return {
        ...(ref.entry || {}),
        ...(cached || {}),
        workflowId:ref.id,
        fields:Array.isArray(cached?.fields) && cached.fields.length ? cached.fields : deps.rhEntryFields(ref.entry),
        optionalImageMode:ref.entry?.optionalImageMode || cached?.optionalImageMode || 'prune-workflow',
        workflowJson:deps.rhWorkflowJsonFromSources(cached?.workflowJson, ref.entry?.workflowJson, ref.entry?.raw?.workflowJson, ref.entry?.raw?.prompt)
    };
}
function rhMediaForRun(prompt, refs){
    const cleanRefs = (refs || []).filter(ref => ref?.url);
    return {
        refs:cleanRefs,
        image:deps.imageRefsOnly(cleanRefs),
        video:deps.videoRefsOnly(cleanRefs),
        audio:deps.audioRefsOnly(cleanRefs),
        prompt:String(prompt || '').trim()
    };
}
function tempShUploadedUrlFor(url, sourceSettings=D("settings")){
    const source = String(url || '');
    const manualLinks = ((sourceSettings || D("settings")).videoTempShLinks || []).filter(item => item?.manual === true);
    const links = [...(D("transientSmartCloudLinks") || []), ...manualLinks];
    const match = links.find(item =>
        item?.url && (item?.source === source || item?.originalLocalUrl === source || item?.url === source)
    );
    return match?.url || url;
}
function mediaRefSourceUrl(ref){
    return deps.localDisplayUrlForMediaItem(ref) || ref?.sourceUrl || ref?.originalLocalUrl || ref?.url || '';
}
function applyUploadedUrlsToSmartRefs(refs, sourceSettings=D("settings")){
    return (refs || []).map(ref => {
        if(!ref?.url) return ref;
        const sourceUrl = mediaRefSourceUrl(ref);
        const url = tempShUploadedUrlFor(sourceUrl, sourceSettings);
        return url && url !== ref.url ? {...ref, url, originalLocalUrl:ref.originalLocalUrl || ref.url} : ref;
    });
}
function manualSmartVideoLink(sourceSettings=D("settings")){
    return ((sourceSettings || D("settings")).videoTempShLinks || []).find(item => item?.manual === true && item?.url) || null;
}
function manualSmartMediaLinks(sourceSettings=D("settings")){
    return ((sourceSettings || D("settings")).videoTempShLinks || []).filter(item => item?.manual === true && item?.url);
}
function renderedInputMediaRefs(){
    if(!D("inputThumbsRow")) return [];
    return [...inputThumbsRow.querySelectorAll('.input-thumb')].map((el, index) => ({
        url:el.dataset.url || '',
        sourceUrl:el.dataset.sourceUrl || el.dataset.url || '',
        nodeId:el.dataset.nodeId || '',
        imageIndex:Number.isFinite(Number(el.dataset.imageIndex)) ? Number(el.dataset.imageIndex) : index,
        kind:el.dataset.kind || 'image',
        name:el.dataset.name || tr('smart.inputNum').replace('{n}', String(index + 1)),
        role:`image_${index + 1}`
    })).filter(ref => ref.url);
}
function comfyWorkflowImageRefsForNode(node, refs=[]){
    const candidates = [...(refs || [])];
    if(node && deps.selectedNode()?.id === node.id){
        candidates.push(...renderedInputMediaRefs());
        candidates.push(...collectMentionedImagesFromPrompt());
    }
    return deps.imageRefsOnly(deps.uniqueReferenceImages(candidates));
}
function currentSmartMediaRefs(node){
    if(!node) return [];
    const request = deps.buildPromptRequest(node, null, true, D("smartLoopContext"));
    return (request.refs || []).filter(ref => ref?.url && ['image','video'].includes(deps.mediaKindForItem(ref)));
}
function currentUploadMediaRefs(node){
    const rendered = renderedInputMediaRefs();
    if(rendered.length) return rendered;
    return currentSmartMediaRefs(node);
}
function currentSmartMediaLinks(node=null){
    return currentUploadMediaRefs(node || deps.activeSettingsSubject()).map(ref => {
        const sourceUrl = mediaRefSourceUrl(ref);
        const uploaded = tempShUploadedUrlFor(sourceUrl);
        return uploaded && uploaded !== sourceUrl ? uploaded : '';
    }).filter(Boolean);
}
function clearManualSmartVideoUrl(){
    D("settings").videoTempShLinks = (D("settings").videoTempShLinks || []).filter(item => item?.manual !== true);
}
function splitManualMediaUrls(text){
    return String(text || '')
        .split(/[\s,，]+/)
        .map(url => url.trim())
        .filter(Boolean);
}
async function uploadMediaRefToCloud(ref, providerId=''){
    const kind = deps.mediaKindForItem(ref);
    const sourceUrl = mediaRefSourceUrl(ref);
    if(!sourceUrl) throw new Error('没有可上传的媒体');
    const existing = tempShUploadedUrlFor(sourceUrl);
    if(existing && existing !== sourceUrl && /^https?:\/\//i.test(existing)) return existing;
    if(/^https?:\/\//i.test(sourceUrl)) return sourceUrl;
    const platform = deps.videoProviderPlatform(providerId || D("settings").videoProvider || '');
    if(platform && platform !== 'volcengine' && platform !== 'runninghub'){
        throw new Error('当前平台暂不支持内置云端上传，请使用“输入网址”填写公网媒体链接');
    }
    const uploadEndpoint = platform === 'runninghub'
        ? '/api/runninghub/upload-asset'
        : '/api/cloud-video/upload';
    const response = await fetch(`${D("RH_OFFICIAL_PROXY_BASE")}${uploadEndpoint}`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({url:sourceUrl})
    });
    if(!response.ok) throw new Error(await deps.smartResponseErrorMessage(response, '云端上传失败'));
    const data = await response.json();
    const payload = data.data && typeof data.data === 'object' ? data.data : data;
    const uploadedUrl = payload.downloadUrl || payload.fileUrl || payload.url || '';
    if(!uploadedUrl) throw new Error('云端没有返回链接');
    deps.setTransientSmartCloudLinks([
        ...(D("transientSmartCloudLinks") || []).filter(item => item?.source !== sourceUrl),
        {source:sourceUrl, url:uploadedUrl, expires:data.expires || '3 days', kind}
    ]);
    return uploadedUrl;
}
function applyManualVideoUrlToSmartRef(ref, manualUrl){
    if(!manualUrl) return;
    const sourceUrl = mediaRefSourceUrl(ref) || manualUrl;
    D("settings").videoTempShLinks = [
        ...(D("settings").videoTempShLinks || []).filter(item => item?.source !== sourceUrl),
        {source:sourceUrl, url:manualUrl, manual:true}
    ];
}
async function setCurrentSmartManualVideoUrl(){
    const node = deps.activeSettingsSubject();
    if(!node) return '';
    deps.savePromptDraftForCurrent();
    const refs = currentUploadMediaRefs(node);
    const firstLocal = refs.find(ref => ref?.url && !deps.isRemoteVideoReferenceUrl(ref.url));
    const firstAny = firstLocal || refs[0] || null;
    const linkedUrls = currentSmartMediaLinks(node);
    const currentLinks = linkedUrls.length ? linkedUrls : (firstAny ? [tempShUploadedUrlFor(mediaRefSourceUrl(firstAny))] : []);
    const value = await deps.openAssetNameDialog({
        title:refs.length > 1 ? `输入 ${refs.length} 个媒体网址 / 火山素材 URI` : '输入媒体网址 / 火山素材 URI',
        value:currentLinks.filter(isRemoteVideoReferenceUrl).join('\n'),
        placeholder:refs.length > 1 ? '每行一个链接，按图1/图2顺序对应' : 'https://example.com/media 或 asset://asset-xxx',
        cancelValue:null,
        multiline:refs.length > 1
    });
    if(value === null) return '';
    const urls = splitManualMediaUrls(value);
    if(!urls.length){
        clearManualSmartVideoUrl();
        deps.persistActiveSmartSettings();
        deps.scheduleSave();
        deps.render();
        deps.toast('已清除手动网址');
        return '';
    }
    const invalid = urls.find(url => !deps.isRemoteVideoReferenceUrl(url));
    if(invalid){
        deps.toast('请输入 http/https 媒体网址或 asset:// 火山素材 URI');
        return '';
    }
    clearManualSmartVideoUrl();
    const targets = refs.length ? refs : [firstAny].filter(Boolean);
    urls.forEach((url, index) => {
        const target = targets[index] || targets[targets.length - 1] || {url};
        applyManualVideoUrlToSmartRef(target, url);
    });
    deps.persistActiveSmartSettings();
    deps.scheduleSave();
    deps.render();
    deps.toast(`已设置 ${urls.length} 个媒体网址`);
    return urls[0] || '';
}
async function uploadCurrentSmartVideosToCloud(){
    const node = deps.activeSettingsSubject();
    if(!node) return [];
    deps.savePromptDraftForCurrent();
    const refs = currentUploadMediaRefs(node);
    const localRefs = refs.filter(ref => {
        const sourceUrl = ref?.sourceUrl || ref?.originalLocalUrl || ref?.url || '';
        if(!sourceUrl) return false;
        const uploaded = tempShUploadedUrlFor(sourceUrl);
        return uploaded !== sourceUrl || !deps.isRemoteVideoReferenceUrl(sourceUrl);
    });
    if(!localRefs.length){
        deps.toast('当前输入图片或视频已是云端链接');
        return [];
    }
    const btn = D("dynamicParams")?.querySelector('[data-trusted-source="cloud"]') || D("inputThumbsRow")?.querySelector('[data-temp-sh-upload-video]');
    if(btn) btn.disabled = true;
    deps.toast(`正在上传 ${localRefs.length} 个媒体文件到云端...`);
    try {
        const urls = [];
    for(const ref of localRefs){
        urls.push(await uploadMediaRefToCloud(ref, D("settings").videoProvider || 'volcengine'));
        }
        deps.toast(`云端上传完成：${urls.length} 个媒体文件`);
        return urls;
    } finally {
        if(btn) btn.disabled = false;
    }
}

    global.CanvasDynamicParamEngine = {
        configure,
        renderComfySettingField,
        rhParamKey,
        rhFieldKind,
        rhCleanNumber,
        rhCleanNumberText,
        rhFieldRole,
        rhExtractFieldOptions,
        rhDefaultValue,
        rhIsWorkflowLinkValue,
        rhRandomEnabled,
        smartRhRandomActive,
        smartRhRandomActiveFor,
        toggleSmartRhRandom,
        smartRhRandomValue,
        rhParamValue,
        rhUserParamValue,
        rhPromptPlaceholder,
        rhDefaultPromptSuggestion,
        promptInputHasContent,
        refreshPromptPlaceholderVisible,
        updatePromptPlaceholder,
        rhFieldIndexes,
        ensureRunningHubWorkflow,
        currentRunningHubWorkflowConfig,
        rhMediaForRun,
        tempShUploadedUrlFor,
        mediaRefSourceUrl,
        applyUploadedUrlsToSmartRefs,
        manualSmartVideoLink,
        manualSmartMediaLinks,
        renderedInputMediaRefs,
        comfyWorkflowImageRefsForNode,
        currentSmartMediaRefs,
        currentUploadMediaRefs,
        currentSmartMediaLinks,
        clearManualSmartVideoUrl,
        splitManualMediaUrls,
        uploadMediaRefToCloud,
        applyManualVideoUrlToSmartRef,
        setCurrentSmartManualVideoUrl,
        uploadCurrentSmartVideosToCloud,
    };
})(typeof window !== 'undefined' ? window : this);
