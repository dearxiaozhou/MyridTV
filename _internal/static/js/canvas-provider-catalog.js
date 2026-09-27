//** Resolves RunningHub node-off state, chat/video providers, model lists and engine select options. */
(function(global){
    'use strict';

    const deps = {};
    function configure(options){Object.assign(deps, options || {});}

    function D(name){return typeof deps[name] === 'function' ? deps[name]() : deps[name];}

function rhToggleNodeOff(nodeId){
    const id = String(nodeId ?? '');
    if(!id) return;
    const ref = deps.selectedRunningHubRef(D("settings"));
    if(!ref) return;
    const key = deps.runningHubEntryKey(ref.kind, ref.id);
    D("settings").rhNodeOff = (D("settings").rhNodeOff && typeof D("settings").rhNodeOff === 'object') ? D("settings").rhNodeOff : {};
    const bucket = (D("settings").rhNodeOff[key] && typeof D("settings").rhNodeOff[key] === 'object') ? D("settings").rhNodeOff[key] : {};
    if(bucket[id] === true) delete bucket[id];
    else bucket[id] = true;
    D("settings").rhNodeOff[key] = bucket;
    deps.persistActiveSmartSettings();
    deps.renderDynamicParams();
    deps.scheduleSave();
}
function rhActiveFields(sourceSettings=D("settings")){
    const ref = deps.selectedRunningHubRef(sourceSettings);
    let fields = deps.rhEntryFields(ref?.entry);
    if(ref?.kind === 'workflow'){
        const cached = D("runningHubWorkflowCache")[ref.id];
        if(Array.isArray(cached?.fields) && cached.fields.length) fields = cached.fields;
    }
    fields = fields.filter(f => f.enabled === true);
    if(ref?.kind === 'workflow'){
        // 被关掉的节点：参数不再出现在节点上，也不参与提交（提交侧见 rhBuildWorkflowRequestExtras）
        fields = fields.filter(f => !deps.rhNodeIsOff(f.nodeId, sourceSettings));
    }
    return sortRunningHubFields(fields);
}
function sortRunningHubFields(fields){
    return [...(fields || [])].sort((a, b) => {
        const ak = deps.rhFieldKind(a), bk = deps.rhFieldKind(b);
        if(ak === 'image' && bk === 'image'){
            const ao = Number(a.imageOrder) || 9999;
            const bo = Number(b.imageOrder) || 9999;
            if(ao !== bo) return ao - bo;
        }
        if(ak === 'image' && bk !== 'image') return -1;
        if(ak !== 'image' && bk === 'image') return 1;
        return String(a.nodeId || '').localeCompare(String(b.nodeId || ''), undefined, {numeric:true}) || String(a.fieldName || '').localeCompare(String(b.fieldName || ''));
    });
}
function chatApiProviders(){
    return (D("apiProviders") || []).filter(p => p.enabled !== false && (p.has_key !== false) && (p.chat_models || []).length);
}
function resolveChatProviderId(providerId=''){
    const providers = chatApiProviders();
    if(providers.some(p => p.id === providerId)) return providerId;
    return providers[0]?.id || 'comfly';
}
function providerChatModels(providerId){
    const provider = chatApiProviders().find(p => p.id === providerId);
    return [...new Set(provider?.chat_models || [])];
}
function resolveChatModel(model='', providerId=''){
    const models = providerChatModels(resolveChatProviderId(providerId));
    return models.includes(model) ? model : (models[0] || model || 'gpt-4o-mini');
}
function chatProviderOptions(selectedId=''){
    const selected = resolveChatProviderId(selectedId);
    return chatApiProviders().map(provider => `<option value="${deps.escapeHtml(provider.id)}" ${provider.id === selected ? 'selected' : ''}>${deps.escapeHtml(provider.name || provider.id)}</option>`).join('');
}
function chatModelOptions(selectedModel='', providerId=''){
    const selectedProvider = resolveChatProviderId(providerId);
    const models = providerChatModels(selectedProvider);
    const selected = resolveChatModel(selectedModel, selectedProvider);
    return [...new Set([selected, ...models].filter(Boolean))].map(model => `<option value="${deps.escapeHtml(model)}" ${model === selected ? 'selected' : ''}>${deps.escapeHtml(model)}</option>`).join('');
}
function apiProviderById(providerId){
    if(providerId === 'volcengine') return deps.volcengineProvider();
    return (D("apiProviders") || []).find(p => p.id === providerId) || deps.imageProviders()[0] || null;
}
// 认证素材 asset:// 是平台绑定的：返回某 provider 所属的认证平台键（与后端一致）
function videoProviderPlatform(providerId){
    const p = (D("apiProviders") || []).find(x => x.id === providerId);
    const proto = String(p?.protocol || '').toLowerCase();
    const base = String(p?.base_url || '').toLowerCase();
    if(proto === 'apimart' || base.includes('apimart.ai')) return 'apimart';
    if(proto === 'volcengine' || providerId === 'volcengine') return 'volcengine';
    return '';
}
function providerImageModels(providerId){
  if(providerId === 'volcengine') return deps.volcengineProvider().image_models || [];
  return (D("apiProviders") || []).find(p => p.id === providerId)?.image_models || [];
}
function providerModelDisplayName(providerId, model){
  const resolved = D("PROVIDER_MODEL_DISPLAY")?.resolveProviderModelDisplayName?.(D("apiProviders"), providerId, model);
  if(resolved) return resolved;
  const provider = providerId === 'volcengine'
    ? deps.volcengineProvider()
    : (D("apiProviders") || []).find(p => p.id === providerId);
  const map = (provider?.model_display_names && typeof provider.model_display_names === 'object') ? provider.model_display_names : {};
  const modelKey = String(model || '').trim();
  return String(map[modelKey] || modelKey).trim();
}
// 即梦图生图（挂了参考图）不支持 3.0/3.1，此时从模型下拉里隐藏它们。
const JIMENG_IMAGE2IMAGE_UNSUPPORTED = ['3.0', '3.1'];
function jimengImageEditMode(){
    if(D("settings").provider_id !== 'jimeng') return false;
    const node = deps.activeComposerNode() || deps.selectedNode();
    const refs = node ? deps.visibleReferenceImagesFor(node) : [];
    return refs.length > 0;
}
function filterJimengImageModels(models){
    if(D("settings").provider_id !== 'jimeng' || !jimengImageEditMode()) return models;
    return (models || []).filter(m => !JIMENG_IMAGE2IMAGE_UNSUPPORTED.includes(String(m)));
}
let _jimengLastEditMode = null;
let _jimengModelRefreshing = false;
// 参考图增删导致即梦文生图/图生图切换时，重新渲染参数面板以更新模型下拉。
function syncJimengModelPillForRefs(){
    if(_jimengModelRefreshing) return;
    if(D("settings").provider_id !== 'jimeng' || D("settings").engine !== 'api' || D("settings").apiKind === 'video'){
        _jimengLastEditMode = null;
        return;
    }
    const mode = jimengImageEditMode();
    if(mode === _jimengLastEditMode) return;
    _jimengLastEditMode = mode;
    _jimengModelRefreshing = true;
    try { deps.renderDynamicParams(); } finally { _jimengModelRefreshing = false; }
}
// 即梦各视频指令支持的模型集合不同，按当前参考素材推断指令并过滤模型下拉。
const JIMENG_SEEDANCE_VIDEO_MODELS = ['seedance2.0_vip', 'seedance2.0fast_vip', 'seedance2.0', 'seedance2.0fast'];
const JIMENG_VIDEO_MODELS_BY_COMMAND = {
    text2video: JIMENG_SEEDANCE_VIDEO_MODELS,
    multimodal2video: JIMENG_SEEDANCE_VIDEO_MODELS,
    image2video: ['3.0', '3.0fast', '3.0pro', '3.5pro', ...JIMENG_SEEDANCE_VIDEO_MODELS],
    frames2video: ['3.0', '3.5pro', ...JIMENG_SEEDANCE_VIDEO_MODELS],
};
function jimengVideoCommand(){
    const node = deps.activeComposerNode() || deps.selectedNode();
    const refs = node ? deps.visibleReferenceImagesFor(node) : [];
    const imageRefs = deps.imageRefsOnly(refs);
    const hasVideoRef = deps.videoRefsOnly(refs).length > 0 || Boolean(deps.manualSmartVideoLink(D("settings")));
    if(D("settings").videoMultimodal || hasVideoRef) return 'multimodal2video';
    if(imageRefs.length >= 2) return D("settings").videoUseFrameRoles ? 'frames2video' : 'multiframe2video';
    if(imageRefs.length >= 1) return 'image2video';
    return 'text2video';
}
function filterJimengVideoModels(models){
    if(D("settings").videoProvider !== 'jimeng') return models;
    const allowed = JIMENG_VIDEO_MODELS_BY_COMMAND[jimengVideoCommand()];
    if(!allowed) return models; // multiframe2video 等：官方规格未知，不过滤
    return (models || []).filter(m => allowed.includes(String(m)));
}
let _jimengLastVideoCommand = null;
function syncJimengVideoModelPillForRefs(){
    if(_jimengModelRefreshing) return;
    if(D("settings").videoProvider !== 'jimeng' || D("settings").engine !== 'api' || D("settings").apiKind !== 'video'){
        _jimengLastVideoCommand = null;
        return;
    }
    const command = jimengVideoCommand();
    if(command === _jimengLastVideoCommand) return;
    _jimengLastVideoCommand = command;
    _jimengModelRefreshing = true;
    try { deps.renderDynamicParams(); } finally { _jimengModelRefreshing = false; }
}
function sanitizeSmartApiSelection(target=D("settings")){
    if(!target || typeof target !== 'object') return target;
    const availableEngines = smartAvailableEngines();
    if(!availableEngines.includes(target.engine)) target.engine = availableEngines[0] || 'api';
 if(target.engine === 'volcengine'){
 if(target.apiKind === 'video'){
 target.videoProvider = 'volcengine';
 const models = volcengineVideoModels();
            if(!models.includes(target.videoModel)) target.videoModel = models[0] || '';
        } else {
            target.provider_id = 'volcengine';
            const models = providerImageModels('volcengine');
            if(!models.includes(target.model)) target.model = models[0] || '';
 }
 return target;
 }
 if(target.engine === 'comfy') return deps.normalizeComfyWorkflowSelection(target);
 deps.clearVolcengineSelectionOutsideVolcengine(target);
    if(target.provider_id){
        const validProvider = deps.imageProviders().some(p => p.id === target.provider_id);
        const models = providerImageModels(target.provider_id);
        if(!validProvider){
            target.provider_id = '';
            target.model = '';
        } else if(!models.includes(target.model)) {
            target.model = models[0] || '';
        }
    }
    if(target.videoProvider){
        const validVideoProvider = videoApiProviders().some(p => p.id === target.videoProvider);
        const models = providerVideoModels(target.videoProvider);
        if(!validVideoProvider){
            target.videoProvider = '';
            target.videoModel = '';
        } else if(!models.includes(target.videoModel)) {
            target.videoModel = models[0] || '';
        }
    }
    return target;
}
function videoApiProviders(){
    const fromConfig = (D("apiProviders") || []).filter(p => p.enabled !== false && p.id !== 'runninghub' && p.id !== 'volcengine' && (p.video_models || []).length);
    return fromConfig;
}
function videoProviderById(providerId){
    if(providerId === 'volcengine') return deps.volcengineProvider();
    return videoApiProviders().find(p => p.id === providerId) || videoApiProviders()[0] || null;
}
function providerVideoModels(providerId){
    if(providerId === 'volcengine') return volcengineVideoModels();
    const provider = videoApiProviders().find(p => p.id === providerId);
    const models = provider?.video_models || [];
    return [...new Set(models)];
}
function volcengineVideoModels(){
    const provider = (D("apiProviders") || []).find(p => p.id === 'volcengine');
    return [...new Set(provider?.video_models || [])];
}
function smartAvailableEngines(){
    const engines = [];
    if(deps.imageProviders().length || videoApiProviders().length) engines.push('api');
    const volc = deps.volcengineProvider();
    if(volc){
        const hasImg = (volc.image_models || []).length;
        const hasVid = (volc.video_models || []).length;
        // 生图模式只认 image_models：纯视频平台（如豆包-SD-2.0）不得出现在生图引擎里
        const show = (typeof D("settings") !== 'undefined' && D("settings") && D("settings").apiKind === 'video') ? (hasVid || hasImg) : hasImg;
        if(show) engines.push('volcengine');
    }
    if((D("comfyWorkflows") || []).length || D("comfyInstanceCount") > 0) engines.push('comfy');
    if(deps.runningHubProvider() && (deps.runningHubEntries('app').length || deps.runningHubEntries('workflow').length)) engines.push('runninghub');
    // 3D预演 引擎（用于节点引擎判断，下拉中会被过滤不显示）
    engines.push('blender');
    if(!engines.length) engines.push('api');
    return engines;
}
function smartEngineLabel(engine){
    const labels = {
        api:tr('smart.engineApi'),
        volcengine:tr('smart.engineVolcengine'),
        comfy:tr('smart.engineComfy'),
        runninghub:tr('smart.engineRh'),
        blender:'3D预演'
    };
    // “API 生成”是泛称，实际落到某个图像平台；直接显示该平台名称，与火山引擎/ComfyUI 保持一致。
    if(engine === 'api'){
        const providers = (typeof deps.imageProviders === 'function') ? deps.imageProviders() : [];
        const currentId = String(D("settings")?.apiProvider || '').trim();
        const picked = providers.find(p => String(p.id) === currentId) || providers[0];
        if(picked?.name) return picked.name;
    }
    if(engine === 'volcengine'){
        const volc = (typeof deps.volcengineProvider === 'function') ? deps.volcengineProvider() : null;
        if(volc?.id === 'volcengine' && volc?.name) return volc.name;
    }
    if(engine === 'runninghub'){
        const rhp = (typeof deps.runningHubProvider === 'function') ? deps.runningHubProvider() : null;
        if(rhp?.name) return rhp.name + ' · 工作流';
    }
    return labels[engine] || engine;
}
function syncEngineSelectOptions(){
    if(!D("engineSelect")) return;
    // 3D预演 节点：引擎固定"3D预演"，隐藏下拉框（纯文本标签由 renderDynamicParams 插入）
    if(D("settings").engine === 'blender'){
        D("engineSelect").style.display = 'none';
        D("engineSelect").disabled = true;
        D("engineSelect").value = 'blender';
        if(typeof deps.enhanceAgentSelects === 'function') deps.enhanceAgentSelects();
        return;
    }
    D("engineSelect").style.display = '';
    D("engineSelect").disabled = false;
    const engines = smartAvailableEngines().filter(e => e !== 'blender');
    const current = D("settings").engine || D("engineSelect").value || '';
    D("engineSelect").innerHTML = engines.map(engine => `<option value="${deps.escapeHtml(engine)}">${deps.escapeHtml(smartEngineLabel(engine))}</option>`).join('');
    if(!engines.includes(current)){
        D("settings").engine = engines[0] || 'api';
    }
    D("engineSelect").value = D("settings").engine;
    if(typeof deps.enhanceAgentSelects === 'function') deps.enhanceAgentSelects();
}

    global.CanvasProviderCatalog = {
        configure,
        rhToggleNodeOff,
        rhActiveFields,
        sortRunningHubFields,
        chatApiProviders,
        resolveChatProviderId,
        providerChatModels,
        resolveChatModel,
        chatProviderOptions,
        chatModelOptions,
        apiProviderById,
        videoProviderPlatform,
        providerImageModels,
        providerModelDisplayName,
        jimengImageEditMode,
        filterJimengImageModels,
        syncJimengModelPillForRefs,
        jimengVideoCommand,
        filterJimengVideoModels,
        syncJimengVideoModelPillForRefs,
        sanitizeSmartApiSelection,
        videoApiProviders,
        videoProviderById,
        providerVideoModels,
        volcengineVideoModels,
        smartAvailableEngines,
        smartEngineLabel,
        syncEngineSelectOptions,
    };
})(typeof window !== 'undefined' ? window : this);
